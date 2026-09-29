"""Etapa 7: fotos de referencia (Wikimedia Commons).

Para cenas de lugar, peca e plano detalhe com um alvo real, a etapa busca no
Commons uma foto com licenca aceita (CC0, dominio publico, CC BY) para servir
de base ao img2img, e guarda autor e licenca para os creditos da descricao.

A busca chega na fase B4 da reconstrucao. Ate la a etapa registra que nenhuma
cena tem referencia, e os cenarios saem so do texto.
"""

from __future__ import annotations

from pathlib import Path

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class ReferenciasStep(Step):
    name = StepName.REFERENCIAS

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("referencias", "indice.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        ctx.store.write_json(
            "referencias",
            "indice.json",
            {"cenas": {}, "pendente": "busca no Commons ainda nao implementada"},
            step="referencias",
        )
        return StepResult.done(summary="nenhuma referencia buscada (busca no Commons pendente)")
