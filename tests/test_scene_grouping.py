"""Agrupamento das frases em cenas (fase B3)."""

from __future__ import annotations

import itertools

import pytest

from mundoantigo.scenes.grouping import group_scenes
from mundoantigo.text.segment import Unit

WPM = 150  # 2,5 palavras por segundo


def _unit(i: int, block: int, words: int) -> Unit:
    return Unit(f"p{i:04d}", block, " ".join(["palavra"] * words))


def test_scenes_stay_between_five_and_seven_seconds() -> None:
    #  Frases de 6 palavras (~2,4 s + pausa) em dois blocos.
    units = [_unit(i, i // 12, 6) for i in range(24)]
    scenes = group_scenes(units, words_per_minute=WPM)
    assert all(4.9 <= s.seconds <= 7.5 for s in scenes[:-1])
    assert [s.index for s in scenes] == list(range(1, len(scenes) + 1))


def test_a_scene_never_crosses_a_block() -> None:
    units = [_unit(1, 0, 6), _unit(2, 0, 6), _unit(3, 1, 6), _unit(4, 1, 6)]
    for scene in group_scenes(units, words_per_minute=WPM):
        blocks = {u.block for u in units if u.id in scene.units}
        assert blocks == {scene.block}


def test_a_short_tail_joins_the_previous_scene() -> None:
    units = [_unit(1, 0, 14), _unit(2, 0, 3)]  # 5,6 s + 1,2 s
    scenes = group_scenes(units, words_per_minute=WPM)
    assert len(scenes) == 1
    assert scenes[0].units == ["p0001", "p0002"]


def test_a_long_sentence_is_a_scene_on_its_own() -> None:
    units = [_unit(1, 0, 25), _unit(2, 0, 12)]  # 10,25 s e 5,05 s
    scenes = group_scenes(units, words_per_minute=WPM)
    assert [s.units for s in scenes] == [["p0001"], ["p0002"]]


def test_block_fractions_cover_the_block_in_order() -> None:
    units = [_unit(i, 0, 6) for i in range(10)]
    scenes = group_scenes(units, words_per_minute=WPM)
    assert scenes[0].span[0] == 0.0
    assert scenes[-1].span[1] == pytest.approx(1.0)
    for before, after in itertools.pairwise(scenes):
        assert before.span[1] == pytest.approx(after.span[0])
