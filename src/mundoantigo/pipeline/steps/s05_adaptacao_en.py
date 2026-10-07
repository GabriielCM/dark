"""Etapa 5: adaptacao para o ingles.

Adaptacao, nao traducao (brief 3.3): unidades, referencias culturais e ritmo
mudam; os fatos, nao. O roteiro EN herda a aprovacao do gate apenas se as
afirmacoes sobreviverem intactas — por isso a conferencia de fatos preservados.

Cada bloco EN tem um limite de palavras: as do bloco PT vezes `ppm EN / ppm
PT`. Com a faixa unica (ADR 0011), a narracao EN toca sobre o video PT, e um
bloco que passa do limite vira pausa no PT. O bloco que passar por mais de
`encurtar_bloco_acima` e encurtado sozinho, uma vez.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...errors import TransientError
from ...providers.base import estimate_tokens
from ...text.segment import segment_script, units_to_json
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step

#  Faixa do limite de saida da adaptacao (ver `_output_budget`). No teto, uma
#  chamada ao modelo principal custa no maximo uns US$ 0,50 de saida.
OUTPUT_TOKENS_MIN = 12000
OUTPUT_TOKENS_MAX = 32000


def _words(block: dict[str, Any]) -> int:
    return len(str(block.get("narracao", "")).split())


class AdaptacaoEnStep(Step):
    name = StepName.ADAPTACAO_EN

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [
            ctx.store.path("adaptacao", "roteiro.en.json"),
            ctx.store.path("adaptacao", "frases.en.json"),
        ]

    async def run(self, ctx: StepContext) -> StepResult:
        roteiro_pt = ctx.store.read_json("roteiro", "roteiro.aprovado.json")
        channel = ctx.channel_en
        low, high = self._target_minutes(roteiro_pt, ctx.channel_pt.wpm)
        limits = self._word_limits(roteiro_pt, ctx.channel_pt.wpm, channel.wpm)

        prompt_obj = ctx.prompts.get("adaptacao/en")
        rendered = prompt_obj.render(
            roteiro_ptbr=json.dumps(roteiro_pt, ensure_ascii=False, indent=2),
            ppm=channel.wpm,
            duracao_alvo_min=low,
            duracao_alvo_max=high,
            unidades=channel.units.get("sistema", "imperial"),
            tom=channel.narrative.get("tom", "serious documentary"),
            limites_por_bloco="\n".join(
                f'- Block {i + 1} ("{b.get("titulo", "")}"): at most {limit} words'
                for i, (b, limit) in enumerate(
                    zip(roteiro_pt.get("blocos", []), limits, strict=True)
                )
            ),
        )
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.7,
            max_tokens=self._output_budget(rendered),
        )
        roteiro_en = response.json()

        missing = self._claims_lost(roteiro_pt, roteiro_en)
        blocks_pt = len(roteiro_pt.get("blocos", []))
        blocks_en = len(roteiro_en.get("blocos", []))
        if blocks_en != blocks_pt:
            #  Os dois videos dividem as mesmas cenas, bloco a bloco: um bloco a
            #  mais ou a menos desalinha tudo. Nova tentativa, nao um aviso.
            raise TransientError(
                f"adaptacao EN com {blocks_en} blocos para {blocks_pt} no PT; refazendo"
            )

        shortened: list[int] = []
        if ctx.settings.narration.single_track:
            over = [
                i
                for i, (block, limit) in enumerate(zip(roteiro_en["blocos"], limits, strict=True))
                if _words(block) > limit * (1 + ctx.settings.narration.shorten_above)
            ]
            if over:
                shortened = await self._shorten(ctx, roteiro_pt, roteiro_en, limits, over)

        ctx.store.write_json(
            "adaptacao",
            "roteiro.en.json",
            roteiro_en,
            step="adaptacao_en",
            provider=llm.name,
            model=llm.model,
            prompt_ref=prompt_obj.ref,
            extra={
                "afirmacoes_perdidas": sorted(missing),
                "blocos": blocks_en,
                "limites_palavras": limits,
                "palavras_por_bloco": [_words(b) for b in roteiro_en["blocos"]],
                "blocos_encurtados": shortened,
            },
        )
        units = segment_script(
            roteiro_en, prefix="e", language=channel.language, words_per_minute=channel.wpm
        )
        ctx.store.write_json(
            "adaptacao", "frases.en.json", units_to_json(units), step="adaptacao_en"
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
        if shortened:
            summary += f"; {len(shortened)} bloco(s) encurtado(s) para caber no tempo do PT"

        return StepResult.done(
            summary=summary,
            blocos_pt=blocks_pt,
            blocos_en=blocks_en,
            afirmacoes_perdidas=sorted(missing),
            blocos_encurtados=shortened,
        )

    async def _shorten(
        self,
        ctx: StepContext,
        roteiro_pt: dict[str, Any],
        roteiro_en: dict[str, Any],
        limits: list[int],
        over: list[int],
    ) -> list[int]:
        """Reescreve so os blocos acima do limite, uma vez (ADR 0011).

        So a `narracao` muda: as afirmacoes, o titulo e as camadas ficam. Um
        bloco que continuar longo segue assim, e a narracao avisa do
        esticamento no PT.
        """
        channel = ctx.channel_en
        prompt_obj = ctx.prompts.get("adaptacao/encurtar")
        rendered = prompt_obj.render(
            blocos=json.dumps(
                [
                    {
                        "indice": i,
                        "pt": roteiro_pt["blocos"][i].get("narracao", ""),
                        "en": roteiro_en["blocos"][i].get("narracao", ""),
                        "limite_palavras": limits[i],
                    }
                    for i in over
                ],
                ensure_ascii=False,
                indent=2,
            ),
            unidades=channel.units.get("sistema", "imperial"),
            tom=channel.narrative.get("tom", "serious documentary"),
        )
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.4,
            max_tokens=min(OUTPUT_TOKENS_MAX, max(4000, 3 * estimate_tokens(rendered))),
        )
        shortened: list[int] = []
        for item in response.json().get("blocos", []):
            index = item.get("indice")
            text = str(item.get("narracao") or "").strip()
            if index in over and text:
                roteiro_en["blocos"][index]["narracao"] = text
                shortened.append(int(index))
        return sorted(shortened)

    @staticmethod
    def _word_limits(roteiro_pt: dict[str, Any], wpm_pt: int, wpm_en: int) -> list[int]:
        """Limite de palavras de cada bloco EN para caber no tempo do bloco PT."""
        ratio = wpm_en / max(wpm_pt, 1)
        return [max(1, round(_words(b) * ratio)) for b in roteiro_pt.get("blocos", [])]

    @staticmethod
    def _output_budget(prompt: str) -> int:
        """Limite de saida proporcional ao roteiro que vai ser adaptado.

        O roteiro EN tem mais ou menos o tamanho do PT que vai no prompt, e o
        modelo principal ainda raciocina antes de responder: na amostra de 60 s,
        600 tokens de JSON custaram 2.500 a 4.200 de saida. Com 12000 fixos, o
        roteiro de 20 min veio cortado. O teto limita o gasto por chamada.
        """
        return min(OUTPUT_TOKENS_MAX, max(OUTPUT_TOKENS_MIN, 3 * estimate_tokens(prompt)))

    @staticmethod
    def _target_minutes(roteiro_pt: dict[str, Any], wpm_pt: int) -> tuple[float, float]:
        """A duracao do roteiro aprovado, com 10% de folga para cada lado.

        A adaptacao acompanha o roteiro que existe, e nao a meta do canal: uma
        amostra de um minuto nao pode voltar do LLM com vinte.
        """
        words = sum(len(str(b.get("narracao", "")).split()) for b in roteiro_pt.get("blocos", []))
        minutes = words / max(wpm_pt, 1)
        return round(max(minutes * 0.9, 0.1), 1), round(max(minutes * 1.1, 0.2), 1)

    @staticmethod
    def _claims_lost(roteiro_pt: dict[str, Any], roteiro_en: dict[str, Any]) -> set[str]:
        """Afirmacoes citadas no PT que sumiram na adaptacao."""

        def claim_ids(script: dict[str, Any]) -> set[str]:
            out: set[str] = set()
            for block in script.get("blocos", []):
                out.update(str(a) for a in block.get("afirmacoes_usadas", []))
            return out

        return claim_ids(roteiro_pt) - claim_ids(roteiro_en)
