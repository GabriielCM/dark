"""Provedor de texto de mentira, para testes e para o modo de ensaio.

Nao e um stub descuidado: ele registra custo como um provedor de verdade, o que
faz os testes de orcamento exercitarem o mesmo caminho da producao.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ...costs import Usage
from ..base import BaseProvider, estimate_tokens
from .base import LLMResponse

Responder = Callable[[str], str]


class FakeLLM(BaseProvider):
    name = "fake"
    is_local = True

    def __init__(self, *, responses: list[str] | Responder | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("model", "fake-llm")
        super().__init__(**kwargs)
        self._responses = responses
        self._index = 0
        self.calls: list[dict[str, Any]] = []

    def _next_text(self, prompt: str) -> str:
        if callable(self._responses):
            return self._responses(prompt)
        if isinstance(self._responses, list) and self._responses:
            text = self._responses[min(self._index, len(self._responses) - 1)]
            self._index += 1
            return text
        return json.dumps({"ok": True, "echo": prompt[:80]})

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
        self.calls.append({"prompt": prompt, "step": step, "system": system})
        text = self._next_text(prompt)
        input_tokens = estimate_tokens((system or "") + prompt)
        output_tokens = estimate_tokens(text)

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        ) as charge:
            charge.record(input_tokens=input_tokens, output_tokens=output_tokens)

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
        )
