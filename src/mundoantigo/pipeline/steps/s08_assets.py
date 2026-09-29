"""Etapa 8: cenarios.

Gera, local primeiro (Z-Image no ComfyUI, ADR 0005):
- uma imagem por cena, com o prompt do tipo da cena (prompts/imagem/);
- as pecas dos cartoes explicativos, isoladas em fundo branco e recortadas;
- o conjunto de poses do MC recortado com o figurino deste video
  (style/character.py), com a posicao da cabeca para o balao.

Nenhum texto sai na imagem: nomes, numeros e rotulos sao camadas do Remotion.

Idempotencia por item (ADR 0002): cada imagem e seu proprio artefato. Falhar
na cena 87 nao refaz as 86 anteriores.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...providers.image import ImageRequest
from ...style.character import generate_pose_set
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step
from .s07_referencias import reference_image


def stable_seed(video_id: str, index: int) -> int:
    """Semente reproduzivel entre processos e maquinas."""
    digest = hashlib.sha256(f"{video_id}:{index}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % (2**31)


#  Quantas imagens em voo ao mesmo tempo. O provedor local ja serializa na GPU;
#  este limite existe para o caso de API, onde o paralelismo ajuda.
MAX_PARALELO = 4
PIECE_SIZE = (1024, 1024)


@dataclass(frozen=True, slots=True)
class ImageJob:
    destination: Path
    prompt: str
    seed: int
    width: int
    height: int
    scene: dict[str, Any]
    #  img2img: a foto de referencia (ou ela em fundo branco, para pecas).
    init_image: Path | None = None
    denoise: float = 1.0


def scene_image(ctx: StepContext, index: int) -> Path:
    return ctx.store.path("assets", f"cena-{index:03d}.png")


def piece_image(ctx: StepContext, index: int, piece: int) -> Path:
    return ctx.store.path("assets", f"cena-{index:03d}-peca-{piece}.png")


class AssetsStep(Step):
    name = StepName.ASSETS

    def outputs(self, ctx: StepContext) -> list[Path]:
        storyboard = self._storyboard(ctx)
        out: list[Path] = []
        for scene in storyboard.get("cenas", []):
            out += self._scene_outputs(ctx, scene)
        if self._poses(storyboard):
            out.append(ctx.store.path("assets", "mc/index.json"))
        return out

    def _scene_outputs(self, ctx: StepContext, scene: dict[str, Any]) -> list[Path]:
        index = int(scene["indice"])
        if scene.get("tipo") == "cartao" and scene.get("cartao"):
            return [piece_image(ctx, index, k) for k in range(1, len(scene["cartao"]["pecas"]) + 1)]
        return [scene_image(ctx, index)]

    async def run(self, ctx: StepContext) -> StepResult:
        storyboard = self._storyboard(ctx)
        scenes = storyboard.get("cenas", [])
        style = ctx.settings.style
        provider = ctx.providers.image()
        width, height = self._scene_size(ctx)
        negatives = ", ".join(style.negatives)
        character = storyboard.get("personagem") or {}

        denoise_by_type = ctx.settings.app.get("referencias", {}).get("denoise", {})
        jobs: list[ImageJob] = []
        for scene in scenes:
            index = int(scene["indice"])
            seed = stable_seed(ctx.video_id, index)
            kind = str(scene.get("tipo") or "lugar")
            if kind == "cartao" and scene.get("cartao"):
                for k, piece in enumerate(scene["cartao"]["pecas"], start=1):
                    prompt = self._render(ctx, "peca", piece["descricao"], None, character)
                    jobs.append(
                        ImageJob(piece_image(ctx, index, k), prompt, seed + k, *PIECE_SIZE, scene)
                    )
                continue
            prompt = self._render(
                ctx, kind, scene["descricao_visual"], scene.get("personagem"), character
            )
            reference = reference_image(ctx, index)
            if scene.get("referencia") and ctx.store.is_complete(reference):
                init = self._on_white(ctx, reference, index) if kind == "peca" else reference
                jobs.append(
                    ImageJob(
                        scene_image(ctx, index),
                        prompt,
                        seed,
                        width,
                        height,
                        scene,
                        init_image=init,
                        denoise=float(denoise_by_type.get(kind, 0.6)),
                    )
                )
            else:
                jobs.append(ImageJob(scene_image(ctx, index), prompt, seed, width, height, scene))

        pending = [job for job in jobs if not ctx.store.is_complete(job.destination)]
        skipped = len(jobs) - len(pending)
        semaphore = asyncio.Semaphore(MAX_PARALELO)
        done = 0

        async def render(job: ImageJob) -> None:
            nonlocal done
            async with semaphore:
                result = await provider.generate(
                    ImageRequest(
                        prompt=job.prompt,
                        negative=negatives,
                        width=job.width,
                        height=job.height,
                        seed=job.seed,
                        init_image=job.init_image,
                        denoise=job.denoise,
                    ),
                    job.destination,
                    step=self.name.value,
                    video_id=ctx.video_id,
                    step_run_id=ctx.step_run_id,
                )
                if "-peca-" in job.destination.name:
                    self._cut_out(job.destination)
                extra: dict[str, Any] = {
                    "prompt": job.prompt,
                    "cena": job.scene["indice"],
                    "tipo": job.scene.get("tipo"),
                    **result.details,
                }
                if job.init_image is not None:
                    reference = ctx.store.read_sidecar(reference_image(ctx, job.scene["indice"]))
                    extra["referencia"] = reference.extra.get("referencia") if reference else None
                ctx.store.write_sidecar(
                    job.destination,
                    step="assets",
                    provider=result.provider,
                    model=result.model,
                    seed=result.seed,
                    extra=extra,
                )
                done += 1
                if ctx.progress:
                    ctx.progress({"feitas": done + skipped, "total": len(jobs)})

        if pending:
            await asyncio.gather(*(render(job) for job in pending))

        poses = self._poses(storyboard)
        if poses and not ctx.store.is_complete(ctx.store.path("assets", "mc/index.json")):
            await self._pose_set(ctx, provider, character, poses)

        return StepResult.done(
            summary=(
                f"{len(pending)} imagens geradas"
                + (f", {skipped} reaproveitadas" if skipped else "")
                + (f"; MC em {len(poses)} poses" if poses else "")
            ),
            gerados=len(pending),
            reaproveitados=skipped,
            provedor=provider.name,
        )

    def _render(
        self,
        ctx: StepContext,
        kind: str,
        description: str,
        acting: dict[str, Any] | None,
        character: dict[str, Any],
    ) -> str:
        style = ctx.settings.style
        person = ""
        if acting:
            person = (
                f"{character.get('descricao_fixa', '')}, wearing {character.get('figurino', '')}, "
                f"{acting.get('acao', '')}, {acting.get('expressao', '')} expression"
            )
        prompt = ctx.prompts.get(f"imagem/{kind}").render(
            estilo=style.base_prompt,
            descricao=description,
            personagem=person,
            restricoes=style.positive_restrictions,
        )
        return " ".join(prompt.split())

    async def _pose_set(
        self, ctx: StepContext, provider: Any, character: dict[str, Any], poses: list[str]
    ) -> None:
        style = ctx.settings.style
        folder = ctx.store.stage("assets") / "mc"
        await generate_pose_set(
            provider,
            folder,
            style=style.base_prompt,
            character=str(character.get("descricao_fixa", "")),
            costume=str(character.get("figurino", "")),
            restrictions=style.positive_restrictions,
            #  Mesma semente para todas as poses: e o que mantem o rosto igual.
            seed=stable_seed(ctx.video_id, 0),
            poses=poses,
        )
        index = folder / "index.json"
        ctx.store.write_sidecar(
            index,
            step="assets",
            provider=getattr(provider, "name", None),
            model=getattr(provider, "model", None),
            extra={"poses": json.loads(index.read_text(encoding="utf-8")).get("poses", {})},
        )

    @staticmethod
    def _on_white(ctx: StepContext, reference: Path, index: int) -> Path:
        """Peca a partir de foto: tira o fundo real e poe o objeto no branco.

        Sem isso, o img2img preservaria a mesa ou a vitrine do museu, e a peca
        nao sairia isolada como o tipo de cena pede.
        """
        target = ctx.store.path("referencias", f"cena-{index:03d}-branco.png")
        if target.exists():
            return target
        from PIL import Image

        try:
            from rembg import remove
        except ImportError:
            return reference
        with Image.open(reference) as photo:
            cut = remove(photo.convert("RGB"))
        assert isinstance(cut, Image.Image)
        canvas = Image.new("RGB", cut.size, "white")
        canvas.paste(cut, mask=cut.getchannel("A"))
        canvas.save(target)
        return target

    @staticmethod
    def _cut_out(path: Path) -> None:
        """Peca de cartao: tira o fundo branco para ela assentar sobre o papel."""
        from PIL import Image

        from ...style.character import cutout_white, trim

        with Image.open(path) as image:
            cut = trim(cutout_white(image))
        cut.save(path)

    @staticmethod
    def _poses(storyboard: dict[str, Any]) -> list[str]:
        """Poses que o storyboard usa, na ordem em que aparecem."""
        seen: list[str] = []
        for scene in storyboard.get("cenas", []):
            pose = (scene.get("mc") or {}).get("pose")
            if pose and pose not in seen:
                seen.append(pose)
        return seen

    @staticmethod
    def _scene_size(ctx: StepContext) -> tuple[int, int]:
        """Tamanho das cenas, do bloco do provedor de imagem no app.yaml."""
        _, cfg = ctx.settings.provider_config("imagem")
        width = int(cfg.get("largura", ctx.settings.render.width))
        height = int(cfg.get("altura", ctx.settings.render.height))
        #  Muitos geradores exigem multiplos de 16.
        return width - width % 16, height - height % 16

    @staticmethod
    def _storyboard(ctx: StepContext) -> dict[str, Any]:
        path = ctx.store.path("cenas", "storyboard.json")
        if not path.exists():
            return {"cenas": []}
        return dict(ctx.store.read_json("cenas", "storyboard.json"))
