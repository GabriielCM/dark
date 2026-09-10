"""Etapa 7: cenarios.

Gera as imagens de fundo, local primeiro. O personagem nao e gerado aqui: ele
vem da biblioteca SVG, produzida uma unica vez (brief, principio 1).

Idempotencia por item (ADR 0002): cada cena e seu proprio artefato. Falhar na
cena 87 nao refaz as 86 anteriores.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from ...providers.image import ImageRequest
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


def stable_seed(video_id: str, index: int) -> int:
    """Semente reproduzivel entre processos e maquinas."""
    digest = hashlib.sha256(f"{video_id}:{index}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % (2**31)


#  Quantas imagens em voo ao mesmo tempo. O provedor local ja serializa na GPU;
#  este limite existe para o caso de API, onde o paralelismo ajuda.
MAX_PARALELO = 4


class AssetsStep(Step):
    name = StepName.ASSETS

    def outputs(self, ctx: StepContext) -> list[Path]:
        storyboard = self._storyboard(ctx)
        return [
            ctx.store.path("assets", f"cena-{s['indice']:03d}.png")
            for s in storyboard.get("cenas", [])
        ]

    async def run(self, ctx: StepContext) -> StepResult:
        storyboard = self._storyboard(ctx)
        scenes = storyboard.get("cenas", [])
        style = ctx.settings.style
        provider = ctx.providers.image()
        negatives = ", ".join(style.negatives)
        width, height = self._scene_size(ctx)

        pending = [
            s
            for s in scenes
            if not ctx.store.is_complete(ctx.store.path("assets", f"cena-{s['indice']:03d}.png"))
        ]
        skipped = len(scenes) - len(pending)

        semaphore = asyncio.Semaphore(MAX_PARALELO)

        async def render(scene: dict[str, Any]) -> None:
            async with semaphore:
                destination = ctx.store.path("assets", f"cena-{scene['indice']:03d}.png")
                prompt = self._compose_prompt(style.base_prompt, scene)
                #  Semente derivada do video e da cena: refazer a mesma cena
                #  reproduz a mesma imagem, o que torna a retomada previsivel.
                #  hashlib, nao hash(): o hash de str do Python muda a cada
                #  processo, e a semente precisa sobreviver a um reinicio.
                seed = stable_seed(ctx.video_id, scene["indice"])
                result = await provider.generate(
                    ImageRequest(
                        prompt=prompt,
                        negative=negatives,
                        width=width,
                        height=height,
                        seed=seed,
                    ),
                    destination,
                    step=self.name.value,
                    video_id=ctx.video_id,
                    step_run_id=ctx.step_run_id,
                )
                ctx.store.write_sidecar(
                    destination,
                    step="assets",
                    provider=result.provider,
                    model=result.model,
                    seed=result.seed,
                    extra={"prompt": prompt, "cena": scene["indice"], "camera": scene["camera"]},
                )

        if pending:
            await asyncio.gather(*(render(scene) for scene in pending))

        return StepResult.done(
            summary=(
                f"{len(pending)} cenarios gerados"
                + (f", {skipped} reaproveitados" if skipped else "")
            ),
            gerados=len(pending),
            reaproveitados=skipped,
            provedor=provider.name,
        )

    @staticmethod
    def _scene_size(ctx: StepContext) -> tuple[int, int]:
        """Cenario e gerado maior que o quadro final.

        O movimento 2.5D faz zoom e pan sobre a imagem (brief 5.3); sem essa
        folga, o pan revelaria a borda. 20% cobre o zoom maximo do guia de estilo.
        """
        _, cfg = ctx.settings.provider_config("imagem")
        width = int(cfg.get("largura", int(ctx.settings.render.width * 1.2)))
        height = int(cfg.get("altura", int(ctx.settings.render.height * 1.2)))
        #  Muitos geradores exigem multiplos de 16.
        return width - width % 16, height - height % 16

    @staticmethod
    def _compose_prompt(base: str, scene: dict[str, Any]) -> str:
        layers = scene.get("camadas", {})
        parts = [base.strip().rstrip(","), scene.get("prompt_cenario", "").strip()]
        for label, key in (
            ("Foreground", "frente"),
            ("Midground", "meio"),
            ("Background", "fundo"),
        ):
            value = str(layers.get(key, "")).strip()
            if value:
                parts.append(f"{label}: {value}")
        return ". ".join(p for p in parts if p)

    @staticmethod
    def _storyboard(ctx: StepContext) -> dict[str, Any]:
        path = ctx.store.path("cenas", "storyboard.json")
        if not path.exists():
            return {"cenas": []}
        return ctx.store.read_json("cenas", "storyboard.json")
