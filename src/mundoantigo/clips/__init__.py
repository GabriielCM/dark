"""Cortes verticais para o TikTok (ADR 0010).

O codigo mede, o LLM escolhe: `candidates` lista os trechos que cabem na
duracao (frases inteiras, dentro de um bloco, nos dois idiomas), o LLM escolhe
os melhores e escreve gancho, legenda e hashtags, e `selection` confere tudo
antes de qualquer render.
"""

from __future__ import annotations

from .candidates import Candidate, ClipsConfig, Span, candidates
from .selection import Clip, Selection, SelectionError, normalize_hashtag, validate_selection

__all__ = [
    "Candidate",
    "Clip",
    "ClipsConfig",
    "Selection",
    "SelectionError",
    "Span",
    "candidates",
    "normalize_hashtag",
    "validate_selection",
]
