"""Trechos candidatos a corte (ADR 0010).

Um corte e um trecho de frases inteiras dentro de um bloco do roteiro: o bloco
e a unidade que se sustenta sozinha (um capitulo ou parte dele). A medida e
feita aqui, nos dois idiomas, antes de o LLM ver qualquer coisa: ele so escolhe
entre trechos que ja cabem na duracao.

- PT: o corte comeca no inicio do bloco ou de uma frase que abre uma cena (a
  imagem troca junto com a voz) e termina no fim de uma frase.
- EN: a adaptacao tem os mesmos blocos, mas nao as mesmas frases. O ponto
  equivalente fica na mesma fracao do bloco, como nas cenas
  (scenes/timeline.py), encaixado no inicio e no fim de frase EN mais proximos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#  Respiro antes da primeira palavra e depois da ultima: corte colado na voz
#  soa como edicao malfeita.
LEAD_S = 0.15
TAIL_S = 0.4
LANGS = ("pt-br", "en")


@dataclass(frozen=True, slots=True)
class ClipsConfig:
    """Bloco `cortes` do config/app.yaml."""

    count: int = 3
    #  So video com mais de 1 minuto entra no Programa de Recompensas do
    #  TikTok. O EN sai 10 a 20% mais longo que o PT.
    pt_range: tuple[float, float] = (65.0, 100.0)
    en_range: tuple[float, float] = (65.0, 115.0)
    #  Dois inicios candidatos no mesmo bloco ficam pelo menos isto separados.
    start_spacing_s: float = 15.0
    width: int = 1080
    height: int = 1920
    hook_s: float = 3.0
    end_s: float = 2.5
    hook_max_words: int = 8
    hashtags_min: int = 3
    hashtags_max: int = 5

    @classmethod
    def from_app(cls, app: dict[str, Any]) -> ClipsConfig:
        raw = app.get("cortes") or {}
        default = cls()

        def pair(key: str, fallback: tuple[float, float]) -> tuple[float, float]:
            value = raw.get(key)
            if not value:
                return fallback
            low, high = (float(v) for v in value)
            return (low, high)

        return cls(
            count=int(raw.get("quantidade", default.count)),
            pt_range=pair("duracao_pt_s", default.pt_range),
            en_range=pair("duracao_en_s", default.en_range),
            start_spacing_s=float(raw.get("espaco_entre_inicios_s", default.start_spacing_s)),
            width=int(raw.get("largura", default.width)),
            height=int(raw.get("altura", default.height)),
            hook_s=float(raw.get("gancho_s", default.hook_s)),
            end_s=float(raw.get("fim_s", default.end_s)),
            hook_max_words=int(raw.get("gancho_max_palavras", default.hook_max_words)),
            hashtags_min=int((raw.get("hashtags") or [default.hashtags_min])[0]),
            hashtags_max=int((raw.get("hashtags") or [0, default.hashtags_max])[-1]),
        )

    def range_for(self, lang: str) -> tuple[float, float]:
        return self.pt_range if lang.startswith("pt") else self.en_range


@dataclass(frozen=True, slots=True)
class Span:
    """Um trecho do audio de um idioma, de frase inteira a frase inteira."""

    start: float
    end: float
    first: str
    last: str

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inicio_s": self.start,
            "fim_s": self.end,
            "duracao_s": self.duration,
            "primeira_frase": self.first,
            "ultima_frase": self.last,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Span:
        return cls(
            start=float(raw["inicio_s"]),
            end=float(raw["fim_s"]),
            first=str(raw["primeira_frase"]),
            last=str(raw["ultima_frase"]),
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    block: int
    title: str
    spans: dict[str, Span] = field(default_factory=dict)

    def span(self, lang: str) -> Span:
        return self.spans[lang]

    def overlaps(self, other: Candidate) -> bool:
        a, b = self.span("pt-br"), other.span("pt-br")
        return a.start < b.end and b.start < a.end

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bloco": self.block,
            "titulo": self.title,
            **{lang: span.to_dict() for lang, span in self.spans.items()},
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Candidate:
        return cls(
            id=str(raw["id"]),
            block=int(raw["bloco"]),
            title=str(raw.get("titulo") or ""),
            spans={lang: Span.from_dict(raw[lang]) for lang in LANGS if lang in raw},
        )


@dataclass(frozen=True, slots=True)
class _Sentence:
    id: str
    block: int
    start: float
    end: float


def _sentences(timings: dict[str, Any]) -> list[_Sentence]:
    items = [
        _Sentence(
            id=str(f["id"]),
            block=int(f["bloco"]),
            start=float(f["inicio"]),
            end=float(f["fim"]),
        )
        for f in timings.get("frases", [])
    ]
    return sorted(items, key=lambda s: s.start)


def _padded(ordered: list[_Sentence], first: _Sentence, last: _Sentence, total: float) -> Span:
    """O trecho com respiro, sem invadir a frase vizinha.

    O respiro para no meio da pausa entre as frases: dois cortes vizinhos
    (o fim de um bloco e o comeco do seguinte) nunca dividem um instante.
    """
    i = ordered.index(first)
    j = ordered.index(last)
    floor = (ordered[i - 1].end + first.start) / 2 if i > 0 else 0.0
    ceiling = (
        (last.end + ordered[j + 1].start) / 2 if j + 1 < len(ordered) else max(total, last.end)
    )
    start = max(floor, first.start - LEAD_S, 0.0)
    end = min(ceiling, last.end + TAIL_S)
    return Span(start=round(start, 3), end=round(end, 3), first=first.id, last=last.id)


def _fits(duration: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= duration <= bounds[1]


def _ends(sentences: list[_Sentence], i: int, bounds: tuple[float, float]) -> list[int]:
    """Onde o trecho que comeca na frase `i` pode terminar.

    A frase mais distante que ainda cabe (o fim do bloco, quando cabe: o
    capitulo fecha a ideia) e a mais perto do meio da faixa, um corte mais
    enxuto. Mais opcoes so diluiriam a lista do LLM.
    """
    start = sentences[i].start
    fitting = [j for j in range(i, len(sentences)) if _fits(sentences[j].end - start, bounds)]
    if not fitting:
        return []
    middle = (bounds[0] + bounds[1]) / 2
    tight = min(fitting, key=lambda j: abs(sentences[j].end - start - middle))
    return sorted({fitting[-1], tight})


def _mapped_en(
    pt_block: tuple[float, float],
    en_block: tuple[float, float],
    pt_first: _Sentence,
    pt_last: _Sentence,
    en_sentences: list[_Sentence],
) -> tuple[_Sentence, _Sentence] | None:
    """As frases EN na mesma fracao do bloco que o trecho PT."""
    pt_length = max(pt_block[1] - pt_block[0], 1e-6)
    en_length = en_block[1] - en_block[0]
    at_start = en_block[0] + (pt_first.start - pt_block[0]) / pt_length * en_length
    at_end = en_block[0] + (pt_last.end - pt_block[0]) / pt_length * en_length
    first = min(en_sentences, key=lambda s: abs(s.start - at_start))
    after = [s for s in en_sentences if s.end > first.start]
    if not after:
        return None
    last = min(after, key=lambda s: abs(s.end - at_end))
    return first, last


def _block_bounds(timings: dict[str, Any]) -> dict[int, tuple[float, float, str]]:
    return {
        int(b["indice"]): (float(b["inicio_s"]), float(b["fim_s"]), str(b.get("titulo") or ""))
        for b in timings.get("blocos", [])
    }


def scene_openers(storyboard: dict[str, Any]) -> set[str]:
    """Frases em que uma cena comeca junto com a frase (nao no meio dela)."""
    return {
        str(scene["frases"][0])
        for scene in storyboard.get("cenas", [])
        if scene.get("frases") and not int(scene.get("inicio_palavra") or 0)
    }


def candidates(
    storyboard: dict[str, Any],
    timings: dict[str, dict[str, Any]],
    config: ClipsConfig,
) -> list[Candidate]:
    """Todos os trechos que cabem na duracao do corte, nos dois idiomas."""
    pt, en = timings["pt-br"], timings["en"]
    pt_blocks, en_blocks = _block_bounds(pt), _block_bounds(en)
    pt_all, en_all = _sentences(pt), _sentences(en)
    pt_total = float(pt.get("duracao_s") or (pt_all[-1].end if pt_all else 0.0))
    en_total = float(en.get("duracao_s") or (en_all[-1].end if en_all else 0.0))
    openers = scene_openers(storyboard)

    found: list[Candidate] = []
    for index in sorted(pt_blocks):
        if index not in en_blocks:
            continue
        sentences = [s for s in pt_all if s.block == index]
        en_sentences = [s for s in en_all if s.block == index]
        if not sentences or not en_sentences:
            continue

        starts: list[int] = []
        for i, sentence in enumerate(sentences):
            if i > 0 and sentence.id not in openers:
                continue
            if starts and sentence.start - sentences[starts[-1]].start < config.start_spacing_s:
                continue
            starts.append(i)

        for i in starts:
            for j in _ends(sentences, i, config.pt_range):
                pt_span = _padded(pt_all, sentences[i], sentences[j], pt_total)
                mapped = _mapped_en(
                    pt_blocks[index][:2],
                    en_blocks[index][:2],
                    sentences[i],
                    sentences[j],
                    en_sentences,
                )
                if mapped is None:
                    continue
                en_span = _padded(en_all, mapped[0], mapped[1], en_total)
                if not (
                    _fits(pt_span.duration, config.pt_range)
                    and _fits(en_span.duration, config.en_range)
                ):
                    continue
                found.append(
                    Candidate(
                        id="",
                        block=index,
                        title=pt_blocks[index][2],
                        spans={"pt-br": pt_span, "en": en_span},
                    )
                )

    return [
        Candidate(id=f"c{n:02d}", block=c.block, title=c.title, spans=c.spans)
        for n, c in enumerate(found, start=1)
    ]
