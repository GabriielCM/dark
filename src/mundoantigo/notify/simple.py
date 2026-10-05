"""Avisos sem janela: no log, em lugar nenhum, e o falso dos testes."""

from __future__ import annotations

import logging

from .base import Notice

log = logging.getLogger(__name__)


class LogNotifier:
    """Fora do Windows (ou sem o extra windows): o aviso vai para o log."""

    name = "log"

    def send(self, notice: Notice) -> bool:
        log.info(
            "AVISO %s: %s%s", notice.title, notice.body, f" ({notice.url})" if notice.url else ""
        )
        return True


class NullNotifier:
    name = "nenhum"

    def send(self, notice: Notice) -> bool:
        return False


class FakeNotifier:
    """Guarda os avisos para os testes conferirem."""

    name = "fake"

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[Notice] = []
        self.fail = fail

    def send(self, notice: Notice) -> bool:
        if self.fail:
            return False
        self.sent.append(notice)
        return True
