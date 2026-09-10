"""Livros: upload, classificacao de direitos e pautas por capitulo."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from ...books import BookIngestor, KnowledgeBase, summarize_rights
from ...books.ingest import SUPPORTED
from ...db.models import Book, RightsStatus, TopicSource

log = logging.getLogger(__name__)
router = APIRouter()

#  Livro grande e normal; 200 MB cobre PDF escaneado com folga.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@router.get("/livros", response_class=HTMLResponse)
async def books_page(request: Request) -> HTMLResponse:
    app = request.app
    with app.state.sessions() as s:
        books = list(s.execute(select(Book).order_by(Book.ingested_at.desc())).scalars().all())
        rows = [
            {
                "id": b.id,
                "titulo": b.title or b.filename,
                "autor": b.author,
                "tradutor": b.translator,
                "ano": b.original_year,
                "idioma": b.language,
                "ocr": b.ocr_used,
                "capitulos": len(b.chapters or []),
                "direitos": summarize_rights(b),
            }
            for b in books
        ]
    return app.state.templates.TemplateResponse(
        request, "livros.html", {"livros": rows, "formatos": sorted(SUPPORTED)}
    )


@router.post("/livros")
async def upload_book(request: Request, arquivo: UploadFile = File(...)) -> RedirectResponse:
    app = request.app
    name = arquivo.filename or "livro"
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED:
        return RedirectResponse(f"/livros?erro=formato-{suffix}", status_code=303)

    payload = await arquivo.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        return RedirectResponse("/livros?erro=arquivo-grande", status_code=303)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(payload)
        temp_path = Path(tmp.name)

    ingestor = BookIngestor(app.state.sessions)
    try:
        extracted = ingestor.extract(temp_path)
        metadata = await ingestor.identify(extracted, name, app.state.providers)
        digest_path = ingestor.store_file(temp_path, _preview_id(temp_path))
        book = ingestor.register(digest_path, extracted, metadata)
    except Exception as exc:
        log.exception("falha ao ingerir %s", name)
        return RedirectResponse(f"/livros?erro={type(exc).__name__}", status_code=303)
    finally:
        temp_path.unlink(missing_ok=True)

    return RedirectResponse(f"/livros/{book.id}", status_code=303)


@router.get("/livros/{book_id}", response_class=HTMLResponse)
async def book_detail(request: Request, book_id: str) -> HTMLResponse:
    app = request.app
    with app.state.sessions() as s:
        book = s.get(Book, book_id)
        if book is None:
            return app.state.templates.TemplateResponse(
                request,
                "erro.html",
                {"codigo": 404, "mensagem": "Livro nao encontrado"},
                status_code=404,
            )
        data = {
            "id": book.id,
            "titulo": book.title or book.filename,
            "subtitulo": book.subtitle,
            "autor": book.author,
            "autor_morte": book.author_death_year,
            "tradutor": book.translator,
            "tradutor_morte": book.translator_death_year,
            "ano_original": book.original_year,
            "ano_edicao": book.edition_year,
            "editora": book.publisher,
            "idioma": book.language,
            "ocr": book.ocr_used,
            "arquivo": book.filename,
            "direitos": summarize_rights(book),
            "capitulos": book.chapters or [],
        }

    topics = KnowledgeBase(app.state.sessions).chapter_topics(book_id)
    return app.state.templates.TemplateResponse(
        request, "livro.html", {"livro": data, "pautas": topics}
    )


@router.post("/livros/{book_id}/pauta")
async def topic_from_chapter(
    request: Request,
    book_id: str,
    capitulo: int = Form(...),
    tema: str = Form(...),
    pilar: str = Form("imperios"),
) -> RedirectResponse:
    """Enfileira uma pauta a partir de um capitulo (brief 4.1).

    Vale para obra protegida tambem: os capitulos servem como guia de pauta e o
    roteiro sai original (brief 4.2). Quem decide o que pode virar narracao e a
    etapa de pesquisa, que recebe o aviso de direitos junto com o trecho.
    """
    app = request.app
    with app.state.sessions() as s:
        book = s.get(Book, book_id)
        if book is None:
            return RedirectResponse("/livros?erro=livro-inexistente", status_code=303)
        status = book.rights_status

    video_id = app.state.runner.queue.enqueue_video(
        tema.strip(),
        pillar=pilar,
        source=TopicSource.LIVRO,
        book_id=book_id,
        book_chapter=capitulo,
    )
    if status is not RightsStatus.LIVRE:
        log.info(
            "pauta %s vem de obra nao livre (%s): o roteiro sera original e o livro "
            "entra apenas como fonte",
            video_id,
            book_id,
        )
    return RedirectResponse(f"/videos/{video_id}", status_code=303)


def _preview_id(path: Path) -> str:
    from ...books.ingest import sha256_of

    return sha256_of(path)[:12]
