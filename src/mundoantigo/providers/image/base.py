"""Contrato do provedor de imagens (cenarios e thumbnails)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ImageRequest:
    prompt: str
    negative: str = ""
    width: int = 1536
    height: int = 864
    #  Semente registrada no sidecar: e o que permite reproduzir um cenario.
    seed: int | None = None


@dataclass(frozen=True, slots=True)
class ImageResult:
    path: Path
    provider: str
    model: str
    seed: int | None
    width: int
    height: int


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
