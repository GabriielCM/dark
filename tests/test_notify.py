"""Avisos do Windows (fase C, C4).

O revisor so e chamado quando a producao precisa dele, uma vez por parada,
com o link que abre a pagina direto na etapa. Um aviso que falha nunca para
o pipeline.
"""

from __future__ import annotations

import dataclasses
import sys

import pytest

from mundoantigo.db.models import Event
from mundoantigo.errors import PermanentError
from mundoantigo.notify import (
    Announcer,
    FakeNotifier,
    LogNotifier,
    NullNotifier,
    build_notifier,
)
from mundoantigo.pipeline import Runner, Worker
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from tests.fakes import responder


def _with(settings, **notificacoes):
    return dataclasses.replace(settings, app={**settings.app, "notificacoes": notificacoes})


class TestFactory:
    def test_the_config_picks_the_adapter(self, settings, monkeypatch) -> None:
        monkeypatch.delenv("MA_NOTIFICACOES", raising=False)
        assert isinstance(build_notifier(_with(settings, padrao="nenhum")), NullNotifier)
        assert isinstance(build_notifier(_with(settings, padrao="log")), LogNotifier)

    def test_windows_off_windows_falls_back_to_the_log(self, settings, monkeypatch) -> None:
        monkeypatch.delenv("MA_NOTIFICACOES", raising=False)
        monkeypatch.setattr(sys, "platform", "linux")
        assert isinstance(build_notifier(_with(settings, padrao="windows")), LogNotifier)

    def test_the_environment_wins(self, settings, monkeypatch) -> None:
        monkeypatch.setenv("MA_NOTIFICACOES", "nenhum")
        assert isinstance(build_notifier(_with(settings, padrao="log")), NullNotifier)


class TestAnnouncer:
    def test_a_block_notifies_once_with_the_deep_link(self, settings, sessions, make_video) -> None:
        video_id = make_video("v-aviso", "Gizé")
        notifier = FakeNotifier()
        announcer = Announcer(sessions, notifier, settings)

        assert announcer.announce(video_id, "bloqueio", "Imagens prontas", step="revisao_imagens")
        assert not announcer.announce(
            video_id, "bloqueio", "Imagens prontas", step="revisao_imagens"
        ), "o mesmo aviso repetiu em menos de 10 minutos"

        assert len(notifier.sent) == 1
        notice = notifier.sent[0]
        assert notice.url and notice.url.endswith(
            f"/videos/{video_id}?abrir=revisao_imagens#etapa-revisao_imagens"
        )
        assert "Gizé" in notice.title and notice.insistent
        with sessions() as s:
            events = s.query(Event).filter(Event.video_id == video_id).all()
        assert len(events) == 2 and [e.notified for e in events] == [True, False]

    def test_waiting_for_the_session_is_only_recorded(self, settings, sessions, make_video) -> None:
        video_id = make_video("v-sessao")
        notifier = FakeNotifier()
        Announcer(sessions, notifier, settings).announce(video_id, "sessao", "aguardando a sessao")
        assert notifier.sent == []
        with sessions() as s:
            assert s.query(Event).filter(Event.kind == "sessao").count() == 1

    def test_ready_package_is_a_quiet_notice(self, settings, sessions, make_video) -> None:
        notifier = FakeNotifier()
        Announcer(sessions, notifier, settings).announce(make_video("v-pronto"), "pronto", "ok")
        assert notifier.sent and notifier.sent[0].insistent is False

    def test_a_failing_notifier_never_raises(self, settings, sessions, make_video) -> None:
        announcer = Announcer(sessions, FakeNotifier(fail=True), settings)
        assert announcer.announce(make_video("v-falha"), "falha", "caiu") is False


def _runner(settings, recorder, sessions, notifier) -> Runner:
    settings = dataclasses.replace(
        settings, app={**settings.app, "revisao_imagens": {"ativo": True}}
    )
    llm = FakeLLM(costs=recorder, responses=responder())
    runner = Runner.build(
        settings=settings,
        providers=fake_registry(settings, recorder, llm=llm),
        session_factory=sessions,
    )
    runner.announcer = Announcer(sessions, notifier, settings)
    return runner


class TestRunnerHooks:
    async def test_the_grid_calls_the_reviewer(
        self, settings, recorder, sessions, com_remotion
    ) -> None:
        notifier = FakeNotifier()
        runner = _runner(settings, recorder, sessions, notifier)
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await Worker(runner, poll_seconds=0).drain(limit=80)

        assert len(notifier.sent) == 1
        notice = notifier.sent[0]
        assert "imagens" in notice.body.lower() and "revisão" in notice.body
        assert notice.url and "abrir=revisao_imagens" in notice.url
        assert notice.video_id == video_id

    async def test_a_permanent_failure_calls_the_reviewer(
        self, settings, recorder, sessions, monkeypatch
    ) -> None:
        notifier = FakeNotifier()
        runner = _runner(settings, recorder, sessions, notifier)
        runner.queue.enqueue_video("X")
        from mundoantigo.pipeline.steps.s01_pauta import PautaStep

        async def broken(self, ctx):
            raise PermanentError("chave invalida")

        monkeypatch.setattr(PautaStep, "run", broken)
        await Worker(runner, poll_seconds=0).drain(limit=3)
        assert [n.kind for n in notifier.sent] == ["falha"]
        assert "Pauta falhou" in notifier.sent[0].body

    async def test_a_retry_does_not_call_anyone(
        self, settings, recorder, sessions, monkeypatch
    ) -> None:
        notifier = FakeNotifier()
        runner = _runner(settings, recorder, sessions, notifier)
        runner.queue.enqueue_video("X")
        from mundoantigo.pipeline.steps.s01_pauta import PautaStep

        async def flaky(self, ctx):
            raise OSError("rede caiu")

        monkeypatch.setattr(PautaStep, "run", flaky)
        await Worker(runner, poll_seconds=0).drain(limit=1)
        assert notifier.sent == []


class TestCli:
    def test_test_notice_reports_the_adapter(self, tmp_project, capsys) -> None:
        from mundoantigo.cli import main

        #  MA_NOTIFICACOES=nenhum nos testes: o aviso nao aparece e o comando diz isso.
        assert main(["notificar"]) == 1
        assert "nenhum" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32", reason="toast so existe no Windows")
def test_windows_toast_errors_are_swallowed(monkeypatch) -> None:
    pytest.importorskip("windows_toasts")
    import windows_toasts

    from mundoantigo.notify.base import Notice
    from mundoantigo.notify.windows import WindowsToastNotifier

    class Broken:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("sem WinRT")

    monkeypatch.setattr(windows_toasts, "InteractableWindowsToaster", Broken)
    assert WindowsToastNotifier().send(Notice("t", "b", url="http://127.0.0.1:8765/")) is False
