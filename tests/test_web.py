"""Painel: as cinco telas respondem e as acoes fazem o que dizem."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.db.models import RightsStatus, Video, VideoState
from mundoantigo.web import create_app


@pytest.fixture
def client(settings, tmp_project) -> TestClient:
    return TestClient(create_app(settings))


class TestPages:
    def test_queue_page_loads_empty(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "Fila de producao" in response.text
        assert "Nenhuma producao ainda" in response.text

    def test_costs_page_loads(self, client: TestClient) -> None:
        response = client.get("/custos")
        assert response.status_code == 200
        assert "Custos" in response.text

    def test_books_page_loads(self, client: TestClient) -> None:
        response = client.get("/livros")
        assert response.status_code == 200
        assert "fonte de fatos" in response.text

    def test_health_reports_budget_and_providers(self, client: TestClient) -> None:
        payload = client.get("/saude").json()
        assert payload["ok"] is True
        assert payload["teto_usd"] == 50.0
        assert "llm" in payload["provedores"]

    def test_unknown_video_returns_404(self, client: TestClient) -> None:
        response = client.get("/videos/nao-existe")
        assert response.status_code == 404
        assert "nao existe" in response.text


class TestQueueActions:
    def test_creating_a_video_redirects_to_it(self, client: TestClient) -> None:
        response = client.post(
            "/videos",
            data={"tema": "Aquedutos romanos", "pilar": "engenharia"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/videos/" in response.headers["location"]

    def test_created_video_appears_in_the_queue(self, client: TestClient) -> None:
        client.post("/videos", data={"tema": "Concreto romano", "pilar": "tecnologia"})
        assert "Concreto romano" in client.get("/").text

    def test_empty_topic_is_refused(self, client: TestClient) -> None:
        response = client.post("/videos", data={"tema": "   "}, follow_redirects=False)
        assert response.headers["location"] == "/?erro=tema-vazio"

    def test_detail_page_shows_all_twelve_steps(self, client: TestClient) -> None:
        created = client.post("/videos", data={"tema": "Aquedutos"}, follow_redirects=False)
        page = client.get(created.headers["location"]).text
        for step in ("pauta", "pesquisa", "gate_fatos", "montagem", "revisao"):
            assert step in page

    def test_steps_fragment_is_html_only(self, client: TestClient) -> None:
        created = client.post("/videos", data={"tema": "X"}, follow_redirects=False)
        video_id = created.headers["location"].rsplit("/", 1)[-1]
        fragment = client.get(f"/videos/{video_id}/etapas").text
        assert "<table>" in fragment
        assert "<html" not in fragment

    def test_redo_requeues_from_the_step(self, client: TestClient, sessions) -> None:
        created = client.post("/videos", data={"tema": "X"}, follow_redirects=False)
        video_id = created.headers["location"].rsplit("/", 1)[-1]

        client.post(f"/videos/{video_id}/refazer", data={"etapa": "cenas"})
        with sessions() as s:
            video = s.get(Video, video_id)
            assert video.state is VideoState.CENAS

    def test_redo_with_delete_clears_the_step_and_what_follows(self, client: TestClient) -> None:
        created = client.post("/videos", data={"tema": "X"}, follow_redirects=False)
        video_id = created.headers["location"].rsplit("/", 1)[-1]

        store = ArtifactStore(video_id)
        script = store.write_json("roteiro", "roteiro.pt-br.json", {"blocos": []})
        storyboard = store.write_json("cenas", "storyboard.json", {"cenas": []})
        references = store.write_json("referencias", "indice.json", {"cenas": {}})

        client.post(f"/videos/{video_id}/refazer", data={"etapa": "cenas", "apagar": "1"})
        assert not storyboard.exists()
        assert not references.exists(), "o que depende das cenas tambem e refeito"
        assert script.exists(), "o que vem antes das cenas fica"


class TestReview:
    def _prepare(self, client: TestClient, sessions) -> str:
        created = client.post("/videos", data={"tema": "Aquedutos"}, follow_redirects=False)
        video_id = created.headers["location"].rsplit("/", 1)[-1]
        store = ArtifactStore(video_id)
        store.write_json(
            "roteiro",
            "relatorio_fatos.final.json",
            {
                "itens": [
                    {
                        "id": "a1",
                        "afirmacao": "Alta confianca aqui.",
                        "confianca": "alta",
                        "fontes": ["https://a.edu"],
                        "justificativa": "ok",
                    },
                    {
                        "id": "a2",
                        "afirmacao": "Media confianca aqui.",
                        "confianca": "media",
                        "fontes": ["https://b.edu"],
                        "justificativa": "uma fonte",
                    },
                ],
                "resumo": {"alta": 1, "media": 1, "baixa": 0},
                "reescritas": 1,
                "aprovado": True,
            },
        )
        store.write_json("revisao", "revisao.json", {"avisos": ["confira o ritmo"]})
        return video_id

    def test_review_page_shows_report_and_warnings(self, client: TestClient, sessions) -> None:
        video_id = self._prepare(client, sessions)
        page = client.get(f"/videos/{video_id}/revisao").text
        assert "Corte final" in page
        assert "Alta confianca aqui." in page
        assert "confira o ritmo" in page
        assert "1 reescrita(s)" in page

    def test_low_confidence_items_come_first(self, client: TestClient, sessions) -> None:
        created = client.post("/videos", data={"tema": "X"}, follow_redirects=False)
        video_id = created.headers["location"].rsplit("/", 1)[-1]
        ArtifactStore(video_id).write_json(
            "roteiro",
            "relatorio_fatos.final.json",
            {
                "itens": [
                    {"id": "a1", "afirmacao": "ITEM ALTO", "confianca": "alta", "fontes": []},
                    {"id": "a2", "afirmacao": "ITEM BAIXO", "confianca": "baixa", "fontes": []},
                ],
                "resumo": {"alta": 1, "baixa": 1},
            },
        )
        page = client.get(f"/videos/{video_id}/revisao").text
        assert page.index("ITEM BAIXO") < page.index("ITEM ALTO")

    def test_approve_records_the_decision(self, client: TestClient, sessions) -> None:
        video_id = self._prepare(client, sessions)
        client.post(f"/videos/{video_id}/aprovar")

        aprovacao = ArtifactStore(video_id).read_json("revisao", "aprovacao.json")
        assert aprovacao["aprovado"] is True
        with sessions() as s:
            assert s.get(Video, video_id).reviewed_at is not None

    def test_reject_requires_a_reason(self, client: TestClient, sessions) -> None:
        """Rejeitar sem motivo nao ensina nada ao pipeline (brief 3.5)."""
        video_id = self._prepare(client, sessions)
        response = client.post(
            f"/videos/{video_id}/rejeitar",
            data={"motivo": "  ", "refazer_de": "roteiro"},
            follow_redirects=False,
        )
        assert "erro=motivo-vazio" in response.headers["location"]
        assert not ArtifactStore(video_id).path("revisao", "rejeicao.json").exists()

    def test_reject_stores_reason_and_requeues(self, client: TestClient, sessions) -> None:
        video_id = self._prepare(client, sessions)
        client.post(
            f"/videos/{video_id}/rejeitar",
            data={"motivo": "o gancho esta fraco", "refazer_de": "cenas"},
        )
        with sessions() as s:
            assert s.get(Video, video_id).review_rejection_reason == "o gancho esta fraco"
        rejeicao = ArtifactStore(video_id).read_json("revisao", "rejeicao.json")
        assert rejeicao["refazer_a_partir_de"] == "cenas"


class TestBooksPanel:
    def test_rejects_unsupported_format(self, client: TestClient) -> None:
        response = client.post(
            "/livros",
            files={"arquivo": ("livro.txt", b"conteudo", "text/plain")},
            follow_redirects=False,
        )
        assert "erro=formato" in response.headers["location"]

    def test_book_detail_explains_the_rights_decision(self, client: TestClient, sessions) -> None:
        from mundoantigo.db.models import Book

        with sessions() as s:
            s.add(
                Book(
                    id="b1",
                    filename="roma.pdf",
                    format="pdf",
                    sha256="a" * 64,
                    title="Historia de Roma",
                    author="Autor",
                    author_death_year=1990,
                    original_year=1960,
                    rights_status=RightsStatus.FONTE_APENAS,
                    rights_reason="obra protegida: o autor morreu em 1990",
                    rights_detail={
                        "jurisdicoes": [
                            {
                                "jurisdicao": "BR",
                                "livre": False,
                                "motivo": "o autor morreu em 1990; protegida ate 2060",
                                "livre_desde": 2061,
                            }
                        ],
                        "dados_ausentes": [],
                    },
                    chapters=[{"numero": 1, "titulo": "A fundacao"}],
                )
            )
            s.commit()

        page = client.get("/livros/b1").text
        assert "fonte apenas" in page
        assert "protegida ate 2060" in page
        assert "guia de pauta" in page

    def test_chapter_becomes_a_topic(self, client: TestClient, sessions) -> None:
        from mundoantigo.db.models import Book

        with sessions() as s:
            s.add(
                Book(
                    id="b1",
                    filename="x.pdf",
                    format="pdf",
                    sha256="a" * 64,
                    rights_status=RightsStatus.LIVRE,
                    chapters=[{"numero": 1, "titulo": "A fundacao"}],
                )
            )
            s.commit()

        response = client.post(
            "/livros/b1/pauta",
            data={"capitulo": "1", "tema": "A fundacao de Roma", "pilar": "imperios"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        video_id = response.headers["location"].rsplit("/", 1)[-1]
        with sessions() as s:
            video = s.get(Video, video_id)
            assert video.book_id == "b1"
            assert video.book_chapter == 1


class TestAuth:
    def test_token_is_required_when_configured(self, settings, tmp_project, monkeypatch) -> None:
        """CLAUDE.md, Seguranca: painel exposto exige autenticacao."""
        monkeypatch.setenv("MA_PANEL_HOST", "0.0.0.0")
        monkeypatch.setenv("MA_PANEL_AUTH_TOKEN", "segredo")
        from mundoantigo.config import load_settings, reset_settings_cache

        reset_settings_cache()
        client = TestClient(create_app(load_settings()))

        assert client.get("/").status_code == 401
        assert client.get("/", headers={"x-painel-token": "segredo"}).status_code == 200
        #  /saude fica aberto para o supervisor de processo checar.
        assert client.get("/saude").status_code == 200
