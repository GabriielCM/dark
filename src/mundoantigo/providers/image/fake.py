"""Imagem de mentira: PNG solido valido, para testes de ponta a ponta sem GPU."""

from __future__ import annotations

import random
import struct
import zlib
from pathlib import Path
from typing import Any

from ...costs import Usage
from ..base import BaseProvider
from .base import ImageRequest, ImageResult


def _solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """PNG minimo escrito a mao — evita depender de Pillow nos testes."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


class FakeImage(BaseProvider):
    name = "fake"
    is_local = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "fake-image")
        super().__init__(**kwargs)
        self.calls: list[ImageRequest] = []

    async def generate(
        self,
        request: ImageRequest,
        destination: Path,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> ImageResult:
        self.calls.append(request)
        seed = request.seed if request.seed is not None else random.randint(0, 2**31 - 1)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(images=1),
        ) as charge:
            #  Cor derivada da semente: cada cena sai visivelmente diferente.
            rng = random.Random(seed)
            destination.write_bytes(
                _solid_png(
                    min(request.width, 64),
                    min(request.height, 36),
                    (rng.randrange(256), rng.randrange(256), rng.randrange(256)),
                )
            )
            charge.record(images=1)

        return ImageResult(
            path=destination,
            provider=self.name,
            model=self.model,
            seed=seed,
            width=request.width,
            height=request.height,
        )
