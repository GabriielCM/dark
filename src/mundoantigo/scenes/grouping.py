"""Agrupa as frases do roteiro em cenas (fase B3).

Codigo, nao LLM: o ritmo e regra. Os videos entregues trocavam de imagem a
cada ~6 s (docs/estilo/analise-entregas.md); aqui as frases sao juntadas em
cenas de 5 a 7 s, sem nunca atravessar a fronteira de um bloco (que e onde
mudam capitulo, titulo e trilha).

Cada cena guarda as frases PT que cobre e a fracao do bloco que ocupa. No
video EN a cena ocupa a mesma fracao do bloco correspondente: a adaptacao
nao tem as mesmas frases, mas tem os mesmos blocos, na mesma ordem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..text.segment import Unit


@dataclass
class SceneSlot:
    index: int
    block: int
    units: list[str] = field(default_factory=list)
    seconds: float = 0.0
    #  Fracao do bloco (por palavras) em que a cena comeca e termina.
    span: tuple[float, float] = (0.0, 1.0)

    def to_json(self) -> dict[str, Any]:
        return {
            "indice": self.index,
            "bloco": self.block,
            "frases": self.units,
            "fracao_bloco": [round(self.span[0], 4), round(self.span[1], 4)],
            "duracao_estimada_s": round(self.seconds, 2),
        }


def estimate_seconds(unit: Unit, words_per_minute: int, pause_s: float = 0.25) -> float:
    return unit.words * 60 / max(words_per_minute, 1) + pause_s


def group_scenes(
    units: list[Unit],
    *,
    words_per_minute: int,
    min_s: float = 5.0,
    max_s: float = 7.0,
) -> list[SceneSlot]:
    scenes: list[SceneSlot] = []
    blocks = sorted({u.block for u in units})
    for block in blocks:
        block_units = [u for u in units if u.block == block]
        block_scenes: list[SceneSlot] = []
        current: SceneSlot | None = None
        for unit in block_units:
            seconds = estimate_seconds(unit, words_per_minute)
            if (
                current is not None
                and current.seconds >= min_s
                and current.seconds + seconds > max_s
            ):
                block_scenes.append(current)
                current = None
            if current is None:
                current = SceneSlot(index=0, block=block)
            current.units.append(unit.id)
            current.seconds += seconds
        if current is not None:
            #  Sobra curta no fim do bloco vai para a cena anterior: uma imagem
            #  de 2 s pisca na tela.
            if block_scenes and current.seconds < min_s * 0.6:
                block_scenes[-1].units += current.units
                block_scenes[-1].seconds += current.seconds
            else:
                block_scenes.append(current)

        total_words = sum(u.words for u in block_units) or 1
        words_by_id = {u.id: u.words for u in block_units}
        cursor = 0
        for scene in block_scenes:
            words = sum(words_by_id[i] for i in scene.units)
            scene.span = (cursor / total_words, (cursor + words) / total_words)
            cursor += words
        scenes += block_scenes

    for index, scene in enumerate(scenes, start=1):
        scene.index = index
    return scenes
