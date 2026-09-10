"""Provedor de texto via OpenRouter (CLAUDE.md: LLM e imagens via OpenRouter)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ...costs import Usage
from ...errors import ProviderUnavailable
from ..base import BaseProvider, estimate_tokens
from .base import LLMResponse


class OpenRouterLLM(BaseProvider):
    name = "openrouter"
    is_local = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")

    async def complete(
        self,
        prompt: str,
        *,
        step: str,
        video_id: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        step_run_id: int | None = None,
    ) -> LLMResponse:
        key = self._require_key(self.api_key, "OPENROUTER_API_KEY")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        #  Estimativa para a checagem de teto antes de a chamada sair.
        estimate = Usage(
            input_tokens=estimate_tokens((system or "") + prompt),
            output_tokens=max_tokens // 2,
        )

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=estimate,
        ) as charge:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            data = await self._with_retry(self._post, key, payload)

            usage = data.get("usage", {}) or {}
            input_tokens = int(usage.get("prompt_tokens", estimate.input_tokens))
            output_tokens = int(usage.get("completion_tokens", 0))
            charge.record(input_tokens=input_tokens, output_tokens=output_tokens)

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ProviderUnavailable(self.name, f"resposta sem conteudo: {data}") from exc

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            raw=data,
        )

    async def _post(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            #  OpenRouter usa estes cabecalhos para atribuicao de uso.
            "HTTP-Referer": "https://localhost/mundoantigo",
            "X-Title": "Mundo Antigo",
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
            except httpx.TimeoutException as exc:
                raise ProviderUnavailable(self.name, f"timeout apos {self.timeout_s}s") from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(self.name, f"erro de rede: {exc}") from exc
            self._raise_for_status(resp)
            return dict(resp.json())
