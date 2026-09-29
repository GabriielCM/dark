"""Etapa 13: metadados, descricao e thumbnails (fase B8).

Por idioma:
- o LLM barato escreve o titulo, dois titulos alternativos, os dois
  paragrafos, as tags e o texto da thumb (prompts/metadados/pacote.v2.md). A
  resposta fica em `llm.<lang>.json`: se algo falhar depois, a retomada nao
  paga a chamada de novo;
- o resto da descricao e montado por codigo (publishing/description.py):
  capitulos no tempo real dos blocos, fontes do relatorio aprovado, aviso do
  canal e creditos das fotos de referencia;
- os limites do YouTube sao conferidos aqui (publishing/limits.py), e nao na
  hora do upload.

A thumbnail vem da arte base gerada com os cenarios (assets/thumb-base.png)
e sai em duas versoes: sem texto, a mesma nos dois idiomas, e com o texto de
cada idioma. As duas vao para o "Testar e comparar" do YouTube (brief 5.4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from ...config import ChannelConfig
from ...errors import TransientError
from ...publishing import thumbnails
from ...publishing.description import (
    MIN_CHAPTERS,
    Credit,
    DescriptionParts,
    DescriptionTexts,
    SourceRef,
    chapters_from_timings,
    credits_from_provenance,
    format_timestamp,
    sources_that_passed,
)
from ...publishing.limits import byte_length, fit_description, fit_tags, fit_title, unaccented_pt
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step
from .s08_assets import scene_image, thumbnail_art

LANGS = ("pt-br", "en")
ALTERNATIVE_TITLES = 2


def thumb_without_text(ctx: StepContext) -> Path:
    return ctx.store.path("metadados", "thumb-sem-texto.jpg")


def thumb_with_text(ctx: StepContext, lang: str) -> Path:
    return ctx.store.path("metadados", f"thumb-com-texto.{lang}.jpg")


class MetadadosStep(Step):
    name = StepName.METADADOS

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [
            *(ctx.store.path("metadados", f"metadados.{lang}.json") for lang in LANGS),
            thumb_without_text(ctx),
            *(thumb_with_text(ctx, lang) for lang in LANGS),
        ]

    def invalidate(self, ctx: StepContext, *, keep_paid: bool = False) -> list[Path]:
        """Refazer os metadados e pedir texto novo ao LLM: o cache vai junto.

        Com `keep_paid` (uma imagem refeita, uma foto trocada), so a montagem
        por codigo e refeita: creditos e thumbs mudam, o texto pago nao.
        """
        removed = super().invalidate(ctx)
        if keep_paid:
            return removed
        for lang in LANGS:
            for name in (f"llm.{lang}.json", f"comentario_fixado.{lang}.txt"):
                path = ctx.store.path("metadados", name)
                if ctx.store.delete(path):
                    removed.append(path)
        return removed

    async def run(self, ctx: StepContext) -> StepResult:
        dossier = ctx.store.read_json("pesquisa", "dossie.json")
        report = ctx.store.read_json("roteiro", "relatorio_fatos.final.json")
        storyboard = ctx.store.read_json("cenas", "storyboard.json")
        sources = sources_that_passed(report, dossier if isinstance(dossier, dict) else {})
        credits = self._credits(ctx, storyboard)
        feedback = self._feedback(ctx)

        concept = storyboard.get("thumbnail") or {}
        side = str(concept.get("lado_texto") or "esquerda")
        base, art = self._thumbnail_base(ctx, storyboard)
        quality = thumbnails.save_jpeg(base, thumb_without_text(ctx))
        ctx.store.write_sidecar(
            thumb_without_text(ctx),
            step="metadados",
            extra={"arte": art, "qualidade_jpeg": quality},
        )

        titles: dict[str, str] = {}
        warnings_total = 0
        for channel, stage, filename in (
            (ctx.channel_pt, "roteiro", "roteiro.aprovado.json"),
            (ctx.channel_en, "adaptacao", "roteiro.en.json"),
        ):
            lang = channel.id
            script = ctx.store.read_json(stage, filename)
            timings = ctx.store.read_json("narracao", f"tempos.{lang}.json")
            written = await self._written(ctx, channel, script, concept, feedback)
            metadata = self._assemble(channel, written, timings, sources, credits)
            metadata["thumbnail"] = self._thumbnail(ctx, lang, base, written, side, concept, art)
            if art is None:
                metadata["avisos"].append("sem arte de thumbnail: as thumbs saíram em fundo liso")
            if metadata["thumbnail"]["texto"] and thumbnails.too_many_words(
                metadata["thumbnail"]["texto"]
            ):
                metadata["avisos"].append(
                    f"texto da thumb com mais de {thumbnails.MAX_WORDS} palavras"
                )

            pinned = metadata.get("comentario_fixado")
            if pinned:
                ctx.store.write_text(
                    "metadados", f"comentario_fixado.{lang}.txt", pinned, step="metadados"
                )
            sidecar = ctx.store.read_sidecar(ctx.store.path("metadados", f"llm.{lang}.json"))
            ctx.store.write_json(
                "metadados",
                f"metadados.{lang}.json",
                metadata,
                step="metadados",
                provider=sidecar.provider if sidecar else None,
                model=sidecar.model if sidecar else None,
                prompt_ref=sidecar.prompt_ref if sidecar else None,
            )
            titles[lang] = metadata["titulo"]
            warnings_total += len(metadata["avisos"])

        ctx.scratch["titles"] = titles
        return StepResult.done(
            summary=(
                f"metadados nos dois idiomas; titulo PT: {titles.get('pt-br', '')[:50]}"
                + (f"; {warnings_total} aviso(s)" if warnings_total else "")
            ),
            titulo_pt=titles.get("pt-br"),
            titulo_en=titles.get("en"),
            fontes=len(sources),
            creditos=len(credits),
            avisos=warnings_total,
        )

    # -- texto escrito pelo LLM ----------------------------------------------

    async def _written(
        self,
        ctx: StepContext,
        channel: ChannelConfig,
        script: dict[str, Any],
        concept: dict[str, Any],
        feedback: str | None,
    ) -> dict[str, Any]:
        cache_name = f"llm.{channel.id}.json"
        if ctx.store.is_complete(ctx.store.path("metadados", cache_name)):
            cached: dict[str, Any] = ctx.store.read_json("metadados", cache_name)
            return cached

        prompt_obj = ctx.prompts.get("metadados/pacote")
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        rendered = prompt_obj.render(
            idioma=channel.language,
            titulo_roteiro=str(script.get("titulo_provisorio") or ctx.topic),
            capitulos=json.dumps(
                [str(b.get("titulo") or "") for b in script.get("blocos", [])],
                ensure_ascii=False,
            ),
            roteiro=self._narration(script),
            thumbnail=str(concept.get("conceito") or "(sem conceito definido)"),
            feedback_revisor=feedback or "(nenhum)",
        )
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.6,
        )
        written = self._validated(response.json())
        ctx.store.write_json(
            "metadados",
            cache_name,
            written,
            step="metadados",
            provider=llm.name,
            model=llm.model,
            prompt_ref=prompt_obj.ref,
            extra={"feedback_revisor": feedback} if feedback else {},
        )
        return written

    @staticmethod
    def _narration(script: dict[str, Any]) -> str:
        return "\n\n".join(
            f"### {block.get('titulo') or ''}\n{block.get('narracao') or ''}"
            for block in script.get("blocos", [])
        )

    @staticmethod
    def _validated(raw: Any) -> dict[str, Any]:
        """O que o LLM tem de devolver. Resposta incompleta e refeita na retomada."""
        if not isinstance(raw, dict) or not str(raw.get("titulo") or "").strip():
            raise TransientError("metadados: resposta do LLM sem titulo")
        paragraphs = [str(p).strip() for p in raw.get("paragrafos") or [] if str(p).strip()]
        if not paragraphs and raw.get("descricao"):
            #  Formato v1: descricao inteira; ficam os paragrafos sem carimbo de tempo.
            blocks = [p.strip() for p in str(raw["descricao"]).split("\n\n") if p.strip()]
            paragraphs = [p for p in blocks if not p[:1].isdigit()][:2]
        if not paragraphs:
            raise TransientError("metadados: resposta do LLM sem os paragrafos da descricao")
        thumb_text = raw.get("thumbnail_texto")
        if thumb_text is None and isinstance(raw.get("thumbnail"), dict):
            thumb_text = raw["thumbnail"].get("texto")
        return {
            "titulo": str(raw["titulo"]),
            "titulos_alternativos": [str(t) for t in raw.get("titulos_alternativos") or []],
            "paragrafos": paragraphs[:2],
            "tags": [str(t) for t in raw.get("tags") or []],
            "thumbnail_texto": " ".join(str(thumb_text or "").split()),
        }

    @staticmethod
    def _feedback(ctx: StepContext) -> str | None:
        """O motivo da ultima rejeicao que pediu metadados novos (fase C5)."""
        path = ctx.store.path("revisao", "rejeicoes.json")
        if not path.exists():
            return None
        history = ctx.store.read_json("revisao", "rejeicoes.json")
        for entry in reversed(history if isinstance(history, list) else []):
            if StepName.METADADOS.value in (entry.get("etapas") or []):
                return str(entry.get("motivo") or "") or None
        return None

    # -- montagem por codigo -------------------------------------------------

    @staticmethod
    def _credits(ctx: StepContext, storyboard: dict[str, Any]) -> list[Credit]:
        provenances: list[dict[str, Any] | None] = []
        for scene in storyboard.get("cenas", []):
            sidecar = ctx.store.read_sidecar(scene_image(ctx, int(scene["indice"])))
            if sidecar is not None:
                provenances.append(sidecar.extra.get("referencia"))
        return credits_from_provenance(provenances)

    @staticmethod
    def _assemble(
        channel: ChannelConfig,
        written: dict[str, Any],
        timings: dict[str, Any],
        sources: list[SourceRef],
        credits: list[Credit],
    ) -> dict[str, Any]:
        texts = DescriptionTexts.for_channel(channel.publishing)
        duration = float(timings.get("duracao_s") or 0.0)
        chapters = chapters_from_timings(timings.get("blocos", []), duration)
        paragraphs = tuple(written["paragrafos"])
        fitted = fit_description(
            DescriptionParts(
                paragraphs=paragraphs,
                chapters=tuple(chapters),
                sources=tuple(sources),
                credits=tuple(credits),
                music=(),
                discloses=channel.discloses_synthetic,
                duration_s=duration,
            ),
            texts,
        )
        title, warnings = fit_title(written["titulo"])
        alternatives = [
            fit_title(t)[0] for t in written["titulos_alternativos"][:ALTERNATIVE_TITLES]
        ]
        tags, tag_warnings = fit_tags(written["tags"])
        warnings += tag_warnings + list(fitted.warnings)
        if len(chapters) < MIN_CHAPTERS:
            warnings.append(
                f"só {len(chapters)} capítulo(s): o YouTube exige {MIN_CHAPTERS} para mostrá-los"
            )
        if channel.language.lower().startswith("pt"):
            missing = unaccented_pt(" ".join([title, *alternatives, *paragraphs]))
            if missing:
                warnings.append(f"texto em PT sem acento: {', '.join(missing)}")
        unverified = [c.url for c in credits if not c.verified]
        if unverified:
            warnings.append(
                "foto(s) de referência com licença não verificada: " + ", ".join(unverified)
            )

        with_hours = duration >= 3600
        return {
            "idioma": channel.id,
            "titulo": title,
            "titulos_alternativos": alternatives,
            "descricao": fitted.text,
            "descricao_bytes": byte_length(fitted.text),
            "comentario_fixado": fitted.pinned_comment,
            "paragrafos": list(paragraphs),
            "tags": tags,
            "capitulos": [
                {"tempo": format_timestamp(c.start_s, with_hours=with_hours), "titulo": c.title}
                for c in chapters
            ],
            "fontes": [{"titulo": s.title, "ano": s.year, "url": s.url} for s in sources],
            "creditos_imagens": [
                {
                    "titulo": c.title,
                    "autor": c.author,
                    "licenca": c.license,
                    "url": c.url,
                    "verificada": c.verified,
                }
                for c in credits
            ],
            "duracao_s": duration,
            "divulgar_conteudo_sintetico": channel.discloses_synthetic,
            "avisos": warnings,
        }

    # -- thumbnails ----------------------------------------------------------

    @staticmethod
    def _thumbnail_base(
        ctx: StepContext, storyboard: dict[str, Any]
    ) -> tuple[Image.Image, str | None]:
        """A arte base; na falta dela (producao anterior a B8), a primeira cena de lugar."""
        candidates = [thumbnail_art(ctx)]
        scenes = storyboard.get("cenas", [])
        for kinds in ({"lugar", "plano_geral"}, None):
            candidates += [
                scene_image(ctx, int(s["indice"]))
                for s in scenes
                if kinds is None or s.get("tipo") in kinds
            ]
        for path in candidates:
            if path.exists():
                return thumbnails.base_image(path), path.relative_to(ctx.store.root).as_posix()
        return Image.new("RGB", thumbnails.SIZE, thumbnails.INK), None

    @staticmethod
    def _thumbnail(
        ctx: StepContext,
        lang: str,
        base: Image.Image,
        written: dict[str, Any],
        side: str,
        concept: dict[str, Any],
        art: str | None,
    ) -> dict[str, Any]:
        text = thumbnails.thumb_text(written.get("thumbnail_texto") or "")
        font = thumbnails.font_file(ctx.settings.render.font_family)
        image = thumbnails.with_text(base, text, side=side, font_path=font)
        destination = thumb_with_text(ctx, lang)
        quality = thumbnails.save_jpeg(image, destination)
        ctx.store.write_sidecar(
            destination,
            step="metadados",
            extra={"texto": text, "lado": side, "fonte": font.name, "qualidade_jpeg": quality},
        )
        return {
            "texto": text,
            "lado": side,
            "conceito": concept.get("conceito"),
            "arte": art,
            "com_texto": destination.relative_to(ctx.store.root).as_posix(),
            "sem_texto": thumb_without_text(ctx).relative_to(ctx.store.root).as_posix(),
        }
