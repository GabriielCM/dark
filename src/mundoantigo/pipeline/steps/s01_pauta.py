"""Etapa 1: pauta.

Registra o tema e o pilar editorial. Nao gasta nada: e so o ponto de partida
que fica gravado para as etapas seguintes lerem.
"""

from __future__ import annotations

from pathlib import Path

from ...db.models import TopicSource
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step

PILLARS = (
    "engenharia",
    "tecnologia",
    "batalhas",
    "cotidiano",
    "medicina",
    "imperios",
    "misterios",
)

#  Variacao do template narrativo por pilar (brief 3.3: template com variacoes).
PILLAR_VARIATION = {
    "engenharia": "abrir pelo problema fisico, resolver pela solucao tecnica, fechar pelo legado",
    "tecnologia": "abrir pelo objeto, reconstruir como funcionava, fechar pelo que se perdeu",
    "batalhas": (
        "abrir pelo dilema do comandante, desenvolver pela logistica, fechar pela consequencia"
    ),
    "cotidiano": (
        "abrir por um gesto banal de hoje, contrastar com o antigo, fechar pela continuidade"
    ),
    "medicina": (
        "abrir pelo sintoma, percorrer o que se acreditava, fechar pelo que acertaram sem saber"
    ),
    "imperios": "abrir pelo auge, desenvolver pelas tensoes, fechar pelo colapso e suas causas",
    "misterios": (
        "abrir pela evidencia, separar o que se sabe do que se especula, "
        "fechar sem inventar resposta"
    ),
}


class PautaStep(Step):
    name = StepName.PAUTA

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("pauta", "pauta.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        pillar = ctx.pillar if ctx.pillar in PILLARS else "engenharia"
        source = TopicSource.LIVRO if ctx.book_id else TopicSource.MANUAL

        payload = {
            "video_id": ctx.video_id,
            "tema": ctx.topic,
            "pilar": pillar,
            "variacao_narrativa": PILLAR_VARIATION[pillar],
            "origem": source.value,
            "livro_id": ctx.book_id,
            "capitulo": ctx.book_chapter,
            "canais": [c.id for c in ctx.channels()],
        }
        ctx.store.write_json("pauta", "pauta.json", payload, step="pauta")

        return StepResult.done(
            summary=f"pauta registrada: {ctx.topic[:60]} (pilar {pillar})",
            pilar=pillar,
        )
