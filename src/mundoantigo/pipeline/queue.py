"""Fila de etapas em SQLite (ADR 0002).

Isolada de proposito: se um dia houver mais de uma maquina, esta e a peca a
trocar, e nada fora daqui sabe como a fila e implementada.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session, sessionmaker

from ..config import QueueConfig
from ..db.models import StepRecord, StepState, TopicSource, Video, VideoState
from ..db.session import get_sessionmaker
from .state import PIPELINE, STEP_TO_VIDEO_STATE, StepName, dependencies_met, spec

log = logging.getLogger(__name__)

#  Uma etapa `skipped` foi retomada do disco: os artefatos existem e ela esta
#  tao concluida quanto uma `done`. Contar so `done` aqui trava a retomada na
#  primeira etapa (ADR 0002).
COMPLETED_STATES = (StepState.DONE, StepState.SKIPPED)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def slugify(text: str, *, max_length: int = 48) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug[:max_length].strip("-") or "sem-tema"


def make_video_id(topic: str, when: datetime | None = None) -> str:
    ts = (when or datetime.now(UTC)).strftime("%Y%m%d-%H%M")
    return f"{ts}-{slugify(topic)}"


@dataclass(frozen=True, slots=True)
class ClaimedStep:
    """Uma etapa reservada por este worker."""

    video_id: str
    step_name: StepName
    step_run_id: int
    topic: str
    pillar: str
    attempts: int
    book_id: str | None
    book_chapter: int | None


class StepQueue:
    def __init__(
        self,
        config: QueueConfig,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.config = config
        self._sessions = session_factory or get_sessionmaker()

    # -- criacao -----------------------------------------------------------

    def enqueue_video(
        self,
        topic: str,
        *,
        pillar: str = "engenharia",
        video_id: str | None = None,
        source: TopicSource = TopicSource.MANUAL,
        book_id: str | None = None,
        book_chapter: int | None = None,
        priority: int = 0,
    ) -> str:
        """Cria a producao e as doze linhas de etapa, todas `pending`."""
        vid = video_id or make_video_id(topic)
        with self._sessions() as s:
            if s.get(Video, vid) is not None:
                #  Reenfileirar um id existente e quase sempre engano de digitacao.
                raise ValueError(f"producao {vid} ja existe")
            video = Video(
                id=vid,
                topic=topic,
                pillar=pillar,
                source=source,
                state=VideoState.PAUTA,
                book_id=book_id,
                book_chapter=book_chapter,
                priority=priority,
            )
            video.steps = [
                StepRecord(video_id=vid, name=st.name.value, ordinal=st.ordinal) for st in PIPELINE
            ]
            s.add(video)
            s.commit()
        log.info("producao enfileirada: %s (%s)", vid, topic[:60])
        return vid

    # -- reserva -----------------------------------------------------------

    def reclaim_expired(self) -> int:
        """Devolve para `pending` as etapas cujo lease venceu.

        E assim que uma queda do processo se recupera sozinha: sem lock file
        preso, sem intervencao (ADR 0002).
        """
        now = datetime.now(UTC)
        with self._sessions() as s:
            result = s.execute(
                update(StepRecord)
                .where(
                    StepRecord.state == StepState.RUNNING,
                    StepRecord.lease_until.is_not(None),
                    StepRecord.lease_until < now,
                )
                .values(state=StepState.PENDING, lease_until=None, worker_id=None)
            )
            s.commit()
            #  `rowcount` so existe no CursorResult que o UPDATE devolve.
            count = cast(CursorResult[Any], result).rowcount or 0
        if count:
            log.warning("%d etapa(s) com lease vencido voltaram para a fila", count)
        return count

    def claim_next(self, *, worker: str | None = None) -> ClaimedStep | None:
        """Reserva a proxima etapa executavel, ou None se nao houver.

        Ordem: prioridade da producao, depois a mais antiga. Dentro de uma
        producao, a primeira etapa cujas dependencias fecharam.
        """
        self.reclaim_expired()
        me = worker or worker_id()
        now = datetime.now(UTC)
        lease_until = now + timedelta(minutes=self.config.lease_minutes)

        with self._sessions() as s:
            running_videos = set(
                s.execute(select(StepRecord.video_id).where(StepRecord.state == StepState.RUNNING))
                .scalars()
                .all()
            )

            videos = (
                s.execute(
                    select(Video)
                    .where(
                        Video.state.not_in(
                            (VideoState.ENTREGUE, VideoState.REJEITADO, VideoState.ARQUIVADO)
                        )
                    )
                    .order_by(Video.priority.desc(), Video.created_at.asc())
                )
                .scalars()
                .all()
            )

            for video in videos:
                if (
                    video.id not in running_videos
                    and len(running_videos) >= self.config.max_concurrent_videos
                ):
                    continue

                steps = {StepName(st.name): st for st in video.steps}
                done = {name for name, st in steps.items() if st.state in COMPLETED_STATES}

                for st_spec in PIPELINE:
                    record = steps.get(st_spec.name)
                    if record is None or record.state is not StepState.PENDING:
                        continue
                    if not dependencies_met(st_spec.name, done):
                        continue
                    if record.run_after and record.run_after > now:
                        continue  # ainda em espera exponencial

                    record.state = StepState.RUNNING
                    record.worker_id = me
                    record.lease_until = lease_until
                    record.started_at = now
                    record.attempts += 1
                    video.state = STEP_TO_VIDEO_STATE[st_spec.name]
                    video.blocked_reason = None
                    s.commit()

                    log.info(
                        "reservada %s/%s (tentativa %d)",
                        video.id,
                        st_spec.name.value,
                        record.attempts,
                    )
                    return ClaimedStep(
                        video_id=video.id,
                        step_name=st_spec.name,
                        step_run_id=record.id,
                        topic=video.topic,
                        pillar=video.pillar,
                        attempts=record.attempts,
                        book_id=video.book_id,
                        book_chapter=video.book_chapter,
                    )
        return None

    def renew_lease(self, step_run_id: int) -> None:
        """Estende o lease de uma etapa longa (assets, montagem)."""
        with self._sessions() as s:
            record = s.get(StepRecord, step_run_id)
            if record and record.state is StepState.RUNNING:
                record.lease_until = datetime.now(UTC) + timedelta(
                    minutes=self.config.lease_minutes
                )
                s.commit()

    # -- conclusao ---------------------------------------------------------

    def mark_done(
        self,
        step_run_id: int,
        *,
        summary: str = "",
        data: dict[str, Any] | None = None,
        skipped: bool = False,
    ) -> None:
        now = datetime.now(UTC)
        with self._sessions() as s:
            record = s.get(StepRecord, step_run_id)
            if record is None:  # pragma: no cover - defensivo
                return
            record.state = StepState.SKIPPED if skipped else StepState.DONE
            record.finished_at = now
            record.lease_until = None
            record.worker_id = None
            record.error = None
            record.error_kind = None
            #  `dados` fica aninhado para que nenhuma chave da etapa possa
            #  sobrescrever o resumo em texto que o painel mostra.
            record.result = {"resumo": summary, "dados": data or {}}
            if record.started_at:
                #  UTCDateTime garante fuso na volta do banco; ver db/models.py.
                record.duration_s = (now - record.started_at).total_seconds()

            video = s.get(Video, record.video_id)
            if video is not None:
                self._advance_video(s, video)
            s.commit()

    def mark_blocked(
        self, step_run_id: int, reason: str, *, data: dict[str, Any] | None = None
    ) -> None:
        """Etapa esperando humano ou orcamento. Nao e falha.

        A etapa fica `blocked` e nao consome tentativas; sai desse estado por
        acao no painel (aprovar, rejeitar, refazer) ou quando o mes virar.
        """
        with self._sessions() as s:
            record = s.get(StepRecord, step_run_id)
            if record is None:  # pragma: no cover
                return
            record.state = StepState.BLOCKED
            record.finished_at = datetime.now(UTC)
            record.lease_until = None
            record.worker_id = None
            record.result = {"resumo": reason, "dados": data or {}}
            #  Bloqueio nao e tentativa gasta.
            record.attempts = max(0, record.attempts - 1)

            video = s.get(Video, record.video_id)
            if video is not None:
                video.blocked_reason = reason
            s.commit()
        log.info("etapa %s bloqueada: %s", step_run_id, reason)

    def mark_failed(
        self, step_run_id: int, error: str, *, kind: str = "", permanent: bool = False
    ) -> None:
        with self._sessions() as s:
            record = s.get(StepRecord, step_run_id)
            if record is None:  # pragma: no cover
                return
            record.error = error[:4000]
            record.error_kind = kind[:64] or type(error).__name__
            record.finished_at = datetime.now(UTC)
            record.lease_until = None
            record.worker_id = None

            exhausted = permanent or record.attempts >= self.config.max_attempts
            if exhausted:
                record.state = StepState.FAILED
                video = s.get(Video, record.video_id)
                if video is not None:
                    video.blocked_reason = f"etapa {record.name} falhou: {error[:200]}"
            else:
                record.state = StepState.PENDING
                index = min(record.attempts - 1, len(self.config.backoff_seconds) - 1)
                delay = self.config.backoff_seconds[max(index, 0)]
                record.run_after = datetime.now(UTC) + timedelta(seconds=delay)
                log.info(
                    "etapa %s vai retentar em %ds (tentativa %d de %d)",
                    record.name,
                    delay,
                    record.attempts,
                    self.config.max_attempts,
                )
            s.commit()

    # -- operacao ----------------------------------------------------------

    def unblock(self, video_id: str, step_name: StepName | str | None = None) -> int:
        """Devolve etapas bloqueadas para a fila. Usado pelo painel."""
        target = StepName(step_name).value if step_name else None
        with self._sessions() as s:
            query = select(StepRecord).where(
                StepRecord.video_id == video_id,
                StepRecord.state.in_((StepState.BLOCKED, StepState.FAILED)),
            )
            if target:
                query = query.where(StepRecord.name == target)
            records = list(s.execute(query).scalars().all())
            for record in records:
                record.state = StepState.PENDING
                record.attempts = 0
                record.run_after = None
                record.error = None
            video = s.get(Video, video_id)
            if video is not None:
                video.blocked_reason = None
            s.commit()
        return len(records)

    def reset_step(self, video_id: str, step_name: StepName | str) -> None:
        """Marca uma etapa e as seguintes como `pending`.

        Refazer uma etapa invalida o que veio depois dela; os artefatos no
        disco e que decidem o que sera realmente reexecutado (ADR 0002).
        """
        target = spec(step_name)
        with self._sessions() as s:
            records = (
                s.execute(select(StepRecord).where(StepRecord.video_id == video_id)).scalars().all()
            )
            for record in records:
                if record.ordinal >= target.ordinal:
                    record.state = StepState.PENDING
                    record.attempts = 0
                    record.run_after = None
                    record.error = None
                    record.result = None
            video = s.get(Video, video_id)
            if video is not None:
                video.state = STEP_TO_VIDEO_STATE[target.name]
                video.blocked_reason = None
            s.commit()

    @staticmethod
    def _advance_video(session: Session, video: Video) -> None:
        """Move o estado da producao para a proxima etapa ainda nao concluida."""
        steps = sorted(video.steps, key=lambda st: st.ordinal)
        for record in steps:
            if record.state not in COMPLETED_STATES:
                video.state = STEP_TO_VIDEO_STATE[StepName(record.name)]
                return
        video.state = VideoState.ENTREGUE

    # -- consultas ---------------------------------------------------------

    def pending_count(self) -> int:
        with self._sessions() as s:
            return len(
                s.execute(select(StepRecord.id).where(StepRecord.state == StepState.PENDING))
                .scalars()
                .all()
            )

    def has_work(self) -> bool:
        return self.claim_peek() is not None

    def claim_peek(self) -> StepName | None:
        """Ha etapa executavel agora? Nao reserva nada."""
        now = datetime.now(UTC)
        with self._sessions() as s:
            videos = (
                s.execute(
                    select(Video).where(
                        Video.state.not_in(
                            (VideoState.ENTREGUE, VideoState.REJEITADO, VideoState.ARQUIVADO)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for video in videos:
                steps = {StepName(st.name): st for st in video.steps}
                done = {n for n, st in steps.items() if st.state in COMPLETED_STATES}
                for st_spec in PIPELINE:
                    record = steps.get(st_spec.name)
                    if (
                        record is not None
                        and record.state is StepState.PENDING
                        and dependencies_met(st_spec.name, done)
                        and not (record.run_after and record.run_after > now)
                    ):
                        return st_spec.name
        return None
