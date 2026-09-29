"""Identificacao de voz (fase B6) com sintese e embedding falsos.

A voz falsa e um sinal constante cujo valor identifica a voz; o embedding
falso e [media, 1]. Assim a voz certa e a de maior cosseno, e a duracao da
sintese controla a velocidade estimada.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from mundoantigo.voice import identify as vid

REPO_ROOT = Path(__file__).resolve().parents[1]
LEVEL = {"pf_dora": 0.1, "pm_alex": 0.5, "pm_santa": 0.9}


def fake_synth(text: str, voice: str, speed: float) -> np.ndarray:
    levels = [LEVEL[v] for v in voice.split(",")]
    seconds = 2.4 / speed  # em 1.0 a sintese dura 2,4 s
    return np.full(int(vid.SR * seconds), float(np.mean(levels)), dtype="float32")


def fake_embed(audio: np.ndarray) -> np.ndarray:
    return np.array([float(audio.mean()), 1.0], dtype="float32")


def test_windows_avoid_the_opening_and_the_end() -> None:
    spans = vid.pick_windows(1000.0, 3, 20.0)
    assert len(spans) == 3
    assert spans[0][0] >= 100.0
    assert spans[-1][1] <= 900.0
    assert vid.pick_windows(10.0, 3, 20.0) == [(0.0, 10.0)]


def test_trim_silence() -> None:
    audio = np.concatenate([np.zeros(8000), np.full(16000, 0.5), np.zeros(8000)]).astype("float32")
    assert abs(len(vid.trim_silence(audio)) - 16000) <= 320


def test_rank_finds_the_voice_and_its_speed() -> None:
    reference = np.full(vid.SR * 2, LEVEL["pm_alex"], dtype="float32")  # 2 s de fala
    ranking = vid.rank_voices([reference], ["texto"], list(LEVEL), fake_synth, fake_embed)
    assert ranking[0].voice == "pm_alex"
    #  A sintese em 1.0 dura 2,4 s; a original, 2 s: foi narrada em 1.2.
    assert ranking[0].speed == pytest.approx(1.2, abs=0.02)


def _write_video_audio(path: Path, level: float, seconds: int = 120) -> Path:
    sf.write(str(path), np.full(vid.SR * seconds, level, dtype="float32"), vid.SR)
    return path


def _fake_transcriber(audio: Path, windows: list[tuple[float, float]]) -> list[vid.Window]:
    return [vid.Window(s, e, "o legionario acorda antes do sol", "pt") for s, e in windows]


def test_identify_writes_ranking_and_samples(tmp_path: Path) -> None:
    audio = _write_video_audio(tmp_path / "a.wav", LEVEL["pm_santa"])
    report = vid.identify(
        tmp_path / "video.mp4",
        tmp_path / "saida",
        transcribe=_fake_transcriber,
        synthesizer_for=lambda _lang: fake_synth,
        embed=fake_embed,
        windows=2,
        window_s=10.0,
        audio=audio,
    )
    assert report["idioma"] == "pt"
    assert report["melhores"][0]["voice"] == "pm_santa"
    assert report["misturas"] == []  # a melhor voz ja convence
    out = tmp_path / "saida"
    assert (out / "referencia.wav").exists()
    assert len(list(out.glob("[123]_*.wav"))) == 3
    assert json.loads((out / "ranking.json").read_text(encoding="utf-8"))["idioma"] == "pt"


def test_blends_are_tried_when_no_voice_is_close(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(vid, "BLEND_THRESHOLD", 1.01)
    audio = _write_video_audio(tmp_path / "a.wav", 0.3)
    report = vid.identify(
        tmp_path / "video.mp4",
        tmp_path / "saida",
        transcribe=_fake_transcriber,
        synthesizer_for=lambda _lang: fake_synth,
        embed=fake_embed,
        windows=1,
        window_s=10.0,
        audio=audio,
    )
    assert {m["voice"] for m in report["misturas"]} <= {
        "pm_alex,pf_dora",
        "pf_dora,pm_alex",
        "pm_alex,pm_santa",
        "pm_santa,pm_alex",
        "pf_dora,pm_santa",
        "pm_santa,pf_dora",
    }
    assert len(report["misturas"]) == 3


def test_apply_voice_keeps_the_comments(tmp_path: Path) -> None:
    channel = tmp_path / "pt-br.yaml"
    shutil.copy(REPO_ROOT / "config" / "canais" / "pt-br.yaml", channel)
    vid.apply_voice(channel, "pm_alex", 1.1)
    text = channel.read_text(encoding="utf-8")
    assert 'voice_id: "pm_alex"' in text
    assert "velocidade: 1.1" in text
    assert "provedor: kokoro" in text
    assert "# Sotaque/variante" in text
