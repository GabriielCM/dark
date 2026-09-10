"""Busca de mentira, com resultados fixos por consulta."""

from __future__ import annotations

from typing import Any

from ...costs import Usage
from ..base import BaseProvider
from .base import SearchHit


class FakeSearch(BaseProvider):
    name = "fake"
    is_local = True

    def __init__(self, *, hits: list[SearchHit] | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("model", "fake-search")
        super().__init__(**kwargs)
        self._hits = hits
        self.queries: list[str] = []

    async def search(
        self,
        query: str,
        *,
        step: str,
        limit: int = 8,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> list[SearchHit]:
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

        if self._hits is not None:
            return self._hits[:limit]
        return [
            SearchHit(
                title=f"Resultado {i + 1} para {query}",
                url=f"https://example.edu/{i + 1}",
                snippet="Trecho de exemplo.",
            )
            for i in range(min(limit, 3))
        ]
