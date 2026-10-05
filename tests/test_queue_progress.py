"""Fundacao da pagina da producao (fase C, C0).

A pagina mostra em que etapa estamos, o progresso dentro dela e o que espera
o revisor. Estes testes protegem os dados que ela le: o progresso que antes
se perdia, o aviso de bloqueio que outra etapa apagava, e a refacao de
imagens soltas, que nao pode levar as outras junto.
"""

from __future__ import annotations

import dataclasses

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.db.models import StepRecord, StepState, Video
from mundoantigo.pipeline import Runner, StepName, Worker
from mundoantigo.pipeline.runner import video_progress
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from tests.fakes import responder


def _runner(settings, recorder, sessions, *, gated: bool = False) -> Runner:
    if gated:
        settings = dataclasses.replace(
            settings, app={**settings.app, "revisao_imagens": {"ativo": True}}
        )
    llm = FakeLLM(costs=recorder, responses=responder())
    return Runner.build(
        settings=settings,
        providers=fake_registry(settings, recorder, llm=llm),
        session_factory=sessions,
    )


@pytest.fixture
def gated(settings, recorder, sessions, com_remotion) -> Runner:
    return _runner(settings, recorder, sessions, gated=True)


async def drain(runner: Runner, limit: int = 80) -> int:
    return await Worker(runner, poll_seconds=0).drain(limit=limit)


class TestProgress:
    def test_progress_is_shown_while_the_step_runs(self, gated, sessions) -> None:
        video_id = gated.queue.enqueue_video("X")
        claimed = gated.queue.claim_next()
        assert claimed is not None
        gated.queue.report_progress(claimed.step_run_id, {"feitas": 30, "total": 120})

        step = next(
            st for st in video_progress(sessions, video_id)["etapas"] if st["nome"] == "pauta"
        )
        assert step["progresso_etapa"] == {"feitas": 30, "total": 120, "pct": 25}
        assert step["rotulo"] == "Pauta"
        assert step["iniciada_em"]

    def test_a_new_attempt_starts_without_the_old_progress(self, gated, sessions) -> None:
        gated.queue.enqueue_video("X")
        claimed = gated.queue.claim_next()
        assert claimed is not None
        gated.queue.report_progress(claimed.step_run_id, {"feitas": 3, "total": 9})
        gated.queue.mark_failed(claimed.step_run_id, "caiu")
        with sessions() as s:
            s.get(StepRecord, claimed.step_run_id).run_after = None
            s.commit()

        again = gated.queue.claim_next()
        assert again is not None and again.step_run_id == claimed.step_run_id
        with sessions() as s:
            assert s.get(StepRecord, claimed.step_run_id).result is None

    def test_mark_failed_tells_when_the_attempts_ran_out(self, gated) -> None:
        gated.queue.enqueue_video("X")
        claimed = gated.queue.claim_next()
        assert claimed is not None
        assert gated.queue.mark_failed(claimed.step_run_id, "rede") is False
        assert gated.queue.mark_failed(claimed.step_run_id, "chave", permanent=True) is True


class TestBlockedReason:
    async def test_the_grid_stays_blocked_while_other_steps_run(self, gated, sessions) -> None:
        video_id = gated.queue.enqueue_video("Aquedutos romanos")
        await drain(gated)

        with sessions() as s:
            video = s.get(Video, video_id)
            steps = {st.name: st.state for st in video.steps}
            reason = video.blocked_reason
        #  A trilha rodou depois que a grade bloqueou e nao apagou o aviso.
        assert steps["trilha"] is StepState.DONE
        assert steps["revisao_imagens"] is StepState.BLOCKED
        assert reason and "revisao das imagens" in reason

        progress = video_progress(sessions, video_id)
        assert progress["precisa_de_voce"] == "revisao_imagens"
        grid = next(st for st in progress["etapas"] if st["nome"] == "revisao_imagens")
        assert grid["precisa_de_voce"] and not grid["com_o_claude"]

    def test_waiting_for_the_session_is_not_waiting_for_the_reviewer(self, gated, sessions) -> None:
        video_id = gated.queue.enqueue_video("X")
        gated.queue.claim_next()  # pauta
        with sessions() as s:
            pauta = (
                s.query(StepRecord)
                .filter(StepRecord.video_id == video_id, StepRecord.name == "pauta")
                .one()
            )
            step_id = pauta.id
        gated.queue.mark_blocked(step_id, "aguardando a sessao: `mundoantigo importar-roteiro`")

        progress = video_progress(sessions, video_id)
        assert progress["precisa_de_voce"] is None
        pauta_view = next(st for st in progress["etapas"] if st["nome"] == "pauta")
        assert pauta_view["com_o_claude"] and not pauta_view["precisa_de_voce"]


class TestApprovalCoverage:
    async def test_the_approval_covers_the_thumbnail_and_the_host_poses(
        self, gated, sessions
    ) -> None:
        video_id = gated.queue.enqueue_video("Aquedutos romanos")
        await drain(gated)
        gated.approve(video_id, gate=StepName.REVISAO_IMAGENS, reviewer="teste")

        store = ArtifactStore(video_id)
        approved = store.read_json("revisao_imagens", "aprovacao.json")["imagens"]
        assert "cena-001.png" in approved
        assert "thumb-base.png" in approved
        poses = sorted(p.name for p in (store.root / "assets" / "mc").glob("*.png"))
        assert all(f"mc/{name}" in approved for name in poses)


class TestRedoImages:
    async def test_only_the_missing_image_is_made_again(self, gated, sessions) -> None:
        video_id = gated.queue.enqueue_video("Aquedutos romanos")
        await drain(gated)
        gated.approve(video_id, gate=StepName.REVISAO_IMAGENS, reviewer="teste")
        await drain(gated)

        store = ArtifactStore(video_id)
        kept = store.path("assets", "cena-001.png")
        redone = store.path("assets", "cena-002.png")
        kept_bytes = kept.read_bytes()
        video_pt = store.path("montagem", "video.pt-br.mp4")
        assert video_pt.exists()

        store.delete(redone)
        affected = gated.redo_images(video_id)

        assert affected[0] is StepName.ASSETS
        assert StepName.MONTAGEM in affected
        #  O mp4 com a imagem antiga nao pode ser reaproveitado.
        assert not video_pt.exists()
        #  A aprovacao antiga caiu: a grade volta a esperar o revisor.
        assert not store.path("revisao_imagens", "aprovacao.json").exists()

        await drain(gated)
        assert redone.exists()
        assert kept.read_bytes() == kept_bytes, "refazer uma imagem mexeu em outra"
        with sessions() as s:
            steps = {st.name: st.state for st in s.get(Video, video_id).steps}
        assert steps["revisao_imagens"] is StepState.BLOCKED
