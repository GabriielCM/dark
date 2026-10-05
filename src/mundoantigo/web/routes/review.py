"""As duas revisoes humanas: a grade de imagens e o corte final.

A grade (primeira revisao) aparece dentro da pagina da producao, na etapa
revisao_imagens: o revisor marca imagens para refazer, com link ou motivo, e
aprova. O corte final (segunda revisao) e o video de um lado e o relatorio
de fatos do outro: aprovar, ou rejeitar informando o motivo.

As rotas `/api/...` respondem JSON e so aceitam JSON: o painel e local, e
exigir `application/json` ja barra um formulario de outro site.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from ...artifacts import ArtifactStore
from ...db.models import StepState, Video
from ...pipeline import StepName
from ...review import final_cut
from ...review import images as review
from .. import views

router = APIRouter()


class DraftBody(BaseModel):
    refazer: bool
    link: str | None = None
    motivo: str | None = None


class NewCommentBody(BaseModel):
    idioma: str
    tempo_s: float


class CommentBody(BaseModel):
    texto: str | None = None
    link: str | None = None


def _require_json(request: Request) -> None:
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(status_code=415, detail="envie application/json")


def _store(request: Request, video_id: str) -> ArtifactStore:
    with request.app.state.sessions() as s:
        if s.get(Video, video_id) is None:
            raise HTTPException(status_code=404, detail="producao nao existe")
    return ArtifactStore(video_id)


def _step_state(request: Request, video_id: str, step: StepName) -> StepState | None:
    with request.app.state.sessions() as s:
        video = s.get(Video, video_id)
        if video is None:
            return None
        return next((st.state for st in video.steps if st.name == step.value), None)


def _card(item: dict[str, Any]) -> dict[str, Any]:
    """O que o JavaScript precisa para atualizar um cartao sem redesenhar a grade."""
    request = item.get("pedido") or {}
    return {
        "chave": item["chave"],
        "estado": item["estado"],
        "existe": item["existe"],
        "versao": item["versao"],
        "imagem": item["imagem"],
        "anterior": item.get("anterior"),
        "refacoes": item["refacoes"],
        "referencia": (item.get("referencia") or {}).get("fonte"),
        "pedido": {
            "id": request.get("id"),
            "estado": request.get("estado"),
            "link": request.get("link"),
            "motivo": request.get("motivo"),
            "resposta": request.get("resposta"),
            "detalhe": request.get("detalhe"),
            "visto_pelo_claude_em": request.get("visto_pelo_claude_em"),
        }
        if request
        else None,
    }


# -- grade de imagens ----------------------------------------------------------


@router.get("/api/videos/{video_id}/imagens", response_class=JSONResponse)
async def grid_state(request: Request, video_id: str) -> dict[str, Any]:
    store = _store(request, video_id)
    items = review.grid(store)
    ok, why = review.can_approve(store)
    blocked = _step_state(request, video_id, StepName.REVISAO_IMAGENS) is StepState.BLOCKED
    return {
        "cartoes": [_card(item) for item in items],
        "pode_aprovar": ok and blocked,
        "motivo_nao_aprova": why
        if not ok
        else ("" if blocked else "a grade ainda nao esta pronta"),
    }


@router.put("/api/videos/{video_id}/imagens/{chave}/rascunho", response_class=JSONResponse)
async def save_draft(request: Request, video_id: str, chave: str, body: DraftBody) -> Any:
    _require_json(request)
    store = _store(request, video_id)
    try:
        draft = review.save_draft(
            store, chave, redo=body.refazer, link=body.link, reason=body.motivo
        )
    except review.ReviewError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=409)
    return {"ok": True, "rascunho": draft}


@router.post("/api/videos/{video_id}/imagens/enviar", response_class=JSONResponse)
async def submit(request: Request, video_id: str) -> Any:
    _require_json(request)
    store = _store(request, video_id)
    try:
        counts = review.submit(store)
    except review.SubmitError as exc:
        return JSONResponse({"erro": str(exc), "erros": exc.errors}, status_code=422)
    return {"ok": True, **counts}


@router.post(
    "/api/videos/{video_id}/imagens/pedidos/{pedido}/cancelar", response_class=JSONResponse
)
async def cancel(request: Request, video_id: str, pedido: int) -> Any:
    _require_json(request)
    store = _store(request, video_id)
    try:
        entry = review.cancel(store, pedido)
    except review.ReviewError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=409)
    return {"ok": True, "pedido": entry}


@router.post("/api/videos/{video_id}/imagens/aprovar", response_class=JSONResponse)
async def approve_grid(request: Request, video_id: str) -> Any:
    _require_json(request)
    store = _store(request, video_id)
    if _step_state(request, video_id, StepName.REVISAO_IMAGENS) is not StepState.BLOCKED:
        return JSONResponse({"erro": "a grade ainda nao esta esperando aprovacao"}, status_code=409)
    ok, why = review.can_approve(store)
    if not ok:
        return JSONResponse({"erro": why}, status_code=409)
    request.app.state.runner.approve(video_id, gate=StepName.REVISAO_IMAGENS, reviewer="painel")
    return {"ok": True}


# -- corte final ---------------------------------------------------------------


@router.get("/videos/{video_id}/revisao")
async def review_page(request: Request, video_id: str) -> RedirectResponse:
    """O corte final mora na pagina da producao, na etapa revisao."""
    query = request.url.query
    suffix = f"&{query}" if query else ""
    return RedirectResponse(
        f"/videos/{video_id}?abrir=revisao{suffix}#etapa-revisao", status_code=303
    )


@router.get("/videos/{video_id}/corte/comentarios", response_class=HTMLResponse)
async def comments_fragment(request: Request, video_id: str) -> HTMLResponse:
    store = _store(request, video_id)
    response: HTMLResponse = request.app.state.templates.TemplateResponse(
        request,
        "_comentarios.html",
        {"video_id": video_id, "comentarios": views.comments_view(store)},
    )
    return response


@router.post("/api/videos/{video_id}/corte/comentarios", response_class=JSONResponse)
async def new_comment(request: Request, video_id: str, body: NewCommentBody) -> Any:
    _require_json(request)
    try:
        entry = final_cut.add(_store(request, video_id), body.idioma, body.tempo_s)
    except final_cut.CommentError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=422)
    return {"ok": True, "comentario": entry}


@router.put("/api/videos/{video_id}/corte/comentarios/{comentario}", response_class=JSONResponse)
async def edit_comment(request: Request, video_id: str, comentario: int, body: CommentBody) -> Any:
    _require_json(request)
    try:
        final_cut.update(_store(request, video_id), comentario, text=body.texto, link=body.link)
    except final_cut.CommentError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=409)
    return {"ok": True}


@router.delete("/api/videos/{video_id}/corte/comentarios/{comentario}", response_class=JSONResponse)
async def delete_comment(request: Request, video_id: str, comentario: int) -> Any:
    try:
        final_cut.delete(_store(request, video_id), comentario)
    except final_cut.CommentError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=409)
    return {"ok": True}


@router.post("/api/videos/{video_id}/corte/enviar", response_class=JSONResponse)
async def submit_comments(request: Request, video_id: str) -> Any:
    _require_json(request)
    try:
        sent = final_cut.submit(_store(request, video_id))
    except final_cut.CommentError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=422)
    return {"ok": True, "enviados": sent}


@router.post("/api/videos/{video_id}/corte/aprovar", response_class=JSONResponse)
async def approve_cut(request: Request, video_id: str) -> Any:
    _require_json(request)
    store = _store(request, video_id)
    if _step_state(request, video_id, StepName.REVISAO) is not StepState.BLOCKED:
        return JSONResponse(
            {"erro": "o corte final ainda nao esta esperando aprovacao"}, status_code=409
        )
    ok, why = final_cut.can_approve(store)
    if not ok:
        return JSONResponse({"erro": why}, status_code=409)
    request.app.state.runner.approve(video_id, reviewer="painel")
    return {"ok": True}


@router.post("/videos/{video_id}/aprovar")
async def approve(request: Request, video_id: str) -> RedirectResponse:
    ok, _ = final_cut.can_approve(ArtifactStore(video_id))
    if not ok:
        return RedirectResponse(
            f"/videos/{video_id}?abrir=revisao&erro=comentarios-abertos", status_code=303
        )
    request.app.state.runner.approve(video_id)
    return RedirectResponse(f"/videos/{video_id}?abrir=revisao", status_code=303)


@router.post("/videos/{video_id}/rejeitar")
async def reject(
    request: Request,
    video_id: str,
    motivo: str = Form(...),
    refazer_de: str = Form(StepName.ROTEIRO.value),
) -> RedirectResponse:
    motivo = motivo.strip()
    if not motivo:
        #  Rejeitar sem motivo nao ensina nada ao pipeline nem ao proximo video.
        return RedirectResponse(f"/videos/{video_id}/revisao?erro=motivo-vazio", status_code=303)
    allowed = views.final_cut(ArtifactStore(video_id))["etapas_refazer"]
    if refazer_de not in allowed:
        raise HTTPException(status_code=400, detail="etapa de refacao nao permitida")
    request.app.state.runner.reject(video_id, motivo, redo_from=StepName(refazer_de))
    return RedirectResponse(f"/videos/{video_id}", status_code=303)
