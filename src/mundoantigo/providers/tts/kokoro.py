"""Kokoro rodando local. Custo zero — o candidato economico do brief 6.1."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ...costs import Usage
from ...errors import ProviderMisconfigured
from ..base import BaseProvider
from .base import SpeechRequest, SpeechResult

log = logging.getLogger(__name__)

_GPU_LOCK = asyncio.Semaphore(1)


class KokoroTTS(BaseProvider):
    name = "local"
    is_local = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "kokoro-v1")
        super().__init__(**kwargs)
        self._pipeline: Any = None

    def _load(self, lang_code: str) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise ProviderMisconfigured(
                self.name,
                "kokoro nao instalado. Este provedor so roda na maquina com GPU.",
            ) from exc
        self._pipeline = KPipeline(lang_code=lang_code)
        return self._pipeline

    async def synthesize(
        self,
        request: SpeechRequest,
        destination: Path,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> SpeechResult:
        destination.parent.mkdir(parents=True, exist_ok=True)
        chars = len(request.text)

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(characters=chars),
        ) as charge:
            async with _GPU_LOCK:
                duration = await asyncio.to_thread(self._render, request, destination)
            charge.record(characters=chars)

        return SpeechResult(
            path=destination,
            provider=self.name,
            model=self.model,
            voice_id=request.voice_id,
            characters=chars,
            duration_s=duration,
        )

    def _render(self, request: SpeechRequest, destination: Path) -> float:
        import numpy as np
        import soundfile as sf

        #  Kokoro usa a inicial do idioma: 'p' para pt-BR, 'a' para en-US.
        lang_code = "p" if request.language.startswith("pt") else "a"
        pipeline = self._load(lang_code)

        chunks = [
            audio
            for _, _, audio in pipeline(request.text, voice=request.voice_id, speed=request.speed)
        ]
        if not chunks:
            raise ProviderMisconfigured(self.name, "kokoro devolveu audio vazio")
        wave = np.concatenate(chunks)
        sample_rate = 24_000
        sf.write(destination, wave, sample_rate)
        return float(len(wave)) / sample_rate
