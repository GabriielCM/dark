"""Contrato do provedor de imagens (cenarios e thumbnails)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ImageRequest:
    prompt: str
    negative: str = ""
    width: int = 1536
    height: int = 864
    #  Semente registrada no sidecar: e o que permite reproduzir um cenario.
    seed: int | None = None
    #  img2img: a imagem de partida (foto de referencia) e quanto o modelo
    #  pode se afastar dela. 1.0 ignora a imagem; 0.0 devolve a propria foto.
    init_image: Path | None = None
    denoise: float = 1.0


@dataclass(frozen=True, slots=True)
class ImageResult:
    path: Path
    provider: str
    model: str
    seed: int | None
    width: int
    height: int
    #  O que o adaptador decidiu e vale registrar no sidecar (workflow,
    #  pesos, se o negativo foi ignorado...).
    details: dict[str, Any] = field(default_factory=dict)


class ImageProvider(Protocol):
    name: str
    model: str
    is_local: bool

    async def generate(
        self,
        request: ImageRequest,
        destination: Path,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> ImageResult: ...
