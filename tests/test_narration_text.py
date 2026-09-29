"""Texto da narracao (fase B5): fala normalizada, legenda fiel ao roteiro."""

from __future__ import annotations

import pytest

from mundoantigo.errors import ProviderMisconfigured
from mundoantigo.providers.align import WordTiming
from mundoantigo.providers.tts.kokoro import lang_code_for
from mundoantigo.text.align_script import align_units, unit_spans
from mundoantigo.text.normalize_pt import normalize_for_speech, roman_to_int
from mundoantigo.text.segment import Unit


class TestNormalize:
    def test_abbreviations_are_spoken_in_full(self) -> None:
        spoken = normalize_for_speech("Morreu em 44 a.C., no séc. I")
        assert "antes de Cristo" in spoken
        assert "século primeiro" in spoken

    def test_roman_numerals(self) -> None:
        assert [roman_to_int(n) for n in ("I", "IV", "IX", "XIV", "XXI")] == [1, 4, 9, 14, 21]

    def test_extra_rules_from_the_channel_come_first(self) -> None:
        rules = [{"de": r"\bPolíbio\b", "para": "Políbio, o historiador"}]
        assert "o historiador" in normalize_for_speech("Segundo Políbio", rules)

    def test_numbers_become_words(self) -> None:
        pytest.importorskip("num2words")
        assert normalize_for_speech("16.800 homens") == "dezesseis mil e oitocentos homens"
        assert normalize_for_speech("2,5 km") == "dois vírgula cinco quilômetros"
        assert normalize_for_speech("o 1º dia") == "o primeiro dia"
        assert normalize_for_speech("no século XV") == "no século quinze"


def _words(*items: tuple[str, float, float]) -> list[WordTiming]:
    return [WordTiming(w, s, e) for w, s, e in items]


class TestAlignScript:
    def test_subtitle_keeps_the_script_text(self) -> None:
        unit = Unit("p0001", 0, "Quase 16.800 homens seguiam Políbio.")
        heard = _words(
            ("Quase", 0.0, 0.3),
            ("dezesseis", 0.3, 0.7),
            ("mil", 0.7, 0.9),
            ("e", 0.9, 1.0),
            ("oitocentos", 1.0, 1.5),
            ("homens", 1.5, 1.9),
            ("seguiam", 1.9, 2.3),
            ("Polibio.", 2.3, 2.8),
        )
        tokens = align_units([unit], heard, {"p0001": (0.0, 2.8)})
        assert [t.text for t in tokens] == ["Quase", "16.800", "homens", "seguiam", "Políbio."]
        number = tokens[1]
        #  "16.800" herda o intervalo das quatro palavras que o Whisper ouviu.
        assert number.start == pytest.approx(0.3) and number.end == pytest.approx(1.5)
        assert tokens[-1].end == pytest.approx(2.8)

    def test_words_never_leak_into_the_next_sentence(self) -> None:
        units = [Unit("p0001", 0, "Primeira frase."), Unit("p0002", 0, "Segunda frase.")]
        heard = _words(("Primeira", 0.0, 0.5), ("frase.", 0.5, 1.0), ("Segunda", 1.3, 1.8))
        tokens = align_units(units, heard, {"p0001": (0.0, 1.0), "p0002": (1.25, 2.4)})
        second = [t for t in tokens if t.unit_id == "p0002"]
        assert second[0].start >= 1.25
        #  "frase." da segunda frase nao foi ouvida: interpolada ate o fim da janela.
        assert second[-1].end == pytest.approx(2.4)

    def test_without_sentence_times_the_spans_come_from_the_words(self) -> None:
        units = [Unit("p0001", 0, "Um dois."), Unit("p0002", 0, "Tres quatro.")]
        heard = _words(("Um", 0, 1), ("dois.", 1, 2), ("Tres", 2.5, 3), ("quatro.", 3, 4))
        spans = unit_spans(align_units(units, heard))
        assert spans == {"p0001": (0.0, 2.0), "p0002": (2.5, 4.0)}


class TestKokoroLanguage:
    def test_language_comes_from_the_voice_prefix(self) -> None:
        assert lang_code_for("pm_alex", "pt-BR") == "p"
        assert lang_code_for("bm_george", "en-US") == "b"
        assert lang_code_for("am_michael,am_adam", "en-US") == "a"

    def test_a_voice_of_the_wrong_language_is_refused(self) -> None:
        with pytest.raises(ProviderMisconfigured, match="nao e de pt-BR"):
            lang_code_for("am_michael", "pt-BR")
