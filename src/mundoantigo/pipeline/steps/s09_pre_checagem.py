"""Etapa 9: pre-checagem das imagens.

Antes de a grade chegar ao revisor, um modelo local (CLIP) mede se cada
imagem bate com a cena e procura texto, rosto em objeto e anacronismo. As
suspeitas sao refeitas uma vez; o que continuar suspeito espera o Claude.

A checagem chega na fase C1 da reconstrucao. Ate la o relatorio sai vazio.
"""

from __future__ import annotations

from pathlib import Path

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class PreChecagemStep(Step):
    name = StepName.PRE_CHECAGEM

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("pre_checagem", "relatorio.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        ctx.store.write_json(
            "pre_checagem",
            "relatorio.json",
            {"suspeitas": [], "pendente": "pre-checagem ainda nao implementada"},
            step="pre_checagem",
        )
        return StepResult.done(summary="pre-checagem pendente: nenhuma imagem avaliada")
