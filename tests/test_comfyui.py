"""Adaptador do ComfyUI (Z-Image Turbo), contra um servidor simulado.

Nenhum teste aqui toca a GPU nem o ComfyUI de verdade: o `MockTransport`
responde as rotas /upload/image, /prompt, /history, /view e /free.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from mundoantigo.errors import ProviderMisconfigured, ProviderUnavailable
from mundoantigo.providers.image import ComfyUIImage, ImageRequest
from mundoantigo.providers.image.comfyui import native_size, node_inputs


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 120, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeComfy:
    """Servidor falso. Guarda o que recebeu para as asserções."""

    def __init__(self, *, history_error: dict[str, Any] | None = None, reject: bool = False):
        self.workflows: list[dict[str, Any]] = []
        self.uploads: list[str] = []
        self.freed = 0
        self.history_calls = 0
        self.history_error = history_error
        self.reject = reject

    def _generated_size(self) -> tuple[int, int]:
        wf = self.workflows[-1]
        for title in ("MA_LATENT", "MA_SCALE"):
            try:
                inputs = node_inputs(wf, title)
            except ProviderMisconfigured:
                continue
            return int(inputs["width"]), int(inputs["height"])
        raise AssertionError("workflow sem tamanho")

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/upload/image":
            self.uploads.append(request.content.decode("latin-1")[:200])
            return httpx.Response(200, json={"name": "abc.png", "subfolder": "mundoantigo"})
        if path == "/prompt":
            if self.reject:
                return httpx.Response(400, json={"error": {"message": "unet ausente"}})
            self.workflows.append(json.loads(request.content)["prompt"])
            return httpx.Response(200, json={"prompt_id": "p1", "number": 1, "node_errors": {}})
        if path == "/history/p1":
            self.history_calls += 1
            if self.history_calls == 1:
                return httpx.Response(200, json={})  # ainda na fila
            if self.history_error:
                status = {
                    "status_str": "error",
                    "messages": [["execution_error", self.history_error]],
                }
                return httpx.Response(200, json={"p1": {"status": status, "outputs": {}}})
            outputs = {"10": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}}
            status = {"status_str": "success", "completed": True, "messages": []}
            return httpx.Response(200, json={"p1": {"status": status, "outputs": outputs}})
        if path == "/view":
            return httpx.Response(200, content=_png(*self._generated_size()))
        if path == "/free":
            self.freed += 1
            return httpx.Response(200, json={})
        return httpx.Response(404)


def _adapter(recorder, server: FakeComfy, **config: Any) -> ComfyUIImage:
    return ComfyUIImage(
        costs=recorder,
        config={"poll_s": 0, **config},
        transport=httpx.MockTransport(server.handler),
    )


def test_native_size_keeps_aspect_and_multiples_of_16() -> None:
    assert native_size(1920, 1088, 1920, 1088) == (1920, 1088)
    assert native_size(2304, 1296, 1920, 1088) == (1920, 1072)
    assert native_size(1280, 720, 1920, 1088) == (1280, 720)


async def test_txt2img_fills_the_workflow_and_saves_the_image(recorder, tmp_path: Path) -> None:
    server = FakeComfy()
    target = tmp_path / "cena-001.png"

    result = await _adapter(recorder, server).generate(
        ImageRequest(prompt="um legionario na chuva", width=64, height=48, seed=7),
        target,
        step="assets",
    )

    wf = server.workflows[0]
    assert node_inputs(wf, "MA_POSITIVE")["text"] == "um legionario na chuva"
    sampler = node_inputs(wf, "MA_SAMPLER")
    assert (sampler["seed"], sampler["steps"], sampler["cfg"], sampler["denoise"]) == (
        7,
        8,
        1.0,
        1.0,
    )
    assert node_inputs(wf, "MA_LATENT")["width"] == 64
    assert node_inputs(wf, "MA_UNET")["unet_name"] == "z_image_turbo_int8_convrot.safetensors"
    with Image.open(target) as image:
        assert image.size == (64, 48)
    assert result.details["workflow"] == "txt2img"
    assert recorder.breakdown_by_step() == [("assets", 0.0, 1)]


async def test_img2img_uploads_the_reference_and_uses_denoise(recorder, tmp_path) -> None:
    server = FakeComfy()
    reference = tmp_path / "panteao.jpg"
    reference.write_bytes(_png(40, 30))

    result = await _adapter(recorder, server).generate(
        ImageRequest(prompt="o Panteao", width=64, height=48, init_image=reference, denoise=0.6),
        tmp_path / "cena.png",
        step="assets",
    )

    wf = server.workflows[0]
    assert server.uploads, "a referencia nao foi enviada"
    assert node_inputs(wf, "MA_INIT")["image"] == "mundoantigo/abc.png"
    assert node_inputs(wf, "MA_SCALE")["width"] == 64
    assert node_inputs(wf, "MA_SAMPLER")["denoise"] == 0.6
    assert result.details["workflow"] == "img2img"


async def test_request_above_native_size_is_upscaled(recorder, tmp_path: Path) -> None:
    server = FakeComfy()
    target = tmp_path / "cena.png"
    adapter = _adapter(recorder, server, max_largura=64, max_altura=36)

    await adapter.generate(ImageRequest(prompt="x", width=128, height=72), target, step="assets")

    assert node_inputs(server.workflows[0], "MA_LATENT")["width"] == 64
    with Image.open(target) as image:
        assert image.size == (128, 72)


async def test_negative_prompt_is_reported_as_ignored(recorder, tmp_path: Path) -> None:
    result = await _adapter(recorder, FakeComfy()).generate(
        ImageRequest(prompt="x", negative="blood", width=32, height=32),
        tmp_path / "c.png",
        step="a",
    )
    assert result.details["negativo_ignorado"] is True


async def test_rejected_workflow_is_permanent(recorder, tmp_path: Path) -> None:
    with pytest.raises(ProviderMisconfigured):
        await _adapter(recorder, FakeComfy(reject=True)).generate(
            ImageRequest(prompt="x", width=32, height=32), tmp_path / "c.png", step="assets"
        )


async def test_out_of_memory_is_transient(recorder, tmp_path: Path) -> None:
    error = {"node_type": "KSampler", "exception_message": "CUDA out of memory"}
    with pytest.raises(ProviderUnavailable, match="VRAM"):
        await _adapter(recorder, FakeComfy(history_error=error)).generate(
            ImageRequest(prompt="x", width=32, height=32), tmp_path / "c.png", step="assets"
        )


async def test_other_execution_errors_are_permanent(recorder, tmp_path: Path) -> None:
    error = {"node_type": "UNETLoader", "exception_message": "file not found"}
    with pytest.raises(ProviderMisconfigured, match="UNETLoader"):
        await _adapter(recorder, FakeComfy(history_error=error)).generate(
            ImageRequest(prompt="x", width=32, height=32), tmp_path / "c.png", step="assets"
        )


async def test_comfyui_down_is_transient(recorder, tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusada", request=request)

    adapter = ComfyUIImage(costs=recorder, config={}, transport=httpx.MockTransport(refuse))
    with pytest.raises(ProviderUnavailable, match="fora do ar"):
        await adapter.generate(
            ImageRequest(prompt="x", width=32, height=32), tmp_path / "c.png", step="assets"
        )
    assert await adapter.health() is False


async def test_release_frees_the_vram(recorder) -> None:
    server = FakeComfy()
    await _adapter(recorder, server).release()
    assert server.freed == 1


def test_registry_builds_comfyui_by_default(settings, recorder) -> None:
    from mundoantigo.providers import ProviderRegistry

    image = ProviderRegistry(settings=settings, costs=recorder).image()
    assert isinstance(image, ComfyUIImage)
    assert image.model == "z-image-turbo"
