"""Etapa 16: pacote de entrega (fase B8).

Reune tudo que o upload manual precisa (brief 7), uma pasta por idioma:

    entrega/
      pacote de entrega.txt   os dois idiomas, no formato do pacote antigo
      CHECKLIST.md            passo a passo do upload, com os avisos
      pacote.json             o mesmo conteudo, para maquina
      thumb-base.png          a arte sem texto, para ajuste manual
      pt-br/ e en/
        video.mp4             hard link do video da montagem
        faixa-en.m4a          so no pt-br, com a faixa unica (ADR 0011): o audio EN
        legendas.srt
        thumb-com-texto.jpg
        thumb-sem-texto.jpg
        publicacao.txt        titulo, descricao e tags prontos para colar
        comentario_fixado.txt so quando os creditos nao couberam na descricao
      tiktok/<idioma>/ (ADR 0010), so das contas que postam: a EN esta parada
        video-inteiro.mp4     hard link do video da montagem, fixado no perfil
        corte-1.mp4 ...       hard links dos cortes verticais
        tiktok.txt            legenda e hashtags de cada post, na ordem de postar

Os videos sao hard links: nao ocupam o disco duas vezes, e o backup pula os
mp4 porque os originais em `montagem/` e `cortes/` ja vao. O pipeline termina
aqui: o upload no YouTube e no TikTok e humano.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ...clips import ClipsConfig, Selection
from ...clips.selection import normalize_hashtag
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step
from .s09_assets import thumbnail_art
from .s13_metadados import thumb_with_text, thumb_without_text
from .s15_cortes import clip_video, load_selection, posts_full_video, posts_on_tiktok

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


def english_track(ctx: StepContext, destination: Path) -> str | None:
    """A faixa EN para o Studio (ADR 0011). Devolve um aviso se nao deu.

    Prefere o audio do video EN, que e a mixagem final (com a trilha, quando
    houver); sem ele, codifica a narracao EN, que ja esta na linha unica.
    """
    exe = shutil.which("ffmpeg")
    if not exe:
        return "faixa EN não gerada: ffmpeg não encontrado"
    base = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i"]
    attempts: list[list[str]] = []
    video = ctx.store.path("montagem", "video.en.mp4")
    if video.exists():
        attempts.append([*base, str(video), "-vn", "-c:a", "copy", str(destination)])
    narration = ctx.store.path("narracao", "narracao.en.wav")
    if narration.exists():
        attempts.append(
            [*base, str(narration), "-vn", "-c:a", "aac", "-b:a", "192k", str(destination)]
        )
    for command in attempts:
        done = subprocess.run(command, capture_output=True, check=False)
        if done.returncode == 0 and destination.exists() and destination.stat().st_size > 0:
            return None
    destination.unlink(missing_ok=True)
    return "faixa EN não gerada: sem vídeo nem narração EN legíveis"


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


def tiktok_caption(caption: str, closing: str, hashtags: list[str]) -> str:
    """A legenda do post do TikTok: texto, a linha fixa do canal e as hashtags."""
    parts = [caption.strip()]
    if closing:
        parts.append(closing.strip())
    text = "\n".join(p for p in parts if p)
    return f"{text}\n\n{' '.join(hashtags)}".strip() if hashtags else text


def tiktok_posts(
    selection: Selection | None,
    lang: str,
    *,
    title: str,
    fixed_hashtag: str | None,
    closing: str,
    full_video: bool = True,
) -> list[dict[str, Any]]:
    """Os posts de um idioma, na ordem de postar: o video inteiro e os cortes.

    O inteiro vai primeiro e fica fixado no perfil: os cortes mandam para ele.
    Producao sem selecao (anterior aos cortes) ainda posta o video inteiro.
    Conta sem o inteiro (`tiktok.video_inteiro: false`) posta so os cortes
    dela, que mandam para o YouTube.
    """
    full = (selection.full_video if selection else {}).get(lang) or {}
    fixed = normalize_hashtag(fixed_hashtag or "")
    posts: list[dict[str, Any]] = []
    if full_video:
        posts.append(
            {
                "arquivo": "video-inteiro.mp4",
                "tipo": "video inteiro",
                "legenda": tiktok_caption(
                    str(full.get("legenda") or title),
                    "",
                    list(full.get("hashtags") or ([fixed] if fixed else [])),
                ),
            }
        )
    for clip in selection.for_lang(lang) if selection else []:
        posts.append(
            {
                "arquivo": f"corte-{clip.number}.mp4",
                "tipo": f"corte {clip.number}",
                "gancho": clip.hook[lang],
                "duracao_s": clip.candidate.span(lang).duration,
                "legenda": tiktok_caption(clip.caption[lang], closing, clip.hashtags[lang]),
            }
        )
    return posts


def tiktok_text(label: str, posts: list[dict[str, Any]]) -> str:
    """O `tiktok.txt` de um idioma: um post por secao, na ordem de postar."""
    lines = [f"TikTok, {label}", ""]
    for n, post in enumerate(posts, start=1):
        pin = " (fixar no perfil)" if post["tipo"] == "video inteiro" else ""
        lines += [f"{n}. {post['arquivo']}{pin}", "", post["legenda"], "", "-" * 40, ""]
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

        single = ctx.settings.narration.single_track
        if single and "pt-br" in languages:
            track = folder / "pt-br" / "faixa-en.m4a"
            problem = english_track(ctx, track)
            entry = languages["pt-br"]
            if problem:
                entry["avisos"] = [*(entry.get("avisos") or []), problem]
            else:
                entry["faixa_en"] = relative(track)

        package: dict[str, Any] = {
            "video_id": ctx.video_id,
            "tema": ctx.topic,
            "faixa_unica": single,
            "idiomas": languages,
            "tiktok": self._tiktok(ctx, folder, languages),
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
    def _tiktok(
        ctx: StepContext, folder: Path, languages: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """A pasta `tiktok/<idioma>/`: o video inteiro, os cortes e as legendas.

        Conta parada (sem cortes e sem o inteiro) nao tem pasta: a de uma
        entrega anterior sai, para nada ser postado por engano.
        """
        selection = load_selection(ctx)
        config = ClipsConfig.from_app(ctx.settings.app)
        result: dict[str, Any] = {}
        for channel in ctx.channels():
            lang = channel.id
            target = folder / "tiktok" / lang
            if not posts_on_tiktok(channel, config):
                shutil.rmtree(target, ignore_errors=True)
                continue
            if lang not in languages:
                continue
            target.mkdir(parents=True, exist_ok=True)
            texts = channel.tiktok.get("textos") or {}
            posts = tiktok_posts(
                selection,
                lang,
                title=str(languages[lang].get("titulo") or ctx.topic),
                fixed_hashtag=channel.tiktok.get("hashtag_fixa"),
                closing=str(texts.get("legenda_fim") or ""),
                full_video=posts_full_video(channel),
            )
            sources = {"video-inteiro.mp4": ctx.store.path("montagem", f"video.{lang}.mp4")}
            for clip in selection.for_lang(lang) if selection else []:
                sources[f"corte-{clip.number}.mp4"] = clip_video(ctx, clip.number, lang)
            #  Um arquivo de antes da mudanca (o inteiro numa conta que deixou de
            #  posta-lo) nao fica na pasta para ser postado por engano.
            for stale in target.glob("*.mp4"):
                if stale.name not in {post["arquivo"] for post in posts}:
                    stale.unlink()
            available = []
            for post in posts:
                source = sources[post["arquivo"]]
                post["presente"] = source.exists()
                if source.exists():
                    link_or_copy(source, target / post["arquivo"])
                available.append(post)
            ctx.store.write_text(
                "entrega",
                f"tiktok/{lang}/tiktok.txt",
                tiktok_text(LANGUAGES.get(lang, lang), available),
                step="entregue",
            )
            result[lang] = {
                "pasta": _relative(ctx, target),
                "posts": available,
                "avisos": list(selection.warnings) if selection else [],
            }
        return result

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
        single = bool(package.get("faixa_unica"))
        for lang, entry in languages.items():
            folder = lang
            subtitles = SUBTITLE_LANGUAGE.get(lang, lang)
            if single and lang == "en":
                use = (
                    "para o TikTok EN e para quando o canal voltar"
                    if "en" in (package.get("tiktok") or {})
                    else "para quando o canal voltar"
                )
                lines += [
                    f"## {CHANNELS.get(lang, lang)} (parado, ADR 0011)",
                    "",
                    "O inglês sobe como faixa de áudio do vídeo PT (seção abaixo). O "
                    f"`en/video.mp4` fica {use}.",
                    "",
                ]
                continue
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
        if single and "pt-br" in languages:
            track = languages["pt-br"].get("faixa_en")
            lines += [
                "## Faixa em inglês no vídeo PT (ADR 0011)",
                "",
                "- [ ] Uma vez por canal: conferir os recursos avançados (Studio → Configurações "
                "→ Canal → Qualificação de recursos)",
                "- [ ] No vídeo PT: Studio → Idiomas → Adicionar idioma → Inglês",
                "- [ ] Áudio: subir `pt-br/faixa-en.m4a`"
                + ("" if track else " (**ausente**, ver Avisos)"),
                "- [ ] Título e descrição em inglês: os de `en/publicacao.txt`",
                f"- [ ] Legenda `en/legendas.srt`, idioma {SUBTITLE_LANGUAGE['en']}",
                "- [ ] Depois de 3 vídeos assim: comparar no Studio as views por idioma do áudio",
                "",
            ]
        for lang, entry in (package.get("tiktok") or {}).items():
            folder = f"tiktok/{lang}"
            lines += [
                f"## TikTok, {CHANNELS.get(lang, lang)}",
                "",
                "Conta pessoal (conta comercial não entra no Programa de Recompensas). Suba pelo",
                f"TikTok Studio no computador, na ordem do `{folder}/tiktok.txt`, que tem a",
                "legenda e as hashtags de cada post.",
                "",
            ]
            for post in entry.get("posts") or []:
                missing = "" if post.get("presente") else " (**ausente**)"
                if post["tipo"] == "video inteiro":
                    lines += [
                        f"- [ ] `{folder}/{post['arquivo']}`{missing}: ligar as legendas "
                        "automáticas e **fixar no perfil** depois de publicar",
                    ]
                else:
                    lines.append(
                        f"- [ ] `{folder}/{post['arquivo']}`{missing} "
                        f"({post.get('duracao_s', 0):.0f} s), agendar para os dias seguintes"
                    )
            if not any(p["tipo"] == "video inteiro" for p in entry.get("posts") or []):
                lines.append(
                    "- [ ] Uma vez por conta: link do documentário no YouTube na bio "
                    "(os cortes desta conta mandam para lá)"
                )
            lines += [
                '- [ ] Em cada post: marcar **"Conteúdo gerado por IA"**',
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
