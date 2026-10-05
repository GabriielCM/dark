"""Contrato dos avisos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Notice:
    title: str
    body: str
    #  Link aberto pelo clique: a pagina da producao, direto na etapa.
    url: str | None = None
    kind: str = "nota"
    video_id: str | None = None
    #  Fica na tela ate ser fechado (precisa do revisor). Falso: some sozinho.
    insistent: bool = True


class Notifier(Protocol):
    name: str

    def send(self, notice: Notice) -> bool:
        """Mostra o aviso. Devolve se mostrou; nunca levanta excecao."""
        ...
