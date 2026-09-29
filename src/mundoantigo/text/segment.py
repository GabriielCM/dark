"""Divide o roteiro em frases com ID (fases B3 e B5).

A frase e a unidade de tempo do video: a narracao e sintetizada frase a frase
(o tempo de cada uma sai exato da propria sintese), as cenas sao grupos de
frases e a legenda e montada sobre elas. IDs estaveis (`p0001` em PT,
`e0001` em EN) ligam roteiro, audio, storyboard e legenda.

Frase longa demais vira duas, cortada numa pausa natural (virgula, ponto e
virgula, travessao): uma imagem nao deve ficar mais de ~12 s na tela.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#  Abreviacoes que terminam em ponto sem terminar a frase.
ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "pt": ("a.C.", "d.C.", "séc.", "sécs.", "Sr.", "Sra.", "Dr.", "Dra.", "p. ex.", "etc.",
           "aprox.", "cf.", "n.º", "vol.", "cap.", "S.", "Sto.", "Sta."),
    "en": ("B.C.", "A.D.", "B.C.E.", "C.E.", "Mr.", "Mrs.", "Ms.", "Dr.", "St.", "e.g.",
           "i.e.", "etc.", "vs.", "approx.", "c.", "vol.", "ch."),
}  # fmt: skip

_PLACEHOLDER = "\u2024"  # "one dot leader": parece ponto, nao e ponto
#  Ponto entre digitos (16.800, 2.5) nunca termina frase.
_NUMBER_DOT = re.compile(r"(?<=\d)\.(?=\d)")
_END = ".!?\u2026"  # . ! ? e reticencias
_CLOSE = "\"\u201d\u00bb')\\]"  # aspas e parenteses que fecham depois do ponto
_DASHES = "\u2014\u2013"  # travessao e meia-risca
#  Fim de frase: pontuacao final (talvez seguida de aspas que fecham), espaco
#  e o comeco da proxima. So o espaco e consumido, as aspas ficam na frase.
_BOUNDARY = re.compile(
    rf"(?:(?<=[{_END}])|(?<=[{_END}][{_CLOSE}]))\s+"
    rf"(?=[\"\u201c\u00ab'(\[]?[A-Z\u00c0-\u00d6\u00d8-\u00dd0-9\u00bf\u00a1{_DASHES}-])"
)
_SOFT_BREAK = re.compile(rf"(?<=[,;:])\s+|\s+(?=[{_DASHES}]\s)")


@dataclass(frozen=True, slots=True)
class Unit:
    id: str
    block: int
    text: str

    @property
    def words(self) -> int:
        return len(self.text.split())


def _language_key(language: str) -> str:
    return "pt" if language.lower().startswith("pt") else "en"


def split_sentences(text: str, language: str = "pt-BR") -> list[str]:
    """Frases de um trecho de narracao, sem quebrar em abreviacao ou numero."""
    protected = " ".join(text.split())
    for abbreviation in ABBREVIATIONS[_language_key(language)]:
        protected = protected.replace(abbreviation, abbreviation.replace(".", _PLACEHOLDER))
    protected = _NUMBER_DOT.sub(_PLACEHOLDER, protected)
    sentences = [s.strip() for s in _BOUNDARY.split(protected) if s.strip()]
    return [s.replace(_PLACEHOLDER, ".") for s in sentences]


def split_long(sentence: str, max_words: int) -> list[str]:
    """Corta uma frase longa demais numa pausa natural perto do meio."""
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]
    cuts = [m.end() for m in _SOFT_BREAK.finditer(sentence)]
    if not cuts:
        #  Sem pausa natural: corta no espaco mais perto do meio.
        half = len(words) // 2
        return split_long(" ".join(words[:half]), max_words) + split_long(
            " ".join(words[half:]), max_words
        )
    middle = len(sentence) / 2
    cut = min(cuts, key=lambda position: abs(position - middle))
    head, tail = sentence[:cut].strip(), sentence[cut:].strip()
    if not head or not tail:
        return [sentence]
    return split_long(head, max_words) + split_long(tail, max_words)


def segment_script(
    script: dict[str, Any],
    *,
    prefix: str,
    language: str,
    words_per_minute: int,
    max_seconds: float = 12.0,
) -> list[Unit]:
    """Todas as frases do roteiro, em ordem, com ID e bloco de origem."""
    max_words = max(6, int(max_seconds * words_per_minute / 60))
    units: list[Unit] = []
    for block_index, block in enumerate(script.get("blocos", [])):
        narration = str(block.get("narracao", "")).strip()
        for sentence in split_sentences(narration, language):
            for piece in split_long(sentence, max_words):
                units.append(Unit(f"{prefix}{len(units) + 1:04d}", block_index, piece))
    return units


def units_to_json(units: list[Unit]) -> list[dict[str, Any]]:
    return [{"id": u.id, "bloco": u.block, "texto": u.text} for u in units]


def units_from_json(raw: list[dict[str, Any]]) -> list[Unit]:
    return [Unit(str(r["id"]), int(r["bloco"]), str(r["texto"])) for r in raw]
