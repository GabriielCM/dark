"""FLUX.1 schnell rodando local na RTX 3060.

Licenca Apache 2.0, uso comercial permitido (brief 5.3). Custo zero, mas
registrado com quantidade para medir volume (ADR 0003).

O `diffusers` so e importado dentro de `_pipeline` — a maquina de CI e a de
desenvolvimento nao precisam de torch para o resto do projeto rodar.
"""

from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path
from typing import Any

from ...costs import Usage
from ...errors import ProviderMisconfigured, ProviderUnavailable
from ..base import BaseProvider
from .base import ImageRequest, ImageResult

log = logging.getLogger(__name__)

#  A GPU e uma so. Este semaforo impede que duas etapas briguem por VRAM.
_GPU_LOCK = asyncio.Semaphore(1)


class FluxLocal(BaseProvider):
    name = "local"
    is_local = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("model", "black-forest-labs/FLUX.1-schnell")
        super().__init__(**kwargs)
        self.steps = int(self.config.get("steps", 4))
        self._pipe: Any = None

    def _pipeline(self) -> Any:
        if self._pipe is not None:
            return self._pipe
        try:
            import torch
            from diffusers import FluxPipeline
        except ImportError as exc:
            raise ProviderMisconfigured(
                self.name,
                "diffusers/torch nao instalados. Este provedor so roda na maquina "
                "com GPU: `uv sync --extra local-gpu` e torch com CUDA.",
            ) from exc

        log.info("carregando %s na GPU (primeira chamada e lenta)", self.model)
        pipe = FluxPipeline.from_pretrained(self.model, torch_dtype=torch.bfloat16)
        #  12 GB de VRAM nao cabem o modelo inteiro; o offload resolve.
        pipe.enable_model_cpu_offload()
        self._pipe = pipe
        return pipe

    async def generate(
        self,
        request: ImageRequest,
        destination: Path,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> ImageResult:
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
            async with _GPU_LOCK:
                await asyncio.to_thread(self._render, request, destination, seed)
            charge.record(images=1)

        return ImageResult(
            path=destination,
            provider=self.name,
            model=self.model,
            seed=seed,
            width=request.width,
            height=request.height,
        )

    def _render(self, request: ImageRequest, destination: Path, seed: int) -> None:
        import torch

        pipe = self._pipeline()
        try:
            image = pipe(
                prompt=request.prompt,
                width=request.width,
                height=request.height,
                num_inference_steps=self.steps,
                #  schnell foi destilado para guidance 0.
                guidance_scale=0.0,
                generator=torch.Generator("cpu").manual_seed(seed),
            ).images[0]
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise ProviderUnavailable(self.name, "VRAM insuficiente") from exc
            raise
        image.save(destination)
