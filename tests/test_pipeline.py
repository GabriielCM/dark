"""Fila, retomada e idempotencia (ADR 0002).

A promessa que estes testes protegem: "se algo falhar, o pipeline retoma da
ultima etapa concluida sem repetir chamadas pagas" (CLAUDE.md).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.db.models import StepRecord, StepState, Video, VideoState
from mundoantigo.pipeline import PIPELINE, StepName, StepQueue, slugify
from mundoantigo.pipeline.state import (
    dependencies_met,
    downstream,
    next_step,
    ready_steps,
    spec,
)
from mundoantigo.pipeline.steps import ALL_STEPS, STEP_BY_NAME


@pytest.fixture
def queue(settings, sessions) -> StepQueue:
    return StepQueue(settings.queue, sessions)


class TestStateMachine:
    def test_every_step_has_an_implementation(self) -> None:
        """Toda etapa do PIPELINE tem classe, e nenhuma classe sobra."""
        assert len(ALL_STEPS) == len(PIPELINE) == 17
        assert set(STEP_BY_NAME) == {s.name for s in PIPELINE}

    def test_ordinals_are_sequential(self) -> None:
        assert [s.ordinal for s in PIPELINE] == list(range(1, len(PIPELINE) + 1))

    def test_dependencies_point_backwards(self) -> None:
        """Uma etapa nunca depende de outra que vem depois dela."""
        for step in PIPELINE:
            for dep in (*step.depends_on, *step.waits_for):
                assert spec(dep).ordinal < step.ordinal, f"{step.name} depende do futuro"

    def test_storyboard_waits_for_the_narration(self) -> None:
        """As cenas sao cortadas pela duracao real das frases (ADR 0008)."""
        done = {s.name for s in PIPELINE if s.ordinal <= 5}
        assert set(ready_steps(done)) == {StepName.NARRACAO}
        done.add(StepName.NARRACAO)
        assert set(ready_steps(done)) == {StepName.CENAS, StepName.TRILHA}

    def test_soundtrack_runs_while_images_wait_for_review(self) -> None:
        done = {s.name for s in PIPELINE if s.ordinal <= 10}  # parado na revisao das imagens
        assert StepName.TRILHA in ready_steps(done)
        assert StepName.MONTAGEM not in ready_steps(done)

    def test_montage_waits_for_approved_images_and_the_soundtrack(self) -> None:
        assert set(spec(StepName.MONTAGEM).depends_on) == {
            StepName.REVISAO_IMAGENS,
            StepName.TRILHA,
        }
        done = {s.name for s in PIPELINE if s.name is not StepName.REVISAO_IMAGENS}
        done -= {StepName.MONTAGEM, StepName.METADADOS, StepName.REVISAO, StepName.ENTREGA}
        assert StepName.MONTAGEM not in ready_steps(done)

    def test_clips_come_after_the_montage_and_before_the_review(self) -> None:
        """Os cortes do TikTok (ADR 0010) saem depois do video inteiro."""
        cortes = spec(StepName.CORTES)
        assert set(cortes.depends_on) == {StepName.REVISAO_IMAGENS, StepName.TRILHA}
        assert cortes.waits_for == (StepName.MONTAGEM,)
        assert StepName.CORTES in spec(StepName.REVISAO).depends_on
        done = {s.name for s in PIPELINE if s.ordinal <= 13}
        assert StepName.CORTES not in ready_steps(done), "o video inteiro sai primeiro"
        done.add(StepName.MONTAGEM)
        assert StepName.CORTES in ready_steps(done)

    def test_redoing_the_montage_keeps_the_clips(self) -> None:
        assert StepName.CORTES not in downstream([StepName.MONTAGEM])
        assert StepName.CORTES in downstream([StepName.NARRACAO])
        assert StepName.CORTES in downstream([StepName.ASSETS])

    def test_both_human_gates_are_marked(self) -> None:
        gates = {s.name for s in PIPELINE if s.human_gate}
        assert {StepName.REVISAO_IMAGENS, StepName.REVISAO} <= gates

    def test_downstream_redoes_only_the_affected_branch(self) -> None:
        affected = downstream([StepName.NARRACAO])
        assert affected[0] is StepName.NARRACAO
        assert StepName.TRILHA in affected and StepName.MONTAGEM in affected
        assert StepName.CENAS not in affected, "refazer a voz nao pode refazer o storyboard"
        assert StepName.ASSETS not in affected, "refazer a voz nao pode refazer as imagens"
        assert downstream([StepName.ENTREGA]) == [StepName.ENTREGA]

    def test_render_requires_approved_fact_gate(self) -> None:
        """Nenhuma renderizacao sem gate aprovado (CLAUDE.md)."""
        done = {StepName.PAUTA, StepName.PESQUISA, StepName.ROTEIRO}
        assert not dependencies_met(StepName.ADAPTACAO_EN, done)
        assert not dependencies_met(StepName.MONTAGEM, done)

    def test_next_step_walks_to_the_end(self) -> None:
        current = StepName.PAUTA
        seen = [current]
        while (nxt := next_step(current)) is not None:
            seen.append(nxt)
            current = nxt
        assert len(seen) == len(PIPELINE)
        assert seen[-1] is StepName.ENTREGA


class TestQueueBasics:
    def test_enqueue_creates_all_steps(self, queue: StepQueue, sessions) -> None:
        video_id = queue.enqueue_video("Aquedutos romanos", pillar="engenharia")
        with sessions() as s:
            video = s.get(Video, video_id)
            assert len(video.steps) == len(PIPELINE)
            assert all(st.state is StepState.PENDING for st in video.steps)

    def test_video_id_is_readable(self, queue: StepQueue) -> None:
        video_id = queue.enqueue_video("Como os romanos faziam concreto")
        assert "como-os-romanos-faziam-concreto" in video_id

    def test_duplicate_id_is_refused(self, queue: StepQueue) -> None:
        queue.enqueue_video("Tema", video_id="fixo")
        with pytest.raises(ValueError, match="ja existe"):
            queue.enqueue_video("Outro tema", video_id="fixo")

    def test_claim_respects_dependency_order(self, queue: StepQueue) -> None:
        queue.enqueue_video("Tema")
        claimed = queue.claim_next()
        assert claimed is not None
        assert claimed.step_name is StepName.PAUTA
        #  Nada mais e reservavel: a etapa 2 depende da 1.
        assert queue.claim_next() is None

    def test_claim_advances_after_done(self, queue: StepQueue) -> None:
        queue.enqueue_video("Tema")
        first = queue.claim_next()
        queue.mark_done(first.step_run_id, summary="ok")
        second = queue.claim_next()
        assert second.step_name is StepName.PESQUISA

    def test_priority_wins_over_age(self, queue: StepQueue) -> None:
        queue.enqueue_video("Antigo", video_id="antigo")
        queue.enqueue_video("Urgente", video_id="urgente", priority=5)
        assert queue.claim_next().video_id == "urgente"

    def test_concurrency_limit_holds(self, queue: StepQueue) -> None:
        """max_videos_concorrentes = 1 no YAML: uma producao por vez."""
        queue.enqueue_video("A", video_id="a")
        queue.enqueue_video("B", video_id="b")
        first = queue.claim_next()
        assert queue.claim_next() is None
        queue.mark_done(first.step_run_id)
        assert queue.claim_next() is not None


class TestFailureAndRetry:
    def test_failure_reschedules_with_backoff(self, queue: StepQueue, sessions) -> None:
        queue.enqueue_video("Tema", video_id="v")
        claimed = queue.claim_next()
        queue.mark_failed(claimed.step_run_id, "rede caiu")

        with sessions() as s:
            record = s.get(StepRecord, claimed.step_run_id)
            assert record.state is StepState.PENDING
            assert record.run_after is not None
            assert record.attempts == 1
        #  Ainda em espera: nao pode ser reservada agora.
        assert queue.claim_next() is None

    def test_exhausted_attempts_become_failed(self, queue: StepQueue, sessions) -> None:
        queue.enqueue_video("Tema", video_id="v")
        for _ in range(3):  # max_attempts = 3
            claimed = queue.claim_next()
            if claimed is None:
                with sessions() as s:
                    s.get(StepRecord, 1).run_after = None
                    s.commit()
                claimed = queue.claim_next()
            queue.mark_failed(claimed.step_run_id, "falha")

        with sessions() as s:
            record = s.get(StepRecord, claimed.step_run_id)
            assert record.state is StepState.FAILED
            video = s.get(Video, "v")
            assert "falhou" in video.blocked_reason

    def test_permanent_failure_skips_retries(self, queue: StepQueue, sessions) -> None:
        queue.enqueue_video("Tema", video_id="v")
        claimed = queue.claim_next()
        queue.mark_failed(claimed.step_run_id, "chave invalida", permanent=True)
        with sessions() as s:
            assert s.get(StepRecord, claimed.step_run_id).state is StepState.FAILED

    def test_blocked_does_not_consume_attempts(self, queue: StepQueue, sessions) -> None:
        """Esperar humano ou orcamento nao e falha."""
        queue.enqueue_video("Tema", video_id="v")
        claimed = queue.claim_next()
        queue.mark_blocked(claimed.step_run_id, "gate de fatos reprovou")
        with sessions() as s:
            record = s.get(StepRecord, claimed.step_run_id)
            assert record.state is StepState.BLOCKED
            assert record.attempts == 0
            assert s.get(Video, "v").blocked_reason


class TestLeaseRecovery:
    """Queda do processo se recupera sozinha, sem lock file preso (ADR 0002)."""

    def test_expired_lease_returns_to_queue(self, queue: StepQueue, sessions) -> None:
        queue.enqueue_video("Tema", video_id="v")
        claimed = queue.claim_next()

        with sessions() as s:
            record = s.get(StepRecord, claimed.step_run_id)
            record.lease_until = datetime.now(UTC) - timedelta(minutes=1)
            s.commit()

        assert queue.reclaim_expired() == 1
        again = queue.claim_next()
        assert again is not None
        assert again.step_name is StepName.PAUTA
        assert again.attempts == 2

    def test_valid_lease_is_left_alone(self, queue: StepQueue) -> None:
        queue.enqueue_video("Tema", video_id="v")
        queue.claim_next()
        assert queue.reclaim_expired() == 0

    def test_step_of_a_dead_local_worker_returns_at_once(
        self, queue: StepQueue, sessions, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`esteira --parar` no meio das imagens: o lease ainda vale, o worker nao."""
        import socket

        from mundoantigo.ops import esteira

        queue.enqueue_video("Tema", video_id="v")
        claimed = queue.claim_next(worker=f"{socket.gethostname()}:424242")
        monkeypatch.setattr(esteira, "pid_alive", lambda pid: pid != 424242)

        assert queue.reclaim_expired() == 1
        with sessions() as s:
            assert s.get(StepRecord, claimed.step_run_id).state is StepState.PENDING

    def test_step_of_another_machine_waits_for_the_lease(
        self, queue: StepQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mundoantigo.ops import esteira

        queue.enqueue_video("Tema", video_id="v")
        queue.claim_next(worker="outra-maquina:424242")
        monkeypatch.setattr(esteira, "pid_alive", lambda pid: False)
        assert queue.reclaim_expired() == 0

    def test_renew_extends_the_lease(self, queue: StepQueue, sessions) -> None:
        """Etapas longas (assets, montagem) precisam disso."""
        queue.enqueue_video("Tema", video_id="v")
        claimed = queue.claim_next()
        with sessions() as s:
            #  Encurta o lease para provar que renovar de fato o estende.
            s.get(StepRecord, claimed.step_run_id).lease_until = datetime.now(UTC) + timedelta(
                seconds=5
            )
            s.commit()
        queue.renew_lease(claimed.step_run_id)
        with sessions() as s:
            after = s.get(StepRecord, claimed.step_run_id).lease_until
        assert after > datetime.now(UTC) + timedelta(minutes=25)


class TestReset:
    def test_reset_marks_step_and_everything_after(self, queue: StepQueue, sessions) -> None:
        video_id = queue.enqueue_video("Tema", video_id="v")
        for _ in range(4):
            claimed = queue.claim_next()
            queue.mark_done(claimed.step_run_id)

        queue.reset_step(video_id, StepName.ROTEIRO)
        with sessions() as s:
            states = {StepName(st.name): st.state for st in s.get(Video, "v").steps}
        assert states[StepName.PAUTA] is StepState.DONE
        assert states[StepName.PESQUISA] is StepState.DONE
        assert states[StepName.ROTEIRO] is StepState.PENDING
        assert states[StepName.GATE_FATOS] is StepState.PENDING

    def test_unblock_returns_blocked_steps(self, queue: StepQueue, sessions) -> None:
        queue.enqueue_video("Tema", video_id="v")
        claimed = queue.claim_next()
        queue.mark_blocked(claimed.step_run_id, "aguardando humano")
        assert queue.unblock("v") == 1
        with sessions() as s:
            assert s.get(StepRecord, claimed.step_run_id).state is StepState.PENDING
            assert s.get(Video, "v").blocked_reason is None

    def test_video_state_follows_first_unfinished_step(self, queue: StepQueue, sessions) -> None:
        queue.enqueue_video("Tema", video_id="v")
        for _ in range(3):
            queue.mark_done(queue.claim_next().step_run_id)
        with sessions() as s:
            assert s.get(Video, "v").state is VideoState.GATE_FATOS

    def test_all_steps_done_marks_delivered(self, queue: StepQueue, sessions) -> None:
        queue.enqueue_video("Tema", video_id="v")
        for _ in range(len(PIPELINE)):
            claimed = queue.claim_next()
            assert claimed is not None
            queue.mark_done(claimed.step_run_id)
        with sessions() as s:
            assert s.get(Video, "v").state is VideoState.ENTREGUE
        assert queue.claim_next() is None


class TestArtifactIdempotence:
    """A verdade esta nos arquivos; a fila so guarda estado (ADR 0002)."""

    def test_complete_requires_file_and_sidecar(self, tmp_project) -> None:
        store = ArtifactStore("v1")
        target = store.write_json("pauta", "pauta.json", {"tema": "x"})
        assert store.is_complete(target)

        store.sidecar_path(target).unlink()
        assert not store.is_complete(target), "sem sidecar nao conta como concluido"

    def test_empty_file_is_not_complete(self, tmp_project) -> None:
        store = ArtifactStore("v1")
        target = store.write_json("pauta", "pauta.json", {})
        target.write_text("")
        assert not store.is_complete(target)

    def test_corrupted_file_detected_with_hash_check(self, tmp_project) -> None:
        store = ArtifactStore("v1")
        target = store.write_text("roteiro", "r.json", '{"a": 1}')
        assert store.is_complete(target, verify_hash=True)
        target.write_text('{"a": 2}')
        assert not store.is_complete(target, verify_hash=True)

    def test_stale_is_flagged_not_rebuilt(self, tmp_project) -> None:
        """Mudar o prompt sinaliza, nao refaz — refazer gasta (ADR 0002)."""
        store = ArtifactStore("v1")
        target = store.write_json("roteiro", "r.json", {"a": 1}, input_hash="abc123")
        assert not store.is_stale(target, "abc123")
        assert store.is_stale(target, "def456")
        #  Continua "completo": defasado nao e incompleto.
        assert store.is_complete(target)

    def test_clear_stage_is_how_you_force_a_redo(self, tmp_project) -> None:
        store = ArtifactStore("v1")
        target = store.write_json("assets", "a.json", {})
        store.clear_stage("assets")
        assert not target.exists()

    def test_all_complete_is_false_for_empty_list(self, tmp_project) -> None:
        """Etapa que nao declara saidas nunca conta como pulavel."""
        assert not ArtifactStore("v1").all_complete([])


def test_slugify_handles_accents_and_punctuation() -> None:
    assert slugify("Aquedutos: a água que subia sozinha!") == "aquedutos-a-agua-que-subia-sozinha"
    assert slugify("") == "sem-tema"
    assert len(slugify("palavra " * 40)) <= 48
