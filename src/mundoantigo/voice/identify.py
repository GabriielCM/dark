"""Qual voz do Kokoro narrava os videos entregues? (fase B6)

O nome da voz se perdeu com o disco. Os videos baixados do YouTube ainda
guardam a voz, entao ela pode ser reencontrada por comparacao:

1. extrai o audio do MP4 e escolhe janelas de narracao;
2. o faster-whisper transcreve cada janela e detecta o idioma;
3. o Kokoro sintetiza o mesmo texto com cada voz candidata daquele idioma;
4. o ECAPA (SpeechBrain) gera uma "impressao" de locutor de cada audio, e a
   semelhanca de cosseno ordena as candidatas;
5. se nenhuma voz sozinha chega perto, testa misturas das melhores (o
   Kokoro aceita "voz_a,voz_b", que tira a media das duas).

A velocidade sai da razao entre a duracao da fala original e a sintetizada.
O resultado e um ranking e as tres melhores em WAV, para confirmar de ouvido.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

SR = 16_000
KOKORO_SR = 24_000

VOICES: dict[str, tuple[str, ...]] = {
    "pt": ("pf_dora", "pm_alex", "pm_santa"),
    "en": (
        "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
        "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
        "am_onyx", "am_puck", "am_santa",
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    ),
}  # fmt: skip

#  Abaixo disso, nenhuma voz sozinha convence: vale testar misturas.
BLEND_THRESHOLD = 0.70


@dataclass(frozen=True, slots=True)
class Window:
    start: float
    end: float
    text: str
    language: str


@dataclass(frozen=True, slots=True)
class Candidate:
    voice: str
    score: float  # cosseno medio entre as janelas
    speed: float  # velocidade estimada do Kokoro


Transcriber = Callable[[Path, list[tuple[float, float]]], list[Window]]
Synthesizer = Callable[[str, str, float], np.ndarray]  # (texto, voz, velocidade) -> audio 16 kHz
Embedder = Callable[[np.ndarray], np.ndarray]


# -- audio -------------------------------------------------------------------


def extract_audio(video: Path, destination: Path, ffmpeg: str | None = None) -> Path:
    exe = ffmpeg or shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg nao encontrado no PATH")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vn", "-ac", "1", "-ar", str(SR), str(destination)],
        check=True,
    )  # fmt: skip
    return destination


def load_audio(path: Path) -> np.ndarray:
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    return resample(mono, int(sr), SR) if sr != SR else mono


def resample(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr_from, sr_to)
    return resample_poly(audio, sr_to // g, sr_from // g).astype("float32")


def trim_silence(audio: np.ndarray, sr: int = SR, threshold_db: float = -40.0) -> np.ndarray:
    """Tira o silencio do comeco e do fim (janelas de 20 ms)."""
    if audio.size == 0:
        return audio
    frame = max(1, int(sr * 0.02))
    frames = audio[: len(audio) // frame * frame].reshape(-1, frame)
    if frames.size == 0:
        return audio
    rms = np.sqrt((frames**2).mean(axis=1) + 1e-12)
    loud = np.where(20 * np.log10(rms / (rms.max() + 1e-12)) > threshold_db)[0]
    if loud.size == 0:
        return audio
    return audio[loud[0] * frame : (loud[-1] + 1) * frame]


def pick_windows(total_s: float, count: int, duration_s: float) -> list[tuple[float, float]]:
    """Janelas espalhadas pelo miolo do video, longe da abertura e do fim."""
    if total_s <= duration_s:
        return [(0.0, total_s)]
    usable_start, usable_end = total_s * 0.1, total_s * 0.9 - duration_s
    if count == 1 or usable_end <= usable_start:
        start = max(0.0, (total_s - duration_s) / 2)
        return [(round(start, 2), round(start + duration_s, 2))]
    step = (usable_end - usable_start) / (count - 1)
    return [
        (round(usable_start + i * step, 2), round(usable_start + i * step + duration_s, 2))
        for i in range(count)
    ]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.ravel(), b.ravel()
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# -- componentes reais (GPU/CPU) ---------------------------------------------


def whisper_transcriber(device: str = "cuda") -> Transcriber:
    from faster_whisper import WhisperModel

    compute = "float16" if device == "cuda" else "int8"
    model = WhisperModel("large-v3", device=device, compute_type=compute)

    def run(audio: Path, windows: list[tuple[float, float]]) -> list[Window]:
        out: list[Window] = []
        for start, end in windows:
            segments, info = model.transcribe(
                str(audio), clip_timestamps=[start, end], vad_filter=False
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            out.append(Window(start, end, text, str(info.language)))
        return out

    return run


def kokoro_synthesizer(language: str, device: str = "cuda") -> Synthesizer:
    from kokoro import KPipeline

    pipelines: dict[str, Any] = {}

    def lang_code(voice: str) -> str:
        #  O prefixo da voz diz o idioma: p = pt-BR, a = ingles americano, b = britanico.
        return voice.split(",")[0][0]

    def run(text: str, voice: str, speed: float) -> np.ndarray:
        code = lang_code(voice)
        if code not in pipelines:
            pipelines[code] = KPipeline(lang_code=code, repo_id="hexgrad/Kokoro-82M", device=device)
        chunks = [
            np.asarray(audio.cpu() if hasattr(audio, "cpu") else audio, dtype="float32")
            for _, _, audio in pipelines[code](text, voice=voice, speed=speed)
        ]
        audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype="float32")
        return resample(audio, KOKORO_SR, SR)

    return run


def ecapa_embedder(cache_dir: Path, device: str = "cuda") -> Embedder:
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy

    model = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(cache_dir / "spkrec-ecapa-voxceleb"),
        run_opts={"device": device},
        #  COPY em vez de symlink: symlink no Windows exige admin.
        local_strategy=LocalStrategy.COPY,
    )

    def run(audio: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            tensor = torch.from_numpy(np.ascontiguousarray(audio, dtype="float32")).unsqueeze(0)
            embedding = model.encode_batch(tensor.to(device))
        return np.asarray(embedding.squeeze().cpu().numpy(), dtype="float32")

    return run


# -- ranking -----------------------------------------------------------------


def rank_voices(
    references: list[np.ndarray],
    texts: list[str],
    voices: list[str],
    synthesize: Synthesizer,
    embed: Embedder,
) -> list[Candidate]:
    """Ordena as vozes pela semelhanca media com as janelas de referencia."""
    ref_embeddings = [embed(trim_silence(r)) for r in references]
    ref_lengths = [len(trim_silence(r)) / SR for r in references]
    results: list[Candidate] = []
    for voice in voices:
        scores, speeds = [], []
        for ref_emb, ref_len, text in zip(ref_embeddings, ref_lengths, texts, strict=True):
            synth = trim_silence(synthesize(text, voice, 1.0))
            scores.append(cosine(ref_emb, embed(synth)))
            #  Fala original mais curta que a sintetizada em 1.0 = narrada mais rapido.
            speeds.append((len(synth) / SR) / max(ref_len, 0.1))
        results.append(
            Candidate(
                voice=voice,
                score=round(float(np.mean(scores)), 4),
                speed=round(float(np.clip(np.median(speeds), 0.5, 2.0)), 2),
            )
        )
    return sorted(results, key=lambda c: c.score, reverse=True)


def identify(
    video: Path,
    out_dir: Path,
    *,
    transcribe: Transcriber,
    synthesizer_for: Callable[[str], Synthesizer],
    embed: Embedder,
    windows: int = 3,
    window_s: float = 20.0,
    voices: list[str] | None = None,
    audio: Path | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = audio or extract_audio(video, out_dir / "audio16k.wav")
    full = load_audio(wav)
    spans = pick_windows(len(full) / SR, windows, window_s)
    found = [w for w in transcribe(wav, spans) if w.text]
    if not found:
        raise RuntimeError("nenhuma fala transcrita nas janelas escolhidas")
    languages = [w.language for w in found]
    language = max(set(languages), key=languages.count)
    candidates_pool = voices or list(VOICES.get(language, ()))
    if not candidates_pool:
        raise RuntimeError(f"sem vozes do Kokoro para o idioma {language!r}")

    references = [full[int(w.start * SR) : int(w.end * SR)] for w in found]
    texts = [w.text for w in found]
    synthesize = synthesizer_for(language)
    ranking = rank_voices(references, texts, candidates_pool, synthesize, embed)

    blends: list[Candidate] = []
    if ranking[0].score < BLEND_THRESHOLD and len(ranking) >= 2:
        top = [c.voice for c in ranking[:3]]
        pairs = [f"{a},{b}" for i, a in enumerate(top) for b in top[i + 1 :]]
        blends = rank_voices(references, texts, pairs, synthesize, embed)

    best = sorted([*ranking, *blends], key=lambda c: c.score, reverse=True)
    import soundfile as sf

    sf.write(str(out_dir / "referencia.wav"), references[0], SR)
    for position, candidate in enumerate(best[:3], start=1):
        sample = synthesize(texts[0], candidate.voice, candidate.speed)
        name = candidate.voice.replace(",", "+")
        sf.write(str(out_dir / f"{position}_{name}_x{candidate.speed}.wav"), sample, SR)

    report = {
        "video": str(video),
        "idioma": language,
        "janelas": [asdict(w) for w in found],
        "ranking": [asdict(c) for c in ranking],
        "misturas": [asdict(c) for c in blends],
        "melhores": [asdict(c) for c in best[:3]],
    }
    (out_dir / "ranking.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def apply_voice(channel_yaml: Path, voice: str, speed: float) -> None:
    """Grava a voz no YAML do canal sem perder os comentarios do arquivo."""
    import re

    text = channel_yaml.read_text(encoding="utf-8")
    for key, value in (("provedor", "kokoro"), ("voice_id", f'"{voice}"'), ("velocidade", speed)):
        text, count = re.subn(
            rf"^(\s*{key}:\s*)[^#\n]*?(\s*(#.*)?)$",
            rf"\g<1>{value}\g<2>",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count == 0:
            raise ValueError(f"{channel_yaml.name}: campo `{key}` nao encontrado em `voz`")
    channel_yaml.write_text(text, encoding="utf-8")
