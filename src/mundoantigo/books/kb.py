"""Base de conhecimento dos livros: trechos e busca vetorial.

ADR 0001: embeddings em SQLite, cosseno com NumPy. Ate ~100 mil trechos isso
responde em milissegundos e nao adiciona infraestrutura. A interface esconde a
implementacao para que trocar por sqlite-vec ou Qdrant seja mudar uma classe.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Book, BookChunk, RightsStatus
from ..db.session import get_sessionmaker
from .rights import usage_policy

log = logging.getLogger(__name__)

#  Trechos de ~1200 caracteres com sobreposicao: grande o bastante para conter
#  um argumento completo, pequeno o bastante para caber varios num prompt.
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150


@dataclass(frozen=True, slots=True)
class SearchResult:
    book_id: str
    book_title: str | None
    chapter: int | None
    text: str
    score: float
    rights_status: RightsStatus

    @property
    def rights_note(self) -> str:
        """Aviso que acompanha o trecho no prompt.

        Vai junto para que o modelo nunca receba um trecho de obra protegida
        sem saber que ele so pode virar fato, nunca narracao.
        """
        if self.rights_status is RightsStatus.LIVRE:
            return "dominio publico: pode ser adaptado com contexto"
        return "obra protegida ou incerta: use apenas como fonte de fato, nao reproduza"


def chunk_text(text: str, *, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Quebra o texto em trechos, preferindo fronteiras de paragrafo e frase."""
    clean = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(clean) <= size:
        return [clean] if clean else []

    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        if end < len(clean):
            #  Recua ate a ultima fronteira boa dentro da janela.
            window = clean[start:end]
            for boundary in ("\n\n", ". ", "; ", "\n"):
                index = window.rfind(boundary)
                if index > size // 2:
                    end = start + index + len(boundary)
                    break
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        start = max(end - overlap, end) if end <= start else end - overlap
        if start >= len(clean) - overlap:
            remainder = clean[start:].strip()
            if remainder and remainder not in chunks:
                chunks.append(remainder)
            break
    return chunks


def hash_embedding(text: str, dims: int = 384) -> np.ndarray:
    """Embedding leve por hashing de trigramas.

    Nao substitui um modelo de embeddings de verdade — captura sobreposicao
    lexical, nao semantica. E o padrao para que a base funcione sem baixar
    modelo nenhum; a maquina com GPU troca por sentence-transformers ligando
    `embedding_model` na configuracao.
    """
    vector = np.zeros(dims, dtype=np.float32)
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = normalized.split()
    for token in tokens:
        padded = f"  {token} "
        for i in range(len(padded) - 2):
            trigram = padded[i : i + 3]
            vector[_stable_hash(trigram) % dims] += 1.0
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else vector


def _stable_hash(text: str) -> int:
    import hashlib

    return int.from_bytes(hashlib.md5(text.encode(), usedforsecurity=False).digest()[:4], "big")


class KnowledgeBase:
    """Busca sobre os trechos dos livros ingeridos."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._sessions = session_factory or get_sessionmaker()

    def index_book(self, book_id: str, chapters: list[tuple[int | None, str]]) -> int:
        """Indexa os capitulos de um livro. Substitui o indice anterior."""
        written = 0
        with self._sessions() as s:
            s.query(BookChunk).filter(BookChunk.book_id == book_id).delete()
            ordinal = 0
            for chapter_number, text in chapters:
                for piece in chunk_text(text):
                    embedding = hash_embedding(piece)
                    s.add(
                        BookChunk(
                            book_id=book_id,
                            chapter=chapter_number,
                            ordinal=ordinal,
                            text=piece,
                            embedding=embedding.tobytes(),
                            embedding_model="hash-trigram-384",
                        )
                    )
                    ordinal += 1
                    written += 1
            s.commit()
        log.info("livro %s indexado em %d trechos", book_id, written)
        return written

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        book_id: str | None = None,
        min_score: float = 0.05,
    ) -> list[SearchResult]:
        """Trechos mais proximos da consulta, com o aviso de direitos junto."""
        query_vector = hash_embedding(query)

        with self._sessions() as s:
            statement = select(BookChunk, Book).join(Book, Book.id == BookChunk.book_id)
            if book_id:
                statement = statement.where(BookChunk.book_id == book_id)
            rows = s.execute(statement).all()

            scored: list[tuple[float, BookChunk, Book]] = []
            for chunk, book in rows:
                if not chunk.embedding:
                    continue
                vector = np.frombuffer(chunk.embedding, dtype=np.float32)
                if vector.shape != query_vector.shape:
                    continue
                score = float(np.dot(vector, query_vector))
                if score >= min_score:
                    scored.append((score, chunk, book))

            scored.sort(key=lambda item: item[0], reverse=True)
            return [
                SearchResult(
                    book_id=chunk.book_id,
                    book_title=book.title,
                    chapter=chunk.chapter,
                    text=chunk.text,
                    score=round(score, 4),
                    rights_status=book.rights_status,
                )
                for score, chunk, book in scored[:limit]
            ]

    def chapter_topics(self, book_id: str) -> list[dict[str, Any]]:
        """Capitulos de um livro como pautas candidatas (brief 4.1).

        Obra protegida vira guia de pauta, nunca roteiro: o aviso vai junto
        para o painel mostrar antes de enfileirar.
        """
        with self._sessions() as s:
            book = s.get(Book, book_id)
            if book is None:
                return []
            policy = usage_policy(book.rights_status)
            return [
                {
                    "livro_id": book.id,
                    "livro": book.title,
                    "capitulo": chapter.get("numero"),
                    "titulo": chapter.get("titulo"),
                    "pode_adaptar": policy["adaptar"],
                    "observacao": policy["observacao"],
                }
                for chapter in (book.chapters or [])
            ]
