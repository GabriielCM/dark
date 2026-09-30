"""Linha do tempo das cenas: cada cena comeca na sua frase (fase B5)."""

from __future__ import annotations

import itertools

import pytest

from mundoantigo.scenes.timeline import scene_times

TEMPOS_PT = {
    "duracao_s": 20.0,
    "frases": [
        {"id": "p0001", "bloco": 0, "inicio": 0.4, "fim": 3.0},
        {"id": "p0002", "bloco": 0, "inicio": 3.3, "fim": 6.1},
        {"id": "p0003", "bloco": 1, "inicio": 7.0, "fim": 12.5},
        {"id": "p0004", "bloco": 1, "inicio": 12.8, "fim": 19.2},
    ],
    "blocos": [
        {"indice": 0, "inicio_s": 0.4, "fim_s": 6.1},
        {"indice": 1, "inicio_s": 7.0, "fim_s": 19.2},
    ],
}
CENAS = [
    {"indice": 1, "bloco": 0, "frases": ["p0001", "p0002"], "fracao_bloco": [0.0, 1.0]},
    {"indice": 2, "bloco": 1, "frases": ["p0003"], "fracao_bloco": [0.0, 0.5]},
    {"indice": 3, "bloco": 1, "frases": ["p0004"], "fracao_bloco": [0.5, 1.0]},
]


def test_portuguese_scenes_start_on_their_sentence() -> None:
    assert scene_times(CENAS, TEMPOS_PT) == [(0.0, 7.0), (7.0, 12.8), (12.8, 20.0)]


def test_english_scenes_use_the_block_fraction() -> None:
    tempos_en = {
        "duracao_s": 18.0,
        "frases": [{"id": "e0001", "bloco": 0, "inicio": 0.2, "fim": 5.0}],
        "blocos": [
            {"indice": 0, "inicio_s": 0.2, "fim_s": 5.0},
            {"indice": 1, "inicio_s": 6.0, "fim_s": 17.0},
        ],
    }
    times = scene_times(CENAS, tempos_en)
    assert times[1][0] == pytest.approx(6.0)
    assert times[2][0] == pytest.approx(6.0 + 0.5 * 11.0)
    assert times[-1][1] == 18.0


def test_a_scene_cut_inside_a_sentence_starts_on_its_word() -> None:
    tempos = {
        "duracao_s": 9.0,
        "palavras": [{"p": f"w{i}", "i": 0.5 * i, "f": 0.5 * i + 0.4} for i in range(16)],
        "frases": [{"id": "p0001", "bloco": 0, "inicio": 0.0, "fim": 8.0, "palavras": [0, 16]}],
        "blocos": [{"indice": 0, "inicio_s": 0.0, "fim_s": 8.0}],
    }
    cenas = [
        {"indice": 1, "bloco": 0, "frases": ["p0001"], "inicio_palavra": 0},
        {"indice": 2, "bloco": 0, "frases": ["p0001"], "inicio_palavra": 9},
    ]
    assert scene_times(cenas, tempos) == [(0.0, 4.5), (4.5, 9.0)]


def test_english_cuts_snap_to_a_sentence_or_a_word() -> None:
    tempos_en = {
        "duracao_s": 12.0,
        "palavras": [{"p": f"w{i}", "i": 0.6 * i, "f": 0.6 * i + 0.5} for i in range(20)],
        "frases": [
            {"id": "e0001", "bloco": 0, "inicio": 0.0, "fim": 5.5},
            {"id": "e0002", "bloco": 0, "inicio": 6.0, "fim": 11.9},
        ],
        "blocos": [{"indice": 0, "inicio_s": 0.0, "fim_s": 11.9}],
    }
    cenas = [
        {"indice": 1, "bloco": 0, "frases": ["p0001"], "fracao_bloco": [0.0, 0.45]},
        #  0,45 * 11,9 = 5,36 s: a frase e0002 comeca a 0,64 s dali.
        {"indice": 2, "bloco": 0, "frases": ["p0002"], "fracao_bloco": [0.45, 0.8]},
        #  0,8 * 11,9 = 9,52 s: sem frase por perto, vai para a palavra mais proxima.
        {"indice": 3, "bloco": 0, "frases": ["p0003"], "fracao_bloco": [0.8, 1.0]},
    ]
    starts = [start for start, _ in scene_times(cenas, tempos_en)]
    assert starts[1] == pytest.approx(6.0)
    assert starts[2] == pytest.approx(9.6)


def test_scenes_cover_the_whole_audio_without_gaps() -> None:
    times = scene_times(CENAS, TEMPOS_PT)
    assert times[0][0] == 0.0
    assert times[-1][1] == TEMPOS_PT["duracao_s"]
    assert all(a[1] == b[0] for a, b in itertools.pairwise(times))
