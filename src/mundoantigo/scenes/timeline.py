"""Linha do tempo das cenas (fase B5).

Antes, a montagem esticava todas as cenas por um fator global para fechar
com a duracao da narracao. Num video de 20 minutos, com 190 cenas, isso
deixava imagens varias frases longe do que a voz dizia.

Agora cada cena comeca na propria frase:
- PT: no inicio exato da primeira frase da cena (tempo da sintese);
- EN: na mesma fracao do bloco correspondente, porque a adaptacao tem os
  mesmos blocos mas nao as mesmas frases.

A cena termina onde a seguinte comeca; a ultima vai ate o fim do audio.
"""

from __future__ import annotations

from typing import Any

MIN_SCENE_S = 0.5


def scene_starts(scenes: list[dict[str, Any]], tempos: dict[str, Any]) -> list[float]:
    sentences = {f["id"]: float(f["inicio"]) for f in tempos.get("frases", [])}
    blocks = {
        int(b["indice"]): (float(b["inicio_s"]), float(b["fim_s"]))
        for b in tempos.get("blocos", [])
    }
    starts: list[float] = []
    for scene in scenes:
        first = (scene.get("frases") or [None])[0]
        if first in sentences:
            starts.append(sentences[first])
            continue
        block = blocks.get(int(scene.get("bloco", -1)))
        fraction = float((scene.get("fracao_bloco") or [0.0])[0])
        if block is not None:
            starts.append(block[0] + fraction * (block[1] - block[0]))
        else:
            #  Sem frase nem bloco com tempo: fica logo depois da anterior.
            starts.append(starts[-1] + MIN_SCENE_S if starts else 0.0)
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
