"""Registrador de custos com teto de orcamento (ADR 0003).

O ponto inteiro deste modulo: a trava fica no ponto de chamada, nao na revisao
posterior. Um teto que so avisa nao e um teto.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..config import BudgetConfig
from ..db.models import CostEntry
from ..db.session import get_sessionmaker
from ..errors import BudgetExceeded
from .pricing import PriceTable, Usage

log = logging.getLogger(__name__)


def month_key(when: datetime | None = None) -> str:
    """Mes de calendario em UTC. Simples de explicar, simples de testar."""
    ts = when or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).strftime("%Y-%m")


@dataclass
class PendingCharge:
    """Handle entregue pelo `guard`. O adaptador informa aqui o que consumiu."""

    step: str
    provider: str
    model: str
    video_id: str | None
    step_run_id: int | None
    usage: Usage = field(default_factory=Usage)
    _recorded: bool = False

    def record(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        images: int = 0,
        characters: int = 0,
        minutes: float = 0.0,
        queries: int = 0,
    ) -> None:
        """Informa o consumo real. Sobrescreve a estimativa."""
        self.usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            images=images,
            characters=characters,
            minutes=minutes,
            queries=queries,
        )
        self._recorded = True


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    month: str
    spent_usd: float
    soft_limit_usd: float
    hard_limit_usd: float

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.hard_limit_usd - self.spent_usd)

    @property
    def over_soft(self) -> bool:
        return self.spent_usd >= self.soft_limit_usd

    @property
    def over_hard(self) -> bool:
        return self.spent_usd >= self.hard_limit_usd

    @property
    def percent(self) -> float:
        if self.hard_limit_usd <= 0:
            return 0.0
        return min(100.0, self.spent_usd / self.hard_limit_usd * 100)


class CostRecorder:
    """Unico caminho pelo qual uma chamada paga pode acontecer."""

    def __init__(
        self,
        budget: BudgetConfig,
        prices: PriceTable,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.budget = budget
        self.prices = prices
        self._sessions = session_factory or get_sessionmaker()

    # -- consultas ---------------------------------------------------------

    def spent_this_month(self, when: datetime | None = None) -> float:
        with self._sessions() as s:
            total = s.execute(
                select(func.coalesce(func.sum(CostEntry.amount_usd), 0.0)).where(
                    CostEntry.month_key == month_key(when)
                )
            ).scalar_one()
        return float(total)

    def spent_on_video(self, video_id: str) -> float:
        with self._sessions() as s:
            total = s.execute(
                select(func.coalesce(func.sum(CostEntry.amount_usd), 0.0)).where(
                    CostEntry.video_id == video_id
                )
            ).scalar_one()
        return float(total)

    def status(self, when: datetime | None = None) -> BudgetStatus:
        return BudgetStatus(
            month=month_key(when),
            spent_usd=self.spent_this_month(when),
            soft_limit_usd=self.budget.soft_limit_usd,
            hard_limit_usd=self.budget.hard_limit_usd,
        )

    def breakdown_by_step(self, *, month: str | None = None) -> list[tuple[str, float, int]]:
        key = month or month_key()
        with self._sessions() as s:
            rows = s.execute(
                select(
                    CostEntry.step,
                    func.sum(CostEntry.amount_usd),
                    func.count(CostEntry.id),
                )
                .where(CostEntry.month_key == key)
                .group_by(CostEntry.step)
                .order_by(func.sum(CostEntry.amount_usd).desc())
            ).all()
        return [(str(r[0]), float(r[1] or 0.0), int(r[2])) for r in rows]

    def breakdown_by_video(self, *, month: str | None = None) -> list[tuple[str, float]]:
        key = month or month_key()
        with self._sessions() as s:
            rows = s.execute(
                select(CostEntry.video_id, func.sum(CostEntry.amount_usd))
                .where(CostEntry.month_key == key, CostEntry.video_id.is_not(None))
                .group_by(CostEntry.video_id)
                .order_by(func.sum(CostEntry.amount_usd).desc())
            ).all()
        return [(str(r[0]), float(r[1] or 0.0)) for r in rows]

    # -- trava -------------------------------------------------------------

    def check_affordable(
        self,
        *,
        estimated_usd: float,
        video_id: str | None = None,
        when: datetime | None = None,
    ) -> None:
        """Levanta `BudgetExceeded` se a chamada nao couber. Nao registra nada."""
        if estimated_usd <= 0:
            return  # Provedor local: sempre cabe.

        spent = self.spent_this_month(when)
        if spent + estimated_usd > self.budget.hard_limit_usd:
            raise BudgetExceeded("mes", spent + estimated_usd, self.budget.hard_limit_usd)

        if video_id is not None:
            per_video = self.spent_on_video(video_id)
            if per_video + estimated_usd > self.budget.per_video_limit_usd:
                raise BudgetExceeded(
                    f"video {video_id}",
                    per_video + estimated_usd,
                    self.budget.per_video_limit_usd,
                )

        if spent >= self.budget.soft_limit_usd:
            log.warning(
                "orcamento acima do aviso: US$ %.2f de US$ %.2f no mes %s",
                spent,
                self.budget.hard_limit_usd,
                month_key(when),
            )

    @contextmanager
    def guard(
        self,
        *,
        step: str,
        provider: str,
        model: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
        estimate: Usage | None = None,
    ) -> Iterator[PendingCharge]:
        """Envolve uma chamada de provedor.

        Antes: valida preco e teto. Depois: grava a linha em `cost_entries`.
        Se o bloco levantar excecao, o custo *estimado* e registrado mesmo
        assim quando o adaptador ja tinha chamado `record` — uma chamada que
        falhou depois de sair da rede pode ter sido cobrada.
        """
        price = self.prices.require(provider, model, strict=self.budget.strict_unknown_model)

        estimated_usd = price.amount_usd(estimate) if estimate else 0.0
        self.check_affordable(estimated_usd=estimated_usd, video_id=video_id)

        charge = PendingCharge(
            step=step,
            provider=provider,
            model=model,
            video_id=video_id,
            step_run_id=step_run_id,
            usage=estimate or Usage(),
        )
        try:
            yield charge
        finally:
            #  Registra mesmo em caso de erro: provedor cobra por chamada feita,
            #  nao por chamada bem-sucedida.
            if charge._recorded or estimated_usd > 0:
                self._persist(charge, price)

    def _persist(self, charge: PendingCharge, price_obj: object) -> None:
        from .pricing import Price  # local: evita import circular no topo

        price = price_obj if isinstance(price_obj, Price) else None
        if price is None:  # pragma: no cover - defensivo
            return
        amount = price.amount_usd(charge.usage)
        entry = CostEntry(
            month_key=month_key(),
            step=charge.step,
            provider=charge.provider,
            model=charge.model,
            unit=price.unit,
            quantity=charge.usage.quantity_for(price.unit),
            detail=charge.usage.as_detail() or None,
            amount_usd=round(amount, 6),
            local=price.is_free,
            video_id=charge.video_id,
            step_run_id=charge.step_run_id,
        )
        self._insert(entry)
        log.info(
            "custo %s/%s etapa=%s video=%s US$ %.6f",
            charge.provider,
            charge.model,
            charge.step,
            charge.video_id,
            amount,
        )

    def _insert(self, entry: CostEntry) -> None:
        """Grava a linha de custo. Nunca perde o registro.

        A chave estrangeira para `videos` protege a integridade no uso normal,
        onde a producao existe antes de qualquer gasto. Mas se ela falhar
        *depois* de uma chamada paga ter saido, o dinheiro ja foi e o registro
        se perderia — o oposto do que o ADR 0003 exige. Entao a falha de chave
        rebaixa o vinculo em vez de descartar a linha.
        """
        try:
            with self._sessions() as s:
                s.add(entry)
                s.commit()
            return
        except IntegrityError:
            log.warning(
                "custo de %s/%s referencia video inexistente (%s); "
                "registrando sem vinculo para nao perder o gasto",
                entry.provider,
                entry.model,
                entry.video_id,
            )

        orphan = CostEntry(
            created_at=entry.created_at,
            month_key=entry.month_key,
            step=entry.step,
            provider=entry.provider,
            model=entry.model,
            unit=entry.unit,
            quantity=entry.quantity,
            detail={**(entry.detail or {}), "video_id_orfao": entry.video_id},
            amount_usd=entry.amount_usd,
            local=entry.local,
            video_id=None,
            step_run_id=entry.step_run_id,
        )
        with self._sessions() as s:
            s.add(orphan)
            s.commit()
