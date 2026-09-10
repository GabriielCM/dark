"""Runner e worker.

Executa uma etapa reservada e traduz o resultado em estado de fila. A regra do
ADR 0002 vive aqui: antes de executar, conferir se os artefatos ja existem — se
existem, marcar concluida sem gastar um centavo.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..artifacts import ArtifactStore
from ..config import Settings, get_settings
from ..costs import CostRecorder, PriceTable
from ..db.models import Confidence, FactItem, StepState, Video, VideoState
from ..db.session import get_sessionmaker
from ..errors import (
    BudgetExceeded,
    FactGateBlocked,
    MundoAntigoError,
    PermanentError,
)
from ..prompts import PromptRegistry, get_prompts
from ..providers import ProviderRegistry
from .context import StepContext, StepResult
from .queue import ClaimedStep, StepQueue
from .state import StepName
from .steps import build

log = logging.getLogger(__name__)


@dataclass
class Runner:
    """Executa etapas. Nao decide o que rodar — isso e da fila."""

    settings: Settings
    queue: StepQueue
    costs: CostRecorder
    providers: ProviderRegistry
    prompts: PromptRegistry
    session_factory: sessionmaker[Session]

    @classmethod
    def build(
        cls,
        *,
        settings: Settings | None = None,
        providers: ProviderRegistry | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> Runner:
        cfg = settings or get_settings()
        sessions = session_factory or get_sessionmaker()
        costs = CostRecorder(cfg.budget, PriceTable.from_yaml(), sessions)
        return cls(
            settings=cfg,
            queue=StepQueue(cfg.queue, sessions),
            costs=costs,
            providers=providers or ProviderRegistry(settings=cfg, costs=costs),
            prompts=get_prompts(),
            session_factory=sessions,
        )

    def context_for(self, claimed: ClaimedStep) -> StepContext:
        store = ArtifactStore(claimed.video_id)
        store.ensure()
        return StepContext(
            video_id=claimed.video_id,
            topic=claimed.topic,
            pillar=claimed.pillar,
            settings=self.settings,
            providers=self.providers,
            prompts=self.prompts,
            costs=self.costs,
            store=store,
            step_run_id=claimed.step_run_id,
            book_id=claimed.book_id,
            book_chapter=claimed.book_chapter,
        )

    async def run_claimed(self, claimed: ClaimedStep) -> StepResult:
        step = build(claimed.step_name)
        ctx = self.context_for(claimed)

        #  A checagem que faz a retomada nao custar dinheiro (ADR 0002).
        if step.is_satisfied(ctx):
            log.info(
                "%s/%s ja tem artefatos completos — pulando sem gastar",
                claimed.video_id,
                claimed.step_name.value,
            )
            result = StepResult.done(summary="artefatos ja existiam; etapa retomada sem custo")
            self.queue.mark_done(claimed.step_run_id, summary=result.summary, skipped=True)
            return result

        try:
            result = await step.run(ctx)
        except BudgetExceeded as exc:
            #  Teto atingido: bloqueia em vez de falhar. O trabalho ja pago fica
            #  no disco e a producao retoma quando o mes virar (ADR 0003).
            self.queue.mark_blocked(claimed.step_run_id, str(exc))
            return StepResult.blocked(str(exc))
        except FactGateBlocked as exc:
            self.queue.mark_blocked(claimed.step_run_id, str(exc))
            return StepResult.blocked(str(exc))
        except PermanentError as exc:
            log.error(
                "%s/%s falhou permanentemente: %s", claimed.video_id, claimed.step_name.value, exc
            )
            self.queue.mark_failed(
                claimed.step_run_id, str(exc), kind=type(exc).__name__, permanent=True
            )
            raise
        except (MundoAntigoError, OSError, ValueError, KeyError) as exc:
            log.warning("%s/%s falhou: %s", claimed.video_id, claimed.step_name.value, exc)
            self.queue.mark_failed(claimed.step_run_id, str(exc), kind=type(exc).__name__)
            return StepResult(ok=False, summary=str(exc))

        self._persist_side_effects(claimed, ctx, result)

        if result.needs_human:
            self.queue.mark_blocked(
                claimed.step_run_id, result.blocked_reason or result.summary, data=result.data
            )
        else:
            self.queue.mark_done(claimed.step_run_id, summary=result.summary, data=result.data)
        return result

    def _persist_side_effects(
        self, claimed: ClaimedStep, ctx: StepContext, result: StepResult
    ) -> None:
        """Grava no banco o que o painel precisa consultar sem abrir arquivos."""
        items = ctx.scratch.get("fact_items")
        if items:
            self._store_facts(claimed.video_id, items)

        titles = ctx.scratch.get("titles")
        if titles:
            with self.session_factory() as s:
                video = s.get(Video, claimed.video_id)
                if video is not None:
                    video.title_pt = titles.get("pt-br") or video.title_pt
                    video.title_en = titles.get("en") or video.title_en
                    s.commit()

    def _store_facts(self, video_id: str, items: list[Any]) -> None:
        with self.session_factory() as s:
            existing = (
                s.query(FactItem)
                .filter(FactItem.video_id == video_id)
                .order_by(FactItem.revision.desc())
                .first()
            )
            revision = (existing.revision + 1) if existing else 1
            for item in items:
                s.add(
                    FactItem(
                        video_id=video_id,
                        revision=revision,
                        claim_id=item.id,
                        claim=item.claim,
                        block_index=item.block_index,
                        sources=list(item.sources),
                        confidence=Confidence(item.confidence.value),
                        justification=item.justification,
                        suggested_fix=item.suggested_fix,
                    )
                )
            s.commit()

    # -- acoes do painel ---------------------------------------------------

    def approve(self, video_id: str, *, reviewer: str = "humano") -> None:
        """Aprova o corte final. Destrava a etapa de entrega."""
        store = ArtifactStore(video_id)
        store.write_json(
            "entrega",
            "aprovacao.json",
            {
                "aprovado": True,
                "revisor": reviewer,
                "em": datetime.now(UTC).isoformat(),
            },
            step="revisao",
        )
        with self.session_factory() as s:
            video = s.get(Video, video_id)
            if video is not None:
                video.reviewed_at = datetime.now(UTC)
                video.review_rejection_reason = None
                video.blocked_reason = None
                s.commit()
        self.queue.unblock(video_id, StepName.REVISAO)

    def reject(
        self, video_id: str, reason: str, *, redo_from: StepName | str = StepName.ROTEIRO
    ) -> None:
        """Rejeita informando o motivo (brief 3.5) e reenfileira a partir da etapa escolhida."""
        with self.session_factory() as s:
            video = s.get(Video, video_id)
            if video is not None:
                video.review_rejection_reason = reason
                video.reviewed_at = datetime.now(UTC)
                s.commit()
        store = ArtifactStore(video_id)
        store.write_json(
            "entrega",
            "rejeicao.json",
            {
                "aprovado": False,
                "motivo": reason,
                "refazer_a_partir_de": StepName(redo_from).value,
                "em": datetime.now(UTC).isoformat(),
            },
            step="revisao",
        )
        #  Apaga os artefatos da etapa alvo em diante seria destrutivo demais
        #  sem confirmacao: aqui so a fila e reposicionada. O painel oferece
        #  "refazer etapa", que apaga o diretorio explicitamente.
        self.queue.reset_step(video_id, redo_from)


class Worker:
    """Laco do worker: reserva, executa, repete."""

    def __init__(self, runner: Runner, *, poll_seconds: float = 5.0) -> None:
        self.runner = runner
        self.poll_seconds = poll_seconds
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    async def run_once(self) -> bool:
        """Executa no maximo uma etapa. Devolve True se fez algo."""
        claimed = self.runner.queue.claim_next()
        if claimed is None:
            return False
        log.info("executando %s/%s", claimed.video_id, claimed.step_name.value)
        #  Falha permanente ja foi registrada na fila pelo runner; o laco
        #  segue para a proxima producao em vez de derrubar o worker.
        with contextlib.suppress(PermanentError):
            await self.runner.run_claimed(claimed)
        return True

    async def run_forever(self, *, max_iterations: int | None = None) -> int:
        executed = 0
        iterations = 0
        while not self._stopping:
            if max_iterations is not None and iterations >= max_iterations:
                break
            iterations += 1
            did_work = await self.run_once()
            if did_work:
                executed += 1
            else:
                await asyncio.sleep(self.poll_seconds)
        return executed

    async def drain(self, *, limit: int = 100) -> int:
        """Executa ate a fila nao ter mais nada pronto. Usado em testes e no CLI."""
        executed = 0
        for _ in range(limit):
            if not await self.run_once():
                break
            executed += 1
        return executed


def video_progress(session_factory: sessionmaker[Session], video_id: str) -> dict[str, Any]:
    """Resumo do andamento de uma producao, para o painel."""
    from .state import PIPELINE

    with session_factory() as s:
        video = s.get(Video, video_id)
        if video is None:
            return {}
        by_name = {st.name: st for st in video.steps}
        steps = []
        for st_spec in PIPELINE:
            record = by_name.get(st_spec.name.value)
            steps.append(
                {
                    "nome": st_spec.name.value,
                    "ordem": st_spec.ordinal,
                    "estado": record.state.value if record else StepState.PENDING.value,
                    "tentativas": record.attempts if record else 0,
                    "resumo": (record.result or {}).get("resumo") if record else None,
                    "dados": (record.result or {}).get("dados") or {} if record else {},
                    "erro": record.error if record else None,
                    "duracao_s": record.duration_s if record else None,
                    "gasta": st_spec.can_spend,
                }
            )
        done = sum(1 for st in steps if st["estado"] in ("done", "skipped"))
        return {
            "video_id": video.id,
            "tema": video.topic,
            "estado": video.state.value,
            "concluido": video.state is VideoState.ENTREGUE,
            "bloqueio": video.blocked_reason,
            "progresso": round(done / len(PIPELINE) * 100),
            "etapas": steps,
        }
