"""Fila de producoes: listar, criar, acompanhar, refazer."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from ...db.models import StepState, Video, VideoState
from ...pipeline import StepName
from ...pipeline.state import waits_for_session
from ...pipeline.steps.s01_pauta import PILLARS

router = APIRouter()


def _state_label(state: VideoState) -> str:
    return {
        VideoState.PAUTA: "pauta",
        VideoState.PESQUISA: "pesquisando",
        VideoState.ROTEIRO: "escrevendo",
        VideoState.GATE_FATOS: "checando fatos",
        VideoState.ADAPTACAO_EN: "adaptando EN",
        VideoState.CENAS: "storyboard",
        VideoState.REFERENCIAS: "buscando referencias",
        VideoState.ASSETS: "gerando cenarios",
        VideoState.PRE_CHECAGEM: "pre-checando imagens",
        VideoState.REVISAO_IMAGENS: "aguardando revisao das imagens",
        VideoState.TRILHA: "trilha",
        VideoState.NARRACAO: "narrando",
        VideoState.MONTAGEM: "montando",
        VideoState.METADADOS: "metadados",
        VideoState.REVISAO: "aguardando revisao",
        VideoState.EMPACOTANDO: "montando o pacote",
        VideoState.ENTREGUE: "entregue",
        VideoState.REJEITADO: "rejeitado",
        VideoState.ARQUIVADO: "arquivado",
    }.get(state, state.value)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    app = request.app
    sessions = app.state.sessions

    with sessions() as s:
        videos = list(s.execute(select(Video).order_by(Video.created_at.desc())).scalars().all())
        rows = []
        for video in videos:
            steps = {st.name: st for st in video.steps}
            done = sum(1 for st in video.steps if st.state in (StepState.DONE, StepState.SKIPPED))
            failed = [st.name for st in video.steps if st.state is StepState.FAILED]
            blocked = [st.name for st in video.steps if st.state is StepState.BLOCKED]
            rows.append(
                {
                    "id": video.id,
                    "tema": video.topic,
                    "pilar": video.pillar,
                    "estado": video.state.value,
                    "rotulo": _state_label(video.state),
                    "progresso": round(done / max(len(steps), 1) * 100),
                    "bloqueio": video.blocked_reason,
                    "falhou": failed,
                    "bloqueadas": blocked,
                    "aguarda_revisao": video.state is VideoState.REVISAO,
                    "precisa_de_voce": next(
                        (
                            st.name
                            for st in sorted(video.steps, key=lambda st: st.ordinal)
                            if (
                                st.state is StepState.BLOCKED
                                and not waits_for_session((st.result or {}).get("resumo"))
                            )
                            or st.state is StepState.FAILED
                        ),
                        None,
                    ),
                    "custo": app.state.costs.spent_on_video(video.id),
                    "criado": video.created_at,
                    "titulo": video.title_pt,
                }
            )

    status = app.state.costs.status()
    return app.state.templates.TemplateResponse(
        request,
        "fila.html",
        {
            "videos": rows,
            "orcamento": status,
            "pilares": PILLARS,
            "provedores": app.state.providers.describe(),
        },
    )


@router.post("/videos")
async def create_video(
    request: Request,
    tema: str = Form(...),
    pilar: str = Form("engenharia"),
    prioridade: int = Form(0),
) -> RedirectResponse:
    tema = tema.strip()
    if not tema:
        return RedirectResponse("/?erro=tema-vazio", status_code=303)
    video_id = request.app.state.runner.queue.enqueue_video(tema, pillar=pilar, priority=prioridade)
    return RedirectResponse(f"/videos/{video_id}", status_code=303)


@router.post("/videos/{video_id}/refazer")
async def redo(
    request: Request, video_id: str, etapa: str = Form(...), apagar: str = Form("")
) -> RedirectResponse:
    """Reenfileira uma etapa e tudo que depende dela.

    Com `apagar`, apaga tambem as saidas dessas etapas — e assim que se forca
    refazer trabalho ja pago (ADR 0002). Sem ele, as etapas voltam para a fila
    mas os artefatos existentes fazem o runner pular sem gastar.
    """
    app = request.app
    try:
        step = StepName(etapa)
    except ValueError:
        return RedirectResponse(f"/videos/{video_id}?erro=etapa-invalida", status_code=303)
    if apagar:
        app.state.runner.redo(video_id, [step])
    else:
        app.state.runner.queue.reset_step(video_id, step)
    return RedirectResponse(f"/videos/{video_id}?abrir={step.value}", status_code=303)


@router.post("/videos/{video_id}/destravar")
async def unblock(request: Request, video_id: str, etapa: str = Form("")) -> RedirectResponse:
    """Devolve para a fila as etapas bloqueadas ou que falharam (ou so a escolhida)."""
    request.app.state.runner.queue.unblock(video_id, etapa or None)
    suffix = f"?abrir={etapa}" if etapa else ""
    return RedirectResponse(f"/videos/{video_id}{suffix}", status_code=303)
