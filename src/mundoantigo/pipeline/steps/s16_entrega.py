"""Etapa 16: pacote de entrega (fase B8).

Reune tudo que o upload manual precisa (brief 7), uma pasta por idioma:

    entrega/
      pacote de entrega.txt   os dois idiomas, no formato do pacote antigo
      CHECKLIST.md            passo a passo do upload, com os avisos
      pacote.json             o mesmo conteudo, para maquina
      thumb-base.png          a arte sem texto, para ajuste manual
      pt-br/ e en/
        video.mp4             hard link do video da montagem
        legendas.srt
        thumb-com-texto.jpg
        thumb-sem-texto.jpg
        publicacao.txt        titulo, descricao e tags prontos para colar
        comentario_fixado.txt so quando os creditos nao couberam na descricao

O video e um hard link: nao ocupa o disco duas vezes, e o backup pula o
`video.mp4` porque o original em `montagem/` ja vai. O pipeline termina aqui:
o upload no YouTube e humano.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step
from .s08_assets import thumbnail_art
from .s13_metadados import thumb_with_text, thumb_without_text

PACKAGE_TEXT = "pacote de entrega.txt"
LANGUAGES = {"pt-br": "português", "en": "inglês"}
CHANNELS = {"pt-br": "Canal PT-BR", "en": "Canal EN"}
SUBTITLE_LANGUAGE = {"pt-br": "Português (Brasil)", "en": "Inglês"}
SEPARATOR = "=" * 60


def _relative(ctx: StepContext, path: Path) -> str:
    return path.relative_to(ctx.store.root).as_posix()


def link_or_copy(source: Path, target: Path) -> None:
    """Hard link quando da (mesmo volume); senao, copia."""
    target.unlink(missing_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def publication_text(label: str, metadata: dict[str, Any]) -> str:
    """Um idioma do pacote: o que se cola no YouTube, na ordem do formulario."""
    lines = [label, "", "título", str(metadata.get("titulo") or ""), ""]
    alternatives = metadata.get("titulos_alternativos") or []
    if alternatives:
        lines += ["títulos alternativos (Testar e comparar)", *(f"- {t}" for t in alternatives), ""]
    lines += ["descrição", str(metadata.get("descricao") or ""), ""]
    lines += ["tags", ",".join(metadata.get("tags") or []), ""]
    thumb = (metadata.get("thumbnail") or {}).get("texto")
    if thumb:
        lines += ["texto da thumbnail", str(thumb), ""]
    pinned = metadata.get("comentario_fixado")
    if pinned:
        lines += ["comentário fixado", str(pinned), ""]
    return "\n".join(lines)


class EntregaStep(Step):
    name = StepName.ENTREGA

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [
            ctx.store.path("entrega", "pacote.json"),
            ctx.store.path("entrega", "CHECKLIST.md"),
            ctx.store.path("entrega", PACKAGE_TEXT),
        ]

    async def run(self, ctx: StepContext) -> StepResult:
        folder = ctx.store.stage("entrega")

        def relative(path: Path) -> str:
            return _relative(ctx, path)

        languages: dict[str, dict[str, Any]] = {}
        sections: list[str] = []

        for lang, label in LANGUAGES.items():
            meta_path = ctx.store.path("metadados", f"metadados.{lang}.json")
            if not meta_path.exists():
                continue
            metadata = ctx.store.read_json("metadados", f"metadados.{lang}.json")
            target = folder / lang
            target.mkdir(exist_ok=True)
            entry: dict[str, Any] = {"pasta": relative(target)}

            video = ctx.store.path("montagem", f"video.{lang}.mp4")
            if video.exists():
                link_or_copy(video, target / "video.mp4")
                entry["video"] = relative(target / "video.mp4")
                entry["tamanho_mb"] = round(video.stat().st_size / 1_048_576, 1)
            srt = ctx.store.path("narracao", f"legendas.{lang}.srt")
            if srt.exists():
                shutil.copy2(srt, target / "legendas.srt")
                entry["legendas"] = relative(target / "legendas.srt")
            thumbs: dict[str, str] = {}
            for key, source, name in (
                ("com_texto", thumb_with_text(ctx, lang), "thumb-com-texto.jpg"),
                ("sem_texto", thumb_without_text(ctx), "thumb-sem-texto.jpg"),
            ):
                if source.exists():
                    shutil.copy2(source, target / name)
                    thumbs[key] = relative(target / name)
            entry["thumbnails"] = thumbs

            text = publication_text(label, metadata)
            ctx.store.write_text("entrega", f"{lang}/publicacao.txt", text, step="entregue")
            entry["publicacao"] = relative(target / "publicacao.txt")
            pinned = target / "comentario_fixado.txt"
            if metadata.get("comentario_fixado"):
                pinned.write_text(str(metadata["comentario_fixado"]), encoding="utf-8")
                entry["comentario_fixado"] = relative(pinned)
            else:
                pinned.unlink(missing_ok=True)

            for key in (
                "titulo",
                "titulos_alternativos",
                "descricao",
                "tags",
                "capitulos",
                "creditos_imagens",
                "avisos",
            ):
                entry[key] = metadata.get(key)
            entry["divulgar_conteudo_sintetico"] = metadata.get("divulgar_conteudo_sintetico", True)
            languages[lang] = entry
            sections.append(text)

        package: dict[str, Any] = {
            "video_id": ctx.video_id,
            "tema": ctx.topic,
            "idiomas": languages,
        }
        art = thumbnail_art(ctx)
        if art.exists():
            shutil.copy2(art, folder / "thumb-base.png")
            package["thumbnail"] = relative(folder / "thumb-base.png")
        report = ctx.store.path("roteiro", "relatorio_fatos.final.json")
        if report.exists():
            package["relatorio_fatos"] = relative(report)
        approval = ctx.store.path("revisao", "aprovacao.json")
        if approval.exists():
            package["aprovacao"] = ctx.store.read_json("revisao", "aprovacao.json")
        package["custo_usd"] = round(ctx.costs.spent_on_video(ctx.video_id), 4)

        ctx.store.write_json("entrega", "pacote.json", package, step="entregue")
        ctx.store.write_text(
            "entrega", PACKAGE_TEXT, f"\n\n{SEPARATOR}\n\n".join(sections), step="entregue"
        )
        ctx.store.write_text(
            "entrega", "CHECKLIST.md", self._checklist(ctx, package), step="entregue"
        )

        delivered = [lang for lang, entry in languages.items() if entry.get("video")]
        return StepResult.done(
            summary=f"pacote pronto para upload manual ({', '.join(delivered) or 'sem videos'})",
            idiomas=delivered,
            custo_usd=package["custo_usd"],
        )

    @staticmethod
    def _checklist(ctx: StepContext, package: dict[str, Any]) -> str:
        languages = package.get("idiomas", {})
        lines = [
            f"# Checklist de publicação — {ctx.video_id}",
            "",
            f"**Tema:** {ctx.topic}",
            f"**Custo total desta produção:** US$ {package.get('custo_usd', 0):.4f}",
            "",
            "O upload no YouTube é manual. Cada pasta de idioma tem o vídeo, a legenda, as duas",
            "thumbs e o `publicacao.txt`, com título, descrição e tags prontos para colar.",
            "",
            "## Avisos",
            "",
        ]
        warnings = [
            f"- **{lang}:** {warning}"
            for lang, entry in languages.items()
            for warning in entry.get("avisos") or []
        ]
        lines += [*(warnings or ["Nenhum aviso."]), ""]

        category = ctx.channel_pt.publishing.get("categoria_youtube", "Education")
        for lang, entry in languages.items():
            folder = lang
            subtitles = SUBTITLE_LANGUAGE.get(lang, lang)
            lines += [
                f"## {CHANNELS.get(lang, lang)}",
                "",
                f"- [ ] Subir `{folder}/video.mp4`"
                + ("" if entry.get("video") else " (**ausente**)"),
                f"- [ ] Título: {entry.get('titulo', '')}",
                f"- [ ] Descrição de `{folder}/publicacao.txt` "
                "(capítulos, fontes, aviso e créditos já incluídos)",
                f"- [ ] Tags ({len(entry.get('tags') or [])} itens, também no `publicacao.txt`)",
                f"- [ ] Legenda `{folder}/legendas.srt`, idioma {subtitles}",
                f"- [ ] Thumbnail `{folder}/thumb-com-texto.jpg`",
                "- [ ] Testar e comparar: `thumb-com-texto.jpg`, `thumb-sem-texto.jpg` e os "
                f"títulos alternativos ({len(entry.get('titulos_alternativos') or [])})",
            ]
            if entry.get("comentario_fixado"):
                lines.append(
                    f"- [ ] Depois de publicar: comentar e fixar `{folder}/comentario_fixado.txt`"
                )
            if entry.get("divulgar_conteudo_sintetico", True):
                lines.append('- [ ] **Marcar "Conteúdo alterado ou sintético"** no formulário')
            lines += [
                '- [ ] Público: "Não, não é conteúdo para crianças"',
                f"- [ ] Categoria: {category}",
                "- [ ] Publicar",
                "",
            ]
        lines += [
            "## Depois de publicar",
            "",
            "- [ ] Anotar a retenção aos 7 dias (critério de sucesso: acima de 35%)",
            "- [ ] Registrar o desempenho para a decisão de escalar de 2 para 5 canais",
            "",
        ]
        return "\n".join(lines)
