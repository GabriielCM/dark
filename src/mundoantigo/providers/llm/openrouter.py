"""Provedor de texto via OpenRouter (CLAUDE.md: LLM e imagens via OpenRouter)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ...costs import Usage
from ...errors import ProviderUnavailable, ResponseTruncated
from ..base import BaseProvider, estimate_tokens
from .base import LLMResponse


def _add_cost(total: float | None, cost: Any) -> float | None:
    """Soma o `usage.cost` de uma resposta; sem o campo, o total vira None.

    Basta uma tentativa sem valor informado para o total nao ser confiavel, e
    ai o registrador usa a tabela para a chamada inteira.
    """
    if total is None or not isinstance(cost, int | float) or isinstance(cost, bool):
        return None
    return total + float(cost)


class OpenRouterLLM(BaseProvider):
    name = "openrouter"
    is_local = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")
        #  Todo prompt do projeto pede um objeto JSON. Sem o modo JSON, o modelo
        #  rapido devolveu duas vezes seguidas, na amostra de 29/09, um JSON que
        #  nao abria (aspas sem escape num paragrafo), e a etapa falhou.
        self.json_mode = bool(self.config.get("modo_json", True))
        #  Esforco de raciocinio por modelo (`reasoning.effort` do OpenRouter).
        #  Modelo fora do mapa fica no padrao dele.
        efforts = self.config.get("raciocinio") or {}
        self.reasoning_effort: str | None = efforts.get(self.model)

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
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if self.json_mode:
                payload["response_format"] = {"type": "json_object"}
            if self.reasoning_effort:
                payload["reasoning"] = {"effort": self.reasoning_effort}
            #  Tokens e valor de tentativas que o provedor do modelo derrubou no
            #  meio: entram no custo se tiverem sido cobrados.
            wasted = [0, 0]
            wasted_usd: list[float | None] = [0.0]

            async def attempt() -> dict[str, Any]:
                data = await self._post(key, payload)
                choice = (data.get("choices") or [{}])[0]
                if choice.get("finish_reason") == "error":
                    #  O provedor do modelo caiu no meio e o OpenRouter devolveu
                    #  o pedaco que tinha: no storyboard de 04/10 isso virou
                    #  "JSON invalido" e derrubou a etapa inteira, que recomecava
                    #  do bloco 0. Aqui so esta chamada e repetida.
                    spent = data.get("usage") or {}
                    wasted[0] += int(spent.get("prompt_tokens") or 0)
                    wasted[1] += int(spent.get("completion_tokens") or 0)
                    wasted_usd[0] = _add_cost(wasted_usd[0], spent.get("cost"))
                    raise ProviderUnavailable(
                        self.name, "o provedor do modelo falhou no meio da resposta"
                    )
                return data

            data = await self._with_retry(attempt)

            usage = data.get("usage", {}) or {}
            input_tokens = int(usage.get("prompt_tokens", estimate.input_tokens))
            output_tokens = int(usage.get("completion_tokens", 0))
            charge.record(
                input_tokens=input_tokens + wasted[0],
                output_tokens=output_tokens + wasted[1],
                #  O OpenRouter devolve o valor cobrado em `usage.cost`. Sem ele,
                #  o registrador cai na tabela de precos.
                billed_usd=_add_cost(wasted_usd[0], usage.get("cost")),
            )

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ProviderUnavailable(self.name, f"resposta sem conteudo: {data}") from exc
        if choice.get("finish_reason") == "length":
            #  Modelos com raciocinio gastam parte do limite antes do texto: a
            #  adaptacao de 20 min parou em 12000 tokens (04/10) e a fila
            #  retentou o mesmo corte, pagando de novo.
            raise ResponseTruncated(
                self.name,
                f"resposta cortada no limite de {max_tokens} tokens de saida "
                f"({output_tokens} usados); aumente o limite ou divida o pedido",
            )

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
