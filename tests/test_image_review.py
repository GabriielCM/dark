"""Grade de revisao das imagens (fase C, C1).

O revisor marca imagens para refazer na pagina, com link ou com motivo. Estes
testes protegem o ciclo do pedido (rascunho, envio, aplicacao), a regra de
que refazer uma imagem nao mexe nas outras, e a semente nova a cada refacao.
"""

from __future__ import annotations

import dataclasses
import io

import httpx
import pytest
from PIL import Image

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.db.models import StepState, Video
from mundoantigo.pipeline import Runner, StepName, Worker
from mundoantigo.pipeline.steps.s09_assets import image_seed, stable_seed
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from mundoantigo.review import images as review
from tests.fakes import responder

COMMONS_OK = "https://commons.wikimedia.org/wiki/File:Piramide_de_Gize.jpg"
COMMONS_BY_SA = "https://commons.wikimedia.org/wiki/File:Foto_BY-SA.jpg"


@pytest.fixture
def gated(settings, recorder, sessions, com_remotion) -> Runner:
    app = {**settings.app, "revisao_imagens": {"ativo": True}}
    cfg = dataclasses.replace(settings, app=app)
    llm = FakeLLM(costs=recorder, responses=responder())
    return Runner.build(
        settings=cfg, providers=fake_registry(cfg, recorder, llm=llm), session_factory=sessions
    )


async def drain(runner: Runner, limit: int = 80) -> int:
    return await Worker(runner, poll_seconds=0).drain(limit=limit)


@pytest.fixture
async def at_grid(gated) -> tuple[Runner, str, ArtifactStore]:
    """Uma producao parada na grade de imagens."""
    video_id = gated.queue.enqueue_video("Aquedutos romanos")
    await drain(gated)
    return gated, video_id, ArtifactStore(video_id)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (120, 80, 40)).save(buffer, "PNG")
    return buffer.getvalue()


def _scene_keys(store: ArtifactStore) -> list[str]:
    return [i["chave"] for i in review.grid(store) if i["tipo_imagem"] == "cena"]


class TestTargets:
    def test_keys_cover_scenes_pieces_thumbnail_and_poses(self, tmp_project) -> None:
        store = ArtifactStore("v")
        assert review.target(store, "cena-007").image.name == "cena-007.png"
        assert review.target(store, "cena-007-peca-2").kind == "peca"
        assert review.target(store, "thumb").image.name == "thumb-base.png"
        pose = review.target(store, "mc-apontando")
        assert pose.kind == "mc" and pose.image.as_posix().endswith("assets/mc/apontando.png")
        with pytest.raises(review.ReviewError):
            review.target(store, "cena-7")


class TestDrafts:
    async def test_draft_is_saved_updated_and_removed(self, at_grid) -> None:
        _, _, store = at_grid
        key = _scene_keys(store)[0]
        review.save_draft(store, key, redo=True, reason="parece moderno")
        review.save_draft(store, key, redo=True, reason="roupas modernas")
        drafts = review.drafts(store)
        assert len(drafts) == 1 and drafts[0]["motivo"] == "roupas modernas"

        review.save_draft(store, key, redo=False)
        assert review.drafts(store) == []

    async def test_submit_refuses_incomplete_cards(self, at_grid) -> None:
        _, _, store = at_grid
        first, second = _scene_keys(store)[:2]
        review.save_draft(store, first, redo=True)
        review.save_draft(store, second, redo=True, link="ftp://x/y.jpg")
        with pytest.raises(review.SubmitError) as caught:
            review.submit(store)
        assert set(caught.value.errors) == {first, second}
        #  Nada foi enviado: tudo ou nada.
        assert all(r["estado"] == "rascunho" for r in review.load_requests(store))

    async def test_link_goes_to_the_worker_and_a_reason_to_claude(self, at_grid) -> None:
        _, _, store = at_grid
        first, second, third = _scene_keys(store)[:3]
        review.save_draft(store, first, redo=True, link=COMMONS_OK)
        review.save_draft(store, second, redo=True, reason="o mapa esta errado")
        review.save_draft(store, third, redo=True, link=COMMONS_OK, reason="use esta foto")

        assert review.submit(store) == {"worker": 1, "claude": 2}
        owners = {r["alvo"]: r["responsavel"] for r in review.load_requests(store)}
        assert owners == {first: "worker", second: "claude", third: "claude"}
        assert {r["alvo"] for r in review.claude_pending(store)} == {second, third}

    async def test_a_host_pose_takes_no_link(self, at_grid) -> None:
        _, _, store = at_grid
        review.save_draft(store, "mc-apontando", redo=True, link=COMMONS_OK)
        with pytest.raises(review.SubmitError, match="pose do MC"):
            review.submit(store)

    async def test_an_open_request_blocks_a_new_draft_and_approval(self, at_grid) -> None:
        _, _, store = at_grid
        key = _scene_keys(store)[0]
        review.save_draft(store, key, redo=True, reason="x")
        assert review.can_approve(store)[0] is False
        review.submit(store)
        with pytest.raises(review.ReviewError, match="em andamento"):
            review.save_draft(store, key, redo=True, reason="y")
        assert review.can_approve(store)[0] is False

        request = review.claude_pending(store)[0]
        review.cancel(store, request["id"])
        assert review.can_approve(store) == (True, "")


class TestApply:
    async def test_link_from_another_site_becomes_an_unverified_reference(self, at_grid) -> None:
        runner, _, store = at_grid
        key = _scene_keys(store)[0]
        image = review.target(store, key).image
        old_bytes = image.read_bytes()
        review.save_draft(store, key, redo=True, link="https://example.org/foto.png")
        review.submit(store)

        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=_png_bytes()))
        report = await review.apply(store, runner.providers.references(), transport=transport)

        assert report.applied == [key]
        chosen = review.target(store, key)
        assert not chosen.image.exists(), "a imagem antiga continua na pasta"
        sidecar = store.read_sidecar(chosen.reference)
        assert sidecar is not None and sidecar.extra["referencia"]["verificada"] is False
        request = review.load_requests(store)[-1]
        assert request["estado"] == "aplicado" and request["refacao"] == 1
        assert (store.root / request["anterior"]).read_bytes() == old_bytes
        storyboard = store.read_json("cenas", "storyboard.json")
        scene = next(s for s in storyboard["cenas"] if s["indice"] == chosen.scene)
        assert scene["refacoes"] == 1 and scene["referencia"]["origem"] == "revisor"

    async def test_a_refused_license_refuses_the_request(self, at_grid) -> None:
        runner, _, store = at_grid
        key = _scene_keys(store)[0]
        review.save_draft(store, key, redo=True, link=COMMONS_BY_SA)
        review.submit(store)

        report = await review.apply(store, runner.providers.references())
        assert report.applied == [] and report.refused[0][0] == key
        request = review.load_requests(store)[-1]
        assert request["estado"] == "recusado" and "licenca" in request["detalhe"]
        assert review.target(store, key).image.exists(), "recusar nao pode apagar a imagem"

    async def test_claude_requests_wait_for_the_new_description(self, at_grid) -> None:
        runner, _, store = at_grid
        key = _scene_keys(store)[0]
        review.save_draft(store, key, redo=True, reason="o mapa cobre o rio")
        review.submit(store)

        assert review.has_ready_requests(store) is False
        review.describe(store, key, "A clear map of the Nile valley.", reply="refiz o mapa")
        assert review.has_ready_requests(store) is True

        await review.apply(store, runner.providers.references())
        storyboard = store.read_json("cenas", "storyboard.json")
        scene = next(s for s in storyboard["cenas"] if f"cena-{s['indice']:03d}" == key)
        assert scene["descricao_visual"] == "A clear map of the Nile valley."
        assert scene["descricao_da_sessao"] is True


class TestThroughTheWorker:
    async def test_only_the_requested_image_is_made_again(self, at_grid, sessions) -> None:
        runner, video_id, store = at_grid
        first, second = _scene_keys(store)[:2]
        untouched = review.target(store, second).image.read_bytes()
        review.save_draft(store, first, redo=True, link=COMMONS_OK)
        review.submit(store)

        await drain(runner)

        image = review.target(store, first).image
        assert image.exists()
        assert review.target(store, second).image.read_bytes() == untouched
        sidecar = store.read_sidecar(image)
        index = review.target(store, first).scene
        assert sidecar is not None and sidecar.seed == image_seed(video_id, index, 1)
        assert sidecar.extra["referencia"]["fonte"] == "commons"
        with sessions() as s:
            steps = {st.name: st.state for st in s.get(Video, video_id).steps}
        assert steps["revisao_imagens"] is StepState.BLOCKED
        item = next(i for i in review.grid(store) if i["chave"] == first)
        assert item["estado"] == "refeita" and item["anterior"]

    async def test_the_worker_waits_while_the_image_step_runs(self, at_grid, sessions) -> None:
        runner, video_id, store = at_grid
        key = _scene_keys(store)[0]
        review.save_draft(store, key, redo=True, link=COMMONS_OK)
        review.submit(store)
        with sessions() as s:
            video = s.get(Video, video_id)
            assets = next(st for st in video.steps if st.name == "assets")
            assets.state = StepState.RUNNING
            s.commit()

        assert await runner.maintain() == []
        assert review.load_requests(store)[-1]["estado"] == "pendente"


class TestSeeds:
    def test_the_seed_only_changes_with_a_redo(self) -> None:
        assert image_seed("v", 12, 0) == stable_seed("v", 12)
        assert image_seed("v", 12, None) == stable_seed("v", 12)
        assert image_seed("v", 12, 1) != stable_seed("v", 12)
        assert image_seed("v", 12, 1) != image_seed("v", 12, 2)


class TestSections:
    async def test_grid_is_split_by_chapter_with_the_top_section_first(self, at_grid) -> None:
        _, _, store = at_grid
        sections = review.sections(store)
        assert sections[0]["id"] == "topo"
        assert sections[0]["itens"][0]["chave"] == "thumb"
        chapters = [s["titulo"] for s in sections[1:]]
        assert len(chapters) >= 2
        storyboard = store.read_json("cenas", "storyboard.json")
        first_title = next(
            s["titulo_capitulo"]["pt"] for s in storyboard["cenas"] if s.get("titulo_capitulo")
        )
        assert chapters[0] == first_title
        total = sum(s["total"] for s in sections)
        assert total == len(review.grid(store))


class TestApproveCommand:
    async def test_cli_refuses_to_approve_with_open_requests(self, at_grid, capsys) -> None:
        from mundoantigo.cli import main

        _, video_id, store = at_grid
        review.save_draft(store, _scene_keys(store)[0], redo=True, reason="x")
        assert main(["aprovar", video_id, "--etapa", StepName.REVISAO_IMAGENS.value]) == 1
        assert "nao pode ser aprovada" in capsys.readouterr().err
