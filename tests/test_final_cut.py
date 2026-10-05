"""Comentarios do corte final por momento do video (fase C, C7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.cli import main
from mundoantigo.conversation import inbox
from mundoantigo.pipeline import Runner, Worker
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from mundoantigo.review import final_cut
from mundoantigo.web import create_app
from tests.fakes import responder

PROPS = {
    "scenes": [
        {"index": 1, "start": 0.0, "duration": 4.8, "background": "assets/cena-001.png"},
        {"index": 2, "start": 4.8, "duration": 3.6, "background": "assets/cena-002.png"},
        {"index": 3, "start": 8.4, "duration": 5.0, "background": "assets/cena-003.png"},
    ]
}


class TestSceneAt:
    def test_the_scene_on_screen_at_a_moment(self) -> None:
        assert final_cut.scene_at(PROPS, 0)["index"] == 1
        assert final_cut.scene_at(PROPS, 4.79)["index"] == 1
        assert final_cut.scene_at(PROPS, 4.8)["index"] == 2
        assert final_cut.scene_at(PROPS, 999)["index"] == 3
        assert final_cut.scene_at({"scenes": []}, 3) is None


@pytest.fixture
def cut(make_video) -> ArtifactStore:
    store = ArtifactStore(make_video("v-corte"))
    store.ensure()
    store.write_json("montagem", "props.pt-br.json", PROPS, step="montagem")
    en = {"scenes": [{**s, "start": s["start"] * 1.2} for s in PROPS["scenes"]]}
    store.write_json("montagem", "props.en.json", en, step="montagem")
    store.write_json(
        "cenas",
        "storyboard.json",
        {"cenas": [{"indice": i, "narracao": f"frase {i}"} for i in (1, 2, 3)]},
        step="cenas",
    )
    return store


class TestComments:
    def test_a_comment_knows_its_scene_in_each_language(self, cut) -> None:
        pt = final_cut.add(cut, "pt-br", 5.0)
        en = final_cut.add(cut, "en", 5.0)
        assert (pt["cena"], pt["narracao"]) == (2, "frase 2")
        assert en["cena"] == 1, "o EN tem outros tempos"

    def test_lifecycle_and_approval_guard(self, cut) -> None:
        first = final_cut.add(cut, "pt-br", 9.0)
        empty = final_cut.add(cut, "pt-br", 1.0)
        assert final_cut.can_approve(cut)[0] is False

        final_cut.update(cut, first["id"], text="a imagem cobre o rio", link=None)
        assert final_cut.submit(cut) == 1
        assert [c["id"] for c in final_cut.pending(cut)] == [first["id"]]
        assert all(c["id"] != empty["id"] for c in final_cut.load(cut)), "rascunho vazio ficou"
        with pytest.raises(final_cut.CommentError):
            final_cut.update(cut, first["id"], text="outra", link=None)

        assert inbox.inbox(cut)["comentarios_corte"]
        final_cut.resolve(cut, first["id"], "refiz a cena 3")
        assert final_cut.can_approve(cut) == (True, "")

    def test_submit_needs_some_text(self, cut) -> None:
        final_cut.add(cut, "pt-br", 1.0)
        with pytest.raises(final_cut.CommentError):
            final_cut.submit(cut)


class TestCli:
    def test_session_reads_and_answers_comments(self, cut, capsys) -> None:
        entry = final_cut.add(cut, "pt-br", 9.0)
        final_cut.update(cut, entry["id"], text="trocar a imagem", link=None)
        final_cut.submit(cut)

        assert main(["corte", "comentarios", cut.video_id]) == 0
        out = capsys.readouterr().out
        assert "trocar a imagem" in out and "cena-003" in out
        assert final_cut.unseen_comments(cut) == []

        assert main(["corte", "resolver", cut.video_id, str(entry["id"]), "refeita"]) == 0
        assert final_cut.load(cut)[0]["resposta"] == "refeita"


@pytest.fixture
async def at_review(settings, recorder, sessions, com_remotion) -> str:
    llm = FakeLLM(costs=recorder, responses=responder())
    runner = Runner.build(
        settings=settings,
        providers=fake_registry(settings, recorder, llm=llm),
        session_factory=sessions,
    )
    video_id = runner.queue.enqueue_video("Aquedutos romanos")
    await Worker(runner, poll_seconds=0).drain(limit=80)
    return video_id


class TestPage:
    def test_comment_from_the_player_and_approval(self, settings, at_review) -> None:
        client = TestClient(create_app(settings))
        page = client.get(f"/videos/{at_review}?abrir=revisao").text
        assert 'data-comentar="pt-br"' in page

        created = client.post(
            f"/api/videos/{at_review}/corte/comentarios", json={"idioma": "pt-br", "tempo_s": 1.0}
        ).json()["comentario"]
        assert created["cena"] == 1
        cid = created["id"]
        assert (
            client.put(
                f"/api/videos/{at_review}/corte/comentarios/{cid}", json={"texto": "mais luz"}
            ).status_code
            == 200
        )
        refused = client.post(f"/api/videos/{at_review}/corte/aprovar", json={})
        assert refused.status_code == 409

        assert client.post(f"/api/videos/{at_review}/corte/enviar", json={}).json()["enviados"] == 1
        fragment = client.get(f"/videos/{at_review}/corte/comentarios").text
        assert "mais luz" in fragment

        final_cut.resolve(ArtifactStore(at_review), cid, "ajustei")
        approved = client.post(f"/api/videos/{at_review}/corte/aprovar", json={})
        assert approved.status_code == 200
        assert ArtifactStore(at_review).path("revisao", "aprovacao.json").exists()

    def test_old_review_link_lands_on_the_step(self, settings, at_review) -> None:
        client = TestClient(create_app(settings))
        response = client.get(f"/videos/{at_review}/revisao", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].endswith(
            f"/videos/{at_review}?abrir=revisao#etapa-revisao"
        )
