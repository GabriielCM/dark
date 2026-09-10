"""Voz de mentira: WAV valido de silencio, com duracao proporcional ao texto."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from ...costs import Usage
from ..base import BaseProvider
from .base import SpeechRequest, SpeechResult

SAMPLE_RATE = 24_000
#  Aproxima 150 palavras por minuto com palavras de ~5 letras: ~13 chars/s.
CHARS_PER_SECOND = 13.0


def _silence_wav(seconds: float) -> bytes:
    frames = max(1, int(SAMPLE_RATE * seconds))
    data = b"\x00\x00" * frames
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


class FakeTTS(BaseProvider):
    name = "fake"
    is_local = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "fake-tts")
        super().__init__(**kwargs)
        self.calls: list[SpeechRequest] = []

    async def synthesize(
        self,
        request: SpeechRequest,
        destination: Path,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> SpeechResult:
        self.calls.append(request)
        destination.parent.mkdir(parents=True, exist_ok=True)
        chars = len(request.text)
        duration = max(0.1, chars / CHARS_PER_SECOND / max(request.speed, 0.1))

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(characters=chars),
        ) as charge:
            destination.write_bytes(_silence_wav(duration))
            charge.record(characters=chars)

        return SpeechResult(
            path=destination,
            provider=self.name,
            model=self.model,
            voice_id=request.voice_id,
            characters=chars,
            duration_s=duration,
        )
