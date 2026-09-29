"""Etapa 6: storyboard.

O corte das cenas e feito por codigo (scenes/grouping.py): frases do roteiro
aprovado juntadas em cenas de 5 a 7 s, como nos videos entregues. O LLM
barato entra depois, um bloco por vez, so para dirigir cada cena: tipo, o que
a imagem mostra, personagem, foto de referencia e as camadas que o Remotion
desenha por cima (titulo, tarja, texto-chave, balao, MC recortado, cartao).

As cenas sao unicas: os dois videos compartilham as mesmas imagens (brief,
principio 2). O que muda no EN e o texto das camadas, que vem nos dois idiomas.

O conceito da thumbnail tambem sai aqui, numa chamada a mais: a arte base e
gerada junto com os cenarios e passa pela mesma revisao de imagens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...errors import ProviderError
from ...scenes.grouping import SceneSlot, group_scenes
from ...scenes.validation import BlockContext, normalize_scene
from ...text.segment import segment_script, units_from_json
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class CenasStep(Step):
    name = StepName.CENAS

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("cenas", "storyboard.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        roteiro_pt = ctx.store.read_json("roteiro", "roteiro.aprovado.json")
        roteiro_en = ctx.store.read_json("adaptacao", "roteiro.en.json")
        channel = ctx.channel_pt
        style = ctx.settings.style

        units_path = ctx.store.path("roteiro", "frases.pt-br.json")
        units = (
            units_from_json(ctx.store.read_json("roteiro", "frases.pt-br.json"))
            if units_path.exists()
            else segment_script(
                roteiro_pt, prefix="p", language=channel.language, words_per_minute=channel.wpm
            )
        )
        slots = group_scenes(
            units,
            words_per_minute=channel.wpm,
            min_s=ctx.settings.scenes.seconds_min,
            max_s=ctx.settings.scenes.seconds_max,
        )
        text_by_unit = {u.id: u.text for u in units}
        character = str(style.character.get("descricao_fixa") or "the host")
        costume = str(
            roteiro_pt.get("figurino") or style.character.get("figurino_padrao") or "a plain tunic"
        )

        prompt_obj = ctx.prompts.get("cenas/storyboard")
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        scenes: list[dict[str, Any]] = []
        notes: list[str] = []
        flagged: list[str] = []
        blocks_pt = roteiro_pt.get("blocos", [])
        blocks_en = roteiro_en.get("blocos", [])

        for block_index, block in enumerate(blocks_pt):
            block_slots = [s for s in slots if s.block == block_index]
            if not block_slots:
                continue
            block_en = blocks_en[block_index] if block_index < len(blocks_en) else {}
            context = BlockContext(
                comments_pt=[str(c) for c in block.get("comentarios_mc", [])],
                comments_en=[str(c) for c in block_en.get("comentarios_mc", [])],
                tags_pt=[str(t) for t in block.get("tarjas", [])],
                tags_en=[str(t) for t in block_en.get("tarjas", [])],
                narration_en=str(block_en.get("narracao") or ""),
            )
            directed = await self._direct_block(
                ctx, prompt_obj, llm, block, block_slots, text_by_unit, context, character, costume
            )
            used_tags: set[int] = set()
            used_comments: set[int] = set()
            for position, slot in enumerate(block_slots):
                narration = " ".join(text_by_unit[i] for i in slot.units)
                scene = normalize_scene(
                    directed.get(slot.index),
                    fallback_text=narration,
                    position=len(scenes) + position,
                    block=context,
                    used_tags=used_tags,
                    used_comments=used_comments,
                    notes=notes,
                    index=slot.index,
                )
                scene["descricao_visual"] = self._clean(
                    scene["descricao_visual"], slot.index, style, flagged
                )
                if position == 0:
                    #  O titulo do capitulo sai do roteiro, nao do LLM: e o mesmo
                    #  texto da descricao, sempre (docs/estilo/analise-entregas.md).
                    scene["titulo_capitulo"] = {
                        "pt": str(block.get("titulo") or ""),
                        "en": str(block_en.get("titulo") or block.get("titulo") or ""),
                    }
                scenes.append({**slot.to_json(), "narracao": narration, **scene})

        thumbnail = await self._direct_thumbnail(
            ctx, llm, roteiro_pt, character, costume, scenes, flagged
        )
        payload = {
            "versao": 2,
            "personagem": {"descricao_fixa": character, "figurino": costume},
            "thumbnail": thumbnail,
            "cenas": scenes,
            "total": len(scenes),
            "duracao_total_s": round(sum(s["duracao_estimada_s"] for s in scenes), 1),
            "ajustes": notes,
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
            ajustes=len(notes),
            prompts_ajustados=len(flagged),
        )

    async def _direct_block(
        self,
        ctx: StepContext,
        prompt_obj: Any,
        llm: Any,
        block: dict[str, Any],
        slots: list[SceneSlot],
        text_by_unit: dict[str, str],
        context: BlockContext,
        character: str,
        costume: str,
    ) -> dict[int, dict[str, Any]]:
        """Uma chamada por bloco: o que cada cena mostra e o que vai por cima."""
        listed = [
            {
                "indice": slot.index,
                "segundos": round(slot.seconds, 1),
                "narracao": " ".join(text_by_unit[i] for i in slot.units),
            }
            for slot in slots
        ]
        rendered = prompt_obj.render(
            bloco_titulo=str(block.get("titulo") or ""),
            secao=str(block.get("secao") or ""),
            personagem=character,
            figurino=costume,
            cenas=json.dumps(listed, ensure_ascii=False, indent=2),
            comentarios_mc=json.dumps(list(enumerate(context.comments_pt)), ensure_ascii=False),
            tarjas=json.dumps(list(enumerate(context.tags_pt)), ensure_ascii=False),
            narracao_en=context.narration_en or "(sem adaptação)",
        )
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.6,
            max_tokens=12000,
        )
        raw = response.json()
        items = raw.get("cenas", []) if isinstance(raw, dict) else []
        return {
            int(item["indice"]): item
            for item in items
            if isinstance(item, dict) and isinstance(item.get("indice"), int)
        }

    async def _direct_thumbnail(
        self,
        ctx: StepContext,
        llm: Any,
        script: dict[str, Any],
        character: str,
        costume: str,
        scenes: list[dict[str, Any]],
        flagged: list[str],
    ) -> dict[str, Any]:
        """O conceito da thumbnail. Resposta ruim nao derruba o storyboard:
        a thumb cai na primeira cena de lugar, e o revisor ve na grade."""
        prompt_obj = ctx.prompts.get("cenas/thumbnail")
        rendered = prompt_obj.render(
            titulo=str(script.get("titulo_provisorio") or ctx.topic),
            gancho=str(script.get("gancho") or ""),
            capitulos=json.dumps(
                [str(b.get("titulo") or "") for b in script.get("blocos", [])],
                ensure_ascii=False,
            ),
            personagem=character,
            figurino=costume,
        )
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.8,
        )
        try:
            raw = response.json()
        except ProviderError:
            raw = None
        return self._thumbnail_concept(raw, scenes, ctx.settings.style, flagged, prompt_obj.ref)

    @classmethod
    def _thumbnail_concept(
        cls,
        raw: Any,
        scenes: list[dict[str, Any]],
        style: Any,
        flagged: list[str],
        prompt_ref: str,
    ) -> dict[str, Any]:
        raw = raw if isinstance(raw, dict) else {}
        visual = " ".join(str(raw.get("descricao_visual") or "").split())
        fallback = not visual
        if fallback:
            places = [s for s in scenes if s.get("tipo") in {"lugar", "plano_geral"}]
            first = (places or scenes or [{}])[0]
            visual = str(first.get("descricao_visual") or "")
        mc = raw.get("mc") if isinstance(raw.get("mc"), dict) else None
        side = raw.get("lado_texto") if raw.get("lado_texto") in {"esquerda", "direita"} else None
        return {
            "conceito": " ".join(str(raw.get("conceito") or "").split()) or visual,
            "descricao_visual": cls._clean(visual, 0, style, flagged),
            "mc": (
                {"acao": str(mc.get("acao") or ""), "expressao": str(mc.get("expressao") or "")}
                if mc and not fallback
                else None
            ),
            #  O MC fica do lado oposto ao texto; sem indicacao, texto a esquerda.
            "lado_texto": side or "esquerda",
            "origem": "fallback" if fallback else prompt_ref,
        }

    @staticmethod
    def _clean(prompt: str, index: int, style: Any, flagged: list[str]) -> str:
        """Originalidade visual (CLAUDE.md): o termo proibido sai do prompt."""
        banned = style.check_originality(prompt)
        if not banned:
            return prompt
        for term in banned:
            prompt = prompt.replace(term, "").replace(term.title(), "")
        flagged.append(f"cena {index}: removido {banned}")
        return " ".join(prompt.split())
