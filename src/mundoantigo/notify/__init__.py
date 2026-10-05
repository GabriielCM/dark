"""Avisos para o revisor: o toast do Windows com som (fase C).

Atras de um adaptador, como todo provedor (CLAUDE.md): `notificacoes.padrao`
no app.yaml escolhe windows, log ou nenhum. Um aviso que falha nunca derruba
o worker.
"""

from .announcer import Announcer, NullAnnouncer
from .base import Notice, Notifier
from .factory import build_notifier
from .simple import FakeNotifier, LogNotifier, NullNotifier

__all__ = [
    "Announcer",
    "FakeNotifier",
    "LogNotifier",
    "Notice",
    "Notifier",
    "NullAnnouncer",
    "NullNotifier",
    "build_notifier",
]
