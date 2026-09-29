"""Busca de fotos de referencia no Wikimedia Commons (fase B4).

API publica e gratuita. A politica da Wikimedia pede um User-Agent com
contato e requisicoes uma de cada vez; o `maxlag` faz o servidor recusar a
consulta quando esta sobrecarregado, e a recusa vira nova tentativa.
Sem custo, mas cada consulta passa pelo registrador (US$ 0) para medir volume.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

import httpx

from ...costs import Usage
from ...errors import ProviderUnavailable
from ..base import BaseProvider
from .base import ReferenceCandidate

API = "https://commons.wikimedia.org/w/api.php"
ACCEPTED_MIME = ("image/jpeg", "image/png", "image/webp")
#  Larguras de miniatura que o servidor aceita (medido em 09/2026): qualquer
#  outra responde 400.
STANDARD_WIDTHS = (250, 330, 500, 960, 1280, 1920, 3840)


def bucket(width: int) -> int:
    """Menor largura padrao que cobre a pedida."""
    return next((w for w in STANDARD_WIDTHS if w >= width), STANDARD_WIDTHS[-1])


class CommonsReferences(BaseProvider):
    name = "commons"
    is_local = False

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, **kwargs: Any):
        kwargs.setdefault("model", "commons-api")
        super().__init__(**kwargs)
        contact = os.environ.get("MA_WIKIMEDIA_CONTATO") or str(self.config.get("contato") or "")
        self.user_agent = (
            f"MundoAntigoBot/0.2 ({contact or 'sem contato configurado'}) httpx/{httpx.__version__}"
        )
        self.width = bucket(int(self.config.get("largura_download", 1920)))
        self._transport = transport
        #  Uma requisicao por vez, como pede a politica da API.
        self._lock = asyncio.Semaphore(1)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip"},
            timeout=httpx.Timeout(self.timeout_s, connect=10.0),
            transport=self._transport,
            follow_redirects=True,
        )

    async def search(
        self,
        query: str,
        *,
        step: str,
        limit: int = 10,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> list[ReferenceCandidate]:
        params: dict[str, str | int] = {
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": self.width,
            "maxlag": 5,
        }
        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(queries=1),
        ) as charge:
            data = await self._with_retry(self._get, params)
            charge.record(queries=1)

        pages = (data.get("query") or {}).get("pages") or []
        out: list[ReferenceCandidate] = []
        for page in sorted(pages, key=lambda p: int(p.get("index", 0))):
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in ACCEPTED_MIME:
                continue
            title = str(page.get("title", "")).removeprefix("File:")
            out.append(
                ReferenceCandidate(
                    curid=int(page.get("pageid", 0)),
                    title=title,
                    page_url=f"https://commons.wikimedia.org/?curid={int(page.get('pageid', 0))}",
                    image_url=str(info.get("thumburl") or info.get("url") or ""),
                    width=int(info.get("width", 0)),
                    height=int(info.get("height", 0)),
                    mime=str(info.get("mime", "")),
                    rank=int(page.get("index", 0)),
                    metadata=dict(info.get("extmetadata") or {}),
                )
            )
        return out

    async def _get(self, params: dict[str, str | int]) -> dict[str, Any]:
        async with self._lock, self._client() as client:
            try:
                response = await client.get(API, params=params)
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(self.name, f"erro de rede: {exc}") from exc
            self._raise_for_status(response)
            body = dict(response.json())
        error = body.get("error") or {}
        if error.get("code") == "maxlag":
            #  Servidor sobrecarregado: transitorio por definicao.
            raise ProviderUnavailable(self.name, "Commons sobrecarregado (maxlag)")
        if error:
            raise ProviderUnavailable(self.name, f"Commons recusou a busca: {error}")
        return body

    async def download(
        self, candidate: ReferenceCandidate, destination: Path, *, width: int | None = None
    ) -> Path:
        url = candidate.image_url
        if width:
            #  As miniaturas do Commons seguem o padrao .../1920px-Nome.jpg.
            url = re.sub(r"/\d+px-", f"/{bucket(width)}px-", url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with self._lock, self._client() as client:
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(self.name, f"erro de rede: {exc}") from exc
            self._raise_for_status(response)
        destination.write_bytes(response.content)
        return destination
