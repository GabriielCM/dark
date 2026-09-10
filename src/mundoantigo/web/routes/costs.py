"""Custos do mes: total, por etapa e por producao (ADR 0003)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from ...costs import month_key
from ...db.models import CostEntry

router = APIRouter()


@router.get("/custos", response_class=HTMLResponse)
async def costs_page(request: Request, mes: str | None = None) -> HTMLResponse:
    app = request.app
    recorder = app.state.costs
    target = mes or month_key()

    with app.state.sessions() as s:
        months = list(
            s.execute(select(CostEntry.month_key).distinct().order_by(CostEntry.month_key.desc()))
            .scalars()
            .all()
        )
        recent = list(
            s.execute(
                select(CostEntry)
                .where(CostEntry.month_key == target)
                .order_by(CostEntry.created_at.desc())
                .limit(60)
            )
            .scalars()
            .all()
        )

    by_step = recorder.breakdown_by_step(month=target)
    by_video = recorder.breakdown_by_video(month=target)
    status = recorder.status()

    #  Comparacao com a estimativa do brief (secao 9), configuracao economica.
    per_video = [v for _, v in by_video]
    average = sum(per_video) / len(per_video) if per_video else 0.0

    return app.state.templates.TemplateResponse(
        request,
        "custos.html",
        {
            "mes": target,
            "meses": months or [target],
            "orcamento": status,
            "por_etapa": by_step,
            "por_video": by_video,
            "media_por_video": average,
            "entradas": recent,
            "estimativa_brief": {"economica_min": 0.5, "economica_max": 1.0},
        },
    )
