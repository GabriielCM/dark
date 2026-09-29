"""Contrato de props entre o Python e o Remotion.

Esta e a fronteira do ADR 0001. O Python escreve um JSON, o Remotion le. Como
nao ha checagem de tipos atravessando a fronteira, o contrato e explicito dos
dois lados: aqui em Pydantic, e em `render/src/types.ts` em TypeScript. Ha um
teste que compara os campos das duas definicoes.

As camadas graficas (docs/estilo/analise-entregas.md) viajam em dois lugares:
o que pertence a uma cena (o MC recortado e o cartao explicativo) vai na cena;
o que tem tempo proprio (titulo de capitulo, tarja, texto-chave, balao) vai na
linha do tempo de camadas, porque atravessa cortes de cena.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

CameraMove = Literal["zoom_in", "zoom_out", "pan_left", "pan_right", "estatica"]
HostSide = Literal["esquerda", "direita"]
OverlayKind = Literal["titulo", "tarja", "texto", "balao"]


class HostProps(BaseModel):
    """O MC recortado, de corpo inteiro, sobreposto a cena."""

    #  PNG com transparencia, relativo ao diretorio do video.
    image: str
    side: HostSide = "direita"
    #  Largura sobre altura do recorte: o Remotion calcula onde fica a cabeca.
    aspect: float = 0.5
    #  Centro da cabeca, em fracao da largura e da altura do recorte.
    headX: float = 0.5
    headY: float = 0.06


class CardPiece(BaseModel):
    image: str
    label: str


class CardProps(BaseModel):
    """Cartao explicativo: pecas com rotulo sobre fundo de papel."""

    pieces: list[CardPiece]
    comparison: bool = False


class OverlayCue(BaseModel):
    kind: OverlayKind
    start: float
    duration: float
    text: str
    #  Balao sem MC recortado (cena atuada): para onde o rabicho aponta, em
    #  fracao do quadro. Com MC recortado, o Remotion usa a cabeca dele.
    anchorX: float | None = None
    anchorY: float | None = None
    #  Cena cujo MC recortado fala (balao), para ancorar na cabeca certa.
    scene: int | None = None


class SubtitleCue(BaseModel):
    start: float
    end: float
    text: str


class SceneProps(BaseModel):
    index: int
    #  Caminho da imagem do cenario, relativo ao diretorio do video. No cartao,
    #  e a cena anterior, que aparece desfocada atras do papel.
    background: str
    start: float
    duration: float
    camera: CameraMove = "estatica"
    kind: str = "lugar"
    host: HostProps | None = None
    card: CardProps | None = None

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
    overlays: list[OverlayCue] = Field(default_factory=list)
    subtitles: list[SubtitleCue] = Field(default_factory=list)
    palette: dict[str, str] = Field(default_factory=dict)
    #  Familia da fonte das camadas (render/src/fonts.ts).
    fontFamily: str = "Comic Neue"
    #  Legenda desenhada no video. Desligada: a legenda vai em SRT separado.
    burnSubtitles: bool = False

    @property
    def duration_in_frames(self) -> int:
        return max(1, round(self.durationInSeconds * self.fps))

    def field_names(self) -> set[str]:
        return set(self.model_fields)
