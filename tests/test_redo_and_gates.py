"""Refacao por ramo, portoes humanos e manutencao da fila (fase B0).

O pipeline tem dois ramos depois da adaptacao EN (imagens e audio) e dois
portoes humanos (grade de imagens e corte final). Estes testes protegem as
regras que vieram com isso.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.db.models import StepRecord, StepState, Video, VideoState
from mundoantigo.pipeline import PIPELINE, Runner, StepName, Worker
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from tests.fakes import responder


def _runner(settings, recorder, sessions) -> Runner:
    llm = FakeLLM(costs=recorder, responses=responder())
    return Runner.build(
        settings=settings,
        providers=fake_registry(settings, recorder, llm=llm),
        session_factory=sessions,
    )


@pytest.fixture
def runner(settings, recorder, sessions, com_remotion) -> Runner:
    return _runner(settings, recorder, sessions)


async def drain(runner: Runner, limit: int = 60) -> int:
    return await Worker(runner, poll_seconds=0).drain(limit=limit)


def _counts(recorder) -> dict[str, int]:
    return {step: n for step, _, n in recorder.breakdown_by_step()}


class TestRedo:
    async def test_redoing_the_voice_keeps_the_images(self, runner, recorder, sessions) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        before = _counts(recorder)
        store = ArtifactStore(video_id)
        image = store.path("assets", "cena-001.png")
        image_bytes = image.read_bytes()

        affected = runner.redo(video_id, [StepName.NARRACAO], reason="voz rapida demais")
        assert StepName.ASSETS not in affected
        assert not store.path("narracao", "narracao.pt-br.wav").exists()
        assert image.read_bytes() == image_bytes, "refazer a voz apagou uma imagem"

        await drain(runner)
        after = _counts(recorder)
        assert after["narracao"] > before["narracao"]
        assert after["assets"] == before["assets"], "as imagens foram geradas de novo"
        with sessions() as s:
            assert s.get(Video, video_id).state is VideoState.REVISAO

    async def test_redo_keeps_the_reason_history(self, runner) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        runner.redo(video_id, [StepName.METADADOS], reason="titulo fraco")
        runner.redo(video_id, [StepName.METADADOS], reason="descricao longa")
        history = ArtifactStore(video_id).read_json("revisao", "rejeicoes.json")
        assert [h["motivo"] for h in history] == ["titulo fraco", "descricao longa"]


class TestImageGate:
    @pytest.fixture
    def gated(self, settings, recorder, sessions, com_remotion) -> Runner:
        app = {**settings.app, "revisao_imagens": {"ativo": True}}
        return _runner(dataclasses.replace(settings, app=app), recorder, sessions)

    async def test_render_waits_for_image_approval(self, gated, sessions) -> None:
        video_id = gated.queue.enqueue_video("Aquedutos romanos")
        await drain(gated)

        with sessions() as s:
            steps = {st.name: st.state for st in s.get(Video, video_id).steps}
        assert steps["revisao_imagens"] is StepState.BLOCKED
        assert steps["montagem"] is StepState.PENDING
        #  O ramo do audio seguiu enquanto a grade esperava.
        assert steps["narracao"] is StepState.DONE
        assert steps["trilha"] is StepState.DONE

        gated.approve(video_id, gate=StepName.REVISAO_IMAGENS, reviewer="teste")
        await drain(gated)
        with sessions() as s:
            assert s.get(Video, video_id).state is VideoState.REVISAO

        approval = ArtifactStore(video_id).read_json("revisao_imagens", "aprovacao.json")
        assert approval["revisor"] == "teste"
        assert "cena-001.png" in approval["imagens"]

    def test_only_human_gates_can_be_approved(self, gated) -> None:
        video_id = gated.queue.enqueue_video("X")
        with pytest.raises(ValueError, match="portao"):
            gated.approve(video_id, gate=StepName.ASSETS)


class TestQueueMaintenance:
    def test_sync_pipeline_adds_missing_steps(self, runner, sessions) -> None:
        video_id = runner.queue.enqueue_video("Producao antiga")
        with sessions() as s:
            s.query(StepRecord).filter(
                StepRecord.video_id == video_id, StepRecord.name == "trilha"
            ).delete()
            s.commit()

        assert runner.queue.sync_pipeline() == 1
        with sessions() as s:
            assert len(s.get(Video, video_id).steps) == len(PIPELINE)

    def test_reset_never_touches_a_running_step(self, runner, sessions) -> None:
        video_id = runner.queue.enqueue_video("X")
        claimed = runner.queue.claim_next()
        assert claimed is not None and claimed.step_name is StepName.PAUTA

        reset = runner.queue.reset_step(video_id, StepName.PAUTA)
        assert StepName.PAUTA not in reset
        with sessions() as s:
            assert s.get(StepRecord, claimed.step_run_id).state is StepState.RUNNING

    def test_progress_is_reported_and_renews_the_lease(self, runner, sessions) -> None:
        runner.queue.enqueue_video("X")
        claimed = runner.queue.claim_next()
        assert claimed is not None
        with sessions() as s:
            record = s.get(StepRecord, claimed.step_run_id)
            record.lease_until = datetime.now(UTC) + timedelta(seconds=5)
            s.commit()

        runner.queue.report_progress(claimed.step_run_id, {"feitas": 57, "total": 130})
        with sessions() as s:
            record = s.get(StepRecord, claimed.step_run_id)
            assert record.result["progresso"] == {"feitas": 57, "total": 130}
            assert record.lease_until > datetime.now(UTC) + timedelta(minutes=1)

    async def test_long_steps_keep_their_lease(self, runner, monkeypatch) -> None:
        runner.queue.enqueue_video("X")
        claimed = runner.queue.claim_next()
        assert claimed is not None
        renewed: list[int] = []
        monkeypatch.setattr(runner, "heartbeat_interval", lambda: 0.01)
        monkeypatch.setattr(runner.queue, "renew_lease", renewed.append)

        from mundoantigo.pipeline.steps.s01_pauta import PautaStep

        original = PautaStep.run

        async def slow(self, ctx):
            await asyncio.sleep(0.08)
            return await original(self, ctx)

        monkeypatch.setattr(PautaStep, "run", slow)
        await runner.run_claimed(claimed)
        assert len(renewed) >= 3
        assert set(renewed) == {claimed.step_run_id}
