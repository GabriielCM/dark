"""Etapa 15: cortes verticais para o TikTok (ADR 0010).

Por video, cortes de cerca de 1 min e meio, feitos das mesmas cenas do video
inteiro. Desde 06/10/2026, cada conta tem trechos proprios: a conta EN nao
posta as imagens que a PT ja postou. A quantidade de cada conta vem do canal
(`tiktok.cortes`); desde 08/10/2026 a conta EN esta parada (0), porque o
TikTok mostrava os cortes em ingles quase so no Brasil, e a PT posta 6.

1. `clips/candidates.py` mede os trechos que cabem na duracao: frases
   inteiras, dentro de um bloco, no idioma das contas que postam. Grava
   `candidatos.json`, sem custo.
2. O LLM barato escolhe entre eles, para cada conta, e escreve o gancho na
   tela, a legenda do post e as hashtags (prompts/cortes/selecao.v3.md). A resposta fica em
   `llm.json`: a retomada nao paga de novo.
3. `clips/selection.py` confere a escolha e grava `selecao.json`. E esse o
   arquivo que a sessao muda para atender um comentario do corte final
   (`mundoantigo cortes editar`), sem chamar o LLM de novo.
4. Cada corte vira props verticais (render/clips.py), um trecho do WAV e um
   mp4: `corte-<n>.<idioma>.mp4`.

Video sem nenhum trecho que caiba (o video-exemplo de 60 s) termina sem cortes
e com aviso, sem chamar o LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...clips import Candidate, ClipsConfig, Selection, SelectionError, candidates
from ...clips.selection import validate_selection
from ...config import ChannelConfig
from ...errors import TransientError
from ...render import RemotionRenderer, props_from_storyboard
from ...render.clips import clip_props, slice_wav
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step

STAGE = "cortes"
LANGS = ("pt-br", "en")
#  Como o prompt chama cada conta.
ACCOUNT_NAMES = {"pt-br": "PT", "en": "EN"}
SELECTION = "selecao.json"
CANDIDATES = "candidatos.json"
LLM_CACHE = "llm.json"


def clip_video(ctx: StepContext, number: int, lang: str) -> Path:
    return ctx.store.path(STAGE, f"corte-{number}.{lang}.mp4")


def clip_props_file(ctx: StepContext, number: int, lang: str) -> Path:
    return ctx.store.path(STAGE, f"props.{lang}.{number}.json")


def clip_audio(ctx: StepContext, number: int, lang: str) -> Path:
    return ctx.store.path(STAGE, f"narracao.{lang}.{number}.wav")


def render_files(ctx: StepContext, number: int) -> list[Path]:
    """O que um corte deixa no disco depois do render, nos dois idiomas."""
    return [
        path
        for lang in LANGS
        for path in (
            clip_video(ctx, number, lang),
            clip_props_file(ctx, number, lang),
            clip_audio(ctx, number, lang),
        )
    ]


def load_selection(ctx: StepContext) -> Selection | None:
    path = ctx.store.path(STAGE, SELECTION)
    if not ctx.store.is_complete(path):
        return None
    return Selection.from_dict(ctx.store.read_json(STAGE, SELECTION))


def end_text(channel: ChannelConfig) -> str:
    return str((channel.tiktok.get("textos") or {}).get("fim") or "")


def posts_full_video(channel: ChannelConfig) -> bool:
    """A conta deste canal posta o video inteiro? (`tiktok.video_inteiro`)"""
    return bool(channel.tiktok.get("video_inteiro", True))


def clips_per_account(channel: ChannelConfig, config: ClipsConfig) -> int:
    """Quantos cortes a conta deste canal posta por video (`tiktok.cortes`).

    Sem o campo, vale `cortes.quantidade` do app.yaml. Com 0, a conta so posta
    o video inteiro, se `video_inteiro` estiver ligado.
    """
    return max(int(channel.tiktok.get("cortes", config.count)), 0)


def posts_on_tiktok(channel: ChannelConfig, config: ClipsConfig) -> bool:
    """A conta deste canal posta alguma coisa? Uma conta parada nao entra na entrega."""
    return clips_per_account(channel, config) > 0 or posts_full_video(channel)


def account_counts(ctx: StepContext, config: ClipsConfig) -> dict[str, int]:
    """A quantidade de cortes de cada conta, por idioma."""
    return {channel.id: clips_per_account(channel, config) for channel in ctx.channels()}


class CortesStep(Step):
    name = StepName.CORTES

    def outputs(self, ctx: StepContext) -> list[Path]:
        selection = load_selection(ctx)
        if selection is None:
            counts = account_counts(ctx, ClipsConfig.from_app(ctx.settings.app))
            expected = [(n, lang) for lang, count in counts.items() for n in range(1, count + 1)]
        else:
            expected = [(clip.number, lang) for clip in selection.clips for lang in clip.langs]
        return [
            ctx.store.path(STAGE, SELECTION),
            *(clip_video(ctx, n, lang) for n, lang in expected),
        ]

    def invalidate(self, ctx: StepContext, *, keep_paid: bool = False) -> list[Path]:
        """Refazer os cortes do zero apaga a escolha paga junto.

        Com `keep_paid` (uma imagem refeita) so os renders saem: o trecho, o
        gancho e a legenda continuam valendo.
        """
        stage = ctx.store.root / STAGE
        if not stage.is_dir():
            return []
        keep = {SELECTION, CANDIDATES, LLM_CACHE} if keep_paid else set()
        removed: list[Path] = []
        for path in sorted(stage.iterdir()):
            if path.name.endswith(".meta.json") or path.name in keep:
                continue
            if ctx.store.delete(path):
                removed.append(path)
        return removed

    async def run(self, ctx: StepContext) -> StepResult:
        config = ClipsConfig.from_app(ctx.settings.app)
        storyboard = ctx.store.read_json("cenas", "storyboard.json")
        timings = {lang: ctx.store.read_json("narracao", f"tempos.{lang}.json") for lang in LANGS}
        counts = account_counts(ctx, config)
        active = tuple(lang for lang in LANGS if counts.get(lang, 0) > 0)

        selection = load_selection(ctx)
        if selection is None:
            found = candidates(storyboard, timings, config, active) if active else []
            ctx.store.write_json(
                STAGE,
                CANDIDATES,
                {"candidatos": [c.to_dict() for c in found]},
                step=self.name.value,
            )
            if not active:
                selection = Selection(
                    clips=[], warnings=["nenhuma conta posta cortes (`tiktok.cortes`)"]
                )
            elif not found:
                low, high = config.pt_range
                selection = Selection(
                    clips=[],
                    warnings=[
                        f"nenhum trecho de {low:.0f} a {high:.0f} s dentro de um bloco: "
                        "o video sai sem cortes"
                    ],
                )
            else:
                selection = await self._select(ctx, config, found, counts)
            ctx.store.write_json(STAGE, SELECTION, selection.to_dict(), step=self.name.value)

        if not selection.clips:
            return StepResult.done(
                summary="; ".join(selection.warnings) or "sem cortes",
                cortes=0,
                avisos=selection.warnings,
            )

        renderer = RemotionRenderer(ctx.settings.render)
        prepared = self._prepare(ctx, renderer, config, storyboard, timings, selection)
        available, reason = renderer.is_available()
        if not available:
            return StepResult.blocked(
                f"props dos cortes geradas, mas o Remotion nao pode rodar: {reason}",
                props=[str(p) for _, _, _, p in prepared],
            )

        rendered = 0
        for number, lang, props, props_file in prepared:
            output = clip_video(ctx, number, lang)
            if ctx.store.is_complete(output):
                continue
            result = await renderer.render(props, props_file, output, public_dir=ctx.store.root)
            clip = selection.clip(number)
            span = clip.candidate.span(lang)
            ctx.store.write_sidecar(
                output,
                step=self.name.value,
                provider="remotion",
                model=f"{config.width}x{config.height}@{ctx.settings.render.fps}",
                extra={
                    "idioma": lang,
                    "corte": number,
                    "candidato": clip.candidate.id,
                    "inicio_s": span.start,
                    "fim_s": span.end,
                    "duracao_s": props.durationInSeconds,
                    "render_s": round(result.duration_s, 1),
                },
            )
            rendered += 1

        summary = f"{len(selection.clips)} corte(s): " + ", ".join(
            f"{len(selection.for_lang(lang))} {lang}" for lang in LANGS
        )
        if selection.warnings:
            summary += f"; {len(selection.warnings)} aviso(s)"
        return StepResult.done(
            summary=summary,
            cortes=len(selection.clips),
            renderizados=rendered,
            avisos=selection.warnings,
        )

    # -- escolha pelo LLM ----------------------------------------------------

    async def _select(
        self,
        ctx: StepContext,
        config: ClipsConfig,
        found: list[Candidate],
        counts: dict[str, int],
    ) -> Selection:
        channels = ctx.channels()
        fixed = {ch.id: ch.tiktok.get("hashtag_fixa") for ch in channels}
        full_langs = tuple(ch.id for ch in channels if posts_full_video(ch))
        raw = await self._written(ctx, config, found, fixed, full_langs, counts)
        try:
            return validate_selection(raw, found, config, fixed, full_langs, counts=counts)
        except SelectionError as exc:
            #  A resposta nao serve: na retomada, o LLM e chamado de novo.
            ctx.store.delete(ctx.store.path(STAGE, LLM_CACHE))
            raise TransientError(f"cortes: {exc}") from exc

    async def _written(
        self,
        ctx: StepContext,
        config: ClipsConfig,
        found: list[Candidate],
        fixed: dict[str, str | None],
        full_langs: tuple[str, ...],
        counts: dict[str, int],
    ) -> Any:
        cache = ctx.store.path(STAGE, LLM_CACHE)
        if ctx.store.is_complete(cache):
            return ctx.store.read_json(STAGE, LLM_CACHE)

        prompt_obj = ctx.prompts.get("cortes/selecao")
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        feedback = self._feedback(ctx)
        active = tuple(lang for lang in LANGS if counts.get(lang, 0) > 0)
        rendered = prompt_obj.render(
            contas=self._accounts_rule(counts),
            titulo_pt=self._title(ctx, "pt-br"),
            titulo_en=self._title(ctx, "en"),
            candidatos=self._candidates_text(ctx, found, active),
            gancho_max_palavras=config.hook_max_words,
            hashtag_pt=fixed.get("pt-br") or "(nenhuma)",
            hashtag_en=fixed.get("en") or "(nenhuma)",
            hashtags_min=config.hashtags_min,
            hashtags_max=config.hashtags_max,
            feedback_revisor=feedback or "(nenhum)",
            video_inteiro=self._full_video_rule(full_langs, counts),
        )
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.6,
        )
        raw = response.json()
        ctx.store.write_json(
            STAGE,
            LLM_CACHE,
            raw,
            step=self.name.value,
            provider=llm.name,
            model=llm.model,
            prompt_ref=prompt_obj.ref,
            extra={"feedback_revisor": feedback} if feedback else {},
        )
        return raw

    @staticmethod
    def _accounts_rule(counts: dict[str, int]) -> str:
        """Quantos cortes cada conta posta, em linhas para o prompt.

        O ensaio (providers/llm/demo.py) le as linhas `- PT: 6 cortes.`.
        """
        lines = [
            f"- {ACCOUNT_NAMES[lang]}: {counts[lang]} cortes."
            if counts.get(lang, 0) > 0
            else f"- {ACCOUNT_NAMES[lang]}: parada. Não escolha nada para ela."
            for lang in LANGS
        ]
        if sum(1 for lang in LANGS if counts.get(lang, 0) > 0) > 1:
            lines += [
                "",
                "As contas usam as mesmas imagens. Para o TikTok não tratar uma como cópia "
                "da outra, **as contas nunca postam o mesmo trecho**: divida os trechos "
                "fortes entre elas.",
            ]
        return "\n".join(lines)

    @staticmethod
    def _full_video_rule(full_langs: tuple[str, ...], counts: dict[str, int]) -> str:
        """Quem posta o video inteiro, em uma frase para o prompt."""
        posting = [ACCOUNT_NAMES[lang] for lang in full_langs]
        if not posting:
            return "Nenhuma conta posta o vídeo inteiro: deixe `video_inteiro` vazio."
        others = [
            ACCOUNT_NAMES[lang]
            for lang in LANGS
            if lang not in full_langs and counts.get(lang, 0) > 0
        ]
        rule = f"O vídeo inteiro fica fixado no perfil da conta {' e '.join(posting)}"
        if others:
            rule += (
                f"; a conta {' e '.join(others)} posta só os cortes, que mandam para o "
                "documentário no YouTube"
            )
        return (
            f"{rule}. Escreva a legenda e as hashtags do vídeo inteiro só em: "
            f"{', '.join(p.lower() for p in posting)}."
        )

    @staticmethod
    def _title(ctx: StepContext, lang: str) -> str:
        """O titulo do YouTube, se os metadados ja sairam; senao, o de trabalho."""
        path = ctx.store.path("metadados", f"metadados.{lang}.json")
        if path.exists():
            title = ctx.store.read_json("metadados", f"metadados.{lang}.json").get("titulo")
            if title:
                return str(title)
        stage, name = (
            ("roteiro", "roteiro.aprovado.json")
            if lang == "pt-br"
            else (
                "adaptacao",
                "roteiro.en.json",
            )
        )
        if ctx.store.path(stage, name).exists():
            return str(ctx.store.read_json(stage, name).get("titulo_provisorio") or ctx.topic)
        return ctx.topic

    @staticmethod
    def _candidates_text(
        ctx: StepContext, found: list[Candidate], langs: tuple[str, ...] = LANGS
    ) -> str:
        """Os candidatos com a duracao e o texto so nos idiomas das contas que postam."""
        texts: dict[str, dict[str, str]] = {}
        for lang in langs:
            path = ctx.store.path("narracao", f"frases.{lang}.json")
            items = ctx.store.read_json("narracao", f"frases.{lang}.json") if path.exists() else []
            texts[lang] = {str(f["id"]): str(f.get("texto") or "") for f in items}
        order = {lang: list(texts[lang]) for lang in langs}

        def excerpt(candidate: Candidate, lang: str) -> str:
            span = candidate.span(lang)
            ids = order[lang]
            if span.first not in ids or span.last not in ids:
                return "(texto indisponivel)"
            chunk = ids[ids.index(span.first) : ids.index(span.last) + 1]
            return " ".join(texts[lang][i] for i in chunk)

        blocks = []
        for c in found:
            durations = " · ".join(
                f"{ACCOUNT_NAMES[lang]} {c.span(lang).duration:.0f} s" for lang in langs
            )
            lines = [f'### {c.id} · bloco {c.block} "{c.title}" · {durations}']
            lines += [f"{ACCOUNT_NAMES[lang]}: {excerpt(c, lang)}" for lang in langs]
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    @staticmethod
    def _feedback(ctx: StepContext) -> str | None:
        """O motivo da ultima rejeicao que pediu cortes novos."""
        path = ctx.store.path("revisao", "rejeicoes.json")
        if not path.exists():
            return None
        history = ctx.store.read_json("revisao", "rejeicoes.json")
        for entry in reversed(history if isinstance(history, list) else []):
            if StepName.CORTES.value in (entry.get("etapas") or []):
                return str(entry.get("motivo") or "") or None
        return None

    # -- props e audio -------------------------------------------------------

    def _prepare(
        self,
        ctx: StepContext,
        renderer: RemotionRenderer,
        config: ClipsConfig,
        storyboard: dict[str, Any],
        timings: dict[str, dict[str, Any]],
        selection: Selection,
    ) -> list[tuple[int, str, Any, Path]]:
        """Props e audio de cada corte, nos idiomas em que ele e postado, antes do render."""
        poses_index = ctx.store.path("assets", "mc/index.json")
        poses = (
            ctx.store.read_json("assets", "mc/index.json").get("poses", {})
            if poses_index.exists()
            else {}
        )
        prepared: list[tuple[int, str, Any, Path]] = []
        for channel in ctx.channels():
            lang = channel.id
            if not selection.for_lang(lang):
                continue
            full = props_from_storyboard(
                video_id=ctx.video_id,
                language=channel.language,
                title=self._title(ctx, lang),
                storyboard=storyboard,
                timings=timings[lang],
                narration_file=f"narracao/narracao.{lang}.wav",
                config=ctx.settings.render,
                palette=ctx.settings.style.palette,
                poses=poses,
                font_family=ctx.settings.render.font_family,
            )
            for clip in selection.for_lang(lang):
                span = clip.candidate.span(lang)
                #  Recortado sempre: leva milissegundos, e um trecho trocado
                #  pela sessao nao pode tocar o audio do trecho antigo.
                audio = slice_wav(
                    ctx.store.path("narracao", f"narracao.{lang}.wav"),
                    clip_audio(ctx, clip.number, lang),
                    span.start,
                    span.end,
                )
                props = clip_props(
                    full,
                    start=span.start,
                    end=span.end,
                    narration_file=audio.relative_to(ctx.store.root).as_posix(),
                    hook=clip.hook[lang],
                    end_text=end_text(channel),
                    width=config.width,
                    height=config.height,
                    hook_s=config.hook_s,
                    end_s=config.end_s,
                )
                #  As props ficam no disco mesmo sem Remotion: os comentarios do
                #  corte final acham a cena de cada momento por elas.
                props_file = renderer.write_props(props, clip_props_file(ctx, clip.number, lang))
                prepared.append((clip.number, lang, props, props_file))
        return prepared
