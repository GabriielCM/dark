"""Pagina da producao: a lista das etapas que expande ao clicar.

O revisor acompanha por aqui em que etapa estamos. Quando uma etapa precisa
dele, o aviso do Windows abre a pagina direto nela (`?abrir=<etapa>`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image

from ...artifacts import ArtifactStore
from ...paths import get_paths
from ...pipeline import StepName, video_progress
from .. import views

router = APIRouter()

#  Etapas que fazem sentido no link direto, alem das 16: as perguntas do Claude.
EXTRA_TARGETS = ("perguntas",)
THUMB_WIDTHS = (240, 480, 960)


def _open_step(progress: dict[str, Any], requested: str | None) -> str | None:
    """Etapa aberta ao carregar: a pedida, senao a que precisa do revisor, senao a que roda."""
    names = {st["nome"] for st in progress["etapas"]}
    if requested and (requested in names or requested in EXTRA_TARGETS):
        return requested
    return progress.get("precisa_de_voce") or progress.get("rodando")


def _step(progress: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((st for st in progress["etapas"] if st["nome"] == name), None)


def _not_found(request: Request, video_id: str) -> HTMLResponse:
    response: HTMLResponse = request.app.state.templates.TemplateResponse(
        request,
        "erro.html",
        {"codigo": 404, "mensagem": f"Producao {video_id} nao existe"},
        status_code=404,
    )
    return response


@router.get("/videos/{video_id}", response_class=HTMLResponse)
async def page(request: Request, video_id: str, abrir: str | None = None) -> HTMLResponse:
    app = request.app
    progress = video_progress(app.state.sessions, video_id)
    if not progress:
        return _not_found(request, video_id)
    store = ArtifactStore(video_id)
    opened = _open_step(progress, abrir)
    bodies = {
        name: views.step_details(store, name, _step(progress, name))
        for name in [opened]
        if name and name not in EXTRA_TARGETS
    }
    response: HTMLResponse = app.state.templates.TemplateResponse(
        request,
        "producao.html",
        {
            "p": progress,
            "custo": app.state.costs.spent_on_video(video_id),
            "aberta": opened,
            "corpos": bodies,
            "video_id": video_id,
            "etapas_nomes": [s.value for s in StepName],
        },
    )
    return response


@router.get("/videos/{video_id}/etapas", response_class=HTMLResponse)
async def steps_fragment(request: Request, video_id: str) -> HTMLResponse:
    """A lista das etapas sem a pagina em volta (para quem so quer o resumo)."""
    app = request.app
    progress = video_progress(app.state.sessions, video_id)
    if not progress:
        return _not_found(request, video_id)
    response: HTMLResponse = app.state.templates.TemplateResponse(
        request, "_lista_etapas.html", {"p": progress, "video_id": video_id, "aberta": None}
    )
    return response


@router.get("/videos/{video_id}/etapas/{nome}", response_class=HTMLResponse)
async def step_body(request: Request, video_id: str, nome: str) -> HTMLResponse:
    """O corpo de uma etapa, carregado quando o revisor a abre."""
    app = request.app
    progress = video_progress(app.state.sessions, video_id)
    if not progress:
        return _not_found(request, video_id)
    step = _step(progress, nome)
    if step is None:
        raise HTTPException(status_code=404, detail="etapa desconhecida")
    store = ArtifactStore(video_id)
    response: HTMLResponse = app.state.templates.TemplateResponse(
        request,
        "etapas/_corpo.html",
        {
            "e": step,
            "d": views.step_details(store, nome, step),
            "video_id": video_id,
            "etapas_nomes": [s.value for s in StepName],
        },
    )
    return response


@router.get("/api/videos/{video_id}/estado", response_class=JSONResponse)
async def state(request: Request, video_id: str) -> dict[str, Any]:
    """O que a pagina atualiza sozinha a cada poucos segundos."""
    app = request.app
    progress = video_progress(app.state.sessions, video_id)
    if not progress:
        raise HTTPException(status_code=404, detail="producao nao existe")
    store = ArtifactStore(video_id)
    from ...review import images as review

    requests_file = review.requests_file(store)
    return {
        **progress,
        "custo": round(app.state.costs.spent_on_video(video_id), 4),
        #  Mudou algo na grade (pedido aplicado, imagem refeita): a pagina recarrega os cartoes.
        "pedidos_versao": int(requests_file.stat().st_mtime_ns) if requests_file.exists() else 0,
    }


@router.get("/miniaturas/{video_id}/{caminho:path}")
async def thumbnail(video_id: str, caminho: str, w: int = Query(480)) -> FileResponse:
    """Miniatura JPEG de uma imagem do video, com cache no disco.

    A grade tem mais de 200 imagens de 1920x1088: servir os PNG inteiros
    passaria de meio gigabyte.
    """
    width = min(THUMB_WIDTHS, key=lambda candidate: abs(candidate - w))
    root = ArtifactStore(video_id).root.resolve()
    source = (root / caminho).resolve()
    if root not in source.parents or source.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise HTTPException(status_code=404, detail="imagem nao encontrada")
    if not source.is_file():
        raise HTTPException(status_code=404, detail="imagem nao encontrada")
    stamp = source.stat().st_mtime_ns
    safe = caminho.replace("/", "__").replace("\\", "__")
    cached = get_paths().data / "cache" / "miniaturas" / video_id / f"{safe}.{stamp}.w{width}.jpg"
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        _make_thumbnail(source, cached, width)
    return FileResponse(cached, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


def _make_thumbnail(source: Path, target: Path, width: int) -> None:
    with Image.open(source) as opened:
        if opened.mode in ("RGBA", "LA", "P"):
            #  Pecas de cartao e poses do MC sao recortadas: fundo de papel.
            rgba = opened.convert("RGBA")
            picture = Image.new("RGB", rgba.size, (245, 239, 226))
            picture.paste(rgba, mask=rgba.split()[-1])
        else:
            picture = opened.convert("RGB")
    picture.thumbnail((width, width * 2), Image.Resampling.LANCZOS)
    temporary = target.with_suffix(".tmp")
    picture.save(temporary, "JPEG", quality=82)
    temporary.replace(target)
