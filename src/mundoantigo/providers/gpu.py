"""A GPU e uma so (RTX 3060, 12 GB).

Todo trabalho de GPU deste processo passa pela mesma trava. Antes havia uma
por adaptador, o que deixava Kokoro e Whisper rodarem juntos e brigarem pela
VRAM.

O ComfyUI roda em outro processo e guarda os modelos na VRAM entre chamadas.
Antes de um trabalho de GPU do lado do Python (Kokoro, Whisper, CLIP), ele
precisa soltar essa memoria: `release_comfyui()`. O contrario nao e preciso:
o ComfyUI mede a VRAM livre e faz offload sozinho.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

GPU_LOCK = asyncio.Semaphore(1)


async def release_comfyui(url: str | None, *, timeout_s: float = 30.0) -> bool:
    """Pede ao ComfyUI que descarregue os modelos. Devolve se conseguiu.

    ComfyUI desligado nao e erro: nesse caso a VRAM ja esta livre.
    """
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                f"{url.rstrip('/')}/free", json={"unload_models": True, "free_memory": True}
            )
        return response.is_success
    except httpx.HTTPError as exc:
        log.debug("ComfyUI nao respondeu ao /free (%s); seguindo", exc)
        return False


def empty_torch_cache() -> None:
    """Devolve ao driver a VRAM que o torch reservou e nao usa mais."""
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
