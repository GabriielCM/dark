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

from ..errors import ConfigError
from ..providers.image import ImageProvider, ImageRequest

log = logging.getLogger(__name__)

POSES: dict[str, str] = {
    "apontando": "pointing to the side with his right arm fully extended",
    #  "giving a thumbs up" sozinho saiu de bracos baixados (B2): o gesto
    #  precisa estar descrito, com a mao na altura do ombro.
    "joinha": (
        "giving a clear thumbs-up gesture: right fist raised to shoulder height with the "
        "thumb pointing straight up, big smile, left arm relaxed"
    ),
    "pensativo": "thinking with one hand on his chin, slightly puzzled",
    "apresentando": "presenting something with an open palm, friendly smile",
    "maos_para_cima": "raising both open hands in surprise",
    "explicando": "explaining with both hands in front of his chest",
}

#  Poses geradas por img2img a partir de outra: (origem, denoise). So o prompt
#  mudava o desenho inteiro do joinha, mesmo com a mesma semente; partindo de
#  "apontando", o rosto, o figurino e as proporcoes ficam (calibracao 29/09).
DERIVED_POSES: dict[str, tuple[str, float]] = {"joinha": ("apontando", 0.8)}

SPRITE_SIZE = (896, 1344)


@dataclass(frozen=True, slots=True)
class PoseSprite:
    pose: str
    path: Path
    head: tuple[float, float]  # centro da cabeca, em fracao da largura/altura
    aspect: float = 0.5  # largura / altura do recorte


def pose_prompt(style: str, character: str, costume: str, pose: str, restrictions: str) -> str:
    return (
        f"{style}. Full body illustration of {character}, wearing {costume}, "
        f"{POSES[pose]}, standing, facing the viewer, the whole figure visible from "
        f"head to feet, centered, isolated on a plain pure white background, no shadow "
        f"on the floor. {restrictions}"
    )


def cutout_white(image: Image.Image, *, light: int = 215, spread: int = 14) -> Image.Image:
    """Remove o fundo: o que e claro e sem cor e esta ligado a borda.

    Funciona bem em desenho de contorno grosso: o contorno fecha a figura, e o
    branco de dentro (olhos, tunica branca) nao se liga a borda. O criterio e
    "claro e cinza", e nao "perto do branco", por causa da elipse cinza-clara
    (~232) que o modelo desenha sob os pes mesmo com o prompt pedindo que nao:
    ela sai junto com o degrade que a liga ao fundo. Tecido creme, pele e
    madeira tem cor, entao ficam mesmo se o contorno tiver uma falha.
    """
    import numpy as np

    rgb = image.convert("RGB")
    pixels = np.asarray(rgb).astype(np.int16)
    low, high = pixels.min(axis=-1), pixels.max(axis=-1)
    candidate = (low >= light) & (high - low <= spread)
    #  `copy`: a imagem de `fromarray` e so leitura, e o floodfill nela nao
    #  grava nada, sem erro.
    mask = Image.fromarray(np.where(candidate, 255, 0).astype("uint8"), mode="L").copy()
    w, h = mask.size
    border = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    border += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    for point in border:
        if mask.getpixel(point) == 255:
            ImageDraw.floodfill(mask, point, 128, thresh=0)

    background = np.asarray(mask) == 128
    alpha = Image.fromarray(np.where(background, 0, 255).astype("uint8"), mode="L")
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


#  Modelos do rembg com licenca que permite uso comercial. O padrao do rembg
#  2.0.8x, quando nenhum modelo e passado, e o BRIA RMBG-2.0, de licenca
#  CC BY-NC: num canal monetizado nao pode. Por isso todo recorte passa o
#  modelo explicitamente, conferido aqui.
COMMERCIAL_REMBG_MODELS: dict[str, str] = {
    "isnet-general-use": "Apache-2.0",
    "isnet-anime": "Apache-2.0",
    "u2net": "Apache-2.0",
    "u2netp": "Apache-2.0",
    "birefnet-general": "MIT",
    "birefnet-general-lite": "MIT",
}


def rembg_session(model: str) -> Any:
    if model not in COMMERCIAL_REMBG_MODELS:
        raise ConfigError(
            f"modelo de recorte {model!r} sem licenca comercial conferida; "
            f"use um de: {', '.join(sorted(COMMERCIAL_REMBG_MODELS))}"
        )
    from rembg import new_session

    return new_session(model)


def cutout_rembg(image: Image.Image, model: str = "isnet-anime") -> Image.Image:
    from rembg import remove

    result = remove(image.convert("RGB"), session=rembg_session(model))
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
    seeds: dict[str, int] | None = None,
) -> list[PoseSprite]:
    chosen = poses or list(POSES)
    unknown = [p for p in chosen if p not in POSES]
    if unknown:
        raise ValueError(f"poses desconhecidas: {', '.join(unknown)}")
    out_dir.mkdir(parents=True, exist_ok=True)

    async def raw_image(pose: str) -> Path:
        raw = out_dir / "brutas" / f"{pose}.png"
        if raw.exists():
            return raw
        origin, denoise = DERIVED_POSES.get(pose, (None, 1.0))
        #  A origem entra so como bruta: nao vira pose do conjunto sem ser pedida.
        init = await raw_image(origin) if origin else None
        log.info("gerando pose %s", pose + (f" a partir de {origin}" if origin else ""))
        await provider.generate(
            ImageRequest(
                prompt=pose_prompt(style, character, costume, pose, restrictions),
                width=SPRITE_SIZE[0],
                height=SPRITE_SIZE[1],
                #  Pose refeita na grade de revisao usa a semente dela.
                seed=(seeds or {}).get(pose, seed),
                init_image=init,
                denoise=denoise,
            ),
            raw,
            step="personagem",
        )
        return raw

    sprites: list[PoseSprite] = []
    for pose in chosen:
        raw = await raw_image(pose)
        with Image.open(raw) as image:
            cut = cutout_rembg(image) if method == "rembg" else cutout_white(image)
        sprite = trim(cut)
        target = out_dir / f"{pose}.png"
        sprite.save(target)
        sprites.append(
            PoseSprite(
                pose=pose,
                path=target,
                head=head_anchor(sprite),
                aspect=round(sprite.width / max(sprite.height, 1), 4),
            )
        )

    index: dict[str, Any] = {
        "figurino": costume,
        "semente": seed,
        "recorte": method,
        "poses": {
            s.pose: {"arquivo": s.path.name, "cabeca": list(s.head), "proporcao": s.aspect}
            for s in sprites
        },
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    return sprites
