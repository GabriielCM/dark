"""Fila de producoes: listar, criar, acompanhar, refazer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from ...artifacts import ArtifactStore
from ...db.models import StepState, Video, VideoState
from ...pipeline import StepName, video_progress
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
        VideoState.ASSETS: "gerando cenarios",
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


@router.get("/videos/{video_id}", response_class=HTMLResponse)
async def detail(request: Request, video_id: str) -> HTMLResponse:
    app = request.app
    progress = video_progress(app.state.sessions, video_id)
    if not progress:
        return app.state.templates.TemplateResponse(
            request,
            "erro.html",
            {"codigo": 404, "mensagem": f"Producao {video_id} nao existe"},
            status_code=404,
        )

    store = ArtifactStore(video_id)
    fact_report = None
    report_path = store.path("roteiro", "relatorio_fatos.final.json")
    if report_path.exists():
        fact_report = store.read_json("roteiro", "relatorio_fatos.final.json")

    return app.state.templates.TemplateResponse(
        request,
        "producao.html",
        {
            "p": progress,
            "custo": app.state.costs.spent_on_video(video_id),
            "relatorio": fact_report,
            "etapas_nomes": [s.value for s in StepName],
            "artefatos": _artifact_tree(store),
        },
    )


@router.get("/videos/{video_id}/etapas", response_class=HTMLResponse)
async def steps_fragment(request: Request, video_id: str) -> HTMLResponse:
    """Fragmento HTMX: a tabela de etapas, recarregada sozinha."""
    app = request.app
    progress = video_progress(app.state.sessions, video_id)
    return app.state.templates.TemplateResponse(
        request, "_etapas.html", {"p": progress, "custo": app.state.costs.spent_on_video(video_id)}
    )


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
    step = StepName(etapa)
    if apagar:
        app.state.runner.redo(video_id, [step])
    else:
        app.state.runner.queue.reset_step(video_id, step)
    return RedirectResponse(f"/videos/{video_id}", status_code=303)


@router.post("/videos/{video_id}/destravar")
async def unblock(request: Request, video_id: str) -> RedirectResponse:
    request.app.state.runner.queue.unblock(video_id)
    return RedirectResponse(f"/videos/{video_id}", status_code=303)


def _artifact_tree(store: ArtifactStore) -> list[dict[str, Any]]:
    """Arquivos gerados, por etapa, sem os sidecars."""
    if not store.root.exists():
        return []
    tree: list[dict[str, Any]] = []
    for stage_dir in sorted(p for p in store.root.iterdir() if p.is_dir()):
        files = [
            {
                "nome": f.name,
                "tamanho": f.stat().st_size,
                "url": f"/artefatos/{store.video_id}/{stage_dir.name}/{f.name}",
            }
            for f in sorted(stage_dir.iterdir())
            if f.is_file() and not f.name.endswith(".meta.json")
        ]
        if files:
            tree.append({"etapa": stage_dir.name, "arquivos": files})
    return tree
