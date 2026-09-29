"""Conjunto de poses do MC recortado (fase B2).

Nos videos entregues, o MC aparece de corpo inteiro sobreposto a cena ou ao
cartao explicativo, com poses (apontando, joinha, pensativo...) e figurino do
tema do video (docs/estilo/analise-entregas.md). Aqui cada pose e gerada em
fundo branco com a mesma semente, recortada e salva como PNG com
transparencia, junto de um indice com a posicao da cabeca (ancora do balao).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ..providers.image import ImageProvider, ImageRequest

log = logging.getLogger(__name__)

POSES: dict[str, str] = {
    "apontando": "pointing to the side with his right arm fully extended",
    "joinha": "smiling and giving a thumbs up with his right hand",
    "pensativo": "thinking with one hand on his chin, slightly puzzled",
    "apresentando": "presenting something with an open palm, friendly smile",
    "maos_para_cima": "raising both open hands in surprise",
    "explicando": "explaining with both hands in front of his chest",
}

SPRITE_SIZE = (896, 1344)


@dataclass(frozen=True, slots=True)
class PoseSprite:
    pose: str
    path: Path
    head: tuple[float, float]  # centro da cabeca, em fracao da largura/altura


def pose_prompt(style: str, character: str, costume: str, pose: str, restrictions: str) -> str:
    return (
        f"{style}. Full body illustration of {character}, wearing {costume}, "
        f"{POSES[pose]}, standing, facing the viewer, the whole figure visible from "
        f"head to feet, centered, isolated on a plain pure white background, no shadow "
        f"on the floor. {restrictions}"
    )


def cutout_white(image: Image.Image, tolerance: int = 18) -> Image.Image:
    """Remove o fundo branco por preenchimento a partir das bordas.

    Funciona bem em desenho de contorno grosso: o contorno fecha a figura e o
    branco de dentro (tunica branca, olhos) fica preservado.
    """
    rgb = image.convert("RGB")
    marker = (255, 0, 255)
    probe = rgb.copy()
    w, h = probe.size
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if probe.getpixel((x, y)) != marker:
            ImageDraw.floodfill(probe, (x, y), marker, thresh=tolerance)
    import numpy as np

    background = np.all(np.asarray(probe) == marker, axis=-1)
    alpha = Image.fromarray(np.where(background, 0, 255).astype("uint8"), mode="L")
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def cutout_rembg(image: Image.Image, model: str = "isnet-anime") -> Image.Image:
    from rembg import new_session, remove

    session = new_session(model)
    result = remove(image.convert("RGB"), session=session)
    assert isinstance(result, Image.Image)
    return result.convert("RGBA")


def trim(sprite: Image.Image, padding: int = 12) -> Image.Image:
    box = sprite.getchannel("A").getbbox()
    if box is None:
        return sprite
    x0, y0, x1, y1 = box
    return sprite.crop(
        (
            max(0, x0 - padding),
            max(0, y0 - padding),
            min(sprite.width, x1 + padding),
            min(sprite.height, y1 + padding),
        )
    )


def head_anchor(sprite: Image.Image) -> tuple[float, float]:
    """Centro aproximado da cabeca: a faixa opaca mais alta da figura.

    Media horizontal dos pixels opacos nos 12% superiores da altura util. Serve
    para o rabicho do balao apontar para a cabeca, nao para a mao erguida.
    """
    alpha = sprite.getchannel("A")
    w, h = sprite.size
    band = max(1, int(h * 0.12))
    xs: list[int] = []
    px = alpha.load()
    assert px is not None
    for y in range(band):
        for x in range(0, w, 2):
            value = px[x, y]
            if isinstance(value, int) and value > 128:
                xs.append(x)
    if not xs:
        return 0.5, 0.06
    xs.sort()
    #  Mediana: uma mao erguida na mesma altura nao puxa o centro.
    center = xs[len(xs) // 2]
    return round(center / w, 3), round(band / 2 / h, 3)


async def generate_pose_set(
    provider: ImageProvider,
    out_dir: Path,
    *,
    style: str,
    character: str,
    costume: str,
    restrictions: str,
    seed: int,
    poses: list[str] | None = None,
    method: str = "branco",
) -> list[PoseSprite]:
    chosen = poses or list(POSES)
    unknown = [p for p in chosen if p not in POSES]
    if unknown:
        raise ValueError(f"poses desconhecidas: {', '.join(unknown)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    sprites: list[PoseSprite] = []
    for pose in chosen:
        raw = out_dir / "brutas" / f"{pose}.png"
        if not raw.exists():
            log.info("gerando pose %s", pose)
            await provider.generate(
                ImageRequest(
                    prompt=pose_prompt(style, character, costume, pose, restrictions),
                    width=SPRITE_SIZE[0],
                    height=SPRITE_SIZE[1],
                    seed=seed,
                ),
                raw,
                step="personagem",
            )
        with Image.open(raw) as image:
            cut = cutout_rembg(image) if method == "rembg" else cutout_white(image)
        sprite = trim(cut)
        target = out_dir / f"{pose}.png"
        sprite.save(target)
        sprites.append(PoseSprite(pose=pose, path=target, head=head_anchor(sprite)))

    index: dict[str, Any] = {
        "figurino": costume,
        "semente": seed,
        "recorte": method,
        "poses": {s.pose: {"arquivo": s.path.name, "cabeca": list(s.head)} for s in sprites},
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return sprites
