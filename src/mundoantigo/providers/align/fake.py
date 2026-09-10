"""Alinhador de mentira: distribui as palavras uniformemente na duracao dada.

Suficiente para exercitar a geracao de SRT e a montagem sem GPU.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from ..base import BaseProvider
from .base import AlignmentResult, WordTiming


def _wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as fh:
            return fh.getnframes() / float(fh.getframerate())
    except (wave.Error, OSError, ZeroDivisionError):
        return None


class FakeAlign(BaseProvider):
    name = "fake"
    is_local = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "fake-align")
        super().__init__(**kwargs)

    async def align(
        self,
        audio: Path,
        transcript: str,
        *,
        language: str,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> AlignmentResult:
        words = transcript.split()
        duration = _wav_duration(audio) or max(1.0, len(words) / 2.5)
        per_word = duration / max(len(words), 1)
        timings = [
            WordTiming(word=w, start=i * per_word, end=(i + 1) * per_word)
            for i, w in enumerate(words)
        ]

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
        ) as charge:
            charge.record(minutes=duration / 60.0)

        return AlignmentResult(
            words=tuple(timings), duration_s=duration, provider=self.name, model=self.model
        )
