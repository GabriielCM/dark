"""Ingestao de livros: PDF e ePub, com OCR quando necessario (brief 4.1).

O fluxo: extrair texto -> identificar metadados -> classificar direitos ->
indexar na base vetorial. A classificacao acontece antes da indexacao para que
nenhum trecho chegue a um prompt sem o aviso de direitos junto.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Book, RightsStatus
from ..db.session import get_sessionmaker
from ..errors import PermanentError
from ..paths import get_paths
from .kb import KnowledgeBase
from .rights import WorkFacts, classify

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".epub"}
#  Paginas com quase nenhum texto extraivel indicam PDF escaneado.
OCR_TEXT_THRESHOLD = 100


@dataclass(slots=True)
class ExtractedBook:
    text: str
    chapters: list[tuple[int | None, str]]
    toc: list[dict[str, Any]]
    ocr_used: bool
    page_count: int


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Extracao
# --------------------------------------------------------------------------


def extract_pdf(path: Path, *, ocr: bool = True) -> ExtractedBook:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PermanentError("pypdf nao instalado: `uv sync --extra books`") from exc

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    total_chars = sum(len(p.strip()) for p in pages)
    ocr_used = False

    if ocr and total_chars < OCR_TEXT_THRESHOLD * max(len(pages), 1):
        log.info("PDF com pouco texto extraivel; tentando OCR em %s", path.name)
        ocr_pages = _ocr_pdf(path)
        if ocr_pages:
            pages = ocr_pages
            ocr_used = True

    text = "\n\n".join(pages)
    toc = _pdf_outline(reader)
    return ExtractedBook(
        text=text,
        chapters=_split_chapters(text, toc),
        toc=toc,
        ocr_used=ocr_used,
        page_count=len(pages),
    )


def _ocr_pdf(path: Path) -> list[str]:
    """OCR pagina a pagina. Sem as dependencias instaladas, devolve vazio."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        log.warning(
            "OCR indisponivel (pdf2image/pytesseract nao instalados). "
            "O livro sera ingerido com o texto que houver."
        )
        return []
    try:
        images = convert_from_path(str(path), dpi=200)
    except Exception as exc:
        log.warning("OCR falhou ao converter %s: %s", path.name, exc)
        return []
    return [pytesseract.image_to_string(image) for image in images]


def _pdf_outline(reader: object) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def walk(items: object, depth: int = 0) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            title = getattr(item, "title", None)
            if title:
                entries.append({"titulo": str(title), "nivel": depth})

    try:
        walk(getattr(reader, "outline", []))
    except Exception:
        return []
    return entries


def extract_epub(path: Path) -> ExtractedBook:
    try:
        import ebooklib
        from bs4 import BeautifulSoup
        from ebooklib import epub
    except ImportError as exc:
        raise PermanentError(
            "ebooklib/beautifulsoup4 nao instalados: `uv sync --extra books`"
        ) from exc

    book = epub.read_epub(str(path))
    chapters: list[tuple[int | None, str]] = []
    toc: list[dict[str, Any]] = []

    for number, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT), start=1):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text("\n").strip()
        if len(text) < 200:
            continue  # capa, colofao, pagina de creditos
        heading = soup.find(["h1", "h2"])
        title = heading.get_text().strip() if heading else f"Secao {number}"
        chapters.append((number, text))
        toc.append({"numero": number, "titulo": title})

    return ExtractedBook(
        text="\n\n".join(t for _, t in chapters),
        chapters=chapters,
        toc=toc,
        ocr_used=False,
        page_count=len(chapters),
    )


_CHAPTER_PATTERN = re.compile(
    r"^\s*(?:cap[ií]tulo|chapter|parte|part|livro|book)\s+([0-9IVXLCDM]+)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


def _split_chapters(text: str, toc: list[dict[str, Any]]) -> list[tuple[int | None, str]]:
    """Divide o texto em capitulos por cabecalhos reconheciveis."""
    matches = list(_CHAPTER_PATTERN.finditer(text))
    if len(matches) < 2:
        return [(None, text)]

    chapters: list[tuple[int | None, str]] = []
    if matches[0].start() > 500:
        chapters.append((0, text[: matches[0].start()]))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chapters.append((index + 1, text[match.start() : end]))
    return chapters


# --------------------------------------------------------------------------
# Ingestao
# --------------------------------------------------------------------------


class BookIngestor:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        kb: KnowledgeBase | None = None,
    ) -> None:
        self._sessions = session_factory or get_sessionmaker()
        self.kb = kb or KnowledgeBase(self._sessions)

    def extract(self, path: Path) -> ExtractedBook:
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED:
            raise PermanentError(
                f"formato nao suportado: {suffix} (aceitos: {', '.join(sorted(SUPPORTED))})"
            )
        return extract_pdf(path) if suffix == ".pdf" else extract_epub(path)

    async def identify(
        self, extracted: ExtractedBook, filename: str, providers: object
    ) -> dict[str, Any]:
        """Identifica titulo, autor, tradutor e capitulos com o LLM (brief 4.1)."""
        from ..prompts import get_prompts

        prompt_obj = get_prompts().get("livros/identificacao")
        rendered = prompt_obj.render(
            texto_inicial=extracted.text[:6000],
            sumario_detectado=json.dumps(extracted.toc[:60], ensure_ascii=False),
            nome_arquivo=filename,
        )
        llm = providers.llm(fast=prompt_obj.prefers_fast_model)  # type: ignore[attr-defined]
        response = await llm.complete(rendered, step="livros", temperature=0.1)
        identified = response.json()
        return identified if isinstance(identified, dict) else {}

    def register(
        self,
        path: Path,
        extracted: ExtractedBook,
        metadata: dict[str, Any],
        *,
        book_id: str | None = None,
    ) -> Book:
        """Grava o livro, classifica os direitos e indexa os trechos."""
        digest = sha256_of(path)
        bid = book_id or f"{digest[:12]}"

        facts = WorkFacts(
            title=metadata.get("titulo"),
            author=metadata.get("autor"),
            author_death_year=_as_year(metadata.get("autor_ano_morte")),
            translator=metadata.get("tradutor") or None,
            translator_death_year=_as_year(metadata.get("tradutor_ano_morte")),
            original_year=_as_year(metadata.get("ano_publicacao_original")),
            edition_year=_as_year(metadata.get("ano_desta_edicao")),
        )
        verdict = classify(facts)

        with self._sessions() as s:
            book = s.get(Book, bid)
            if book is None:
                book = Book(
                    id=bid, filename=path.name, format=path.suffix.lstrip("."), sha256=digest
                )
                s.add(book)

            book.title = facts.title
            book.subtitle = metadata.get("subtitulo")
            book.author = facts.author
            book.author_death_year = facts.author_death_year
            book.translator = facts.translator
            book.translator_death_year = facts.translator_death_year
            book.language = metadata.get("idioma")
            book.original_year = facts.original_year
            book.edition_year = facts.edition_year
            book.publisher = metadata.get("editora")
            book.chapters = metadata.get("capitulos") or extracted.toc
            book.ocr_used = extracted.ocr_used
            book.rights_status = verdict.status
            book.rights_reason = verdict.reason
            book.rights_detail = verdict.as_dict()
            book.rights_checked_at = datetime.now(UTC)
            s.commit()
            s.refresh(book)

        self.kb.index_book(bid, extracted.chapters)
        log.info(
            "livro %s ingerido: %s — direitos: %s",
            bid,
            book.title or path.name,
            verdict.status.value,
        )
        return book

    def store_file(self, source: Path, book_id: str) -> Path:
        """Copia o arquivo para `livros/<book_id>/`."""
        destination_dir = get_paths().book_dir(book_id)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / source.name
        if source.resolve() != destination.resolve():
            destination.write_bytes(source.read_bytes())
        return destination


def _as_year(value: object) -> int | None:
    """Converte para ano, recusando o que nao for plausivel.

    Um ano chutado corrompe a classificacao de direitos, que e a decisao mais
    cara do sistema — melhor `None` e classificar como incerto.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        year = int(str(value).strip()[:4])
    except (TypeError, ValueError):
        return None
    current = datetime.now(UTC).year
    return year if -800 <= year <= current else None


def summarize_rights(book: Book) -> dict[str, Any]:
    """Resumo dos direitos para o painel."""
    from .rights import usage_policy

    policy = usage_policy(book.rights_status)
    return {
        "status": book.rights_status.value,
        "motivo": book.rights_reason,
        "pode_adaptar": policy["adaptar"],
        "pode_narrar": policy["narrar"],
        "observacao": policy["observacao"],
        "detalhe": book.rights_detail,
        "livre": book.rights_status is RightsStatus.LIVRE,
    }
