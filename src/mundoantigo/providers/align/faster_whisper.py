"""Alinhamento local com faster-whisper na RTX 3060.

CLAUDE.md, processamento local: alinhamento de legendas roda na maquina.
Custo zero, registrado por minuto de audio para medir volume.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ...errors import ProviderMisconfigured
from ..base import BaseProvider
from ..gpu import GPU_LOCK
from .base import AlignmentResult, WordTiming

log = logging.getLogger(__name__)


class FasterWhisperAlign(BaseProvider):
    name = "local"
    is_local = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "large-v3")
        super().__init__(**kwargs)
        self.device = str(self.config.get("device", "cuda"))
        self.compute_type = str(self.config.get("compute_type", "float16"))
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ProviderMisconfigured(
                self.name,
                "faster-whisper nao instalado: `uv sync --extra local-gpu`",
            ) from exc
        if self.device == "cuda":
            #  No Windows, o CTranslate2 procura cublas64_12.dll e cudnn64_9.dll
            #  no PATH e nao acha; o torch traz as duas e as carrega ao ser
            #  importado. Sem isto, o alinhamento so funcionava quando o Kokoro
            #  (que importa o torch) tinha rodado antes no mesmo processo.
            import torch  # noqa: F401
        log.info("carregando whisper %s em %s", self.model, self.device)
        self._model = WhisperModel(self.model, device=self.device, compute_type=self.compute_type)
        return self._model

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
        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
        ) as charge:
            async with GPU_LOCK:
                words, duration = await asyncio.to_thread(self._transcribe, audio, language)
            charge.record(minutes=duration / 60.0)

        return AlignmentResult(
            words=tuple(words), duration_s=duration, provider=self.name, model=self.model
        )

    def _transcribe(self, audio: Path, language: str) -> tuple[list[WordTiming], float]:
        model = self._load()
        segments, info = model.transcribe(
            str(audio),
            language=language.split("-")[0],
            word_timestamps=True,
            #  A narracao ja e limpa; VAD so introduziria cortes indevidos.
            vad_filter=False,
        )
        words: list[WordTiming] = []
        for segment in segments:
            for word in segment.words or []:
                words.append(
                    WordTiming(word=word.word.strip(), start=float(word.start), end=float(word.end))
                )
        return words, float(info.duration)
