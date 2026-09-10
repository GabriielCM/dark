"""Etapa 3: roteiro PT-BR e relatorio de fatos.

O roteiro sai junto com o relatorio, e nao depois, porque o gate da etapa 4
precisa dos dois para decidir. Pegar o erro onde ele e barato (brief, principio 3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class RoteiroStep(Step):
    name = StepName.ROTEIRO

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [
            ctx.store.path("roteiro", "roteiro.pt-br.json"),
            ctx.store.path("roteiro", "relatorio_fatos.json"),
        ]

    async def run(self, ctx: StepContext) -> StepResult:
        pauta = ctx.store.read_json("pauta", "pauta.json")
        dossie = ctx.store.read_json("pesquisa", "dossie.json")
        channel = ctx.channel_pt

        roteiro, prompt_ref, llm_name, llm_model = await self._write_script(
            ctx, pauta, dossie, channel
        )
        ctx.store.write_json(
            "roteiro",
            "roteiro.pt-br.json",
            roteiro,
            step="roteiro",
            provider=llm_name,
            model=llm_model,
            prompt_ref=prompt_ref,
        )

        report, report_ref = await self._fact_check(ctx, roteiro, dossie)
        ctx.store.write_json(
            "roteiro",
            "relatorio_fatos.json",
            report,
            step="roteiro",
            provider=llm_name,
            model=llm_model,
            prompt_ref=report_ref,
        )

        words = int(roteiro.get("palavras_total") or self._count_words(roteiro))
        minutes = words / max(channel.wpm, 1)
        n_items = len(report.get("itens", []))

        return StepResult.done(
            summary=(
                f"roteiro com {words} palavras (~{minutes:.1f} min), {n_items} afirmacoes checadas"
            ),
            palavras=words,
            minutos_estimados=round(minutes, 1),
            afirmacoes=n_items,
        )

    async def _write_script(
        self, ctx: StepContext, pauta: dict[str, Any], dossie: dict[str, Any], channel: object
    ) -> tuple[dict[str, Any], str, str, str]:
        prompt_obj = ctx.prompts.get("roteiro/roteiro_ptbr")
        wpm = ctx.channel_pt.wpm
        rendered = prompt_obj.render(
            dossie=json.dumps(dossie, ensure_ascii=False, indent=2),
            template=ctx.channel_pt.narrative.get("template", ""),
            tom=ctx.channel_pt.narrative.get("tom", "documental serio"),
            ppm=wpm,
            duracao_alvo_min=ctx.channel_pt.target_min_minutes,
            duracao_alvo_max=ctx.channel_pt.target_max_minutes,
            pilar=pauta["pilar"],
            variacao=pauta.get("variacao_narrativa", ""),
            palavras_min=ctx.channel_pt.target_min_minutes * wpm,
            palavras_max=ctx.channel_pt.target_max_minutes * wpm,
        )
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.8,
            max_tokens=12000,
        )
        return response.json(), prompt_obj.ref, llm.name, llm.model

    async def _fact_check(
        self, ctx: StepContext, roteiro: dict[str, Any], dossie: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        prompt_obj = ctx.prompts.get("roteiro/relatorio_fatos")
        rendered = prompt_obj.render(
            roteiro=json.dumps(roteiro, ensure_ascii=False, indent=2),
            dossie=json.dumps(dossie, ensure_ascii=False, indent=2),
        )
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            #  Temperatura baixa: checagem nao e lugar para criatividade.
            temperature=0.1,
            max_tokens=12000,
        )
        return response.json(), prompt_obj.ref

    @staticmethod
    def _count_words(roteiro: dict[str, Any]) -> int:
        return sum(len(str(b.get("narracao", "")).split()) for b in roteiro.get("blocos", []))
