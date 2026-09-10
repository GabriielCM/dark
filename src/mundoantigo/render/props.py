"""Contrato de props entre o Python e o Remotion.

Esta e a fronteira do ADR 0001. O Python escreve um JSON, o Remotion le. Como
nao ha checagem de tipos atravessando a fronteira, o contrato e explicito dos
dois lados: aqui em Pydantic, e em `render/src/types.ts` em TypeScript. Ha um
teste que compara os campos das duas definicoes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

CameraMove = Literal["zoom_in", "zoom_out", "pan_left", "pan_right", "estatica"]
CharacterSide = Literal["esquerda", "direita", "centro"]


class CharacterProps(BaseModel):
    pose: str
    #  Caminho do SVG na biblioteca, relativo a raiz do repositorio.
    svg: str | None = None
    position: CharacterSide = "direita"


class SubtitleCue(BaseModel):
    start: float
    end: float
    text: str


class SceneProps(BaseModel):
    index: int
    #  Caminho da imagem do cenario, relativo ao diretorio do video.
    background: str
    start: float
    duration: float
    camera: CameraMove = "estatica"
    character: CharacterProps | None = None
    #  Camadas de profundidade para o parallax 2.5D.
    layers: list[str] = Field(default_factory=list)
    music: str | None = None
    sfx: str | None = None

    @field_validator("duration")
    @classmethod
    def _positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("duracao de cena precisa ser positiva")
        return value


class VideoProps(BaseModel):
    """O que o Remotion recebe para renderizar um dos dois videos."""

    videoId: str
    language: str
    title: str
    fps: int = 30
    width: int = 1920
    height: int = 1080
    durationInSeconds: float
    #  Caminho do WAV da narracao, relativo ao diretorio do video.
    narration: str
    scenes: list[SceneProps]
    subtitles: list[SubtitleCue] = Field(default_factory=list)
    palette: dict[str, str] = Field(default_factory=dict)
    #  Ligado por padrao no PT-BR; o EN usa legenda embutida so se pedido.
    burnSubtitles: bool = False

    @property
    def duration_in_frames(self) -> int:
        return max(1, round(self.durationInSeconds * self.fps))

    def field_names(self) -> set[str]:
        return set(self.model_fields)
