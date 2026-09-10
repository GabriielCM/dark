"""Gate de fatos.

Regra que nao muda sem aprovacao (CLAUDE.md): nenhuma renderizacao sem
relatorio de fatos aprovado; um item de baixa confianca bloqueia a etapa.

Este modulo e a decisao pura — recebe o relatorio, devolve o veredito. A
reescrita automatica e a escalada para humano vivem na etapa que o usa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import FactsConfig
from ..db.models import Confidence


@dataclass(frozen=True, slots=True)
class FactCheckItem:
    """Uma linha do relatorio de fatos."""

    id: str
    claim: str
    confidence: Confidence
    sources: tuple[str, ...] = ()
    justification: str | None = None
    suggested_fix: str | None = None
    block_index: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, fallback_id: str = "?") -> FactCheckItem:
        confidence = str(raw.get("confianca", "baixa")).strip().lower()
        #  Qualquer coisa que nao seja um dos tres niveis conhecidos vira
        #  "baixa": um relatorio malformado nao pode passar pelo gate.
        if confidence not in {c.value for c in Confidence}:
            confidence = Confidence.BAIXA.value
        sources = raw.get("fontes") or []
        if isinstance(sources, str):
            sources = [sources]
        block = raw.get("bloco")
        return cls(
            id=str(raw.get("id") or fallback_id),
            claim=str(raw.get("afirmacao", "")).strip(),
            confidence=Confidence(confidence),
            sources=tuple(str(s) for s in sources),
            justification=raw.get("justificativa"),
            suggested_fix=raw.get("correcao_sugerida") or None,
            block_index=int(block)
            if isinstance(block, int | str) and str(block).isdigit()
            else None,
        )


@dataclass(frozen=True, slots=True)
class GateVerdict:
    passed: bool
    blocking: tuple[FactCheckItem, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    reason: str = ""

    @property
    def blocking_count(self) -> int:
        return len(self.blocking)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class FactGate:
    """Avalia um relatorio de fatos contra a politica configurada."""

    def __init__(self, config: FactsConfig) -> None:
        self.config = config
        self._blocking_levels = {Confidence(level) for level in config.blocks_on}

    def parse(self, report: Any) -> list[FactCheckItem]:
        """Le o relatorio vindo do LLM, tolerando as formas que ele costuma usar."""
        if isinstance(report, dict):
            items = report.get("itens") or report.get("items") or []
        elif isinstance(report, list):
            items = report
        else:
            items = []
        return [
            FactCheckItem.from_dict(raw, fallback_id=f"a{i + 1}")
            for i, raw in enumerate(items)
            if isinstance(raw, dict)
        ]

    def evaluate(self, items: list[FactCheckItem]) -> GateVerdict:
        counts = {c.value: 0 for c in Confidence}
        for item in items:
            counts[item.confidence.value] += 1

        if not items:
            #  Relatorio vazio nao e aprovacao: e ausencia de checagem.
            return GateVerdict(
                passed=False,
                counts=counts,
                reason="relatorio de fatos vazio — nenhuma afirmacao foi checada",
            )

        blocking = tuple(i for i in items if i.confidence in self._blocking_levels)
        if blocking:
            return GateVerdict(
                passed=False,
                blocking=blocking,
                counts=counts,
                reason=(
                    f"{len(blocking)} de {len(items)} afirmacoes com confianca "
                    f"{'/'.join(sorted(c.value for c in self._blocking_levels))}"
                ),
            )

        return GateVerdict(
            passed=True,
            counts=counts,
            reason=f"{len(items)} afirmacoes checadas, nenhuma bloqueante",
        )

    def check(self, report: Any) -> tuple[list[FactCheckItem], GateVerdict]:
        items = self.parse(report)
        return items, self.evaluate(items)

    def downgrade_unsourced(self, items: list[FactCheckItem]) -> list[FactCheckItem]:
        """Rebaixa itens que o modelo classificou bem demais.

        O prompt ja pede severidade, mas o modelo e o autor do roteiro e do
        relatorio — ele tem incentivo a se aprovar. Esta checagem e mecanica:
        'alta' exige o numero configurado de fontes; sem fonte nenhuma, e baixa.
        """
        adjusted: list[FactCheckItem] = []
        for item in items:
            confidence = item.confidence
            reason = item.justification
            if not item.sources and confidence is not Confidence.BAIXA:
                confidence = Confidence.BAIXA
                reason = f"[rebaixado: sem fonte] {item.justification or ''}".strip()
            elif confidence is Confidence.ALTA and len(item.sources) < self.config.sources_for_high:
                confidence = Confidence.MEDIA
                reason = (
                    f"[rebaixado: {len(item.sources)} fonte(s), "
                    f"minimo {self.config.sources_for_high}] {item.justification or ''}"
                ).strip()

            if confidence is item.confidence:
                adjusted.append(item)
            else:
                adjusted.append(
                    FactCheckItem(
                        id=item.id,
                        claim=item.claim,
                        confidence=confidence,
                        sources=item.sources,
                        justification=reason,
                        suggested_fix=item.suggested_fix,
                        block_index=item.block_index,
                    )
                )
        return adjusted
