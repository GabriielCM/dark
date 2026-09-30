"""Titulo de capitulo na tela.

Nos videos entregues, a descricao trazia o titulo inteiro ("Antes do sol:
desmontar o mundo") e a tela so o trecho curto ("ANTES DO SOL"). O roteiro
escreve um titulo so; a tela usa o que vem antes dos dois-pontos.
"""

from __future__ import annotations

#  Acima disto o titulo encolhe na tela; o importador avisa.
SCREEN_TITLE_MAX_CHARS = 24


def screen_title(title: str) -> str:
    """O trecho antes dos primeiros dois-pontos, ou o titulo inteiro."""
    short = title.split(":", 1)[0].strip()
    return short or title.strip()
