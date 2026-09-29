"""Etapa 16: pacote de entrega.

Reune tudo que o upload manual precisa (brief 7) e escreve o checklist de
publicacao. O pipeline termina aqui: o upload no YouTube e humano.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class EntregaStep(Step):
    name = StepName.ENTREGA

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [
            ctx.store.path("entrega", "pacote.json"),
            ctx.store.path("entrega", "CHECKLIST.md"),
        ]

    async def run(self, ctx: StepContext) -> StepResult:
        languages: dict[str, dict[str, Any]] = {}
        package: dict[str, Any] = {
            "video_id": ctx.video_id,
            "tema": ctx.topic,
            "idiomas": languages,
        }

        for lang in ("pt-br", "en"):
            entry: dict[str, Any] = {}
            video = ctx.store.path("montagem", f"video.{lang}.mp4")
            srt = ctx.store.path("narracao", f"legendas.{lang}.srt")
            meta = ctx.store.path("metadados", f"metadados.{lang}.json")

            if video.exists():
                entry["video"] = str(video.relative_to(ctx.store.root))
                entry["tamanho_mb"] = round(video.stat().st_size / 1_048_576, 1)
            if srt.exists():
                entry["legendas"] = str(srt.relative_to(ctx.store.root))
            if meta.exists():
                metadata = json.loads(meta.read_text(encoding="utf-8"))
                entry["titulo"] = metadata.get("titulo")
                entry["descricao"] = metadata.get("descricao")
                entry["tags"] = metadata.get("tags")
                entry["capitulos"] = metadata.get("capitulos")
                entry["divulgar_conteudo_sintetico"] = metadata.get(
                    "divulgar_conteudo_sintetico", True
                )
            languages[lang] = entry

        thumbnail = ctx.store.path("metadados", "thumbnail.png")
        if thumbnail.exists():
            package["thumbnail"] = str(thumbnail.relative_to(ctx.store.root))

        report = ctx.store.path("roteiro", "relatorio_fatos.final.json")
        if report.exists():
            package["relatorio_fatos"] = str(report.relative_to(ctx.store.root))

        approval = ctx.store.path("revisao", "aprovacao.json")
        if approval.exists():
            package["aprovacao"] = json.loads(approval.read_text(encoding="utf-8"))

        package["custo_usd"] = round(ctx.costs.spent_on_video(ctx.video_id), 4)

        ctx.store.write_json("entrega", "pacote.json", package, step="entregue")
        ctx.store.write_text(
            "entrega", "CHECKLIST.md", self._checklist(ctx, package), step="entregue"
        )

        delivered = [lang for lang, entry in languages.items() if entry]
        return StepResult.done(
            summary=f"pacote pronto para upload manual ({', '.join(delivered)})",
            idiomas=delivered,
            custo_usd=package["custo_usd"],
        )

    @staticmethod
    def _checklist(ctx: StepContext, package: dict[str, Any]) -> str:
        lines = [
            f"# Checklist de publicacao — {ctx.video_id}",
            "",
            f"**Tema:** {ctx.topic}",
            f"**Custo total desta producao:** US$ {package.get('custo_usd', 0):.4f}",
            "",
            "O upload no YouTube e manual. Percorra a lista por canal.",
            "",
        ]
        for lang, label in (("pt-br", "Canal PT-BR"), ("en", "Canal EN")):
            entry = package.get("idiomas", {}).get(lang) or {}
            if not entry:
                continue
            lines += [
                f"## {label}",
                "",
                f"- [ ] Subir `{entry.get('video', '(video ausente)')}`",
                f"- [ ] Titulo: `{entry.get('titulo', '')}`",
                "- [ ] Colar a descricao de `metadados/metadados."
                + lang
                + ".json` (inclui as fontes)",
                f"- [ ] Tags ({len(entry.get('tags') or [])} itens)",
                f"- [ ] Capitulos ({len(entry.get('capitulos') or [])} itens, o primeiro em 00:00)",
                f"- [ ] Subir legendas `{entry.get('legendas', '(ausente)')}`",
                "- [ ] Subir thumbnail `"
                + str(package.get("thumbnail", "(ausente)"))
                + "` com o texto aplicado",
            ]
            if entry.get("divulgar_conteudo_sintetico", True):
                lines.append(
                    "- [ ] **Marcar 'conteudo alterado ou sintetico'** no formulario do YouTube"
                )
            lines += [
                "- [ ] Conferir que o video esta como 'nao feito para criancas'",
                "- [ ] Publicar",
                "",
            ]
        lines += [
            "## Depois de publicar",
            "",
            "- [ ] Anotar a retencao aos 7 dias (criterio de sucesso: acima de 35%)",
            "- [ ] Registrar o desempenho para a decisao de escalar de 2 para 5 canais",
            "",
        ]
        return "\n".join(lines)
