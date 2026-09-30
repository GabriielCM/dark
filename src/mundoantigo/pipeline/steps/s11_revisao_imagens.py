"""Etapa 11: revisao das imagens (primeira revisao humana).

O painel mostra todas as imagens do video numa grade. O revisor aprova todas,
ou pede para refazer uma imagem colando uma foto de referencia ou escrevendo
o que esperava. A etapa so termina com a aprovacao gravada.

A grade chega na fase C2 da reconstrucao. Com `revisao_imagens.ativo: false`
no app.yaml, a etapa aprova sozinha e registra que foi automatica.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class RevisaoImagensStep(Step):
    name = StepName.REVISAO_IMAGENS

    def outputs(self, ctx: StepContext) -> list[Path]:
        #  Como no corte final, a aprovacao e o artefato.
        return [ctx.store.path("revisao_imagens", "aprovacao.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        config = ctx.settings.app.get("revisao_imagens", {})
        if config.get("ativo", True):
            return StepResult.blocked("aguardando revisao das imagens no painel")
        ctx.store.write_json(
            "revisao_imagens",
            "aprovacao.json",
            {"aprovado": True, "automatica": True, "em": datetime.now(UTC).isoformat()},
            step="revisao_imagens",
        )
        return StepResult.done(summary="imagens aprovadas automaticamente (revisao desligada)")
