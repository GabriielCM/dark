"""Corta a narracao em cenas (fase B3, revisto no ADR 0008).

Codigo, nao LLM: o ritmo e regra. Os videos entregues trocavam de imagem a
cada ~6 s (docs/estilo/analise-entregas.md), 164 de 185 cenas entre 4 e 8 s.

A narracao roda antes do storyboard, entao o corte usa o tempo real de cada
palavra, e nao uma estimativa por palavras por minuto (a primeira amostra
real saiu com 7,8 s por cena por causa da estimativa e de uma regra gulosa).
Bloco a bloco, sem nunca atravessar a fronteira de um bloco (onde mudam
capitulo, titulo e trilha), escolhe os cortes que deixam cada cena mais perto
do alvo, em PT e em EN ao mesmo tempo:
- o corte normal e no comeco de uma frase;
- uma frase longa demais (acima de `comma_above_s` em PT ou no EN) tambem
  pode ser cortada depois de uma virgula, ponto e virgula, dois-pontos ou
  antes de um travessao, onde a voz ja pausa.

A cena guarda texto, nao segundos: as frases que cobre, a palavra da primeira
frase em que comeca e a fracao do bloco que ocupa. Refazer a voz muda os
tempos, mas nao o corte: a montagem recalcula (scenes/timeline.py). No video
EN a cena ocupa a mesma fracao do bloco correspondente: a adaptacao nao tem
as mesmas frases, mas tem os mesmos blocos, na mesma ordem.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from ..text.segment import Unit

#  Pausa depois de cada frase na estimativa (a mesma da narracao).
PAUSE_S = 0.25
#  Custo de uma cena fora da faixa: domina qualquer desvio do alvo dentro dela.
OUT_OF_RANGE_WEIGHT = 20.0
OUT_OF_RANGE_STEP = 5.0
#  Custo de trocar de imagem no meio de uma frase: so quando compensa.
MID_SENTENCE_COST = 1.0
_DASHES = ("\u2014", "\u2013", "-")  # travessao, meia-risca, hifen


@dataclass
class SceneSlot:
    index: int
    block: int
    units: list[str] = field(default_factory=list)
    #  Duracao da cena na narracao PT e a estimada no EN.
    seconds: float = 0.0
    seconds_en: float = 0.0
    #  Fracao do bloco (por palavras) em que a cena comeca e termina.
    span: tuple[float, float] = (0.0, 1.0)
    #  Palavra da primeira frase em que a cena comeca (0: no comeco da frase).
    first_word: int = 0
    text: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "indice": self.index,
            "bloco": self.block,
            "frases": self.units,
            "inicio_palavra": self.first_word,
            "fracao_bloco": [round(self.span[0], 4), round(self.span[1], 4)],
            "duracao_s": round(self.seconds, 2),
            "duracao_en_s": round(self.seconds_en, 2),
        }


@dataclass(frozen=True)
class SpeechTimings:
    """Onde cada palavra do roteiro PT comeca e quanto dura cada bloco no EN.

    `starts` tem uma entrada por palavra de `units` (na ordem) e mais uma, o
    fim do audio. A primeira palavra de cada frase comeca no inicio da frase,
    como a montagem conta.
    """

    starts: tuple[float, ...]
    en_blocks: dict[int, float]
    measured: bool

    @classmethod
    def from_tempos(
        cls, units: list[Unit], pt: dict[str, Any], en: dict[str, Any] | None = None
    ) -> SpeechTimings | None:
        """Tempos da narracao (`narracao/tempos.*.json`); None se nao casam com o roteiro."""
        words = pt.get("palavras") or []
        total = sum(u.words for u in units)
        if not total or len(words) != total:
            return None
        starts = [float(w["i"]) for w in words]
        sentence_start = {f["id"]: float(f["inicio"]) for f in pt.get("frases", [])}
        cursor = 0
        for unit in units:
            if unit.id in sentence_start:
                starts[cursor] = sentence_start[unit.id]
            cursor += unit.words
        starts.append(float(pt.get("duracao_s") or starts[-1]))
        for i in range(1, len(starts)):
            #  O alinhamento pode devolver palavras coladas; o tempo nunca volta.
            starts[i] = max(starts[i], starts[i - 1])
        pt_blocks = _block_seconds(units, starts)
        en_blocks = {
            int(b["indice"]): float(b["fim_s"]) - float(b["inicio_s"])
            for b in (en or {}).get("blocos", [])
        }
        return cls(tuple(starts), {**pt_blocks, **en_blocks}, measured=True)

    @classmethod
    def estimated(cls, units: list[Unit], words_per_minute: int) -> SpeechTimings:
        """Sem narracao: palavras por minuto do canal e a pausa entre frases."""
        per_word = 60 / max(words_per_minute, 1)
        starts: list[float] = []
        clock = 0.0
        for unit in units:
            for _ in range(unit.words):
                starts.append(clock)
                clock += per_word
            clock += PAUSE_S
        starts.append(clock)
        return cls(tuple(starts), _block_seconds(units, starts), measured=False)


def _block_seconds(units: list[Unit], starts: list[float]) -> dict[int, float]:
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    cursor = 0
    for unit in units:
        first.setdefault(unit.block, cursor)
        cursor += unit.words
        last[unit.block] = cursor
    return {b: starts[last[b]] - starts[first[b]] for b in first}


def _soft_breaks(tokens: list[str]) -> list[int]:
    """Palavras da frase antes das quais a voz ja pausa (virgula, travessao)."""
    return [k for k in range(1, len(tokens)) if tokens[k - 1][-1] in ",;:" or tokens[k] in _DASHES]


@dataclass(frozen=True)
class _Block:
    """Um bloco da narracao e seus pontos de corte."""

    first: int
    words: int
    en_seconds: float
    #  Palavra de cada ponto de corte, se ele cai no meio de uma frase e de que
    #  frase ele e. O ultimo ponto e o fim do bloco.
    cuts: list[tuple[int, bool, str]]
    owner: list[str]

    def durations(self, starts: tuple[float, ...], a: int, b: int) -> tuple[float, float]:
        """Duracao da cena entre dois pontos de corte, em PT e no EN."""
        begin, end = self.cuts[a][0], self.cuts[b][0]
        return starts[end] - starts[begin], self.en_seconds * (end - begin) / self.words


@dataclass(frozen=True)
class _Pace:
    target_s: float
    min_s: float
    max_s: float

    def cost(self, seconds: float) -> float:
        total = (seconds - self.target_s) ** 2 / 2
        excess = max(self.min_s - seconds, seconds - self.max_s, 0.0)
        if excess:
            total += OUT_OF_RANGE_WEIGHT * excess**2 + OUT_OF_RANGE_STEP
        return total


def _best_path(block: _Block, starts: tuple[float, ...], pace: _Pace) -> list[int]:
    """Programacao dinamica: o jeito mais barato de cobrir o bloco ate cada corte."""
    n = len(block.cuts)
    best = [0.0] + [float("inf")] * (n - 1)
    previous = [0] * n
    for b in range(1, n):
        for a in range(b):
            pt, en = block.durations(starts, a, b)
            candidate = best[a] + pace.cost(pt) + pace.cost(en)
            if block.cuts[a][1]:
                candidate += MID_SENTENCE_COST
            if candidate < best[b]:
                best[b], previous[b] = candidate, a
    path = [n - 1]
    while path[-1] != 0:
        path.append(previous[path[-1]])
    return path[::-1]


def group_scenes(
    units: list[Unit],
    timings: SpeechTimings,
    *,
    target_s: float = 6.0,
    min_s: float = 4.0,
    max_s: float = 8.0,
    comma_above_s: float = 8.0,
) -> list[SceneSlot]:
    tokens = [t for u in units for t in u.text.split()]
    starts = timings.starts
    pace = _Pace(target_s, min_s, max_s)
    scenes: list[SceneSlot] = []
    cursor = 0
    for block_index in sorted({u.block for u in units}):
        block_units = [u for u in units if u.block == block_index]
        block_words = sum(u.words for u in block_units) or 1
        en_seconds = timings.en_blocks.get(block_index, 0.0)
        cuts: list[tuple[int, bool, str]] = []
        owner: list[str] = []
        block_first = cursor
        for unit in block_units:
            first = cursor
            cuts.append((first, False, unit.id))
            owner += [unit.id] * unit.words
            cursor += unit.words
            pt_seconds = starts[cursor] - starts[first]
            en_estimate = en_seconds * unit.words / block_words
            if max(pt_seconds, en_estimate) > comma_above_s:
                cuts += [(first + k, True, unit.id) for k in _soft_breaks(unit.text.split())]
        cuts.append((cursor, False, ""))
        block = _Block(block_first, block_words, en_seconds, cuts, owner)
        sentence_first = {uid: w for w, mid, uid in cuts if not mid}

        for a, b in itertools.pairwise(_best_path(block, starts, pace)):
            begin, end = cuts[a][0], cuts[b][0]
            pt_seconds, en_estimate = block.durations(starts, a, b)
            scenes.append(
                SceneSlot(
                    index=0,
                    block=block_index,
                    units=list(dict.fromkeys(owner[begin - block_first : end - block_first])),
                    seconds=pt_seconds,
                    seconds_en=en_estimate,
                    span=((begin - block_first) / block_words, (end - block_first) / block_words),
                    first_word=begin - sentence_first[cuts[a][2]],
                    text=" ".join(tokens[begin:end]),
                )
            )

    for index, scene in enumerate(scenes, start=1):
        scene.index = index
    return scenes
