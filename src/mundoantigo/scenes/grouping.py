"""Corta a narracao em cenas (fase B3, revisto nos ADRs 0008 e 0012).

Codigo, nao LLM: o ritmo e regra. Os videos entregues trocavam de imagem a
cada ~6 s (docs/estilo/analise-entregas.md); desde o ADR 0012 o alvo e ~3 s,
e ~2,5 s no primeiro minuto (`PaceBands`), pelo ritmo dos cortes do TikTok.

A narracao roda antes do storyboard, entao o corte usa o tempo real de cada
palavra, e nao uma estimativa por palavras por minuto (a primeira amostra
real saiu com 7,8 s por cena por causa da estimativa e de uma regra gulosa).
Bloco a bloco, sem nunca atravessar a fronteira de um bloco (onde mudam
capitulo, titulo e trilha), escolhe os cortes que deixam cada cena mais perto
do alvo, em PT e em EN ao mesmo tempo:
- o corte normal e no comeco de uma frase;
- uma frase que nao cabe numa cena (acima do maximo do ritmo daquele trecho,
  em PT ou no EN) tambem pode ser cortada: de preferencia depois de uma
  virgula, ponto e virgula, dois-pontos ou antes de um travessao, onde a voz
  ja pausa; depois, antes de uma conjuncao; por fim, entre duas palavras
  quaisquer, mas nunca colado nas pontas da frase, depois de um numero ou de
  uma palavra que pede a seguinte ("de", "para", "cada", "foi").
  O alinhamento devolve as palavras coladas, sem pausa entre elas, entao a
  pontuacao e o unico sinal de respiro que existe.

A cena guarda texto, nao segundos: as frases que cobre, a palavra da primeira
frase em que comeca e a fracao do bloco que ocupa. Refazer a voz muda os
tempos, mas nao o corte: a montagem recalcula (scenes/timeline.py). No video
EN a cena ocupa a mesma fracao do bloco correspondente: a adaptacao nao tem
as mesmas frases, mas tem os mesmos blocos, na mesma ordem.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple

from ..text.segment import Unit

if TYPE_CHECKING:
    from ..config import ScenesConfig

#  Pausa depois de cada frase na estimativa (a mesma da narracao).
PAUSE_S = 0.25
#  Custo de uma cena fora da faixa: domina qualquer desvio do alvo dentro dela.
OUT_OF_RANGE_WEIGHT = 20.0
OUT_OF_RANGE_STEP = 5.0
#  Custo de trocar de imagem no meio de uma frase: so quando compensa. Na
#  pontuacao, onde a voz pausa; antes de uma conjuncao; entre duas palavras.
MID_SENTENCE_COST = 1.0
CLAUSE_CUT_COST = 1.5
WORD_CUT_COST = 2.5
#  Entre palavras, o corte deixa pelo menos isto de cada lado da frase.
WORD_CUT_MARGIN = 2
_DASHES = ("\u2014", "\u2013", "-")  # travessao, meia-risca, hifen
_STRIP = ".,;:!?\"'()[]\u201c\u201d\u2018\u2019\u00ab\u00bb"
#  Comeco de oracao: a voz ja muda de rumo antes delas.
_CLAUSE_WORDS = frozenset(
    {"e", "que", "mas", "quando", "porque", "enquanto", "onde", "como", "se", "pois", "embora"}
)
#  Palavras que pedem a seguinte: a troca de imagem logo depois delas parte a
#  ideia ao meio. Toda palavra de ate tres letras tambem (de, o, a, um, em...).
_NO_CUT_AFTER = frozenset(
    """
    para pela pelo pelas pelos sobre entre numa numas nuns cada seus suas esse essa esses
    essas este esta estes estas isso isto aquele aquela aqueles aquelas dessa desse desta
    deste nessa nesse nesta neste naquele naquela daquele daquela mais muito muita muitos
    muitas todo toda todos todas outro outra outros outras quando porque como onde desde
    durante cerca contra após até ante perante quase tanto tanta tantos tantas qual quais
    cujo cuja cujos cujas mesmo mesma mesmos mesmas nosso nossa nossos nossas dois duas
    três quatro cinco seis sete oito nove dez vinte trinta cem cento milhão milhões
    milhares centenas dezenas são era eram foi foram será serão seria seriam está estão
    estava estavam vai vão iam pode podem podia podiam deve devem devia tinha tinham
    havia têm
    """.split()  # noqa: SIM905 - uma lista longa de palavras le melhor assim
)


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


def _word_breaks(tokens: list[str]) -> dict[int, float]:
    """Onde a frase pode trocar de imagem e quanto custa cada lugar.

    A chave e a palavra antes da qual o corte cai. Pontuacao custa menos que
    conjuncao, que custa menos que o corte entre duas palavras quaisquer.
    """
    breaks = dict.fromkeys(_soft_breaks(tokens), MID_SENTENCE_COST)
    for k in range(WORD_CUT_MARGIN, len(tokens) - WORD_CUT_MARGIN + 1):
        if k in breaks:
            continue
        before = tokens[k - 1]
        word = before.strip(_STRIP).lower()
        if (
            not word
            or before[-1].isdigit()
            or (before[-1].isalpha() and len(word) <= 3)
            or word in _NO_CUT_AFTER
        ):
            continue
        clause = tokens[k].strip(_STRIP).lower() in _CLAUSE_WORDS
        breaks[k] = CLAUSE_CUT_COST if clause else WORD_CUT_COST
    return breaks


class _Cut(NamedTuple):
    """Ponto de corte: a palavra em que a cena comeca, o custo de cortar ali
    (zero no comeco de uma frase) e a frase dona da palavra."""

    word: int
    cost: float
    sentence: str


@dataclass(frozen=True)
class _Block:
    """Um bloco da narracao e seus pontos de corte."""

    first: int
    words: int
    en_seconds: float
    #  O ultimo ponto e o fim do bloco.
    cuts: list[_Cut]
    owner: list[str]

    def durations(self, starts: tuple[float, ...], a: int, b: int) -> tuple[float, float]:
        """Duracao da cena entre dois pontos de corte, em PT e no EN."""
        begin, end = self.cuts[a].word, self.cuts[b].word
        return starts[end] - starts[begin], self.en_seconds * (end - begin) / self.words


@dataclass(frozen=True)
class Pace:
    target_s: float
    min_s: float
    max_s: float

    def cost(self, seconds: float) -> float:
        total = (seconds - self.target_s) ** 2 / 2
        excess = max(self.min_s - seconds, seconds - self.max_s, 0.0)
        if excess:
            total += OUT_OF_RANGE_WEIGHT * excess**2 + OUT_OF_RANGE_STEP
        return total


@dataclass(frozen=True)
class PaceBands:
    """O ritmo do video e, nos primeiros `opening_s` segundos, o da abertura."""

    body: Pace
    opening: Pace | None = None
    opening_s: float = 0.0

    def at(self, seconds: float) -> Pace:
        """O ritmo de uma cena que comeca neste ponto da narracao PT."""
        if self.opening is not None and seconds < self.opening_s:
            return self.opening
        return self.body

    @classmethod
    def from_config(cls, cfg: ScenesConfig) -> PaceBands:
        body = Pace(cfg.seconds_target, cfg.seconds_min, cfg.seconds_max)
        if cfg.opening_s <= 0:
            return cls(body)
        opening = Pace(cfg.opening_target_s, cfg.opening_min_s, cfg.opening_max_s)
        return cls(body, opening, cfg.opening_s)


def _best_path(block: _Block, starts: tuple[float, ...], bands: PaceBands) -> list[int]:
    """Programacao dinamica: o jeito mais barato de cobrir o bloco ate cada corte.

    O ritmo de cada cena candidata e o do ponto em que ela comeca; o custo
    continua dependendo so do par de cortes, entao a solucao segue exata.
    """
    n = len(block.cuts)
    best = [0.0] + [float("inf")] * (n - 1)
    previous = [0] * n
    for b in range(1, n):
        for a in range(b):
            pace = bands.at(starts[block.cuts[a].word])
            pt, en = block.durations(starts, a, b)
            candidate = best[a] + pace.cost(pt) + pace.cost(en) + block.cuts[a].cost
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
    comma_above_s: float | None = 8.0,
    bands: PaceBands | None = None,
) -> list[SceneSlot]:
    """Cenas do roteiro inteiro.

    `bands` (o ritmo do `app.yaml`, com a abertura) substitui alvo, minimo e
    maximo. Sem `comma_above_s`, a frase pode ser cortada quando passa do
    maximo do ritmo do trecho em que comeca.
    """
    tokens = [t for u in units for t in u.text.split()]
    starts = timings.starts
    bands = bands or PaceBands(Pace(target_s, min_s, max_s))
    scenes: list[SceneSlot] = []
    cursor = 0
    for block_index in sorted({u.block for u in units}):
        block_units = [u for u in units if u.block == block_index]
        block_words = sum(u.words for u in block_units) or 1
        en_seconds = timings.en_blocks.get(block_index, 0.0)
        cuts: list[_Cut] = []
        owner: list[str] = []
        block_first = cursor
        for unit in block_units:
            first = cursor
            cuts.append(_Cut(first, 0.0, unit.id))
            owner += [unit.id] * unit.words
            cursor += unit.words
            pt_seconds = starts[cursor] - starts[first]
            en_estimate = en_seconds * unit.words / block_words
            limit = comma_above_s if comma_above_s is not None else bands.at(starts[first]).max_s
            if max(pt_seconds, en_estimate) > limit:
                breaks = _word_breaks(unit.text.split())
                cuts += [_Cut(first + k, breaks[k], unit.id) for k in sorted(breaks)]
        cuts.append(_Cut(cursor, 0.0, ""))
        block = _Block(block_first, block_words, en_seconds, cuts, owner)
        sentence_first = {c.sentence: c.word for c in cuts if c.cost == 0.0}

        for a, b in itertools.pairwise(_best_path(block, starts, bands)):
            begin, end = cuts[a].word, cuts[b].word
            pt_seconds, en_estimate = block.durations(starts, a, b)
            scenes.append(
                SceneSlot(
                    index=0,
                    block=block_index,
                    units=list(dict.fromkeys(owner[begin - block_first : end - block_first])),
                    seconds=pt_seconds,
                    seconds_en=en_estimate,
                    span=((begin - block_first) / block_words, (end - block_first) / block_words),
                    first_word=begin - sentence_first[cuts[a].sentence],
                    text=" ".join(tokens[begin:end]),
                )
            )

    for index, scene in enumerate(scenes, start=1):
        scene.index = index
    return scenes
