"""Linha do tempo unica das duas narracoes (ADR 0011)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from mundoantigo.text.shared_timeline import (
    Sentence,
    block_spans,
    place,
    relay_wav,
    shared_timeline,
    stretch,
)

#  PT mais curto no bloco 0, EN mais curto no bloco 1.
PT = [
    Sentence("p1", 0, 0.0, 2.0),
    Sentence("p2", 0, 2.25, 4.0),
    Sentence("p3", 1, 4.8, 9.0),
]
EN = [
    Sentence("e1", 0, 0.0, 2.5),
    Sentence("e2", 0, 2.75, 5.2),
    Sentence("e3", 1, 6.0, 9.6),
]
PT_TOTAL, EN_TOTAL = 9.8, 10.4


def test_block_spans_cover_the_audio_with_the_closing_pause() -> None:
    assert block_spans(PT, PT_TOTAL) == {0: (0.0, 4.8), 1: (4.8, 9.8)}
    assert block_spans(EN, EN_TOTAL) == {0: (0.0, 6.0), 1: (6.0, 10.4)}


def test_each_block_takes_the_longer_language() -> None:
    line = shared_timeline(block_spans(PT, PT_TOTAL), block_spans(EN, EN_TOTAL))
    assert line.lengths == {0: 6.0, 1: 5.0}
    assert line.starts == {0: 0.0, 1: 6.0}
    assert line.total == pytest.approx(11.0)


def test_shorter_language_keeps_speed_and_fraction_and_only_pauses_grow() -> None:
    pt_spans = block_spans(PT, PT_TOTAL)
    line = shared_timeline(pt_spans, block_spans(EN, EN_TOTAL))
    placed = place(PT, pt_spans, line)

    #  Bloco 0: o PT tinha 4,8 s e passa a 6,0 s, fator 1,25.
    assert placed["p1"] == (0.0, 2.0)
    assert placed["p2"] == pytest.approx((2.8125, 4.5625), abs=1e-3)
    #  Bloco 1: o PT ja era o mais longo e so muda de lugar.
    assert placed["p3"] == pytest.approx((6.0, 10.2), abs=1e-3)
    for s in PT:
        start, end = placed[s.id]
        assert end - start == pytest.approx(s.end - s.start, abs=1e-3)


def test_longer_language_only_shifts_with_the_blocks_before_it() -> None:
    en_spans = block_spans(EN, EN_TOTAL)
    line = shared_timeline(block_spans(PT, PT_TOTAL), en_spans)
    placed = place(EN, en_spans, line)
    assert placed["e1"] == pytest.approx((0.0, 2.5), abs=1e-3)
    assert placed["e2"] == pytest.approx((2.75, 5.2), abs=1e-3)
    #  Bloco 1: EN tinha 4,4 s e passa a 5,0 s; a primeira frase fica no inicio.
    assert placed["e3"] == pytest.approx((6.0, 9.6), abs=1e-3)


def test_stretch_reports_how_much_each_block_grew() -> None:
    pt_spans, en_spans = block_spans(PT, PT_TOTAL), block_spans(EN, EN_TOTAL)
    line = shared_timeline(pt_spans, en_spans)
    assert stretch(pt_spans, line) == {0: 0.25, 1: 0.0}
    assert stretch(en_spans, line) == {0: 0.0, 1: pytest.approx(0.1364, abs=1e-4)}


def test_languages_must_have_the_same_blocks() -> None:
    with pytest.raises(ValueError, match="blocos diferentes"):
        shared_timeline({0: (0.0, 1.0), 1: (1.0, 2.0)}, {0: (0.0, 1.0)})


def _write_wav(path: Path, samples: list[int], rate: int = 100) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(s.to_bytes(2, "little", signed=True) for s in samples))


def _read_wav(path: Path) -> list[int]:
    with wave.open(str(path), "rb") as w:
        data = w.readframes(w.getnframes())
    return [int.from_bytes(data[i : i + 2], "little", signed=True) for i in range(0, len(data), 2)]


def test_relay_moves_each_sentence_and_pads_with_silence(tmp_path: Path) -> None:
    #  1 s de audio a 100 Hz: frase A de 0,0 a 0,3 s, frase B de 0,5 a 0,8 s.
    source = tmp_path / "natural.wav"
    _write_wav(source, [100] * 30 + [0] * 20 + [200] * 30 + [0] * 20)
    output = tmp_path / "linha.wav"

    relay_wav(source, output, [(0.0, 0.3, 0.0), (0.5, 0.8, 0.9)], total=1.4)

    samples = _read_wav(output)
    assert len(samples) == 140
    assert samples[:30] == [100] * 30
    assert samples[30:90] == [0] * 60
    assert samples[90:120] == [200] * 30
    assert samples[120:] == [0] * 20
