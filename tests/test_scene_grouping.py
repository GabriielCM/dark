"""Corte da narracao em cenas pela duracao real (fase B3, ADRs 0008 e 0012)."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from mundoantigo.scenes.grouping import (
    CLAUSE_CUT_COST,
    MID_SENTENCE_COST,
    WORD_CUT_COST,
    Pace,
    PaceBands,
    SpeechTimings,
    _word_breaks,
    group_scenes,
)
from mundoantigo.text.segment import Unit

PAUSE = 0.25


def _tempos(sentences: list[tuple[int, str, float]]) -> tuple[list[Unit], dict[str, Any]]:
    """Unidades e um tempos.json sintetico: palavras de mesma duracao por frase."""
    units: list[Unit] = []
    words: list[dict[str, Any]] = []
    frases: list[dict[str, Any]] = []
    clock = 0.0
    for i, (block, text, seconds) in enumerate(sentences, start=1):
        unit = Unit(f"p{i:04d}", block, text)
        units.append(unit)
        first = len(words)
        per_word = seconds / unit.words
        for k, token in enumerate(text.split()):
            words.append({"p": token, "i": clock + k * per_word, "f": clock + (k + 1) * per_word})
        frases.append(
            {
                "id": unit.id,
                "bloco": block,
                "inicio": clock,
                "fim": clock + seconds,
                "palavras": [first, len(words)],
            }
        )
        clock += seconds + PAUSE
    return units, {"duracao_s": clock, "palavras": words, "frases": frases}


def _sentence(words: int, seconds: float, block: int = 0) -> tuple[int, str, float]:
    return (block, " ".join(["palavra"] * words), seconds)


def _group(units: list[Unit], tempos: dict[str, Any], en: dict[str, Any] | None = None):
    timings = SpeechTimings.from_tempos(units, tempos, en)
    assert timings is not None
    return group_scenes(units, timings)


def test_scenes_aim_at_six_seconds() -> None:
    units, tempos = _tempos([_sentence(8, 2.8, block=i // 12) for i in range(24)])
    scenes = _group(units, tempos)
    assert all(4.0 <= s.seconds <= 8.0 for s in scenes)
    average = sum(s.seconds for s in scenes) / len(scenes)
    assert 5.0 <= average <= 7.0
    assert [s.index for s in scenes] == list(range(1, len(scenes) + 1))


def test_a_scene_never_crosses_a_block() -> None:
    units, tempos = _tempos([_sentence(6, 2.0, block=b) for b in (0, 0, 1, 1)])
    for scene in _group(units, tempos):
        blocks = {u.block for u in units if u.id in scene.units}
        assert blocks == {scene.block}


def test_a_short_sentence_does_not_drag_the_next_one_into_a_long_scene() -> None:
    """A amostra de 29/09: 4,0 s + 7,1 s viraram um cartao de 12 s no fim."""
    units, tempos = _tempos(
        [
            _sentence(12, 4.8),
            _sentence(10, 3.4),
            _sentence(12, 4.0),
            _sentence(20, 7.1),
        ]
    )
    scenes = _group(units, tempos)
    assert max(s.seconds for s in scenes) <= 8.0
    assert scenes[-1].units == ["p0004"]


def test_a_long_sentence_is_cut_at_a_comma() -> None:
    text = (
        "um dois tres quatro cinco seis sete oito nove dez, "
        "onze doze treze quatorze quinze dezesseis dezessete dezoito vinte"
    )
    units, tempos = _tempos([(0, text, 11.0)])
    scenes = _group(units, tempos)
    assert len(scenes) == 2
    assert scenes[1].units == ["p0001"]
    assert scenes[1].first_word == 10
    assert scenes[0].text.endswith("dez,")
    assert scenes[1].text.startswith("onze")


def test_a_sentence_under_the_limit_keeps_its_comma() -> None:
    text = "um dois tres quatro, cinco seis sete oito nove dez onze doze"
    units, tempos = _tempos([(0, text, 6.5), _sentence(10, 5.5)])
    scenes = _group(units, tempos)
    assert all(s.first_word == 0 for s in scenes)


def test_a_longer_english_narration_makes_shorter_scenes() -> None:
    """O alvo vale para a media dos dois idiomas."""
    units, tempos = _tempos([_sentence(6, 2.0) for _ in range(12)])
    same = _group(units, tempos)
    longer_en = {"blocos": [{"indice": 0, "inicio_s": 0.0, "fim_s": tempos["duracao_s"] * 1.5}]}
    faster = _group(units, tempos, longer_en)
    assert len(faster) > len(same)
    assert all(s.seconds_en > s.seconds for s in faster)


def test_block_fractions_cover_the_block_in_order() -> None:
    units, tempos = _tempos([_sentence(6, 2.2) for _ in range(10)])
    scenes = _group(units, tempos)
    assert scenes[0].span[0] == 0.0
    assert scenes[-1].span[1] == pytest.approx(1.0)
    for before, after in itertools.pairwise(scenes):
        assert before.span[1] == pytest.approx(after.span[0])


def test_timings_that_do_not_match_the_script_are_ignored() -> None:
    units, tempos = _tempos([_sentence(6, 2.2)])
    tempos["palavras"] = tempos["palavras"][:-1]
    assert SpeechTimings.from_tempos(units, tempos) is None


def test_without_narration_the_channel_rate_is_the_estimate() -> None:
    units = [Unit(f"p{i:04d}", 0, " ".join(["palavra"] * 8)) for i in range(20)]
    timings = SpeechTimings.estimated(units, words_per_minute=150)
    assert not timings.measured
    scenes = group_scenes(units, timings)
    assert all(4.0 <= s.seconds <= 8.0 for s in scenes)


# Ritmo de ~3 s e abertura de ~2,5 s (ADR 0012) -----------------------------

BODY = Pace(3.0, 2.0, 4.5)
BANDS = PaceBands(BODY, opening=Pace(2.5, 1.8, 3.5), opening_s=60.0)
NO_CUT_AFTER = {"de", "o", "a", "pela", "foi", "até"}


def _fast(units: list[Unit], tempos: dict[str, Any], bands: PaceBands = BANDS):
    timings = SpeechTimings.from_tempos(units, tempos)
    assert timings is not None
    return group_scenes(units, timings, comma_above_s=None, bands=bands)


def _clock(scenes) -> list[float]:
    """Onde cada cena comeca: a duracao de cada uma ja inclui a pausa."""
    return list(itertools.accumulate([0.0] + [s.seconds for s in scenes[:-1]]))


def test_the_new_pace_aims_at_three_seconds() -> None:
    units, tempos = _tempos([_sentence(8, 2.8, block=i // 12) for i in range(24)])
    scenes = _fast(units, tempos, PaceBands(BODY))
    assert all(2.0 <= s.seconds <= 4.5 for s in scenes)
    assert 2.5 <= sum(s.seconds for s in scenes) / len(scenes) <= 3.5


def test_the_opening_minute_is_faster_and_the_clock_decides_not_the_block() -> None:
    """Um bloco so, de ~110 s: a primeira parte no ritmo da abertura, o resto no do video."""
    units, tempos = _tempos([_sentence(12, 5.6) for _ in range(19)])
    scenes = _fast(units, tempos)
    assert {s.block for s in scenes} == {0}
    opening = [s for s, t in zip(scenes, _clock(scenes), strict=True) if t < 60]
    body = [s for s, t in zip(scenes, _clock(scenes), strict=True) if t >= 60]
    assert opening and body
    assert all(1.8 <= s.seconds <= 3.5 for s in opening)
    assert all(2.0 <= s.seconds <= 4.5 for s in body)
    mean = lambda group: sum(s.seconds for s in group) / len(group)  # noqa: E731
    assert mean(opening) < mean(body)


def test_a_long_sentence_without_commas_is_cut_between_words() -> None:
    text = (
        "Os trabalhadores egípcios arrastavam blocos enormes de calcário pela rampa "
        "molhada enquanto cantavam juntos até o alto da pirâmide"
    )
    units, tempos = _tempos([(0, text, 7.0), _sentence(8, 3.0)])
    scenes = _fast(units, tempos, PaceBands(BODY))
    first = [s for s in scenes if "p0001" in s.units]
    assert len(first) >= 2
    assert all(s.seconds <= 4.5 for s in scenes)
    for before, after in itertools.pairwise(first):
        assert after.first_word > 0
        assert before.text.split()[-1].lower() not in NO_CUT_AFTER
        #  Nunca colado nas pontas da frase.
        assert len(before.text.split()) >= 2 and len(after.text.split()) >= 2


def test_a_number_stays_with_the_word_after_it() -> None:
    text = "Durante décadas trabalharam 2.500 homens em turnos longos sob um sol forte no deserto"
    units, tempos = _tempos([(0, text, 7.0)])
    scenes = _fast(units, tempos, PaceBands(BODY))
    assert len(scenes) >= 2
    assert all(not s.text.split()[-1][-1].isdigit() for s in scenes[:-1])


def test_punctuation_beats_a_conjunction_which_beats_any_word() -> None:
    tokens = ["aaaa", "bbbb,", "cccc", "dddd", "e", "ffff", "gggg", "hhhh"]
    breaks = _word_breaks(tokens)
    assert breaks[2] == MID_SENTENCE_COST  # depois de "bbbb,"
    assert breaks[3] == WORD_CUT_COST  # entre "cccc" e "dddd"
    assert breaks[4] == CLAUSE_CUT_COST  # antes de "e"
    assert 5 not in breaks  # depois de "e"
    assert 1 not in breaks and 7 not in breaks  # colado nas pontas
    assert MID_SENTENCE_COST < CLAUSE_CUT_COST < WORD_CUT_COST


def test_a_sentence_that_fits_in_a_scene_stays_whole() -> None:
    units, tempos = _tempos([_sentence(10, 4.0) for _ in range(6)])
    assert all(s.first_word == 0 for s in _fast(units, tempos, PaceBands(BODY)))


def test_the_bands_come_from_the_config(settings) -> None:
    bands = PaceBands.from_config(settings.scenes)
    assert bands.at(10.0).target_s == 2.5
    assert bands.at(60.0).target_s == 3.0
