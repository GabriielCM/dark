"""Etapa 12: trilha e efeitos.

Escolhe uma faixa por bloco do roteiro na biblioteca do canal (YouTube Audio
Library), posiciona os efeitos nas pausas da narracao e mixa tudo por idioma,
com a musica baixando sob a voz (ducking) e volume final em -14 LUFS.

A mixagem chega na fase D da reconstrucao. Ate la a etapa grava um plano
vazio por idioma, e a montagem usa so a narracao.
"""

from __future__ import annotations

from pathlib import Path

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step

LANGUAGES = ("pt-br", "en")


class TrilhaStep(Step):
    name = StepName.TRILHA

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("trilha", f"plano.{lang}.json") for lang in LANGUAGES]

    async def run(self, ctx: StepContext) -> StepResult:
        for lang in LANGUAGES:
            ctx.store.write_json(
                "trilha",
                f"plano.{lang}.json",
                {"faixas": [], "efeitos": [], "pendente": "mixagem ainda nao implementada"},
                step="trilha",
            )
        return StepResult.done(summary="sem trilha: mixagem pendente, o video sai so com a voz")
