"""A esteira: ComfyUI, painel e worker, cada um no seu processo.

Sobe o que nao estiver rodando como processo destacado, que sobrevive ao
terminal e a sessao do Claude Code que o chamou: uma tarefa em segundo plano
da sessao morre em 2 h, e foi assim que o ComfyUI caiu no meio das imagens
de Gize (04/10). Depois abre a pagina da producao no navegador.

Idempotente: chamar de novo so confere e abre a pagina. O pid de cada
processo fica em `data/run/<servico>.json` e o log em `data/logs/`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..paths import get_paths
from ..web.links import page_url, panel_base

#  Windows: processo sem console, em grupo proprio e fora do "job" de quem
#  chamou, para nao morrer junto com o terminal ou a sessao.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
LOG_MAX_BYTES = 20 * 1024 * 1024
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


class EsteiraError(RuntimeError):
    """Algo impediu a esteira de subir. A mensagem diz o que fazer."""


@dataclass
class Service:
    name: str
    argv: list[str]
    cwd: Path
    health: Callable[[], bool]
    #  Saude de quem ocupa o endereco mas nao e o nosso servico (porta tomada).
    foreign: Callable[[], bool] | None = None

    @property
    def pidfile(self) -> Path:
        return get_paths().data / "run" / f"{self.name}.json"

    @property
    def log(self) -> Path:
        return get_paths().logs / f"{self.name}.log"


# -- processos -----------------------------------------------------------------


def pid_alive(pid: int) -> bool:
    """O processo existe e e um Python (protege contra pid reaproveitado)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                return False
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return "python" in buffer.value.lower()
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(service: Service) -> int | None:
    try:
        data = json.loads(service.pidfile.read_text(encoding="utf-8"))
        return int(data["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def is_running(service: Service) -> bool:
    if service.health():
        return True
    pid = read_pid(service)
    return pid is not None and pid_alive(pid)


def _rotate(log: Path) -> None:
    if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
        log.replace(log.with_suffix(".log.1"))


def start(service: Service) -> int:
    """Sobe o servico destacado. Devolve o pid."""
    service.log.parent.mkdir(parents=True, exist_ok=True)
    service.pidfile.parent.mkdir(parents=True, exist_ok=True)
    _rotate(service.log)
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    with service.log.open("ab") as log:
        log.write(f"\n--- {datetime.now(UTC).isoformat()} esteira sobe {service.name}\n".encode())
        log.flush()
        kwargs: dict[str, Any] = {
            "cwd": str(service.cwd),
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "env": env,
            "close_fds": True,
        }
        if sys.platform == "win32":
            flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            try:
                process = subprocess.Popen(
                    service.argv, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **kwargs
                )
            except OSError:
                #  O job de quem chamou nao deixa sair dele: sobe dentro mesmo.
                process = subprocess.Popen(service.argv, creationflags=flags, **kwargs)
        else:
            process = subprocess.Popen(service.argv, start_new_session=True, **kwargs)
    service.pidfile.write_text(
        json.dumps(
            {
                "pid": process.pid,
                "argv": service.argv,
                "iniciado_em": datetime.now(UTC).isoformat(),
                "log": str(service.log),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return process.pid


def tail(log: Path, lines: int = 20) -> str:
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def wait_for(check: Callable[[], bool], seconds: float, *, step: float = 1.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(step)
    return check()


# -- servicos ------------------------------------------------------------------


def _get(url: str, timeout: float = 2.0) -> httpx.Response | None:
    try:
        return httpx.get(url, timeout=timeout)
    except httpx.HTTPError:
        return None


def comfyui_url(settings: Settings) -> str | None:
    """Endereco do ComfyUI, se a esteira deve cuidar dele (provedor comfyui, local)."""
    images = (settings.app.get("provedores") or {}).get("imagem") or {}
    if images.get("padrao") != "comfyui":
        return None
    url = str((images.get("comfyui") or {}).get("url", "http://127.0.0.1:8188")).rstrip("/")
    return url if urlparse(url).hostname in LOCAL_HOSTS else None


def services(settings: Settings) -> list[Service]:
    root = get_paths().root
    python = sys.executable
    base = panel_base(settings)

    def panel_ok() -> bool:
        response = _get(f"{base}/saude")
        if response is None or response.status_code != 200:
            return False
        try:
            data = response.json()
        except ValueError:
            return False
        return bool(data.get("ok")) and "provedores" in data

    def panel_foreign() -> bool:
        response = _get(base)
        return response is not None and not panel_ok()

    found = [
        Service(
            "painel",
            [python, "-m", "mundoantigo", "painel"],
            root,
            panel_ok,
            panel_foreign,
        ),
    ]

    worker = Service("worker", [python, "-m", "mundoantigo", "worker"], root, lambda: False)
    found.append(worker)

    url = comfyui_url(settings)
    cfg = (settings.app.get("esteira") or {}).get("comfyui") or {}
    if url and cfg.get("ligar", "auto") != "nunca":
        folder = Path(os.environ.get("MA_COMFYUI_DIR") or cfg.get("diretorio", "C:/dev/ComfyUI"))
        command = [str(part) for part in cfg.get("comando", [])]
        if command:
            executable = folder / command[0]
            argv = [str(executable) if executable.exists() else command[0], *command[1:]]
            found.insert(
                0,
                Service(
                    "comfyui",
                    argv,
                    folder,
                    lambda: (r := _get(f"{url}/system_stats")) is not None and r.status_code == 200,
                ),
            )
    return found


# -- comandos ------------------------------------------------------------------


def disabled() -> bool:
    """MA_ESTEIRA=nenhuma desliga a esteira (os testes, uma maquina so de painel)."""
    return os.environ.get("MA_ESTEIRA", "").lower() in ("nenhuma", "desligada", "0")


def ensure_all(
    settings: Settings,
    video_id: str | None = None,
    *,
    step: str | None = None,
    open_browser: bool = True,
    with_comfyui: bool = True,
    report: Callable[[str], None] = print,
) -> list[str]:
    """Sobe o que falta e abre a pagina. Devolve os servicos que subiram agora."""
    if disabled():
        report("esteira desligada (MA_ESTEIRA)")
        return []
    started: list[str] = []
    by_name = {s.name: s for s in services(settings)}

    comfy = by_name.get("comfyui")
    if comfy and with_comfyui and not is_running(comfy):
        pid = start(comfy)
        started.append("comfyui")
        report(f"ComfyUI subindo (pid {pid}); o log fica em {comfy.log}")

    panel = by_name["painel"]
    if not panel.health():
        if panel.foreign and panel.foreign():
            raise EsteiraError(
                f"a porta do painel ({panel_base(settings)}) esta ocupada por outro programa; "
                "feche-o ou use MA_PANEL_PORT"
            )
        pid = start(panel)
        started.append("painel")
        if not wait_for(panel.health, 25):
            raise EsteiraError(f"o painel nao respondeu. Fim do log:\n{tail(panel.log)}")
        report(f"painel no ar em {panel_base(settings)} (pid {pid})")

    if video_id and open_browser:
        url = page_url(settings, video_id, step)
        webbrowser.open(url)
        report(f"pagina aberta: {url}")

    if comfy and with_comfyui and "comfyui" in started:
        espera = float(
            ((settings.app.get("esteira") or {}).get("comfyui") or {}).get("espera_s", 180)
        )
        if not wait_for(comfy.health, espera, step=2.0):
            raise EsteiraError(
                f"o ComfyUI nao respondeu em {espera:.0f} s. Fim do log:\n{tail(comfy.log)}"
            )
        report("ComfyUI no ar")

    worker = by_name["worker"]
    if not is_running(worker):
        pid = start(worker)
        started.append("worker")
        time.sleep(3)
        if not pid_alive(pid):
            raise EsteiraError(f"o worker caiu ao subir. Fim do log:\n{tail(worker.log)}")
        report(f"worker rodando (pid {pid}); o log fica em {worker.log}")
    return started


def status(settings: Settings) -> list[dict[str, Any]]:
    rows = []
    for service in services(settings):
        pid = read_pid(service)
        rows.append(
            {
                "servico": service.name,
                "rodando": is_running(service),
                "pid": pid if pid and pid_alive(pid) else None,
                "log": str(service.log),
            }
        )
    return rows


def stop_all(settings: Settings, *, report: Callable[[str], None] = print) -> list[str]:
    """Para o que a esteira subiu (so os processos com pid registrado)."""
    stopped = []
    for service in services(settings):
        pid = read_pid(service)
        if pid is None or not pid_alive(pid):
            service.pidfile.unlink(missing_ok=True)
            continue
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False
            )
        else:
            os.kill(pid, 15)
        service.pidfile.unlink(missing_ok=True)
        stopped.append(service.name)
        report(f"{service.name} parado (pid {pid})")
    return stopped
