"""Lancador da esteira (fase C, C5).

Sobe ComfyUI, painel e worker como processos destacados, so o que falta, e
abre a pagina. Nenhum processo de verdade sobe nestes testes: Popen, saude
e navegador sao simulados.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import Any

import httpx
import pytest

from mundoantigo.ops import esteira


class FakeProcess:
    _next = 1000

    def __init__(self, argv: list[str], **kwargs: Any) -> None:
        FakeProcess._next += 1
        self.pid = FakeProcess._next
        self.argv = argv
        self.kwargs = kwargs


@pytest.fixture
def world(monkeypatch, tmp_project):
    """Saude dos servicos, processos iniciados e paginas abertas."""
    monkeypatch.delenv("MA_ESTEIRA", raising=False)
    state: dict[str, Any] = {
        "painel": False,
        "comfyui": False,
        "estranho": False,
        "popen": [],
        "abertas": [],
        "vivos": set(),
    }

    def fake_get(url: str, timeout: float = 2.0) -> httpx.Response | None:
        if "8188" in url:
            return httpx.Response(200, json={}) if state["comfyui"] else None
        if state["estranho"]:
            return httpx.Response(200, text="<html>outro programa</html>")
        if url.endswith("/saude") and state["painel"]:
            return httpx.Response(200, json={"ok": True, "provedores": {}})
        return None

    def fake_popen(argv: list[str], **kwargs: Any) -> FakeProcess:
        process = FakeProcess(argv, **kwargs)
        state["popen"].append(process)
        state["vivos"].add(process.pid)
        if "painel" in argv:
            state["painel"] = True
        if any("main.py" in part for part in argv):
            state["comfyui"] = True
        return process

    monkeypatch.setattr(esteira, "_get", fake_get)
    monkeypatch.setattr(esteira.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(esteira, "pid_alive", lambda pid: pid in state["vivos"])
    monkeypatch.setattr(esteira.time, "sleep", lambda s: None)
    monkeypatch.setattr(esteira.webbrowser, "open", lambda url: state["abertas"].append(url))
    return state


def _names(state) -> list[str]:
    started = []
    for process in state["popen"]:
        if "painel" in process.argv:
            started.append("painel")
        elif "worker" in process.argv:
            started.append("worker")
        else:
            started.append("comfyui")
    return started


class TestEnsure:
    def test_brings_up_what_is_missing_and_opens_the_page(self, settings, world) -> None:
        started = esteira.ensure_all(settings, "v1", step="revisao_imagens", report=lambda m: None)
        assert started == ["comfyui", "painel", "worker"]
        assert _names(world) == started
        assert world["abertas"][0].endswith(
            "/videos/v1?abrir=revisao_imagens#etapa-revisao_imagens"
        )
        assert esteira.read_pid(esteira.services(settings)[1]) is not None

    def test_running_services_are_left_alone(self, settings, world) -> None:
        world["painel"] = world["comfyui"] = True
        worker = next(s for s in esteira.services(settings) if s.name == "worker")
        worker.pidfile.parent.mkdir(parents=True, exist_ok=True)
        worker.pidfile.write_text('{"pid": 4242}', encoding="utf-8")
        world["vivos"].add(4242)

        assert esteira.ensure_all(settings, "v1", report=lambda m: None) == []
        assert world["popen"] == []
        assert len(world["abertas"]) == 1

    def test_a_foreign_program_on_the_panel_port_is_an_error(self, settings, world) -> None:
        world["comfyui"] = True
        world["estranho"] = True
        with pytest.raises(esteira.EsteiraError, match="ocupada"):
            esteira.ensure_all(settings, "v1", report=lambda m: None)

    def test_comfyui_is_skipped_when_images_come_from_elsewhere(self, settings, world) -> None:
        providers = {**settings.app["provedores"], "imagem": {"padrao": "flux_local"}}
        other = dataclasses.replace(settings, app={**settings.app, "provedores": providers})
        assert [s.name for s in esteira.services(other)] == ["painel", "worker"]
        assert esteira.ensure_all(other, None, report=lambda m: None) == ["painel", "worker"]

    def test_disabled_by_the_environment(self, settings, world, monkeypatch) -> None:
        monkeypatch.setenv("MA_ESTEIRA", "nenhuma")
        assert esteira.ensure_all(settings, "v1", report=lambda m: None) == []
        assert world["popen"] == []

    @pytest.mark.skipif(sys.platform != "win32", reason="flags de processo do Windows")
    def test_detached_flags_and_the_job_fallback(self, settings, world, monkeypatch) -> None:
        calls: list[int] = []
        original = esteira.subprocess.Popen

        def picky(argv, **kwargs):
            calls.append(kwargs["creationflags"])
            if kwargs["creationflags"] & esteira.CREATE_BREAKAWAY_FROM_JOB:
                raise OSError(5, "acesso negado")
            return original(argv, **kwargs)

        monkeypatch.setattr(esteira.subprocess, "Popen", picky)
        world["comfyui"] = True
        esteira.ensure_all(settings, None, report=lambda m: None)
        assert calls[0] & esteira.DETACHED_PROCESS
        assert calls[0] & esteira.CREATE_BREAKAWAY_FROM_JOB
        assert not calls[1] & esteira.CREATE_BREAKAWAY_FROM_JOB


class TestStop:
    def test_stop_uses_the_pid_files(self, settings, world, monkeypatch) -> None:
        esteira.ensure_all(settings, None, report=lambda m: None)
        killed: list[list[str]] = []
        monkeypatch.setattr(esteira.subprocess, "run", lambda argv, **kw: killed.append(argv))
        monkeypatch.setattr(esteira.os, "kill", lambda pid, sig: killed.append([str(pid)]))
        stopped = esteira.stop_all(settings, report=lambda m: None)
        assert set(stopped) == {"comfyui", "painel", "worker"}
        assert len(killed) == 3


class TestCli:
    def test_nova_starts_the_esteira_unless_told_not_to(
        self, settings, sessions, monkeypatch
    ) -> None:
        from mundoantigo import cli

        calls: list[str] = []
        monkeypatch.setattr(esteira, "ensure_all", lambda s, vid, **kw: calls.append(vid))
        assert cli.main(["nova", "Termas de Roma", "--pilar", "cotidiano"]) == 0
        assert cli.main(["nova", "Estradas romanas", "--sem-esteira"]) == 0
        assert len(calls) == 1 and "termas" in calls[0]
