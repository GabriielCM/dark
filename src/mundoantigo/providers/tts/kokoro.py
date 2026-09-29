"""Kokoro rodando local. Custo zero — o candidato economico do brief 6.1.

Tres cuidados que a primeira versao nao tinha:

- um pipeline por idioma, todos sobre o mesmo modelo carregado uma vez. Antes
  o primeiro idioma ficava em cache e o ingles saia pela fonetica do
  portugues;
- o idioma vem do prefixo da voz (p = pt-BR, a = ingles americano, b =
  britanico) e precisa bater com o canal;
- sintese frase a frase: o G2P do portugues (espeak) pode truncar texto
  longo, e sintetizar por frase ainda devolve o tempo exato de cada uma.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ...costs import Usage
from ...errors import ProviderMisconfigured
from ..base import BaseProvider
from ..gpu import GPU_LOCK
from .base import SpeechRequest, SpeechResult

log = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
#  Prefixos de voz aceitos por idioma do canal.
_LANG_CODES = {"pt": ("p",), "en": ("a", "b")}


def lang_code_for(voice_id: str, language: str) -> str:
    """Codigo de idioma do Kokoro a partir da voz, conferido contra o canal."""
    code = voice_id.split(",")[0].strip()[:1].lower()
    family = "pt" if language.lower().startswith("pt") else "en"
    if code not in _LANG_CODES[family]:
        raise ProviderMisconfigured(
            "local", f"a voz {voice_id!r} nao e de {language}: use {_LANG_CODES[family]}*"
        )
    return code


class KokoroTTS(BaseProvider):
    name = "local"
    is_local = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "kokoro-v1")
        super().__init__(**kwargs)
        self.repo_id = str(self.config.get("repo_id", "hexgrad/Kokoro-82M"))
        self.device = str(self.config.get("device", "cuda"))
        self._model: Any = None
        self._pipelines: dict[str, Any] = {}

    def _pipeline(self, code: str) -> Any:
        if code in self._pipelines:
            return self._pipelines[code]
        try:
            import torch
            from kokoro import KModel, KPipeline
        except ImportError as exc:
            raise ProviderMisconfigured(
                self.name,
                "kokoro nao instalado. Este provedor so roda na maquina com GPU: "
                "`uv sync --extra local-gpu`.",
            ) from exc
        if self._model is None:
            device = self.device if torch.cuda.is_available() else "cpu"
            self._model = KModel(repo_id=self.repo_id).to(device).eval()
        self._pipelines[code] = KPipeline(lang_code=code, repo_id=self.repo_id, model=self._model)
        return self._pipelines[code]

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
        text = " ".join(request.segments) if request.segments else request.text
        chars = len(text)

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(characters=chars),
        ) as charge:
            async with GPU_LOCK:
                duration, times = await asyncio.to_thread(self._render, request, destination)
            charge.record(characters=chars)

        return SpeechResult(
            path=destination,
            provider=self.name,
            model=self.model,
            voice_id=request.voice_id,
            characters=chars,
            duration_s=duration,
            segment_times=times,
        )

    def _render(
        self, request: SpeechRequest, destination: Path
    ) -> tuple[float, tuple[tuple[float, float], ...]]:
        import numpy as np
        import soundfile as sf

        pipeline = self._pipeline(lang_code_for(request.voice_id, request.language))
        segments = request.segments or (request.text,)
        pauses = request.pauses or tuple(0.0 for _ in segments)
        if len(pauses) != len(segments):
            raise ValueError("um valor de pausa por segmento")

        pieces: list[Any] = []
        times: list[tuple[float, float]] = []
        cursor = 0.0
        for text, pause in zip(segments, pauses, strict=True):
            chunks = [
                np.asarray(audio.cpu() if hasattr(audio, "cpu") else audio, dtype="float32")
                for _, _, audio in pipeline(text, voice=request.voice_id, speed=request.speed)
            ]
            if not chunks:
                raise ProviderMisconfigured(
                    self.name, f"kokoro devolveu audio vazio: {text[:60]!r}"
                )
            audio = np.concatenate(chunks)
            start = cursor
            cursor += len(audio) / SAMPLE_RATE
            times.append((round(start, 3), round(cursor, 3)))
            pieces.append(audio)
            if pause > 0:
                pieces.append(np.zeros(int(pause * SAMPLE_RATE), dtype="float32"))
                cursor += pause

        wave = np.concatenate(pieces)
        sf.write(destination, wave, SAMPLE_RATE)
        return float(len(wave)) / SAMPLE_RATE, tuple(times) if request.segments else ()
