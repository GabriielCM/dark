"""Contrato do provedor de fotos de referencia (fase B4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ReferenceCandidate:
    #  Id estavel do arquivo no acervo (no Commons, o pageid: ?curid=N).
    curid: int
    title: str
    #  Endereco publico para o credito.
    page_url: str
    #  Endereco da imagem a baixar (versao reduzida, ate ~2048 px).
    image_url: str
    width: int
    height: int
    mime: str
    rank: int
    metadata: dict[str, Any] = field(default_factory=dict)


class ReferenceProvider(Protocol):
    name: str
    model: str
    is_local: bool

    async def search(
        self,
        query: str,
        *,
        step: str,
        limit: int = 10,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> list[ReferenceCandidate]: ...

    async def lookup(
        self,
        file: str | int,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> ReferenceCandidate | None:
        """Um arquivo pelo nome ('File:...') ou pelo id; None se nao existe."""
        ...

    async def download(
        self, candidate: ReferenceCandidate, destination: Path, *, width: int | None = None
    ) -> Path:
        """Baixa a imagem; `width` pede uma miniatura menor (para comparar)."""
        ...
