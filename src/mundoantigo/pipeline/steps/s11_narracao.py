"""Etapa 11: narracao e legendas.

TTS nos dois idiomas e alinhamento local para gerar os timestamps e os SRTs
(brief 6.3: um arquivo por idioma).

Os timestamps tambem realimentam o storyboard: a duracao real da narracao e o
que manda no corte, nao a estimativa da etapa 6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...providers.tts import SpeechRequest
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class NarracaoStep(Step):
    name = StepName.NARRACAO

    def outputs(self, ctx: StepContext) -> list[Path]:
        out: list[Path] = []
        for lang in ("pt-br", "en"):
            out += [
                ctx.store.path("narracao", f"narracao.{lang}.wav"),
                ctx.store.path("narracao", f"legendas.{lang}.srt"),
                ctx.store.path("narracao", f"tempos.{lang}.json"),
            ]
        return out

    async def run(self, ctx: StepContext) -> StepResult:
        tts = ctx.providers.tts()
        aligner = ctx.providers.align()
        summary: dict[str, dict[str, float]] = {}

        for channel, script_stage, script_file in (
            (ctx.channel_pt, "roteiro", "roteiro.aprovado.json"),
            (ctx.channel_en, "adaptacao", "roteiro.en.json"),
        ):
            script = ctx.store.read_json(script_stage, script_file)
            text = self._narration_text(script)
            lang = channel.id

            audio_path = ctx.store.path("narracao", f"narracao.{lang}.wav")
            if not ctx.store.is_complete(audio_path):
                speech = await tts.synthesize(
                    SpeechRequest(
                        text=text,
                        voice_id=str(channel.voice.get("voice_id", "")),
                        language=channel.language,
                        speed=float(channel.voice.get("velocidade", 1.0)),
                    ),
                    audio_path,
                    step=self.name.value,
                    video_id=ctx.video_id,
                    step_run_id=ctx.step_run_id,
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
                    },
                )

            alignment = await aligner.align(
                audio_path,
                text,
                language=channel.language,
                step=self.name.value,
                video_id=ctx.video_id,
                step_run_id=ctx.step_run_id,
            )

            srt_path = ctx.store.write_text(
                "narracao",
                f"legendas.{lang}.srt",
                alignment.to_srt(),
                step="narracao",
                provider=alignment.provider,
                model=alignment.model,
                extra={"palavras": len(alignment.words)},
            )
            ctx.store.write_json(
                "narracao",
                f"tempos.{lang}.json",
                {
                    "duracao_s": round(alignment.duration_s, 3),
                    "palavras": [
                        {"p": w.word, "i": round(w.start, 3), "f": round(w.end, 3)}
                        for w in alignment.words
                    ],
                    "blocos": self._block_timings(script, alignment),
                },
                step="narracao",
                provider=alignment.provider,
                model=alignment.model,
            )
            summary[lang] = {
                "duracao_min": round(alignment.duration_s / 60, 2),
                "palavras": len(alignment.words),
                "legendas": srt_path.stat().st_size,
            }

        durations = ", ".join(f"{k}: {v['duracao_min']} min" for k, v in summary.items())
        return StepResult.done(summary=f"narracao pronta ({durations})", **summary)

    @staticmethod
    def _narration_text(script: dict[str, Any]) -> str:
        return "\n\n".join(
            str(b.get("narracao", "")).strip()
            for b in script.get("blocos", [])
            if str(b.get("narracao", "")).strip()
        )

    @staticmethod
    def _block_timings(script: dict[str, Any], alignment: object) -> list[dict[str, Any]]:
        """Onde cada bloco do roteiro comeca e termina no audio.

        Feito por contagem de palavras: o alinhador devolve a sequencia na
        mesma ordem do texto enviado, entao a fronteira de um bloco e a
        n-esima palavra. Barato e suficiente para posicionar as cenas.
        """
        words = getattr(alignment, "words", ())
        blocks: list[dict[str, Any]] = []
        cursor = 0
        for index, block in enumerate(script.get("blocos", [])):
            count = len(str(block.get("narracao", "")).split())
            if count == 0:
                continue
            start_word = words[cursor] if cursor < len(words) else None
            end_index = min(cursor + count - 1, len(words) - 1)
            end_word = words[end_index] if end_index >= 0 and words else None
            blocks.append(
                {
                    "indice": index,
                    "secao": block.get("secao"),
                    "inicio_s": round(getattr(start_word, "start", 0.0), 3),
                    "fim_s": round(getattr(end_word, "end", 0.0), 3),
                    "palavras": count,
                }
            )
            cursor += count
        return blocks
