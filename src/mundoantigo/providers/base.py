"""Contrato comum dos adaptadores.

Todo provedor (texto, imagem, voz, alinhamento, busca) fica atras de um
Protocol. Trocar de provedor e trocar a configuracao — CLAUDE.md.

Cada adaptador e responsavel por chamar o registrador de custos, porque so ele
sabe traduzir a resposta do provedor em unidades cobraveis.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from ..costs import CostRecorder
from ..errors import ProviderMisconfigured, ProviderUnavailable, TransientError

log = logging.getLogger(__name__)

#  Codigos que valem nova tentativa. 429 e limite de taxa; 5xx e do outro lado.
RETRIABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class CallContext:
    """De onde partiu a chamada. Vai inteiro para o registrador de custos."""

    step: str
    video_id: str | None = None
    step_run_id: int | None = None


@runtime_checkable
class Provider(Protocol):
    """Superficie minima que todo adaptador expoe."""

    name: str
    model: str
    is_local: bool


class BaseProvider:
    """Base concreta com retentativa, timeout e acesso ao registrador."""

    name: str = "base"
    is_local: bool = False

    def __init__(
        self,
        *,
        model: str,
        costs: CostRecorder,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.costs = costs
        self.config = config or {}
        self.timeout_s = float(self.config.get("timeout_s", 120))
        self.max_retries = int(self.config.get("max_retries", 2))

    # -- utilitarios compartilhados ---------------------------------------

    async def _with_retry(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Repete falhas transitorias com espera exponencial e jitter."""
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except TransientError as exc:
                last = exc
                if attempt == self.max_retries:
                    break
                delay = (2**attempt) + random.uniform(0, 0.5)
                log.warning(
                    "%s: falha transitoria (%s), nova tentativa em %.1fs",
                    self.name,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
        assert last is not None
        raise last

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        body = response.text[:500]
        if response.status_code in {401, 403}:
            raise ProviderMisconfigured(
                self.name, f"credencial rejeitada ({response.status_code}): {body}"
            )
        if response.status_code == 404:
            raise ProviderMisconfigured(self.name, f"modelo ou rota inexistente: {body}")
        if response.status_code in RETRIABLE_STATUS:
            raise ProviderUnavailable(self.name, f"HTTP {response.status_code}: {body}")
        raise ProviderMisconfigured(self.name, f"HTTP {response.status_code}: {body}")

    def _require_key(self, key: str | None, env_name: str) -> str:
        if not key:
            raise ProviderMisconfigured(self.name, f"{env_name} nao configurado no .env")
        return key


def estimate_tokens(text: str) -> int:
    """Estimativa grosseira de tokens, boa o bastante para o teto.

    ~4 caracteres por token em portugues e ingles. Usada so para a checagem
    *antes* da chamada (ADR 0003); o valor cobrado usa o consumo real
    devolvido pelo provedor.
    """
    return max(1, len(text) // 4)
