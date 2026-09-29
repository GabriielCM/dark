"""Casa as palavras reconhecidas pelo Whisper com o texto do roteiro (fase B5).

O faster-whisper transcreve o que ouve: "dezesseis mil e oitocentos" onde o
roteiro diz "16.800", "Polibio" onde o roteiro diz "Políbio". A legenda precisa
ser o roteiro, com acento e pontuacao. Aqui cada palavra do roteiro recebe um
tempo: o do Whisper quando as palavras casam, interpolado quando nao casam.

Com o tempo exato de cada frase (a sintese e frase a frase), o casamento e
feito dentro da janela da frase: um erro de reconhecimento nunca empurra a
legenda para a frase vizinha.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..providers.align import WordTiming
from .segment import Unit

#  Folga nas bordas da frase: o Whisper as vezes marca o inicio um pouco antes.
_WINDOW_SLACK_S = 0.25


@dataclass(frozen=True, slots=True)
class TimedToken:
    text: str
    start: float
    end: float
    unit_id: str | None


def _norm(token: str) -> str:
    ascii_token = unicodedata.normalize("NFKD", token).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_token.lower())


def _align_tokens(
    tokens: list[str],
    words: Sequence[WordTiming],
    start: float,
    end: float,
    unit_id: str | None,
) -> list[TimedToken]:
    if not tokens:
        return []
    times: list[tuple[float, float] | None] = [None] * len(tokens)
    matcher = SequenceMatcher(
        a=[_norm(t) for t in tokens], b=[_norm(w.word) for w in words], autojunk=False
    )
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            word = words[block.b + k]
            times[block.a + k] = (word.start, word.end)

    #  Lacunas: reparte o intervalo livre entre os tokens sem par, pelo tamanho.
    index = 0
    while index < len(tokens):
        if times[index] is not None:
            index += 1
            continue
        gap_end = index
        while gap_end < len(tokens) and times[gap_end] is None:
            gap_end += 1
        previous = times[index - 1] if index > 0 else None
        following = times[gap_end] if gap_end < len(tokens) else None
        left = previous[1] if previous else start
        right = following[0] if following else end
        right = max(right, left)
        weights = [max(1, len(tokens[i])) for i in range(index, gap_end)]
        total = sum(weights)
        cursor = left
        for i, weight in zip(range(index, gap_end), weights, strict=True):
            span = (right - left) * weight / total
            times[i] = (cursor, cursor + span)
            cursor += span
        index = gap_end

    out: list[TimedToken] = []
    last_end = start
    for token, pair in zip(tokens, times, strict=True):
        assert pair is not None
        token_start = min(max(pair[0], last_end, start), end)
        token_end = min(max(pair[1], token_start), end)
        out.append(TimedToken(token, round(token_start, 3), round(token_end, 3), unit_id))
        last_end = token_end
    return out


def align_units(
    units: Sequence[Unit],
    words: Sequence[WordTiming],
    unit_times: dict[str, tuple[float, float]] | None = None,
) -> list[TimedToken]:
    """Tempo de cada palavra do roteiro, na ordem, com a frase de origem."""
    if unit_times:
        out: list[TimedToken] = []
        for unit in units:
            start, end = unit_times[unit.id]
            window = [
                w
                for w in words
                if start - _WINDOW_SLACK_S <= (w.start + w.end) / 2 <= end + _WINDOW_SLACK_S
            ]
            out += _align_tokens(unit.text.split(), window, start, end, unit.id)
        return out

    #  Sem tempo por frase (provedor de voz que nao segmenta): alinha o texto
    #  todo de uma vez e marca cada palavra com a frase de onde veio.
    tokens = [(token, unit.id) for unit in units for token in unit.text.split()]
    start = words[0].start if words else 0.0
    end = words[-1].end if words else 0.0
    timed = _align_tokens([t for t, _ in tokens], words, start, end, None)
    return [
        TimedToken(t.text, t.start, t.end, unit_id)
        for t, (_, unit_id) in zip(timed, tokens, strict=True)
    ]


def unit_spans(tokens: Sequence[TimedToken]) -> dict[str, tuple[float, float]]:
    """Inicio e fim de cada frase a partir das palavras alinhadas."""
    spans: dict[str, tuple[float, float]] = {}
    for token in tokens:
        if token.unit_id is None:
            continue
        first = spans.get(token.unit_id)
        spans[token.unit_id] = (first[0] if first else token.start, token.end)
    return spans
