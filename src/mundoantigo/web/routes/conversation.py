"""Perguntas do Claude na pagina da producao: o revisor responde por aqui."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ...artifacts import ArtifactStore
from ...conversation import inbox, questions
from ...db.models import Video

router = APIRouter()


class AnswerBody(BaseModel):
    opcao: str | None = None
    texto: str | None = None


def _require_json(request: Request) -> None:
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(status_code=415, detail="envie application/json")


def _store(request: Request, video_id: str) -> ArtifactStore:
    with request.app.state.sessions() as s:
        if s.get(Video, video_id) is None:
            raise HTTPException(status_code=404, detail="producao nao existe")
    return ArtifactStore(video_id)


def questions_context(store: ArtifactStore) -> dict[str, Any]:
    items = questions.load(store)
    return {
        "abertas": [q for q in items if q.get("estado") == "aberta"],
        #  As ultimas respondidas, para o revisor lembrar o que ja disse.
        "respondidas": [q for q in items if q.get("estado") == "respondida"][-5:],
        "claude": inbox.presence(store.video_id),
    }


@router.get("/videos/{video_id}/perguntas", response_class=HTMLResponse)
async def fragment(request: Request, video_id: str) -> HTMLResponse:
    store = _store(request, video_id)
    response: HTMLResponse = request.app.state.templates.TemplateResponse(
        request,
        "_perguntas.html",
        {"video_id": video_id, "perguntas": questions_context(store)},
    )
    return response


@router.get("/api/videos/{video_id}/perguntas", response_class=JSONResponse)
async def list_questions(request: Request, video_id: str) -> dict[str, Any]:
    return {"perguntas": questions.load(_store(request, video_id))}


@router.put("/api/videos/{video_id}/perguntas/{pergunta}/rascunho", response_class=JSONResponse)
async def draft(request: Request, video_id: str, pergunta: int, body: AnswerBody) -> Any:
    _require_json(request)
    try:
        questions.save_draft(
            _store(request, video_id), pergunta, option=body.opcao, text=body.texto
        )
    except questions.QuestionError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=409)
    return {"ok": True}


@router.post("/api/videos/{video_id}/perguntas/{pergunta}/responder", response_class=JSONResponse)
async def answer(request: Request, video_id: str, pergunta: int, body: AnswerBody) -> Any:
    _require_json(request)
    try:
        entry = questions.answer(
            _store(request, video_id), pergunta, option=body.opcao, text=body.texto
        )
    except questions.QuestionError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=422)
    return {"ok": True, "pergunta": entry}
