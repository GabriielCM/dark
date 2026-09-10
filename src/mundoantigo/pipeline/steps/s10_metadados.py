"""Etapa 10: metadados.

Titulo, descricao com fontes, tags, capitulos e conceito de thumbnail — nos
dois idiomas (brief 3.6). A thumbnail sai em duas versoes porque com e sem
texto ainda esta em teste (brief 5.4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...providers.image import ImageRequest
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class MetadadosStep(Step):
    name = StepName.METADADOS

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [
            ctx.store.path("metadados", "metadados.pt-br.json"),
            ctx.store.path("metadados", "metadados.en.json"),
            ctx.store.path("metadados", "thumbnail.png"),
        ]

    async def run(self, ctx: StepContext) -> StepResult:
        dossie = ctx.store.read_json("pesquisa", "dossie.json")
        storyboard = ctx.store.read_json("cenas", "storyboard.json")
        sources = dossie.get("fontes", []) if isinstance(dossie, dict) else []

        prompt_obj = ctx.prompts.get("metadados/pacote")
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        titles: dict[str, str] = {}
        thumb_prompt = ""

        for channel, stage, filename in (
            (ctx.channel_pt, "roteiro", "roteiro.aprovado.json"),
            (ctx.channel_en, "adaptacao", "roteiro.en.json"),
        ):
            lang = channel.id
            script = ctx.store.read_json(stage, filename)
            timings = ctx.store.read_json("narracao", f"tempos.{lang}.json")

            rendered = prompt_obj.render(
                roteiro=json.dumps(script, ensure_ascii=False, indent=2),
                fontes=json.dumps(sources, ensure_ascii=False, indent=2),
                cenas=json.dumps(timings.get("blocos", []), ensure_ascii=False, indent=2),
                idioma=channel.language,
                divulgar_sintetico=channel.discloses_synthetic,
            )
            response = await llm.complete(
                rendered,
                step=self.name.value,
                video_id=ctx.video_id,
                step_run_id=ctx.step_run_id,
                temperature=0.6,
            )
            metadata = response.json()
            metadata = self._finalize(metadata, channel, sources, timings)

            ctx.store.write_json(
                "metadados",
                f"metadados.{lang}.json",
                metadata,
                step="metadados",
                provider=llm.name,
                model=llm.model,
                prompt_ref=prompt_obj.ref,
            )
            titles[lang] = str(metadata.get("titulo", ""))
            thumb_prompt = thumb_prompt or str((metadata.get("thumbnail") or {}).get("prompt", ""))

        await self._thumbnail(ctx, thumb_prompt, storyboard)
        ctx.scratch["titles"] = titles

        return StepResult.done(
            summary=f"metadados nos dois idiomas; titulo PT: {titles.get('pt-br', '')[:50]}",
            titulo_pt=titles.get("pt-br"),
            titulo_en=titles.get("en"),
        )

    def _finalize(
        self, metadata: dict[str, Any], channel: object, sources: list[Any], timings: dict[str, Any]
    ) -> dict[str, Any]:
        """Ajusta o que nao se deve confiar ao modelo: capitulos e divulgacao."""
        chapters = metadata.get("capitulos") or []
        #  O YouTube exige que o primeiro capitulo seja 00:00.
        if chapters and str(chapters[0].get("tempo")) != "00:00":
            chapters.insert(0, {"tempo": "00:00", "titulo": chapters[0].get("titulo", "Abertura")})
        metadata["capitulos"] = chapters

        metadata["fontes"] = sources
        metadata["duracao_s"] = timings.get("duracao_s")

        discloses = getattr(channel, "discloses_synthetic", True)
        metadata["divulgar_conteudo_sintetico"] = discloses
        description = str(metadata.get("descricao", ""))
        disclosure = self._disclosure_line(channel)
        if discloses and disclosure not in description:
            description = f"{description.rstrip()}\n\n{disclosure}"
        metadata["descricao"] = description
        return metadata

    @staticmethod
    def _disclosure_line(channel: object) -> str:
        language = str(getattr(channel, "language", "pt-BR"))
        if language.startswith("pt"):
            return (
                "Este video usa narracao e ilustracoes geradas por inteligencia artificial. "
                "A pesquisa, o roteiro e a revisao editorial sao humanos. Fontes acima."
            )
        return (
            "This video uses AI-generated narration and illustration. "
            "Research, script and editorial review are human. Sources above."
        )

    async def _thumbnail(self, ctx: StepContext, prompt: str, storyboard: dict[str, Any]) -> None:
        destination = ctx.store.path("metadados", "thumbnail.png")
        if ctx.store.is_complete(destination):
            return

        style = ctx.settings.style
        if not prompt:
            first = (storyboard.get("cenas") or [{}])[0]
            prompt = str(first.get("prompt_cenario", ctx.topic))
        banned = style.check_originality(prompt)
        for term in banned:
            prompt = prompt.replace(term, "")

        full_prompt = f"{style.base_prompt}. {prompt}. Bold composition, single clear subject"
        provider = ctx.providers.image()
        result = await provider.generate(
            ImageRequest(
                prompt=full_prompt,
                negative=", ".join(style.negatives),
                width=1280,
                height=720,
            ),
            destination,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
        )
        ctx.store.write_sidecar(
            destination,
            step="metadados",
            provider=result.provider,
            model=result.model,
            seed=result.seed,
            extra={
                "prompt": full_prompt,
                #  Sem texto embutido: as duas versoes sao testadas (brief 5.4),
                #  e o texto e sobreposto pelo humano no ajuste.
                "versao": "sem_texto",
            },
        )
