"""Hierarquia de erros do pipeline.

A distincao que importa para a fila (ADR 0002): `TransientError` merece nova
tentativa, `PermanentError` nao. Chave de API invalida nao melhora esperando.
"""

from __future__ import annotations


class MundoAntigoError(Exception):
    """Base de todos os erros do projeto."""


class TransientError(MundoAntigoError):
    """Falha que pode passar sozinha: rede, limite de taxa, GPU ocupada."""


class PermanentError(MundoAntigoError):
    """Falha que nao muda com nova tentativa: configuracao, contrato, credencial."""


class ConfigError(PermanentError):
    """Configuracao ausente ou invalida."""


class ProviderError(MundoAntigoError):
    """Falha vinda de um provedor externo."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider


class ProviderUnavailable(ProviderError, TransientError):
    """Provedor fora do ar, sem cota ou em limite de taxa."""


class ProviderMisconfigured(ProviderError, PermanentError):
    """Credencial ausente ou invalida, modelo inexistente."""


class ResponseTruncated(ProviderError, PermanentError):
    """O modelo parou no limite de tokens de saida e a resposta veio cortada.

    Permanente de proposito: repetir com o mesmo limite paga de novo pelo
    mesmo corte. Quem chama precisa pedir um limite maior ou dividir o pedido.
    """


class BudgetExceeded(PermanentError):
    """Teto de orcamento atingido. A chamada paga nao foi feita.

    Permanente de proposito: retentar nao ajuda. O video fica `blocked` e volta
    quando o mes virar ou o teto for elevado (ADR 0003).
    """

    def __init__(self, scope: str, spent_usd: float, limit_usd: float) -> None:
        super().__init__(
            f"teto de orcamento atingido ({scope}): US$ {spent_usd:.4f} de US$ {limit_usd:.2f}"
        )
        self.scope = scope
        self.spent_usd = spent_usd
        self.limit_usd = limit_usd


class UnknownPrice(PermanentError):
    """Modelo sem preco em config/precos.yaml e o modo e `strict` (ADR 0003)."""


class FactGateBlocked(MundoAntigoError):
    """Ha item de baixa confianca no relatorio de fatos.

    Nao e falha do pipeline: e o gate funcionando. O video vai para revisao
    humana em vez de `failed`.
    """

    def __init__(self, low_confidence_count: int) -> None:
        super().__init__(
            f"{low_confidence_count} item(ns) de baixa confianca bloqueiam a renderizacao"
        )
        self.low_confidence_count = low_confidence_count


class RightsViolation(PermanentError):
    """Tentativa de adaptar ou narrar obra que nao esta em dominio publico."""
