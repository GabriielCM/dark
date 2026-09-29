"""Acervo de mentira: candidatas deterministicas, para testes e para o ensaio."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from ...costs import Usage
from ..base import BaseProvider
from .base import ReferenceCandidate


def _meta(license_short: str, artist: str) -> dict[str, Any]:
    return {
        "LicenseShortName": {"value": license_short},
        "License": {"value": license_short.lower().replace(" ", "-")},
        "Artist": {"value": artist},
    }


class FakeReferences(BaseProvider):
    name = "fake"
    is_local = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "fake-references")
        super().__init__(**kwargs)
        self.queries: list[str] = []

    async def search(
        self,
        query: str,
        *,
        step: str,
        limit: int = 10,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> list[ReferenceCandidate]:
        self.queries.append(query)
        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(queries=1),
        ) as charge:
            charge.record(queries=1)
        base = int(hashlib.sha256(query.encode()).hexdigest()[:8], 16) % 100_000
        #  A primeira e BY-SA (tem de ser recusada); as outras sao livres.
        licenses = [("CC BY-SA 4.0", "Autor SA"), ("CC BY 2.0", "Fotografo"), ("CC0", "")]
        return [
            ReferenceCandidate(
                curid=base + i,
                title=f"{query} {i}.jpg",
                page_url=f"https://commons.wikimedia.org/?curid={base + i}",
                image_url=f"fake://{base + i}",
                width=2400,
                height=1600,
                mime="image/jpeg",
                rank=i,
                metadata=_meta(*licenses[i % len(licenses)]),
            )
            for i in range(min(limit, 3))
        ]

    async def lookup(
        self,
        file: str | int,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> ReferenceCandidate | None:
        """Um arquivo pelo nome: com 'BY-SA' no nome, a licenca e recusavel."""
        title = str(file).removeprefix("File:")
        curid = file if isinstance(file, int) else len(title) * 1000
        license_short = "CC BY-SA 4.0" if "BY-SA" in title else "CC0"
        return ReferenceCandidate(
            curid=curid,
            title=title,
            page_url=f"https://commons.wikimedia.org/?curid={curid}",
            image_url=f"fake://{curid}",
            width=2400,
            height=1600,
            mime="image/jpeg",
            rank=0,
            metadata=_meta(license_short, "Autor do link"),
        )

    async def download(
        self, candidate: ReferenceCandidate, destination: Path, *, width: int | None = None
    ) -> Path:
        from PIL import Image

        destination.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        Image.new("RGB", (96, 64), (120 + candidate.rank * 30, 110, 90)).save(buffer, "JPEG")
        destination.write_bytes(buffer.getvalue())
        return destination
