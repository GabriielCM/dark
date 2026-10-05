"""Escolhe o adaptador de avisos pela configuracao (`notificacoes` no app.yaml)."""

from __future__ import annotations

import importlib.util
import logging
import os
import sys

from ..config import Settings
from .base import Notifier
from .simple import LogNotifier, NullNotifier

log = logging.getLogger(__name__)


def build_notifier(settings: Settings) -> Notifier:
    cfg = settings.app.get("notificacoes") or {}
    #  MA_NOTIFICACOES sobrescreve (os testes desligam: nenhum toast de verdade).
    chosen = os.environ.get("MA_NOTIFICACOES") or str(cfg.get("padrao", "log"))
    if chosen == "nenhum":
        return NullNotifier()
    if chosen == "windows":
        if sys.platform != "win32":
            log.info("avisos do Windows fora do Windows: indo para o log")
            return LogNotifier()
        if importlib.util.find_spec("windows_toasts") is None:
            log.warning("windows-toasts nao instalado (uv sync --extra windows): avisos no log")
            return LogNotifier()
        from .windows import WindowsToastNotifier

        windows = cfg.get("windows") or {}
        return WindowsToastNotifier(
            sound=str(windows.get("som", "Reminder")),
            insistent=bool(windows.get("insistente", True)),
            aumid=windows.get("aumid"),
        )
    return LogNotifier()
