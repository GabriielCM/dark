"""Linha do tempo unica para as duas narracoes (ADR 0011).

Com `faixa_unica`, o video PT sobe com a narracao EN como segunda faixa de
audio, e a faixa precisa caber no mesmo video. Cada bloco do roteiro fica
com a duracao da mais longa das duas narracoes. No idioma mais curto, cada
frase vai para a mesma fracao do bloco em que estava no audio natural: a
frase mantem a velocidade, e so as pausas crescem, mais depois das frases
longas. Como a montagem acompanha o bloco por fracao (ADR 0008), a fala dos
dois idiomas continua no mesmo ponto das imagens.

O bloco vai do inicio da primeira frase ate o inicio do bloco seguinte, com
a pausa que o fecha; o primeiro comeca no zero e o ultimo vai ate o fim do
audio. O WAV e lido e escrito com a biblioteca padrao, que basta para o PCM
mono do Kokoro.
"""

from __future__ import annotations

import wave
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Sentence:
    id: str
    block: int
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class SharedTimeline:
    #  Duracao de cada bloco na linha unica e onde ele comeca.
    lengths: dict[int, float]
    starts: dict[int, float]
    total: float


def block_spans(sentences: Sequence[Sentence], total: float) -> dict[int, tuple[float, float]]:
    """(inicio, fim) de cada bloco no audio natural, cobrindo o audio inteiro."""
    firsts: dict[int, float] = {}
    for s in sentences:
        firsts[s.block] = min(s.start, firsts.get(s.block, s.start))
    order = sorted(firsts)
    spans: dict[int, tuple[float, float]] = {}
    for i, block in enumerate(order):
        start = 0.0 if i == 0 else firsts[block]
        end = firsts[order[i + 1]] if i + 1 < len(order) else total
        spans[block] = (start, max(end, start))
    return spans


def shared_timeline(*languages: Mapping[int, tuple[float, float]]) -> SharedTimeline:
    """A linha unica: cada bloco com a duracao maior entre os idiomas."""
    blocks = set(languages[0])
    for spans in languages[1:]:
        if set(spans) != blocks:
            raise ValueError(
                f"blocos diferentes entre os idiomas: {sorted(blocks)} e {sorted(spans)}"
            )
    lengths: dict[int, float] = {}
    starts: dict[int, float] = {}
    cursor = 0.0
    for block in sorted(blocks):
        #  Ao milissegundo, como os tempos de frase.
        lengths[block] = round(max(end - start for start, end in (s[block] for s in languages)), 3)
        starts[block] = round(cursor, 3)
        cursor += lengths[block]
    return SharedTimeline(lengths=lengths, starts=starts, total=round(cursor, 3))


def place(
    sentences: Sequence[Sentence],
    spans: Mapping[int, tuple[float, float]],
    timeline: SharedTimeline,
) -> dict[str, tuple[float, float]]:
    """Novo (inicio, fim) de cada frase: mesma fracao do bloco, mesma duracao."""
    placed: dict[str, tuple[float, float]] = {}
    for s in sentences:
        start, end = spans[s.block]
        natural = end - start
        factor = timeline.lengths[s.block] / natural if natural > 0 else 1.0
        new_start = timeline.starts[s.block] + (s.start - start) * factor
        placed[s.id] = (round(new_start, 3), round(new_start + s.end - s.start, 3))
    return placed


def stretch(spans: Mapping[int, tuple[float, float]], timeline: SharedTimeline) -> dict[int, float]:
    """Quanto cada bloco foi esticado neste idioma (0.05 = 5% mais longo)."""
    return {
        block: round(timeline.lengths[block] / (end - start) - 1, 4) if end > start else 0.0
        for block, (start, end) in spans.items()
    }


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as fh:
        return fh.getnframes() / float(fh.getframerate())


def relay_wav(
    source: Path,
    destination: Path,
    moves: Iterable[tuple[float, float, float]],
    total: float,
) -> None:
    """Copia cada trecho (inicio, fim, novo inicio) do audio natural para a linha unica."""
    with wave.open(str(source), "rb") as src:
        channels, width, rate = src.getnchannels(), src.getsampwidth(), src.getframerate()
        data = src.readframes(src.getnframes())
    frame = channels * width
    out = bytearray(round(total * rate) * frame)
    for start, end, new_start in moves:
        piece = data[round(start * rate) * frame : round(end * rate) * frame]
        at = round(new_start * rate) * frame
        piece = piece[: max(0, len(out) - at)]
        out[at : at + len(piece)] = piece
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(width)
        dst.setframerate(rate)
        dst.writeframes(bytes(out))
