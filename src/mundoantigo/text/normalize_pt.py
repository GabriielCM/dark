"""Normalizacao do portugues para a fala (fase B5).

Muda so o que o Kokoro le, nunca a legenda: "a.C." vira "antes de Cristo",
"16.800" vira "dezesseis mil e oitocentos", "seculo I" vira "seculo
primeiro". Sem isso o G2P le a abreviacao letra a letra ou o numero como
"dezesseis ponto oitocentos".

Regras extras por canal ficam em `canais/pt-br.yaml`, bloco
`voz.normalizacoes` (lista de pares `de`/`para`, expressoes regulares).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_FIXED: tuple[tuple[str, str], ...] = (
    (r"\ba\.\s?C\.", "antes de Cristo"),
    (r"\bd\.\s?C\.", "depois de Cristo"),
    (r"\bs[ée]cs?\.", "século"),
    (r"\bn\.?\s?º", "número"),
    (r"\bkm/h\b", "quilômetros por hora"),
    (r"\bm/s\b", "metros por segundo"),
    (r"(?<=\d)\s?km\b", " quilômetros"),
    (r"(?<=\d)\s?kg\b", " quilos"),
    (r"(?<=\d)\s?%", " por cento"),
)

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "M": 1000}
_ORDINALS = (
    "primeiro", "segundo", "terceiro", "quarto", "quinto",
    "sexto", "sétimo", "oitavo", "nono", "décimo",
)  # fmt: skip
_CENTURY = re.compile(r"\b(século|séculos)\s+([IVXLC]+)\b")
#  Milhar com ponto (16.800) e decimal com virgula (2,5), como se escreve em PT.
_NUMBER = re.compile(r"\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\b|\b\d+(?:,\d+)?\b")
_ORDINAL_NUMBER = re.compile(r"\b(\d+)\s?([ºª])")


def roman_to_int(numeral: str) -> int:
    total = 0
    for current, following in zip(numeral, [*numeral[1:], ""], strict=True):
        value = _ROMAN[current]
        total += -value if following and _ROMAN[following] > value else value
    return total


def _say_number(raw: str) -> str:
    try:
        from num2words import num2words
    except ImportError:
        #  Sem num2words (maquina sem o extra de GPU), o espeak le os digitos.
        return raw
    integer, _, decimals = raw.replace(".", "").partition(",")
    spoken = str(num2words(int(integer), lang="pt_BR"))
    if decimals:
        spoken += " vírgula " + " ".join(str(num2words(int(d), lang="pt_BR")) for d in decimals)
    return spoken


def _say_ordinal(match: re.Match[str]) -> str:
    number, marker = int(match.group(1)), match.group(2)
    if 1 <= number <= 10:
        word = _ORDINALS[number - 1]
        return word[:-1] + "a" if marker == "ª" else word
    return match.group(0)


def _say_century(match: re.Match[str]) -> str:
    #  Seculo I a X se le como ordinal (seculo quinto); de XI em diante, cardinal
    #  (seculo quinze).
    value = roman_to_int(match.group(2))
    spoken = _ORDINALS[value - 1] if 1 <= value <= 10 else _say_number(str(value))
    return f"{match.group(1)} {spoken}"


def normalize_for_speech(text: str, extra_rules: Iterable[Mapping[str, str]] = ()) -> str:
    out = text
    for rule in extra_rules:
        out = re.sub(str(rule["de"]), str(rule["para"]), out)
    for pattern, replacement in _FIXED:
        out = re.sub(pattern, replacement, out)
    out = _CENTURY.sub(_say_century, out)
    out = _ORDINAL_NUMBER.sub(_say_ordinal, out)
    out = _NUMBER.sub(lambda m: _say_number(m.group(0)), out)
    return re.sub(r"\s{2,}", " ", out).strip()
