"""Tabela de precos.

Regra do ADR 0003: o codigo nunca traz numero embutido. Todo preco vem de
`config/precos.yaml`, e modelo sem preco e bloqueado no modo estrito.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, ClassVar

import yaml

from ..errors import ConfigError, UnknownPrice
from ..paths import get_paths

#  Como cada unidade vira dinheiro. A chave e o campo do YAML.
UNIT_KINDS = frozenset({"token_io", "imagem", "caractere", "minuto", "consulta"})


@dataclass(frozen=True, slots=True)
class Usage:
    """Quanto foi consumido numa chamada.

    Os campos sao mutuamente exclusivos na pratica — cada unidade usa os seus —
    mas ficam num objeto so para o registrador nao precisar de kwargs soltos.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    images: int = 0
    characters: int = 0
    minutes: float = 0.0
    queries: int = 0

    def quantity_for(self, unit: str) -> float:
        match unit:
            case "token_io":
                return float(self.input_tokens + self.output_tokens)
            case "imagem":
                return float(self.images)
            case "caractere":
                return float(self.characters)
            case "minuto":
                return self.minutes
            case "consulta":
                return float(self.queries)
        raise ConfigError(f"unidade desconhecida: {unit!r}")

    def as_detail(self) -> dict[str, Any]:
        """So os campos que foram usados. `Usage` tem slots, entao nao ha __dict__."""
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name)}


@dataclass(frozen=True, slots=True)
class Price:
    provider: str
    model: str
    unit: str
    values: dict[str, float]

    _FIELDS: ClassVar[dict[str, tuple[str, ...]]] = {
        "token_io": ("usd_por_1m_entrada", "usd_por_1m_saida"),
        "imagem": ("usd_por_imagem",),
        "caractere": ("usd_por_1k",),
        "minuto": ("usd_por_minuto",),
        "consulta": ("usd_por_consulta",),
    }

    def amount_usd(self, usage: Usage) -> float:
        match self.unit:
            case "token_io":
                return (
                    usage.input_tokens / 1_000_000 * self.values["usd_por_1m_entrada"]
                    + usage.output_tokens / 1_000_000 * self.values["usd_por_1m_saida"]
                )
            case "imagem":
                return usage.images * self.values["usd_por_imagem"]
            case "caractere":
                return usage.characters / 1_000 * self.values["usd_por_1k"]
            case "minuto":
                return usage.minutes * self.values["usd_por_minuto"]
            case "consulta":
                return usage.queries * self.values["usd_por_consulta"]
        raise ConfigError(f"unidade desconhecida: {self.unit!r}")  # pragma: no cover

    @property
    def is_free(self) -> bool:
        return all(v == 0.0 for v in self.values.values())


class PriceTable:
    """Precos carregados do YAML, indexados por (provedor, modelo)."""

    def __init__(self, prices: dict[tuple[str, str], Price], effective_from: str = "") -> None:
        self._prices = prices
        self.effective_from = effective_from

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> PriceTable:
        target = path or (get_paths().config / "precos.yaml")
        if not target.exists():
            raise ConfigError(f"tabela de precos ausente: {target}")
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        effective = str(raw.pop("vigencia", ""))

        prices: dict[tuple[str, str], Price] = {}
        for provider, models in raw.items():
            if not isinstance(models, dict):
                raise ConfigError(f"bloco de precos invalido para {provider!r}")
            for model, spec in models.items():
                unit = spec.get("unidade")
                if unit not in UNIT_KINDS:
                    raise ConfigError(
                        f"{provider}/{model}: unidade {unit!r} desconhecida "
                        f"(esperava uma de {sorted(UNIT_KINDS)})"
                    )
                missing = [f for f in Price._FIELDS[unit] if f not in spec]
                if missing:
                    raise ConfigError(f"{provider}/{model}: faltam campos de preco {missing}")
                prices[(provider, model)] = Price(
                    provider=provider,
                    model=model,
                    unit=unit,
                    values={f: float(spec[f]) for f in Price._FIELDS[unit]},
                )
        return cls(prices, effective)

    def get(self, provider: str, model: str) -> Price | None:
        return self._prices.get((provider, model)) or self._prices.get(("local", model))

    def require(self, provider: str, model: str, *, strict: bool = True) -> Price:
        """Preco de um modelo.

        No modo estrito, ausencia e erro: um preco que nao sabemos e um preco
        que nao cabe no teto (ADR 0003).
        """
        price = self.get(provider, model)
        if price is not None:
            return price
        if strict:
            raise UnknownPrice(
                f"{provider}/{model} nao esta em config/precos.yaml. "
                "Adicione o preco antes de usar este modelo."
            )
        return Price(
            provider=provider, model=model, unit="consulta", values={"usd_por_consulta": 0.0}
        )

    def __len__(self) -> int:
        return len(self._prices)

    def __contains__(self, key: tuple[str, str]) -> bool:
        return self.get(*key) is not None
