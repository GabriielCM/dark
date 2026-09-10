"""Etapa 6: storyboard.

Quebra o roteiro em cenas com duracao, prompt de cenario e pose do personagem.
As cenas sao unicas: os dois videos compartilham as mesmas imagens (brief,
principio 2), so a narracao muda.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class CenasStep(Step):
    name = StepName.CENAS

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("cenas", "storyboard.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        roteiro = ctx.store.read_json("roteiro", "roteiro.aprovado.json")
        style = ctx.settings.style
        scenes_cfg = ctx.settings.scenes

        prompt_obj = ctx.prompts.get("cenas/storyboard")
        rendered = prompt_obj.render(
            roteiro=json.dumps(roteiro, ensure_ascii=False, indent=2),
            segundos_por_cena_min=scenes_cfg.seconds_min,
            segundos_por_cena_max=scenes_cfg.seconds_max,
            ppm=ctx.channel_pt.wpm,
            prompt_base_estilo=style.base_prompt,
            poses_disponiveis=", ".join(style.character.get("poses_minimas", [])),
        )
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.6,
            max_tokens=16000,
        )
        storyboard = response.json()
        scenes = storyboard.get("cenas", []) if isinstance(storyboard, dict) else []

        scenes, flagged = self._normalize(scenes, ctx)
        payload = {
            "cenas": scenes,
            "total": len(scenes),
            "duracao_total_s": round(sum(s["duracao_estimada_s"] for s in scenes), 1),
            "prompts_ajustados_por_originalidade": flagged,
        }
        ctx.store.write_json(
            "cenas",
            "storyboard.json",
            payload,
            step="cenas",
            provider=llm.name,
            model=llm.model,
            prompt_ref=prompt_obj.ref,
        )

        minutes = payload["duracao_total_s"] / 60
        return StepResult.done(
            summary=f"{len(scenes)} cenas, ~{minutes:.1f} min de video",
            cenas=len(scenes),
            duracao_s=payload["duracao_total_s"],
            prompts_ajustados=len(flagged),
        )

    def _normalize(
        self, scenes: list[Any], ctx: StepContext
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Garante indices, limites de duracao e originalidade dos prompts."""
        cfg = ctx.settings.scenes
        style = ctx.settings.style
        clean: list[dict[str, Any]] = []
        flagged: list[str] = []

        for i, raw in enumerate(scenes, start=1):
            if not isinstance(raw, dict):
                continue
            prompt = str(raw.get("prompt_cenario", "")).strip()
            banned = style.check_originality(prompt)
            if banned:
                #  Originalidade visual e restricao dura do CLAUDE.md: o termo
                #  sai do prompt em vez de a cena ser descartada.
                for term in banned:
                    prompt = prompt.replace(term, "").replace(term.title(), "")
                prompt = " ".join(prompt.split())
                flagged.append(f"cena {i}: removido {banned}")

            duration = float(raw.get("duracao_estimada_s") or cfg.seconds_min)
            duration = min(max(duration, cfg.seconds_min), cfg.seconds_max * 1.5)

            layers = raw.get("camadas") or {}
            character = raw.get("personagem")
            if isinstance(character, dict) and not character.get("pose"):
                character = None

            clean.append(
                {
                    "indice": i,
                    "narracao": str(raw.get("narracao", "")),
                    "duracao_estimada_s": round(duration, 2),
                    "prompt_cenario": prompt,
                    "camadas": {
                        "frente": str(layers.get("frente", "")),
                        "meio": str(layers.get("meio", "")),
                        "fundo": str(layers.get("fundo", "")),
                    },
                    "camera": str(raw.get("camera") or "estatica"),
                    "personagem": character,
                    "sfx": raw.get("sfx") or None,
                    "musica": raw.get("musica") or None,
                }
            )
        return clean, flagged
