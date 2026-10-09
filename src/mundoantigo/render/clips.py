"""Props e audio de um corte vertical (ADR 0010).

O corte nao recorta o mp4 da montagem: ele parte das mesmas props do video
inteiro, na largura e altura do TikTok, e fica so com o intervalo do trecho.
Assim o Remotion desenha as camadas no tamanho certo para a tela em pe, e a
legenda vai queimada (no TikTok quase todo mundo assiste sem som no comeco).

O audio e o trecho do WAV da narracao, com um fade curto nas pontas para nao
estalar. O Remotion toca o arquivo inteiro do corte, sem deslocamento.
"""

from __future__ import annotations

import array
import sys
import wave
from pathlib import Path

from .props import OverlayCue, SceneProps, SubtitleCue, VideoProps

#  Cena que sobra com menos que isto nas pontas do corte e engolida pela vizinha.
MIN_SCENE_S = 0.5
MIN_CUE_S = 1.2
FADE_S = 0.03
#  Camadas que dividem o alto da tela com o gancho e o cartao do fim.
TOP_KINDS = ("tarja", "texto")


def _scenes(scenes: list[SceneProps], start: float, end: float) -> list[SceneProps]:
    length = end - start
    kept: list[tuple[SceneProps, float, float]] = []
    for scene in sorted(scenes, key=lambda s: s.start):
        begin = max(scene.start, start) - start
        finish = min(scene.start + scene.duration, end) - start
        if finish - begin <= 0:
            continue
        kept.append((scene, begin, finish))
    #  Lasca de cena nas pontas: a vizinha cobre o tempo dela.
    while len(kept) > 1 and kept[0][2] - kept[0][1] < MIN_SCENE_S:
        kept.pop(0)
    while len(kept) > 1 and kept[-1][2] - kept[-1][1] < MIN_SCENE_S:
        kept.pop()
    #  Corte seco do primeiro ao ultimo quadro (ADR 0012): o quadro zero e o que
    #  aparece no feed antes de qualquer movimento.
    result: list[SceneProps] = []
    for i, (scene, begin, finish) in enumerate(kept):
        begin = 0.0 if i == 0 else begin
        finish = length if i == len(kept) - 1 else finish
        result.append(
            scene.model_copy(
                update={
                    "start": round(begin, 3),
                    "duration": round(max(finish - begin, 0.1), 3),
                    "fadeIn": False,
                    "fadeOut": False,
                }
            )
        )
    return result


def _overlays(
    overlays: list[OverlayCue], start: float, end: float, hook_s: float, end_s: float
) -> list[OverlayCue]:
    length = end - start
    kept: list[OverlayCue] = []
    for cue in overlays:
        if cue.kind == "titulo":
            #  O gancho faz o papel do titulo de capitulo no corte.
            continue
        begin = cue.start - start
        finish = begin + cue.duration
        if cue.kind in TOP_KINDS:
            begin = max(begin, hook_s)
            finish = min(finish, length - end_s)
        begin, finish = max(begin, 0.0), min(finish, length)
        if finish - begin < MIN_CUE_S:
            continue
        kept.append(
            cue.model_copy(update={"start": round(begin, 3), "duration": round(finish - begin, 3)})
        )
    return kept


def clip_props(
    full: VideoProps,
    *,
    start: float,
    end: float,
    narration_file: str,
    hook: str,
    end_text: str,
    width: int,
    height: int,
    hook_s: float,
    end_s: float,
) -> VideoProps:
    """As props do corte: o intervalo [start, end] do video, comecando do zero."""
    if end <= start:
        raise ValueError(f"corte vazio: {start} a {end}")
    length = round(end - start, 3)
    overlays = _overlays(full.overlays, start, end, hook_s, end_s)
    overlays.insert(
        0, OverlayCue(kind="gancho", start=0.0, duration=min(hook_s, length), text=hook)
    )
    if end_text:
        overlays.append(
            OverlayCue(
                kind="fim",
                start=round(max(length - end_s, 0.0), 3),
                duration=round(min(end_s, length), 3),
                text=end_text,
            )
        )
    subtitles = [
        SubtitleCue(
            start=round(max(cue.start - start, 0.0), 3),
            end=round(min(cue.end - start, length), 3),
            text=cue.text,
        )
        for cue in full.subtitles
        if cue.end > start and cue.start < end
    ]
    return full.model_copy(
        update={
            "width": width,
            "height": height,
            "durationInSeconds": length,
            "narration": narration_file,
            "scenes": _scenes(full.scenes, start, end),
            "overlays": overlays,
            "subtitles": subtitles,
            "burnSubtitles": True,
        }
    )


def slice_wav(source: Path, destination: Path, start: float, end: float) -> Path:
    """Copia o trecho [start, end] do WAV, com fade curto nas pontas."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(source), "rb") as reader:
        params = reader.getparams()
        rate = reader.getframerate()
        first = max(0, round(start * rate))
        last = min(reader.getnframes(), round(end * rate))
        reader.setpos(first)
        frames = reader.readframes(max(last - first, 0))

    if params.sampwidth == 2:
        samples = array.array("h")
        samples.frombytes(frames)
        if sys.byteorder == "big":  # pragma: no cover - WAV e little-endian
            samples.byteswap()
        channels = params.nchannels
        fade = min(int(FADE_S * rate), len(samples) // (2 * channels))
        for k in range(fade):
            gain = k / fade
            for c in range(channels):
                samples[k * channels + c] = int(samples[k * channels + c] * gain)
                tail = len(samples) - (k + 1) * channels + c
                samples[tail] = int(samples[tail] * gain)
        if sys.byteorder == "big":  # pragma: no cover
            samples.byteswap()
        frames = samples.tobytes()

    temporary = destination.with_suffix(".tmp.wav")
    with wave.open(str(temporary), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames)
    temporary.replace(destination)
    return destination
