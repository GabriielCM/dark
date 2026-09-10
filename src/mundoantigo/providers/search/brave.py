"""Busca web via Brave Search API."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ...costs import Usage
from ...errors import ProviderUnavailable
from ..base import BaseProvider
from .base import SearchHit


class BraveSearch(BaseProvider):
    name = "brave"
    is_local = False

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "search")
        super().__init__(**kwargs)
        self.api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")

    async def search(
        self,
        query: str,
        *,
        step: str,
        limit: int = 8,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> list[SearchHit]:
        key = self._require_key(self.api_key, "BRAVE_SEARCH_API_KEY")

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(queries=1),
        ) as charge:
            data = await self._with_retry(self._get, key, query, limit)
            charge.record(queries=1)

        results = (data.get("web") or {}).get("results") or []
        return [
            SearchHit(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                age=item.get("age"),
            )
            for item in results[:limit]
        ]

    async def _get(self, key: str, query: str, limit: int) -> dict[str, Any]:
        headers = {"X-Subscription-Token": key, "Accept": "application/json"}
        params: dict[str, str | int] = {"q": query, "count": min(limit, 20)}
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            try:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params=params,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(self.name, f"erro de rede: {exc}") from exc
            self._raise_for_status(resp)
            return dict(resp.json())
