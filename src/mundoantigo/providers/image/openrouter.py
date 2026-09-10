"""Imagens por API (plano B do brief 5.3: Nano Banana / Recraft via OpenRouter)."""

from __future__ import annotations

import base64
import os
import random
from pathlib import Path
from typing import Any

import httpx

from ...costs import Usage
from ...errors import ProviderUnavailable
from ..base import BaseProvider
from .base import ImageRequest, ImageResult


class OpenRouterImage(BaseProvider):
    name = "openrouter"
    is_local = False

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "google/nano-banana-2")
        super().__init__(**kwargs)
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")

    async def generate(
        self,
        request: ImageRequest,
        destination: Path,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> ImageResult:
        key = self._require_key(self.api_key, "OPENROUTER_API_KEY")
        seed = request.seed if request.seed is not None else random.randint(0, 2**31 - 1)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(images=1),
        ) as charge:
            data = await self._with_retry(self._post, key, request, seed)
            payload = self._extract_image(data)
            destination.write_bytes(payload)
            charge.record(images=1)

        return ImageResult(
            path=destination,
            provider=self.name,
            model=self.model,
            seed=seed,
            width=request.width,
            height=request.height,
        )

    async def _post(self, key: str, request: ImageRequest, seed: int) -> dict[str, Any]:
        prompt = request.prompt
        if request.negative:
            prompt = f"{prompt}\n\nAvoid: {request.negative}"
        body = {
            "model": self.model,
            "prompt": prompt,
            "size": f"{request.width}x{request.height}",
            "seed": seed,
            "n": 1,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/images/generations", json=body, headers=headers
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(self.name, f"erro de rede: {exc}") from exc
            self._raise_for_status(resp)
            return dict(resp.json())

    def _extract_image(self, data: dict[str, Any]) -> bytes:
        items = data.get("data") or []
        if not items:
            raise ProviderUnavailable(self.name, f"resposta sem imagem: {str(data)[:300]}")
        item = items[0]
        if "b64_json" in item:
            return base64.b64decode(item["b64_json"])
        raise ProviderUnavailable(
            self.name, "resposta traz URL em vez de bytes; baixe antes de gravar"
        )
