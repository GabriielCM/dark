"""Z-Image Turbo no ComfyUI local (ADR 0005).

O ComfyUI roda como servidor proprio (C:\\dev\\ComfyUI, porta 8188) e recebe
workflows no formato de API. Os workflows ficam versionados em
config/comfyui/. O adaptador acha os nos que preenche pelo titulo
(`MA_POSITIVE`, `MA_SAMPLER`...), nao pelo id: assim o arquivo pode ser
reexportado do ComfyUI sem quebrar o codigo.

Licenca do Z-Image Turbo: Apache 2.0, uso comercial permitido.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
import logging
import random
import time
import uuid
from functools import cache
from pathlib import Path
from typing import Any

import httpx

from ...costs import Usage
from ...errors import ProviderMisconfigured, ProviderUnavailable
from ...paths import get_paths
from ..base import BaseProvider
from ..gpu import GPU_LOCK
from .base import ImageRequest, ImageResult

log = logging.getLogger(__name__)

_DEFAULT_WORKFLOWS = {
    "txt2img": "config/comfyui/zimage_txt2img.v1.json",
    "img2img": "config/comfyui/zimage_img2img.v1.json",
}


@cache
def _read_workflow(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _multiple_of_16(value: int) -> int:
    return max(16, value - value % 16)


def native_size(width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    """Maior tamanho que o modelo gera direto, mantendo a proporcao pedida."""
    scale = min(1.0, max_width / width, max_height / height)
    return _multiple_of_16(round(width * scale)), _multiple_of_16(round(height * scale))


def node_id(workflow: dict[str, Any], title: str) -> str:
    for key, node in workflow.items():
        if node.get("_meta", {}).get("title") == title:
            return str(key)
    raise ProviderMisconfigured("local", f"workflow sem o no {title!r}")


def node_inputs(workflow: dict[str, Any], title: str) -> dict[str, Any]:
    inputs: dict[str, Any] = workflow[node_id(workflow, title)]["inputs"]
    return inputs


class ComfyUIImage(BaseProvider):
    name = "local"
    is_local = True

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, **kwargs: Any):
        kwargs.setdefault("model", "z-image-turbo")
        super().__init__(**kwargs)
        cfg = self.config
        self.url = str(cfg.get("url", "http://127.0.0.1:8188")).rstrip("/")
        root = get_paths().root
        workflows = {**_DEFAULT_WORKFLOWS, **cfg.get("workflows", {})}
        self.workflows = {kind: root / str(path) for kind, path in workflows.items()}
        self.unet = str(cfg.get("unet", "z_image_turbo_int8_convrot.safetensors"))
        self.weight_dtype = str(cfg.get("weight_dtype", "default"))
        self.clip = str(cfg.get("clip", "qwen_3_4b_fp8_mixed.safetensors"))
        self.vae = str(cfg.get("vae", "ae.safetensors"))
        self.steps = int(cfg.get("steps", 8))
        self.cfg_scale = float(cfg.get("cfg", 1.0))
        self.sampler = str(cfg.get("sampler", "res_multistep"))
        self.scheduler = str(cfg.get("scheduler", "simple"))
        self.shift = float(cfg.get("shift", 3.0))
        self.max_width = int(cfg.get("max_largura", 1920))
        self.max_height = int(cfg.get("max_altura", 1088))
        #  Com CFG 1 o negativo nao tem efeito nenhum. As restricoes do guia
        #  de estilo vao no prompt positivo (ver a etapa de assets).
        self.supports_negative = bool(cfg.get("suporta_negativo", False))
        self.poll_s = float(cfg.get("poll_s", 0.5))
        self.timeout_s = float(cfg.get("timeout_s", 600))
        self._transport = transport
        self._client_id = f"mundoantigo-{uuid.uuid4().hex[:8]}"

    # -- montagem do workflow ------------------------------------------------

    def build_workflow(
        self,
        request: ImageRequest,
        *,
        seed: int,
        width: int,
        height: int,
        init_name: str | None = None,
    ) -> dict[str, Any]:
        kind = "img2img" if init_name else "txt2img"
        path = self.workflows[kind]
        if not path.exists():
            raise ProviderMisconfigured(self.name, f"workflow ausente: {path}")
        workflow = copy.deepcopy(_read_workflow(path))

        node_inputs(workflow, "MA_UNET").update(unet_name=self.unet, weight_dtype=self.weight_dtype)
        node_inputs(workflow, "MA_CLIP")["clip_name"] = self.clip
        node_inputs(workflow, "MA_VAE")["vae_name"] = self.vae
        node_inputs(workflow, "MA_SHIFT")["shift"] = self.shift
        node_inputs(workflow, "MA_POSITIVE")["text"] = request.prompt
        node_inputs(workflow, "MA_SAMPLER").update(
            seed=seed,
            steps=self.steps,
            cfg=self.cfg_scale,
            sampler_name=self.sampler,
            scheduler=self.scheduler,
            denoise=request.denoise if init_name else 1.0,
        )
        if init_name:
            node_inputs(workflow, "MA_INIT")["image"] = init_name
            node_inputs(workflow, "MA_SCALE").update(width=width, height=height)
        else:
            node_inputs(workflow, "MA_LATENT").update(width=width, height=height)
        node_inputs(workflow, "MA_SAVE")["filename_prefix"] = "mundoantigo/cena"
        return workflow

    # -- HTTP ----------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.url,
            timeout=httpx.Timeout(60.0, connect=5.0),
            transport=self._transport,
        )

    async def _call(self, client: httpx.AsyncClient, method: str, path: str, **kw: Any) -> Any:
        try:
            response = await client.request(method, path, **kw)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderUnavailable(
                self.name,
                f"ComfyUI fora do ar em {self.url}. Suba com scripts/esteira.ps1 "
                "ou C:\\dev\\ComfyUI\\run_nvidia_gpu.bat",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(self.name, f"ComfyUI: {exc}") from exc
        return response

    async def _upload(self, client: httpx.AsyncClient, image: Path) -> str:
        if not image.exists():
            raise ProviderMisconfigured(self.name, f"imagem de referencia ausente: {image}")
        data = image.read_bytes()
        #  Nome pelo conteudo: a mesma foto enviada duas vezes nao duplica.
        name = hashlib.sha1(data).hexdigest()[:16] + image.suffix.lower()
        response = await self._call(
            client,
            "POST",
            "/upload/image",
            files={"image": (name, data, "application/octet-stream")},
            data={"overwrite": "true", "subfolder": "mundoantigo", "type": "input"},
        )
        self._raise_for_status(response)
        body = response.json()
        subfolder = body.get("subfolder") or ""
        return f"{subfolder}/{body['name']}" if subfolder else str(body["name"])

    async def _submit(self, client: httpx.AsyncClient, workflow: dict[str, Any]) -> str:
        response = await self._call(
            client, "POST", "/prompt", json={"prompt": workflow, "client_id": self._client_id}
        )
        if response.status_code == 400:
            #  400 do ComfyUI e workflow invalido: no ausente, peso inexistente.
            raise ProviderMisconfigured(self.name, f"workflow recusado: {response.text[:800]}")
        self._raise_for_status(response)
        body = response.json()
        if body.get("node_errors"):
            raise ProviderMisconfigured(self.name, f"workflow recusado: {body['node_errors']}")
        return str(body["prompt_id"])

    def _execution_error(self, status: dict[str, Any]) -> Exception:
        details = [
            data
            for kind, data in status.get("messages", [])
            if kind == "execution_error" and isinstance(data, dict)
        ]
        info = details[0] if details else {}
        message = f"{info.get('node_type', '?')}: {info.get('exception_message', status)}"
        text = f"{info.get('exception_type', '')} {info.get('exception_message', '')}".lower()
        if "memory" in text:
            return ProviderUnavailable(self.name, f"VRAM insuficiente ({message})")
        return ProviderMisconfigured(self.name, f"falha no workflow ({message})")

    async def _wait(self, client: httpx.AsyncClient, prompt_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            response = await self._call(client, "GET", f"/history/{prompt_id}")
            self._raise_for_status(response)
            entry = response.json().get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise self._execution_error(status)
                if entry.get("outputs") and status.get("completed", True):
                    return dict(entry["outputs"])
            await asyncio.sleep(self.poll_s)
        raise ProviderUnavailable(self.name, f"ComfyUI nao terminou em {self.timeout_s:.0f} s")

    async def _fetch(
        self, client: httpx.AsyncClient, outputs: dict[str, Any], save_id: str
    ) -> bytes:
        images = outputs.get(save_id, {}).get("images") or []
        if not images:
            raise ProviderUnavailable(self.name, "ComfyUI terminou sem imagem na saida")
        response = await self._call(client, "GET", "/view", params=images[0])
        self._raise_for_status(response)
        return bytes(response.content)

    # -- contrato ------------------------------------------------------------

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
        width, height = native_size(request.width, request.height, self.max_width, self.max_height)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self.costs.guard(
            step=step,
            provider=self.name,
            model=self.model,
            video_id=video_id,
            step_run_id=step_run_id,
            estimate=Usage(images=1),
        ) as charge:
            async with GPU_LOCK, self._client() as client:
                init_name = (
                    await self._upload(client, request.init_image) if request.init_image else None
                )
                workflow = self.build_workflow(
                    request, seed=seed, width=width, height=height, init_name=init_name
                )
                prompt_id = await self._submit(client, workflow)
                outputs = await self._wait(client, prompt_id)
                data = await self._fetch(client, outputs, node_id(workflow, "MA_SAVE"))
            self._save(data, destination, request.width, request.height)
            charge.record(images=1)

        return ImageResult(
            path=destination,
            provider=self.name,
            model=self.model,
            seed=seed,
            width=request.width,
            height=request.height,
            details={
                "workflow": "img2img" if init_name else "txt2img",
                "unet": self.unet,
                "gerado_em": f"{width}x{height}",
                "denoise": request.denoise if init_name else 1.0,
                "negativo_ignorado": bool(request.negative) and not self.supports_negative,
            },
        )

    @staticmethod
    def _save(data: bytes, destination: Path, width: int, height: int) -> None:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if image.size == (width, height):
                image.save(destination)
                return
            #  Pedido acima do limite nativo: amplia mantendo a proporcao.
            resized = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
            resized.save(destination)

    async def release(self) -> None:
        """Descarrega os modelos da VRAM (antes de Kokoro, Whisper ou CLIP)."""
        async with self._client() as client:
            await self._call(
                client, "POST", "/free", json={"unload_models": True, "free_memory": True}
            )

    async def health(self) -> bool:
        try:
            async with self._client() as client:
                response = await self._call(client, "GET", "/system_stats")
            return bool(response.is_success)
        except ProviderUnavailable:
            return False
