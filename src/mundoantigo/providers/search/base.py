"""Contrato da busca web, usada na checagem de fatos (brief 3.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#  Dominios com peso academico ou institucional. Sobe a confianca de uma fonte
#  no relatorio de fatos; nao substitui a avaliacao do modelo.
TRUSTED_SUFFIXES = (
    ".edu",
    ".ac.uk",
    ".gov",
    ".edu.br",
    ".gov.br",
    "britannica.com",
    "jstor.org",
    "cambridge.org",
    "oup.com",
    "doi.org",
    "smithsonianmag.com",
    "unesco.org",
    "worldhistory.org",
    "archaeology.org",
)


@dataclass(frozen=True, slots=True)
class SearchHit:
    title: str
    url: str
    snippet: str
    age: str | None = None

    @property
    def is_trusted_domain(self) -> bool:
        low = self.url.lower()
        return any(suffix in low for suffix in TRUSTED_SUFFIXES)

    @property
    def quality(self) -> str:
        return "academica" if self.is_trusted_domain else "geral"


class SearchProvider(Protocol):
    name: str
    model: str
    is_local: bool

    async def search(
        self,
        query: str,
        *,
        step: str,
        limit: int = 8,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> list[SearchHit]: ...
