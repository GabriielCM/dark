"""Etapa 6: narracao e legendas.

TTS nos dois idiomas e alinhamento local para gerar os timestamps e os SRTs
(brief 6.3: um arquivo por idioma).

A narracao e sintetizada frase a frase (text/segment.py), com uma pausa curta
entre frases e uma maior entre blocos. O provedor que segmenta (Kokoro)
devolve o tempo exato de cada frase; esses tempos ancoram as cenas na
montagem. O Whisper so da o tempo das palavras dentro de cada frase, e a
legenda sai com o texto do roteiro, nao com o que o Whisper entendeu.

Com a faixa unica (ADR 0011), a sintese grava `natural.<idioma>.wav`, e os
dois `narracao.<idioma>.wav` saem na mesma linha do tempo
(text/shared_timeline.py): cada bloco com a duracao da narracao mais longa, e
pausas maiores no idioma mais curto. O alinhamento roda sobre esse audio, entao
legendas e tempos ja nascem na linha unica.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config import ChannelConfig
from ...errors import PermanentError
from ...providers.align import AlignmentResult, WordTiming
from ...providers.tts import SpeechRequest
from ...text.align_script import align_units, unit_spans
from ...text.normalize_pt import normalize_for_speech
from ...text.segment import Unit, segment_script, units_from_json, units_to_json
from ...text.shared_timeline import (
    Sentence,
    block_spans,
    place,
    relay_wav,
    shared_timeline,
    stretch,
    wav_duration,
)
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step

SENTENCE_PAUSE_S = 0.25
BLOCK_PAUSE_S = 0.8

#  Um idioma pronto para alinhar: canal, roteiro, frases, audio e tempo de cada frase.
Voiced = tuple[ChannelConfig, dict[str, Any], list[Unit], Path, dict[str, tuple[float, float]]]


def load_units(ctx: StepContext, lang: str) -> list[Unit]:
    """Frases do roteiro de um idioma: as gravadas pelo gate/adaptacao, ou recalculadas."""
    if lang == "pt-br":
        stage, units_file, script_file, prefix = (
            "roteiro",
            "frases.pt-br.json",
            "roteiro.aprovado.json",
            "p",
        )
        channel = ctx.channel_pt
    else:
        stage, units_file, script_file, prefix = (
            "adaptacao",
            "frases.en.json",
            "roteiro.en.json",
            "e",
        )
        channel = ctx.channel_en
    if ctx.store.path(stage, units_file).exists():
        return units_from_json(ctx.store.read_json(stage, units_file))
    return segment_script(
        ctx.store.read_json(stage, script_file),
        prefix=prefix,
        language=channel.language,
        words_per_minute=channel.wpm,
    )  # fmt: skip


class NarracaoStep(Step):
    name = StepName.NARRACAO

    def outputs(self, ctx: StepContext) -> list[Path]:
        out: list[Path] = []
        for lang in ("pt-br", "en"):
            if ctx.settings.narration.single_track:
                out.append(ctx.store.path("narracao", f"natural.{lang}.wav"))
            out += [
                ctx.store.path("narracao", f"narracao.{lang}.wav"),
                ctx.store.path("narracao", f"legendas.{lang}.srt"),
                ctx.store.path("narracao", f"tempos.{lang}.json"),
            ]
        return out

    async def run(self, ctx: StepContext) -> StepResult:
        tts = ctx.providers.tts()
        aligner = ctx.providers.align()
        single = ctx.settings.narration.single_track
        summary: dict[str, dict[str, float]] = {}

        voiced: list[Voiced] = []
        for channel, script_stage, script_file in (
            (ctx.channel_pt, "roteiro", "roteiro.aprovado.json"),
            (ctx.channel_en, "adaptacao", "roteiro.en.json"),
        ):
            lang = channel.id
            script = ctx.store.read_json(script_stage, script_file)
            units = load_units(ctx, lang)
            if not units:
                raise ValueError(f"roteiro {lang} sem narracao")

            name = f"natural.{lang}.wav" if single else f"narracao.{lang}.wav"
            audio_path = ctx.store.path("narracao", name)
            unit_times = await self._synthesize(ctx, tts, channel, units, audio_path)
            voiced.append((channel, script, units, audio_path, unit_times))

        stretched: dict[str, dict[int, float]] = {}
        if single:
            voiced, stretched = self._lay_out(ctx, voiced)

        for channel, script, units, audio_path, unit_times in voiced:
            lang = channel.id
            text = " ".join(unit.text for unit in units)
            alignment = await aligner.align(
                audio_path,
                text,
                language=channel.language,
                step=self.name.value,
                video_id=ctx.video_id,
                step_run_id=ctx.step_run_id,
            )
            tokens = align_units(units, alignment.words, unit_times or None)
            if not unit_times:
                unit_times = unit_spans(tokens)

            subtitles = AlignmentResult(
                words=tuple(WordTiming(t.text, t.start, t.end) for t in tokens),
                duration_s=alignment.duration_s,
                provider=alignment.provider,
                model=alignment.model,
            )
            srt_path = ctx.store.write_text(
                "narracao",
                f"legendas.{lang}.srt",
                subtitles.to_srt(),
                step="narracao",
                provider=alignment.provider,
                model=alignment.model,
                extra={"palavras": len(tokens), "texto": "roteiro"},
            )
            #  Faixa de cada frase em `palavras`: uma palavra por token do texto,
            #  na ordem (align_units). E o que ancora um corte no meio da frase.
            word_ranges: dict[str, tuple[int, int]] = {}
            cursor = 0
            for u in units:
                word_ranges[u.id] = (cursor, cursor + u.words)
                cursor += u.words
            ctx.store.write_json(
                "narracao",
                f"tempos.{lang}.json",
                {
                    "duracao_s": round(alignment.duration_s, 3),
                    "palavras": [{"p": t.text, "i": t.start, "f": t.end} for t in tokens],
                    "frases": [
                        {
                            "id": u.id,
                            "bloco": u.block,
                            "inicio": unit_times[u.id][0],
                            "fim": unit_times[u.id][1],
                            "palavras": list(word_ranges[u.id]),
                        }
                        for u in units
                        if u.id in unit_times
                    ],
                    "blocos": self._block_timings(script, units, unit_times),
                },
                step="narracao",
                provider=alignment.provider,
                model=alignment.model,
            )
            summary[lang] = {
                "duracao_min": round(alignment.duration_s / 60, 2),
                "frases": len(units),
                "legendas": srt_path.stat().st_size,
            }

        durations = ", ".join(f"{k}: {v['duracao_min']} min" for k, v in summary.items())
        message = f"narracao pronta ({durations})"
        limit = ctx.settings.narration.stretch_warning
        warnings = [
            f"{lang} bloco {block + 1} +{value * 100:.0f}%"
            for lang, blocks in stretched.items()
            for block, value in blocks.items()
            if value > limit
        ]
        if single:
            message = f"narracao pronta na linha unica ({durations})"
        if warnings:
            #  Nao bloqueia: o revisor ouve no corte final. Pausa longa demais
            #  pede adaptacao EN mais curta (refazer adaptacao_en) ou PT.
            message += f" — pausas maiores em {'; '.join(warnings)}"
        return StepResult.done(
            summary=message,
            esticamento={k: {str(b): v for b, v in d.items()} for k, d in stretched.items()},
            **summary,
        )

    def _lay_out(
        self,
        ctx: StepContext,
        voiced: list[Voiced],
    ) -> tuple[
        list[Voiced],
        dict[str, dict[int, float]],
    ]:
        """Poe as duas narracoes naturais na mesma linha do tempo (ADR 0011)."""
        sentences: dict[str, list[Sentence]] = {}
        spans: dict[str, dict[int, tuple[float, float]]] = {}
        for channel, _script, units, natural, unit_times in voiced:
            if not unit_times:
                raise PermanentError(
                    "a faixa unica precisa do tempo de cada frase na sintese, e este "
                    "provedor de voz nao devolve: use o Kokoro ou desligue "
                    "narracao.faixa_unica no app.yaml"
                )
            sentences[channel.id] = [Sentence(u.id, u.block, *unit_times[u.id]) for u in units]
            spans[channel.id] = block_spans(sentences[channel.id], wav_duration(natural))

        line = shared_timeline(*spans.values())
        laid: list[Voiced] = []
        stretched: dict[str, dict[int, float]] = {}
        for channel, script, units, natural, _times in voiced:
            lang = channel.id
            placed = place(sentences[lang], spans[lang], line)
            final = ctx.store.path("narracao", f"narracao.{lang}.wav")
            relay_wav(
                natural,
                final,
                [(s.start, s.end, placed[s.id][0]) for s in sentences[lang]],
                line.total,
            )
            stretched[lang] = stretch(spans[lang], line)
            ctx.store.write_sidecar(
                final,
                step="narracao",
                provider="local",
                model="linha-unica",
                extra={
                    "origem": natural.name,
                    "duracao_s": line.total,
                    "esticamento": {str(b): v for b, v in stretched[lang].items()},
                    "frases": {k: list(v) for k, v in placed.items()},
                },
            )
            laid.append((channel, script, units, final, placed))
        return laid, stretched

    async def _synthesize(
        self,
        ctx: StepContext,
        tts: Any,
        channel: ChannelConfig,
        units: list[Unit],
        audio_path: Path,
    ) -> dict[str, tuple[float, float]]:
        """Sintetiza o audio (se ainda nao existe) e devolve o tempo de cada frase."""
        if ctx.store.is_complete(audio_path):
            sidecar = ctx.store.read_sidecar(audio_path)
            saved = (sidecar.extra.get("frases") if sidecar else None) or {}
            return {k: (float(v[0]), float(v[1])) for k, v in saved.items()}

        voice = channel.voice
        rules = voice.get("normalizacoes") or [] if channel.language.startswith("pt") else []
        spoken = [
            normalize_for_speech(u.text, rules) if channel.language.startswith("pt") else u.text
            for u in units
        ]
        sentence_pause = float(voice.get("pausa_frase_s", SENTENCE_PAUSE_S))
        block_pause = float(voice.get("pausa_bloco_s", BLOCK_PAUSE_S))
        pauses = [
            block_pause
            if index + 1 == len(units) or units[index + 1].block != unit.block
            else sentence_pause
            for index, unit in enumerate(units)
        ]
        speech = await tts.synthesize(
            SpeechRequest(
                text=" ".join(spoken),
                voice_id=str(voice.get("voice_id", "")),
                language=channel.language,
                speed=float(voice.get("velocidade", 1.0)),
                segments=tuple(spoken),
                pauses=tuple(pauses),
            ),
            audio_path,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
        )
        unit_times = (
            {u.id: times for u, times in zip(units, speech.segment_times, strict=True)}
            if speech.segment_times
            else {}
        )
        ctx.store.write_sidecar(
            audio_path,
            step="narracao",
            provider=speech.provider,
            model=speech.model,
            extra={
                "voz": speech.voice_id,
                "caracteres": speech.characters,
                "idioma": channel.language,
                "frases": {k: list(v) for k, v in unit_times.items()},
            },
        )
        #  As frases vao junto do audio: e o mapa que ancora cenas e legendas.
        ctx.store.write_json(
            "narracao",
            f"frases.{channel.id}.json",
            units_to_json(units),
            step="narracao",
        )
        return unit_times

    @staticmethod
    def _block_timings(
        script: dict[str, Any], units: list[Unit], unit_times: dict[str, tuple[float, float]]
    ) -> list[dict[str, Any]]:
        """Onde cada bloco do roteiro comeca e termina no audio (para capitulos)."""
        blocks: list[dict[str, Any]] = []
        raw_blocks = script.get("blocos", [])
        for index, block in enumerate(raw_blocks):
            spans = [unit_times[u.id] for u in units if u.block == index and u.id in unit_times]
            if not spans:
                continue
            blocks.append(
                {
                    "indice": index,
                    "secao": block.get("secao"),
                    "titulo": block.get("titulo"),
                    "inicio_s": round(spans[0][0], 3),
                    "fim_s": round(spans[-1][1], 3),
                    "palavras": len(str(block.get("narracao", "")).split()),
                }
            )
        return blocks
