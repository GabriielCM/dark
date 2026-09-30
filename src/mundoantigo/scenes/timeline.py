"""Linha do tempo das cenas (fase B5, revisto no ADR 0008).

Antes, a montagem esticava todas as cenas por um fator global para fechar
com a duracao da narracao. Num video de 20 minutos, com 190 cenas, isso
deixava imagens varias frases longe do que a voz dizia.

Agora cada cena comeca no proprio texto:
- PT: no inicio exato da primeira frase da cena, ou da palavra em que ela
  comeca quando o corte e no meio de uma frase longa;
- EN: na mesma fracao do bloco correspondente, porque a adaptacao tem os
  mesmos blocos mas nao as mesmas frases. O ponto e encaixado no inicio de
  frase EN mais proximo (ate `SNAP_SENTENCE_S`) ou, sem frase por perto, no
  inicio de palavra mais proximo: a imagem nunca troca no meio de uma palavra.

A cena termina onde a seguinte comeca; a ultima vai ate o fim do audio.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any

MIN_SCENE_S = 0.5
SNAP_SENTENCE_S = 1.0


def _nearest(sorted_values: list[float], value: float) -> float | None:
    if not sorted_values:
        return None
    i = bisect_left(sorted_values, value)
    near = sorted_values[max(i - 1, 0) : i + 1]
    return min(near, key=lambda v: abs(v - value))


def scene_starts(scenes: list[dict[str, Any]], tempos: dict[str, Any]) -> list[float]:
    sentences = {f["id"]: f for f in tempos.get("frases", [])}
    words = [float(w["i"]) for w in tempos.get("palavras", [])]
    blocks = {
        int(b["indice"]): (float(b["inicio_s"]), float(b["fim_s"]))
        for b in tempos.get("blocos", [])
    }
    sentence_starts: dict[int, list[float]] = {}
    for f in tempos.get("frases", []):
        sentence_starts.setdefault(int(f["bloco"]), []).append(float(f["inicio"]))

    starts: list[float] = []
    for scene in scenes:
        first = (scene.get("frases") or [None])[0]
        sentence = sentences.get(first)
        if sentence is not None:
            offset = int(scene.get("inicio_palavra") or 0)
            span = sentence.get("palavras")
            if offset and span and int(span[0]) + offset < len(words):
                starts.append(words[int(span[0]) + offset])
            else:
                starts.append(float(sentence["inicio"]))
            continue
        index = int(scene.get("bloco", -1))
        block = blocks.get(index)
        if block is None:
            #  Sem frase nem bloco com tempo: fica logo depois da anterior.
            starts.append(starts[-1] + MIN_SCENE_S if starts else 0.0)
            continue
        fraction = float((scene.get("fracao_bloco") or [0.0])[0])
        at = block[0] + fraction * (block[1] - block[0])
        near = _nearest(sentence_starts.get(index, []), at)
        taken = starts[-1] + MIN_SCENE_S if starts else -1.0
        if near is not None and abs(near - at) <= SNAP_SENTENCE_S and near >= taken:
            at = near
        else:
            inside = [w for w in words if block[0] <= w <= block[1]]
            at = _nearest(inside, at) or at
        starts.append(at)
    if starts:
        #  A primeira imagem cobre desde o quadro zero, inclusive o respiro inicial.
        starts[0] = 0.0
    for i in range(1, len(starts)):
        starts[i] = max(starts[i], starts[i - 1] + MIN_SCENE_S)
    return starts


def scene_times(scenes: list[dict[str, Any]], tempos: dict[str, Any]) -> list[tuple[float, float]]:
    """(inicio, fim) de cada cena, cobrindo o audio inteiro sem buracos."""
    starts = scene_starts(scenes, tempos)
    total = float(tempos.get("duracao_s") or (starts[-1] + MIN_SCENE_S if starts else 0.0))
    ends = [*starts[1:], max(total, (starts[-1] + MIN_SCENE_S) if starts else total)]
    return [(round(s, 3), round(e, 3)) for s, e in zip(starts, ends, strict=True)]
