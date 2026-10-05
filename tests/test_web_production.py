"""Pagina da producao (fase C, C2 e C3).

A lista das etapas que expande ao clicar, o link direto que o aviso usa, e a
grade de imagens: rascunho salvo sozinho, envio, aprovacao e miniaturas.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.paths import get_paths
from mundoantigo.pipeline import Runner, StepName, Worker
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from mundoantigo.review import images as review
from mundoantigo.web import create_app
from tests.fakes import responder

JSON = {"Content-Type": "application/json"}


@pytest.fixture
def gated_settings(settings):
    return dataclasses.replace(settings, app={**settings.app, "revisao_imagens": {"ativo": True}})


@pytest.fixture
async def at_grid(gated_settings, recorder, sessions, com_remotion) -> str:
    """Uma producao parada na grade de imagens."""
    llm = FakeLLM(costs=recorder, responses=responder())
    runner = Runner.build(
        settings=gated_settings,
        providers=fake_registry(gated_settings, recorder, llm=llm),
        session_factory=sessions,
    )
    video_id = runner.queue.enqueue_video("Aquedutos romanos")
    await Worker(runner, poll_seconds=0).drain(limit=80)
    return video_id


@pytest.fixture
def client(gated_settings, tmp_project) -> TestClient:
    return TestClient(create_app(gated_settings))


def _first_scene(video_id: str) -> str:
    return next(
        i["chave"] for i in review.grid(ArtifactStore(video_id)) if i["tipo_imagem"] == "cena"
    )


class TestPage:
    def test_the_step_needing_the_reviewer_opens_by_itself(self, client, at_grid) -> None:
        page = client.get(f"/videos/{at_grid}").text
        assert 'id="etapa-revisao_imagens" data-etapa="revisao_imagens"' in page
        opened = page.split('id="etapa-revisao_imagens"', 1)[1].split(">", 1)[0]
        assert "open" in opened
        #  O corpo da etapa aberta ja vem na pagina: a grade, por capitulo.
        assert "data-grade" in page
        assert "Precisa de você" in page

    def test_deep_link_opens_the_requested_step(self, client, at_grid) -> None:
        page = client.get(f"/videos/{at_grid}?abrir=narracao").text
        opened = page.split('id="etapa-narracao"', 1)[1].split(">", 1)[0]
        assert "open" in opened
        assert 'data-aberta="narracao"' in page

    def test_state_api_tells_what_needs_the_reviewer(self, client, at_grid) -> None:
        state = client.get(f"/api/videos/{at_grid}/estado").json()
        assert state["precisa_de_voce"] == "revisao_imagens"
        labels = {e["nome"]: e["rotulo"] for e in state["etapas"]}
        assert labels["revisao_imagens"] == "Revisão das imagens"

    def test_step_body_loads_on_demand(self, client, at_grid) -> None:
        body = client.get(f"/videos/{at_grid}/etapas/roteiro").text
        assert "<html" not in body
        assert "capítulos" in body
        assert client.get(f"/videos/{at_grid}/etapas/nao-existe").status_code == 404


class TestGrid:
    def test_draft_needs_json(self, client, at_grid) -> None:
        key = _first_scene(at_grid)
        url = f"/api/videos/{at_grid}/imagens/{key}/rascunho"
        assert client.put(url, data={"refazer": "true"}).status_code in (415, 422)

    def test_draft_submit_and_card_state(self, client, at_grid) -> None:
        key = _first_scene(at_grid)
        url = f"/api/videos/{at_grid}/imagens/{key}/rascunho"
        saved = client.put(url, json={"refazer": True, "motivo": "parece moderno"})
        assert saved.status_code == 200 and saved.json()["rascunho"]["motivo"] == "parece moderno"

        grid = client.get(f"/api/videos/{at_grid}/imagens").json()
        card = next(c for c in grid["cartoes"] if c["chave"] == key)
        assert card["estado"] == "rascunho"
        assert grid["pode_aprovar"] is False

        sent = client.post(f"/api/videos/{at_grid}/imagens/enviar", headers=JSON, json={})
        assert sent.json() == {"ok": True, "worker": 0, "claude": 1}
        grid = client.get(f"/api/videos/{at_grid}/imagens").json()
        card = next(c for c in grid["cartoes"] if c["chave"] == key)
        assert card["estado"] == "aguardando_claude"

    def test_incomplete_cards_are_reported_one_by_one(self, client, at_grid) -> None:
        key = _first_scene(at_grid)
        client.put(f"/api/videos/{at_grid}/imagens/{key}/rascunho", json={"refazer": True})
        sent = client.post(f"/api/videos/{at_grid}/imagens/enviar", headers=JSON, json={})
        assert sent.status_code == 422
        assert key in sent.json()["erros"]

    def test_approval_is_guarded_and_then_unblocks(self, client, at_grid) -> None:
        key = _first_scene(at_grid)
        client.put(
            f"/api/videos/{at_grid}/imagens/{key}/rascunho", json={"refazer": True, "motivo": "x"}
        )
        refused = client.post(f"/api/videos/{at_grid}/imagens/aprovar", headers=JSON, json={})
        assert refused.status_code == 409

        client.put(f"/api/videos/{at_grid}/imagens/{key}/rascunho", json={"refazer": False})
        approved = client.post(f"/api/videos/{at_grid}/imagens/aprovar", headers=JSON, json={})
        assert approved.status_code == 200
        approval = ArtifactStore(at_grid).read_json("revisao_imagens", "aprovacao.json")
        assert approval["revisor"] == "painel"


class TestThumbnails:
    def test_thumbnail_is_a_cached_jpeg(self, client, at_grid) -> None:
        item = next(i for i in review.grid(ArtifactStore(at_grid)) if i["tipo_imagem"] == "cena")
        response = client.get(f"/miniaturas/{at_grid}/{item['imagem']}?w=480")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        cache = get_paths().data / "cache" / "miniaturas" / at_grid
        assert any(cache.iterdir())

    def test_thumbnail_refuses_paths_outside_the_video(self, client, at_grid) -> None:
        assert client.get(f"/miniaturas/{at_grid}/../../etc/passwd").status_code == 404
        assert client.get(f"/miniaturas/{at_grid}/cenas/storyboard.json").status_code == 404


class TestFinalCut:
    def test_review_page_and_step_body_share_the_final_cut(self, client, at_grid) -> None:
        assert "Corte final" in client.get(f"/videos/{at_grid}/revisao").text
        body = client.get(f"/videos/{at_grid}/etapas/revisao").text
        assert "Relatório de fatos" in body

    def test_reject_cannot_ask_to_redo_every_image(self, client, at_grid) -> None:
        response = client.post(
            f"/videos/{at_grid}/rejeitar",
            data={"motivo": "imagem errada", "refazer_de": StepName.ASSETS.value},
            follow_redirects=False,
        )
        assert response.status_code == 400
        assert ArtifactStore(at_grid).path("assets", "cena-001.png").exists()


class TestAuth:
    def test_api_needs_the_token_outside_localhost(
        self, gated_settings, tmp_project, monkeypatch
    ) -> None:
        panel = dataclasses.replace(gated_settings.panel, host="0.0.0.0", auth_token="segredo")
        app = create_app(dataclasses.replace(gated_settings, panel=panel))
        client = TestClient(app)
        assert client.get("/api/videos/x/estado").status_code == 401
        assert client.get("/miniaturas/x/a.png").status_code == 401
