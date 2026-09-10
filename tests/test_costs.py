"""Registrador de custos e teto de orcamento (ADR 0003).

O que estes testes protegem: que a trava esteja *antes* da chamada, nao depois.
Um teto que so avisa nao e um teto.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from mundoantigo.config import BudgetConfig
from mundoantigo.costs import CostRecorder, PriceTable, Usage, month_key
from mundoantigo.errors import BudgetExceeded, UnknownPrice


def make_recorder(sessions, prices, **overrides) -> CostRecorder:
    budget = BudgetConfig(
        soft_limit_usd=overrides.get("soft", 35.0),
        hard_limit_usd=overrides.get("hard", 50.0),
        per_video_limit_usd=overrides.get("per_video", 5.0),
        unknown_model=overrides.get("unknown", "strict"),
    )
    return CostRecorder(budget, prices, sessions)


class TestPricing:
    def test_token_price_matches_table(self, prices: PriceTable) -> None:
        price = prices.require("openrouter", "anthropic/claude-sonnet-5")
        #  1M entrada a 3.00 + 1M saida a 15.00
        amount = price.amount_usd(Usage(input_tokens=1_000_000, output_tokens=1_000_000))
        assert amount == pytest.approx(18.0)

    def test_per_thousand_characters(self, prices: PriceTable) -> None:
        price = prices.require("elevenlabs", "eleven_multilingual_v2")
        #  12 mil caracteres, o tamanho de um roteiro, a US$ 0.18/1k
        assert price.amount_usd(Usage(characters=12_000)) == pytest.approx(2.16)

    def test_local_provider_is_free(self, prices: PriceTable) -> None:
        price = prices.require("local", "black-forest-labs/FLUX.1-schnell")
        assert price.is_free
        assert price.amount_usd(Usage(images=90)) == 0.0

    def test_unknown_model_blocks_in_strict_mode(self, prices: PriceTable) -> None:
        with pytest.raises(UnknownPrice, match=re.escape("precos.yaml")):
            prices.require("openrouter", "modelo/que-nao-existe", strict=True)

    def test_unknown_model_allowed_when_not_strict(self, prices: PriceTable) -> None:
        price = prices.require("openrouter", "modelo/que-nao-existe", strict=False)
        assert price.amount_usd(Usage(queries=10)) == 0.0


class TestRecording:
    def test_guard_records_actual_usage(self, sessions, prices, make_video) -> None:
        recorder = make_recorder(sessions, prices)
        make_video("v1")
        with recorder.guard(
            step="roteiro",
            provider="openrouter",
            model="anthropic/claude-sonnet-5",
            video_id="v1",
        ) as charge:
            charge.record(input_tokens=20_000, output_tokens=6_000)

        #  20k * 3/1M + 6k * 15/1M = 0.06 + 0.09
        assert recorder.spent_on_video("v1") == pytest.approx(0.15)
        assert recorder.spent_this_month() == pytest.approx(0.15)

    def test_local_call_recorded_at_zero(self, sessions, prices, make_video) -> None:
        recorder = make_recorder(sessions, prices)
        make_video("v1")
        with recorder.guard(
            step="assets",
            provider="local",
            model="black-forest-labs/FLUX.1-schnell",
            video_id="v1",
        ) as charge:
            charge.record(images=90)

        assert recorder.spent_on_video("v1") == 0.0
        #  Registrado mesmo custando zero: e assim que se mede volume local.
        steps = dict((s, n) for s, _, n in recorder.breakdown_by_step())
        assert steps["assets"] == 1

    def test_cost_recorded_even_when_call_raises(self, sessions, prices, make_video) -> None:
        """Provedor cobra por chamada feita, nao por chamada bem-sucedida."""
        recorder = make_recorder(sessions, prices)
        make_video("v1")
        with (
            pytest.raises(RuntimeError),
            recorder.guard(
                step="narracao",
                provider="elevenlabs",
                model="eleven_multilingual_v2",
                video_id="v1",
            ) as charge,
        ):
            charge.record(characters=5_000)
            raise RuntimeError("conexao caiu depois de enviar")

        assert recorder.spent_on_video("v1") == pytest.approx(0.9)

    def test_breakdown_by_step_and_video(self, sessions, prices, make_video) -> None:
        recorder = make_recorder(sessions, prices)
        for video, chars in (("v1", 10_000), ("v2", 4_000)):
            make_video(video)
            with recorder.guard(
                step="narracao", provider="fish", model="s2-pro", video_id=video
            ) as charge:
                charge.record(characters=chars)

        by_video = dict(recorder.breakdown_by_video())
        assert by_video["v1"] == pytest.approx(0.15)
        assert by_video["v2"] == pytest.approx(0.06)


class TestBudgetCap:
    def test_hard_limit_blocks_before_the_call(self, sessions, prices) -> None:
        """A chamada nao pode sair. Este e o teste central do ADR 0003."""
        recorder = make_recorder(sessions, prices, hard=1.0, per_video=100.0)
        with recorder.guard(
            step="roteiro", provider="openrouter", model="anthropic/claude-sonnet-5"
        ) as charge:
            charge.record(input_tokens=300_000, output_tokens=0)  # US$ 0,90

        called = False
        with (
            pytest.raises(BudgetExceeded) as exc,
            recorder.guard(
                step="roteiro",
                provider="openrouter",
                model="anthropic/claude-sonnet-5",
                estimate=Usage(input_tokens=100_000),
            ),
        ):
            called = True  # pragma: no cover - nao deve chegar aqui

        assert called is False, "a chamada rodou apesar do teto"
        assert exc.value.scope == "mes"
        assert exc.value.limit_usd == 1.0

    def test_per_video_limit_is_independent(self, sessions, prices, make_video) -> None:
        recorder = make_recorder(sessions, prices, hard=100.0, per_video=1.0)
        make_video("caro")
        make_video("barato")
        with recorder.guard(
            step="narracao",
            provider="elevenlabs",
            model="eleven_multilingual_v2",
            video_id="caro",
        ) as charge:
            charge.record(characters=5_000)  # US$ 0,90

        with (
            pytest.raises(BudgetExceeded, match="video caro"),
            recorder.guard(
                step="narracao",
                provider="elevenlabs",
                model="eleven_multilingual_v2",
                video_id="caro",
                estimate=Usage(characters=5_000),
            ),
        ):
            pass

        #  Outro video continua livre: o teto e por video, nao global.
        with recorder.guard(
            step="narracao",
            provider="elevenlabs",
            model="eleven_multilingual_v2",
            video_id="barato",
            estimate=Usage(characters=1_000),
        ) as charge:
            charge.record(characters=1_000)
        assert recorder.spent_on_video("barato") == pytest.approx(0.18)

    def test_local_provider_never_blocked_by_budget(self, sessions, prices, make_video) -> None:
        """Teto atingido bloqueia o pago; o local segue (ADR 0003)."""
        recorder = make_recorder(sessions, prices, hard=0.01, per_video=0.01)
        make_video("v1")
        with recorder.guard(
            step="roteiro", provider="openrouter", model="anthropic/claude-sonnet-5"
        ) as charge:
            charge.record(input_tokens=100_000, output_tokens=0)  # estoura

        with recorder.guard(
            step="assets",
            provider="local",
            model="black-forest-labs/FLUX.1-schnell",
            video_id="v1",
            estimate=Usage(images=90),
        ) as charge:
            charge.record(images=90)
        assert recorder.spent_on_video("v1") == 0.0

    def test_status_thresholds(self, sessions, prices) -> None:
        recorder = make_recorder(sessions, prices, soft=1.0, hard=2.0)
        assert not recorder.status().over_soft

        with recorder.guard(
            step="roteiro", provider="openrouter", model="anthropic/claude-sonnet-5"
        ) as charge:
            charge.record(input_tokens=400_000, output_tokens=0)  # US$ 1,20

        status = recorder.status()
        assert status.over_soft and not status.over_hard
        assert status.remaining_usd == pytest.approx(0.8)
        assert status.percent == pytest.approx(60.0)


def test_month_key_is_calendar_month_utc() -> None:
    assert month_key(datetime(2026, 9, 1, 0, 0, tzinfo=UTC)) == "2026-09"
    assert month_key(datetime(2026, 9, 30, 23, 59, tzinfo=UTC)) == "2026-09"
    assert month_key(datetime(2026, 10, 1, 0, 0, tzinfo=UTC)) == "2026-10"


def test_orphan_cost_is_recorded_without_link(sessions, prices, caplog) -> None:
    """Gasto de uma producao inexistente nao pode sumir.

    A chamada paga ja saiu quando a gravacao acontece; perder a linha para
    proteger uma chave estrangeira seria trocar dinheiro por integridade.
    """
    recorder = make_recorder(sessions, prices)
    with recorder.guard(
        step="pesquisa", provider="brave", model="search", video_id="producao-que-nao-existe"
    ) as charge:
        charge.record(queries=4)

    assert recorder.spent_this_month() == pytest.approx(0.02)

    from sqlalchemy import select

    from mundoantigo.db.models import CostEntry

    with sessions() as s:
        entry = s.execute(select(CostEntry)).scalars().one()
    assert entry.video_id is None
    assert entry.detail["video_id_orfao"] == "producao-que-nao-existe"
