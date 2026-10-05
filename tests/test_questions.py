"""Perguntas do Claude na pagina e o vigia da sessao (fase C, C6)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.cli import main
from mundoantigo.conversation import inbox, questions
from mundoantigo.db.models import Event
from mundoantigo.web import create_app


@pytest.fixture
def video(make_video) -> ArtifactStore:
    video_id = make_video("v-perguntas", "Gizé")
    store = ArtifactStore(video_id)
    store.ensure()
    return store


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(inbox.time, "sleep", lambda s: None)


class TestQuestions:
    def test_ask_draft_and_answer(self, video) -> None:
        entry = questions.ask(video, "A ou B na cena 45?", options=["A", "B"], target="cena-045")
        questions.save_draft(video, entry["id"], option="B", text="mais claro")
        assert questions.open_questions(video)[0]["rascunho"]["opcao"] == "B"

        answered = questions.answer(video, entry["id"], option="B", text="mais claro")
        assert answered["estado"] == "respondida"
        assert questions.answered_unseen(video)[0]["resposta"]["opcao"] == "B"
        questions.mark_seen(video, [entry["id"]])
        assert questions.answered_unseen(video) == []

    def test_answers_are_validated(self, video) -> None:
        entry = questions.ask(video, "Qual?", options=["A"], free_text=False)
        with pytest.raises(questions.QuestionError, match="opcao desconhecida"):
            questions.answer(video, entry["id"], option="Z", text=None)
        with pytest.raises(questions.QuestionError):
            questions.answer(video, entry["id"], option=None, text=None)
        questions.answer(video, entry["id"], option="A", text=None)
        with pytest.raises(questions.QuestionError, match="ja foi respondida"):
            questions.answer(video, entry["id"], option="A", text=None)


class TestWatcher:
    def test_wait_returns_what_arrived_and_keeps_presence(self, video, no_sleep) -> None:
        entry = questions.ask(video, "Pergunta?")
        questions.answer(video, entry["id"], option=None, text="sim")
        box = inbox.wait(video, timeout_s=5)
        assert [q["id"] for q in box["respostas"]] == [entry["id"]]
        assert inbox.presence(video.video_id)["estado"] == "acompanhando"

    def test_wait_gives_up_after_the_timeout(self, video, no_sleep) -> None:
        assert inbox.is_empty(inbox.wait(video, timeout_s=0.05))

    def test_no_heartbeat_means_absent(self, video) -> None:
        assert inbox.presence(video.video_id)["estado"] == "ausente"


class TestCli:
    def test_perguntar_records_the_question_and_the_event(self, video, sessions, capsys) -> None:
        assert (
            main(["perguntar", video.video_id, "Prefere A ou B?", "--opcao", "A", "--opcao", "B"])
            == 0
        )
        assert capsys.readouterr().out.strip() == "1"
        assert questions.open_questions(video)[0]["opcoes"] == ["A", "B"]
        with sessions() as s:
            event = s.query(Event).filter(Event.kind == "pergunta").one()
        assert event.url and "abrir=perguntas#perguntas" in event.url

    def test_respostas_waits_and_times_out(self, video, no_sleep, capsys) -> None:
        questions.ask(video, "Pergunta?")
        code = main(
            ["respostas", video.video_id, "--pergunta", "1", "--esperar", "--timeout", "0.05"]
        )
        assert code == 3

        questions.answer(video, 1, option=None, text="pode seguir")
        assert main(["respostas", video.video_id, "--pergunta", "1", "--esperar"]) == 0
        assert "pode seguir" in capsys.readouterr().out
        assert questions.load(video)[0]["vista_pelo_claude_em"]

    def test_aguardar_wakes_up_on_a_reason_request(self, video, no_sleep, capsys) -> None:
        from mundoantigo.review import images as review

        video.write_json(
            "cenas",
            "storyboard.json",
            {"cenas": [{"indice": 1, "tipo": "lugar", "descricao_visual": "x"}]},
            step="cenas",
        )
        review.save_draft(video, "cena-001", redo=True, reason="parece moderno")
        review.submit(video)
        assert main(["aguardar", video.video_id, "--timeout", "5"]) == 0
        assert "cena-001" in capsys.readouterr().out
        assert review.claude_pending(video)[0]["visto_pelo_claude_em"]
        assert main(["aguardar", video.video_id, "--timeout", "0.05"]) == 3

    def test_nota_shows_up_under_the_step(self, video, settings, sessions) -> None:
        assert (
            main(["nota", video.video_id, "--etapa", "pesquisa", "Dossiê com 49 afirmações"]) == 0
        )
        client = TestClient(create_app(settings))
        body = client.get(f"/videos/{video.video_id}/etapas/pesquisa").text
        assert "Dossiê com 49 afirmações" in body


class TestPage:
    def test_open_questions_are_on_top_and_can_be_answered(self, video, settings) -> None:
        entry = questions.ask(video, "A ou B?", options=["A", "B"])
        client = TestClient(create_app(settings))
        page = client.get(f"/videos/{video.video_id}?abrir=perguntas").text
        assert 'id="perguntas"' in page and "A ou B?" in page
        state = client.get(f"/api/videos/{video.video_id}/estado").json()
        assert state["perguntas_abertas"] == 1 and state["claude"]["estado"] == "ausente"

        url = f"/api/videos/{video.video_id}/perguntas/{entry['id']}"
        assert client.put(f"{url}/rascunho", json={"opcao": "A"}).status_code == 200
        answered = client.post(f"{url}/responder", json={"opcao": "A", "texto": "ok"})
        assert answered.status_code == 200
        assert questions.answered_unseen(video)[0]["resposta"]["texto"] == "ok"
        bad = client.post(f"{url}/responder", json={"opcao": "A"})
        assert bad.status_code == 422
