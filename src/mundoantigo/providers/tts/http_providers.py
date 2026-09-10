"""Provedores de voz por API: ElevenLabs, Fish Audio e Gemini.

Os tres compartilham o mesmo formato: POST com texto, resposta em bytes de
audio, cobranca por caractere. A diferenca cabe em tres metodos.
"""

from __future__ import annotations

import os
from abc import abstractmethod
from pathlib import Path
from typing import Any

import httpx

from ...costs import Usage
from ...errors import ProviderUnavailable
from ..base import BaseProvider
from .base import SpeechRequest, SpeechResult


class HTTPTTSProvider(BaseProvider):
    """Base dos provedores de voz por HTTP."""

    env_key: str = ""
    is_local = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_key = os.environ.get(self.env_key, "")

    @abstractmethod
    def _endpoint(self, request: SpeechRequest) -> str: ...

    @abstractmethod
    def _headers(self, key: str) -> dict[str, str]: ...

    @abstractmethod
    def _body(self, request: SpeechRequest) -> dict[str, Any]: ...

    async def synthesize(
        self,
        request: SpeechRequest,
        destination: Path,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> SpeechResult:
        key = self._require_key(self.api_key, self.env_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        chars = len(request.text)

        #  Caractere e unidade conhecida de antemao: a estimativa e exata,
        #  entao o teto e verificado com o valor real antes da chamada sair.
        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(characters=chars),
        ) as charge:
            audio = await self._with_retry(self._post, key, request)
            destination.write_bytes(audio)
            charge.record(characters=chars)

        return SpeechResult(
            path=destination,
            provider=self.name,
            model=self.model,
            voice_id=request.voice_id,
            characters=chars,
        )

    async def _post(self, key: str, request: SpeechRequest) -> bytes:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            try:
                resp = await client.post(
                    self._endpoint(request),
                    json=self._body(request),
                    headers=self._headers(key),
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(self.name, f"erro de rede: {exc}") from exc
            self._raise_for_status(resp)
            return resp.content


class ElevenLabsTTS(HTTPTTSProvider):
    name = "elevenlabs"
    env_key = "ELEVENLABS_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "eleven_multilingual_v2")
        super().__init__(**kwargs)

    def _endpoint(self, request: SpeechRequest) -> str:
        return f"https://api.elevenlabs.io/v1/text-to-speech/{request.voice_id}"

    def _headers(self, key: str) -> dict[str, str]:
        return {"xi-api-key": key, "Content-Type": "application/json"}

    def _body(self, request: SpeechRequest) -> dict[str, Any]:
        return {
            "text": request.text,
            "model_id": self.model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": request.speed},
        }


class FishAudioTTS(HTTPTTSProvider):
    name = "fish"
    env_key = "FISH_AUDIO_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "s2-pro")
        super().__init__(**kwargs)

    def _endpoint(self, request: SpeechRequest) -> str:
        return "https://api.fish.audio/v1/tts"

    def _headers(self, key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _body(self, request: SpeechRequest) -> dict[str, Any]:
        return {
            "text": request.text,
            "reference_id": request.voice_id,
            "format": "wav",
            "latency": "normal",
        }


class GeminiTTS(HTTPTTSProvider):
    name = "gemini"
    env_key = "GEMINI_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "gemini-3.1-flash-tts")
        super().__init__(**kwargs)

    def _endpoint(self, request: SpeechRequest) -> str:
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )

    def _headers(self, key: str) -> dict[str, str]:
        return {"x-goog-api-key": key, "Content-Type": "application/json"}

    def _body(self, request: SpeechRequest) -> dict[str, Any]:
        return {
            "contents": [{"parts": [{"text": request.text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": request.voice_id}}
                },
            },
        }
