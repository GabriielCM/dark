"""Etapa 5: adaptacao para o ingles.

Adaptacao, nao traducao (brief 3.3): unidades, referencias culturais e ritmo
mudam; os fatos, nao. O roteiro EN herda a aprovacao do gate apenas se as
afirmacoes sobreviverem intactas — por isso a conferencia de fatos preservados.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class AdaptacaoEnStep(Step):
    name = StepName.ADAPTACAO_EN

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("adaptacao", "roteiro.en.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        roteiro_pt = ctx.store.read_json("roteiro", "roteiro.aprovado.json")
        channel = ctx.channel_en

        prompt_obj = ctx.prompts.get("adaptacao/en")
        rendered = prompt_obj.render(
            roteiro_ptbr=json.dumps(roteiro_pt, ensure_ascii=False, indent=2),
            ppm=channel.wpm,
            duracao_alvo_min=channel.target_min_minutes,
            duracao_alvo_max=channel.target_max_minutes,
            unidades=channel.units.get("sistema", "imperial"),
            tom=channel.narrative.get("tom", "serious documentary"),
        )
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.7,
            max_tokens=12000,
        )
        roteiro_en = response.json()

        missing = self._claims_lost(roteiro_pt, roteiro_en)
        blocks_pt = len(roteiro_pt.get("blocos", []))
        blocks_en = len(roteiro_en.get("blocos", []))

        ctx.store.write_json(
            "adaptacao",
            "roteiro.en.json",
            roteiro_en,
            step="adaptacao_en",
            provider=llm.name,
            model=llm.model,
            prompt_ref=prompt_obj.ref,
            extra={"afirmacoes_perdidas": sorted(missing), "blocos": blocks_en},
        )

        if missing:
            #  Nao bloqueia a producao: o corte final vai mostrar isso ao humano
            #  junto com o relatorio de fatos, que e onde a decisao cabe.
            summary = (
                f"adaptacao EN com {blocks_en} blocos; "
                f"{len(missing)} afirmacao(oes) do PT nao aparecem no EN"
            )
        else:
            summary = f"adaptacao EN com {blocks_en} blocos, todas as afirmacoes preservadas"

        return StepResult.done(
            summary=summary,
            blocos_pt=blocks_pt,
            blocos_en=blocks_en,
            afirmacoes_perdidas=sorted(missing),
        )

    @staticmethod
    def _claims_lost(roteiro_pt: dict[str, Any], roteiro_en: dict[str, Any]) -> set[str]:
        """Afirmacoes citadas no PT que sumiram na adaptacao."""

        def claim_ids(script: dict[str, Any]) -> set[str]:
            out: set[str] = set()
            for block in script.get("blocos", []):
                out.update(str(a) for a in block.get("afirmacoes_usadas", []))
            return out

        return claim_ids(roteiro_pt) - claim_ids(roteiro_en)
