"""Gate de fatos.

Regra que nao muda sem aprovacao (CLAUDE.md): um item de baixa confianca
bloqueia a renderizacao. Estes testes existem para que afrouxar isso exija
apagar um teste, e nao so mudar uma condicao.
"""

from __future__ import annotations

import pytest

from mundoantigo.config import FactsConfig
from mundoantigo.db.models import Confidence
from mundoantigo.pipeline.fact_gate import FactCheckItem, FactGate


@pytest.fixture
def gate() -> FactGate:
    return FactGate(FactsConfig(blocks_on=("baixa",), max_rewrites=2, sources_for_high=2))


def item(**kwargs) -> dict:
    base = {
        "id": "a1",
        "afirmacao": "Os aquedutos funcionavam por gravidade.",
        "confianca": "alta",
        "fontes": ["https://a.edu/1", "https://b.edu/2"],
        "justificativa": "duas fontes academicas",
    }
    return {**base, **kwargs}


class TestVerdict:
    def test_all_high_confidence_passes(self, gate: FactGate) -> None:
        _, verdict = gate.check({"itens": [item(), item(id="a2")]})
        assert verdict.passed
        assert verdict.counts["alta"] == 2

    def test_single_low_confidence_blocks(self, gate: FactGate) -> None:
        """Um item basta. E o coracao do gate."""
        _, verdict = gate.check(
            {"itens": [item(), item(id="a2", confianca="baixa", fontes=["https://x.edu"])]}
        )
        assert not verdict.passed
        assert verdict.blocking_count == 1
        assert verdict.blocking[0].id == "a2"

    def test_medium_confidence_alone_does_not_block(self, gate: FactGate) -> None:
        _, verdict = gate.check({"itens": [item(confianca="media", fontes=["https://a.edu"])]})
        assert verdict.passed

    def test_empty_report_does_not_pass(self, gate: FactGate) -> None:
        """Relatorio vazio e ausencia de checagem, nao aprovacao."""
        _, verdict = gate.check({"itens": []})
        assert not verdict.passed
        assert "vazio" in verdict.reason

    def test_malformed_confidence_treated_as_low(self, gate: FactGate) -> None:
        """Relatorio malformado nao pode passar por acidente."""
        items, verdict = gate.check({"itens": [item(confianca="excelente")]})
        assert items[0].confidence is Confidence.BAIXA
        assert not verdict.passed

    def test_accepts_bare_list(self, gate: FactGate) -> None:
        items = gate.parse([item(), item(id="a2")])
        assert len(items) == 2

    def test_ignores_non_dict_entries(self, gate: FactGate) -> None:
        items = gate.parse({"itens": [item(), "lixo", None, 42]})
        assert len(items) == 1


class TestDowngrade:
    """O modelo escreve o roteiro e o proprio relatorio — tem incentivo a se aprovar."""

    def test_unsourced_claim_is_downgraded_to_low(self, gate: FactGate) -> None:
        items = gate.downgrade_unsourced(gate.parse({"itens": [item(fontes=[])]}))
        assert items[0].confidence is Confidence.BAIXA
        assert "sem fonte" in (items[0].justification or "")
        assert not gate.evaluate(items).passed

    def test_high_with_single_source_becomes_medium(self, gate: FactGate) -> None:
        items = gate.downgrade_unsourced(gate.parse({"itens": [item(fontes=["https://a.edu"])]}))
        assert items[0].confidence is Confidence.MEDIA
        #  Media nao bloqueia: rebaixar nao e reprovar.
        assert gate.evaluate(items).passed

    def test_sources_threshold_comes_from_config(self) -> None:
        strict = FactGate(FactsConfig(blocks_on=("baixa",), max_rewrites=2, sources_for_high=3))
        items = strict.downgrade_unsourced(strict.parse({"itens": [item()]}))
        assert items[0].confidence is Confidence.MEDIA

    def test_already_low_is_left_alone(self, gate: FactGate) -> None:
        original = gate.parse({"itens": [item(confianca="baixa", fontes=[])]})
        adjusted = gate.downgrade_unsourced(original)
        assert adjusted[0].justification == original[0].justification

    def test_downgrade_preserves_other_fields(self, gate: FactGate) -> None:
        items = gate.downgrade_unsourced(
            gate.parse({"itens": [item(fontes=[], bloco=3, correcao_sugerida="reescrever")]})
        )
        assert items[0].block_index == 3
        assert items[0].suggested_fix == "reescrever"


class TestPolicy:
    def test_blocking_levels_come_from_config(self) -> None:
        """Politica configuravel — mas o padrao bloqueia em 'baixa'."""
        strict = FactGate(
            FactsConfig(blocks_on=("baixa", "media"), max_rewrites=2, sources_for_high=2)
        )
        _, verdict = strict.check({"itens": [item(confianca="media", fontes=["https://a.edu"])]})
        assert not verdict.passed

    def test_default_config_blocks_on_low(self, settings) -> None:
        """O YAML entregue no repositorio bloqueia em baixa. Nao afrouxar."""
        assert "baixa" in settings.facts.blocks_on


def test_item_from_dict_defaults_to_low_when_missing() -> None:
    parsed = FactCheckItem.from_dict({}, fallback_id="a9")
    assert parsed.confidence is Confidence.BAIXA
    assert parsed.id == "a9"
    assert parsed.sources == ()


def test_single_source_string_is_accepted() -> None:
    parsed = FactCheckItem.from_dict({"fontes": "https://a.edu", "confianca": "media"})
    assert parsed.sources == ("https://a.edu",)
