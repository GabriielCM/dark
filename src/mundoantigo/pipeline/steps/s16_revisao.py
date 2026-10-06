"""Etapa 16: revisao humana do corte final.

Segundo ponto de revisao (o primeiro e a grade de imagens): o corte final, no
painel, com o relatorio de fatos ao lado e os cortes do TikTok embaixo (ADR
0010). Esta etapa nao decide nada: monta o dossie de revisao e bloqueia
esperando aprovar ou rejeitar.
"""

from __future__ import annotations

from pathlib import Path

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step
from .s15_cortes import clip_video, load_selection


class RevisaoStep(Step):
    name = StepName.REVISAO

    def outputs(self, ctx: StepContext) -> list[Path]:
        #  A aprovacao humana e o artefato: sem ela, a etapa nunca esta feita.
        return [ctx.store.path("revisao", "aprovacao.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        report = ctx.store.read_json("roteiro", "relatorio_fatos.final.json")
        summary = report.get("resumo", {})

        dossier = {
            "video_id": ctx.video_id,
            "tema": ctx.topic,
            "videos": {
                lang: str(
                    ctx.store.path("montagem", f"video.{lang}.mp4").relative_to(ctx.store.root)
                )
                for lang in ("pt-br", "en")
                if ctx.store.path("montagem", f"video.{lang}.mp4").exists()
            },
            "relatorio_fatos": report,
            "resumo_confianca": summary,
            "metadados": {
                lang: f"metadados/metadados.{lang}.json"
                for lang in ("pt-br", "en")
                if ctx.store.path("metadados", f"metadados.{lang}.json").exists()
            },
            "cortes": self._clips(ctx),
            "avisos": self._warnings(ctx),
        }
        ctx.store.write_json("revisao", "revisao.json", dossier, step="revisao")

        return StepResult.blocked(
            "aguardando corte final no painel: aprovar ou rejeitar com motivo",
            resumo_confianca=summary,
            avisos=dossier["avisos"],
        )

    @staticmethod
    def _clips(ctx: StepContext) -> dict[str, list[str]]:
        """Os mp4 dos cortes do TikTok de cada idioma, para o dossie."""
        selection = load_selection(ctx)
        if selection is None:
            return {}
        return {
            lang: [
                clip_video(ctx, clip.number, lang).relative_to(ctx.store.root).as_posix()
                for clip in selection.clips
                if clip_video(ctx, clip.number, lang).exists()
            ]
            for lang in ("pt-br", "en")
        }

    @staticmethod
    def _warnings(ctx: StepContext) -> list[str]:
        """Pontos que merecem o olho do revisor, reunidos dos sidecars."""
        warnings: list[str] = []

        selection = load_selection(ctx)
        if selection is not None:
            warnings += [f"cortes do TikTok: {w}" for w in selection.warnings]

        adaptation = ctx.store.path("adaptacao", "roteiro.en.json")
        sidecar = ctx.store.read_sidecar(adaptation)
        if sidecar and sidecar.extra.get("afirmacoes_perdidas"):
            lost = sidecar.extra["afirmacoes_perdidas"]
            warnings.append(
                f"{len(lost)} afirmacao(oes) do roteiro PT nao aparecem na versao EN: {lost}"
            )

        storyboard_path = ctx.store.path("cenas", "storyboard.json")
        if storyboard_path.exists():
            storyboard = ctx.store.read_json("cenas", "storyboard.json")
            adjusted = storyboard.get("prompts_ajustados_por_originalidade") or []
            if adjusted:
                warnings.append(
                    f"{len(adjusted)} prompt(s) de cenario tiveram termos removidos "
                    f"pela regra de originalidade visual"
                )

        report_path = ctx.store.path("roteiro", "relatorio_fatos.final.json")
        if report_path.exists():
            report = ctx.store.read_json("roteiro", "relatorio_fatos.final.json")
            if report.get("reescritas"):
                warnings.append(
                    f"o gate de fatos reescreveu o roteiro {report['reescritas']} vez(es); "
                    "confira se o texto continua fluindo"
                )
            media = (report.get("resumo") or {}).get("media", 0)
            if media:
                warnings.append(f"{media} afirmacao(oes) de confianca media no relatorio")

        return warnings
