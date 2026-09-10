"""Revisao do corte final.

Unico ponto de revisao humana (brief 3.5): o video de um lado, o relatorio de
fatos do outro. Duas acoes — aprovar, ou rejeitar informando o motivo.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ...artifacts import ArtifactStore
from ...db.models import Video
from ...pipeline import StepName

router = APIRouter()


@router.get("/videos/{video_id}/revisao", response_class=HTMLResponse)
async def review(request: Request, video_id: str) -> HTMLResponse:
    app = request.app
    store = ArtifactStore(video_id)

    with app.state.sessions() as s:
        video = s.get(Video, video_id)
        if video is None:
            return app.state.templates.TemplateResponse(
                request,
                "erro.html",
                {"codigo": 404, "mensagem": f"Producao {video_id} nao existe"},
                status_code=404,
            )
        topic, title_pt, title_en = video.topic, video.title_pt, video.title_en

    dossier = {}
    if store.path("entrega", "revisao.json").exists():
        dossier = store.read_json("entrega", "revisao.json")

    report = {}
    if store.path("roteiro", "relatorio_fatos.final.json").exists():
        report = store.read_json("roteiro", "relatorio_fatos.final.json")

    videos = {
        lang: f"/artefatos/{video_id}/entrega/video.{lang}.mp4"
        for lang in ("pt-br", "en")
        if store.path("entrega", f"video.{lang}.mp4").exists()
    }
    metadata = {
        lang: store.read_json("metadados", f"metadados.{lang}.json")
        for lang in ("pt-br", "en")
        if store.path("metadados", f"metadados.{lang}.json").exists()
    }

    items = report.get("itens", [])
    #  Baixa primeiro, depois media: o revisor le o que importa antes de cansar.
    order = {"baixa": 0, "media": 1, "alta": 2}
    items = sorted(items, key=lambda i: order.get(str(i.get("confianca")), 3))

    return app.state.templates.TemplateResponse(
        request,
        "revisao.html",
        {
            "video_id": video_id,
            "tema": topic,
            "titulo_pt": title_pt,
            "titulo_en": title_en,
            "videos": videos,
            "itens": items,
            "resumo": report.get("resumo", {}),
            "reescritas": report.get("reescritas", 0),
            "avisos": dossier.get("avisos", []),
            "metadados": metadata,
            "thumbnail": (
                f"/artefatos/{video_id}/metadados/thumbnail.png"
                if store.path("metadados", "thumbnail.png").exists()
                else None
            ),
            "etapas_refazer": [
                StepName.ROTEIRO.value,
                StepName.CENAS.value,
                StepName.ASSETS.value,
                StepName.NARRACAO.value,
                StepName.METADADOS.value,
            ],
        },
    )


@router.post("/videos/{video_id}/aprovar")
async def approve(request: Request, video_id: str) -> RedirectResponse:
    request.app.state.runner.approve(video_id)
    return RedirectResponse(f"/videos/{video_id}", status_code=303)


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
    request.app.state.runner.reject(video_id, motivo, redo_from=StepName(refazer_de))
    return RedirectResponse(f"/videos/{video_id}", status_code=303)
