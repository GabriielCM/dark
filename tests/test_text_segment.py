"""Segmentacao do roteiro em frases (fases B3 e B5)."""

from __future__ import annotations

from mundoantigo.text.segment import (
    segment_script,
    split_long,
    split_sentences,
    units_from_json,
    units_to_json,
)


def test_abbreviations_and_numbers_do_not_end_a_sentence() -> None:
    text = (
        "Em 79 d.C. o Vesúvio entrou em erupção. Quase 16.800 homens marchavam "
        "a 2,5 km por hora, no séc. I. Era muito? Não para eles!"
    )
    assert split_sentences(text) == [
        "Em 79 d.C. o Vesúvio entrou em erupção.",
        "Quase 16.800 homens marchavam a 2,5 km por hora, no séc. I.",
        "Era muito?",
        "Não para eles!",
    ]


def test_english_abbreviations() -> None:
    text = "In 79 A.D. the volcano erupted. Dr. Jackson studied it, e.g. in Utah."
    assert split_sentences(text, "en-US") == [
        "In 79 A.D. the volcano erupted.",
        "Dr. Jackson studied it, e.g. in Utah.",
    ]


def test_quotes_after_the_period_stay_with_the_sentence() -> None:
    assert split_sentences('Ele disse: "Marchem." Depois calou.') == [
        'Ele disse: "Marchem."',
        "Depois calou.",
    ]


def test_long_sentences_are_cut_at_a_natural_pause() -> None:
    sentence = (
        "O acampamento era desmontado antes do amanhecer, as tendas eram enroladas "
        "e presas nas mulas, e a coluna seguia pela estrada em silencio absoluto"
    )
    pieces = split_long(sentence, max_words=12)
    assert len(pieces) >= 2
    assert all(len(p.split()) <= 12 for p in pieces)
    assert " ".join(pieces) == sentence


def test_segment_script_numbers_units_and_keeps_blocks() -> None:
    script = {
        "blocos": [
            {"narracao": "Primeira frase. Segunda frase."},
            {"narracao": "Terceira frase, do segundo bloco."},
        ]
    }
    units = segment_script(script, prefix="p", language="pt-BR", words_per_minute=150)
    assert [u.id for u in units] == ["p0001", "p0002", "p0003"]
    assert [u.block for u in units] == [0, 0, 1]
    assert units_from_json(units_to_json(units)) == units
