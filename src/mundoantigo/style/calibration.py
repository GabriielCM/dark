"""Calibracao do estilo contra o teste de 17/09/2026 (fase B2).

O prompt exato do "zimage forte" se perdeu com o disco. Esta ferramenta refaz
as cenas daquela folha com a mesma semente, para cada variante candidata de
prompt, e monta uma folha nova com a coluna antiga recortada na primeira
posicao. O olho humano escolhe; a variante aprovada vira o `prompt_base` do
guia de estilo.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont

from ..providers.image import ImageProvider, ImageRequest

log = logging.getLogger(__name__)

CELL = (384, 216)
LABEL_W = 250
HEADER_H = 44


@dataclass(frozen=True, slots=True)
class CalibrationScene:
    id: str
    sheet: int
    row: int
    kind: str
    prompt: str


@dataclass(frozen=True, slots=True)
class Calibration:
    seed: int
    reference: dict[str, Any]
    restrictions: str
    character: str
    costume: str
    variants: dict[str, str]
    scenes: tuple[CalibrationScene, ...]
    root: Path = field(default=Path("."))

    @classmethod
    def from_yaml(cls, path: Path, root: Path) -> Calibration:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        scenes = tuple(
            CalibrationScene(
                id=str(s["id"]),
                sheet=int(s["folha"]),
                row=int(s["linha"]),
                kind=str(s["tipo"]),
                prompt=str(s["prompt"]),
            )
            for s in raw["cenas"]
        )
        return cls(
            seed=int(raw.get("semente", 11)),
            reference=dict(raw["referencia"]),
            restrictions=" ".join(str(raw.get("restricoes", "")).split()),
            character=" ".join(str(raw["personagem"]).split()),
            costume=str(raw["figurino"]),
            variants={k: " ".join(str(v).split()) for k, v in raw["variantes"].items()},
            scenes=scenes,
            root=root,
        )

    def scene_prompt(self, variant: str, scene: CalibrationScene) -> str:
        body = scene.prompt.format(mc=self.character, figurino=self.costume)
        return f"{self.variants[variant]}. {body}. {self.restrictions}"

    def reference_crop(self, scene: CalibrationScene) -> Image.Image | None:
        ref = self.reference
        sheet = self.root / str(ref["folhas"]).format(folha=scene.sheet)
        if not sheet.exists():
            return None
        width = int(ref["largura_celula"])
        x0 = int(ref["coluna"]) * width
        y0 = int(ref["topo"]) + scene.row * int(ref["periodo"])
        with Image.open(sheet) as image:
            return image.convert("RGB").crop((x0, y0, x0 + width, y0 + int(ref["altura_imagem"])))

    def pick(
        self, variants: list[str] | None, scene_ids: list[str] | None
    ) -> tuple[list[str], list[CalibrationScene]]:
        chosen_variants = variants or list(self.variants)
        unknown = [v for v in chosen_variants if v not in self.variants]
        if unknown:
            raise ValueError(f"variantes desconhecidas: {', '.join(unknown)}")
        scenes = [
            s
            for s in self.scenes
            if not scene_ids or any(s.id.startswith(prefix) for prefix in scene_ids)
        ]
        if not scenes:
            raise ValueError("nenhuma cena selecionada")
        return chosen_variants, scenes


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in ("C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_into(image: Image.Image, cell: tuple[int, int] = CELL) -> Image.Image:
    """Encaixa na celula mantendo a proporcao (a referencia antiga e 200x112).

    Tambem monta as folhas da pre-checagem (review/sheets.py).
    """
    canvas = Image.new("RGB", cell, "white")
    copy = image.convert("RGB")
    copy.thumbnail(cell, Image.Resampling.LANCZOS)
    scale = min(cell[0] / copy.width, cell[1] / copy.height)
    if scale > 1:
        copy = copy.resize(
            (int(copy.width * scale), int(copy.height * scale)), Image.Resampling.LANCZOS
        )
    canvas.paste(copy, ((cell[0] - copy.width) // 2, (cell[1] - copy.height) // 2))
    return canvas


def build_sheet(
    calibration: Calibration,
    scenes: list[CalibrationScene],
    variants: list[str],
    images: dict[tuple[str, str], Path],
    destination: Path,
) -> Path:
    columns = ["antigo: zimage forte", *variants]
    sheet = Image.new(
        "RGB",
        (LABEL_W + CELL[0] * len(columns), HEADER_H + CELL[1] * len(scenes)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    header, label = font(20), font(17)
    for c, name in enumerate(columns):
        draw.text((LABEL_W + c * CELL[0] + 8, 10), name, fill="black", font=header)
    for r, scene in enumerate(scenes):
        y = HEADER_H + r * CELL[1]
        draw.text((8, y + CELL[1] // 2 - 10), scene.id, fill="black", font=label)
        old = calibration.reference_crop(scene)
        if old is not None:
            sheet.paste(fit_into(old), (LABEL_W, y))
        for c, variant in enumerate(variants, start=1):
            path = images.get((scene.id, variant))
            if path and path.exists():
                with Image.open(path) as image:
                    sheet.paste(fit_into(image), (LABEL_W + c * CELL[0], y))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, quality=90)
    return destination


async def run_calibration(
    calibration: Calibration,
    provider: ImageProvider,
    out_dir: Path,
    *,
    variants: list[str] | None = None,
    scene_ids: list[str] | None = None,
    seed: int | None = None,
    size: tuple[int, int] = (1920, 1088),
) -> Path:
    """Gera as variantes e devolve o caminho da folha comparativa."""
    chosen, scenes = calibration.pick(variants, scene_ids)
    use_seed = calibration.seed if seed is None else seed
    out_dir.mkdir(parents=True, exist_ok=True)
    images: dict[tuple[str, str], Path] = {}
    log_rows: list[dict[str, Any]] = []
    for variant in chosen:
        for scene in scenes:
            target = out_dir / variant / f"{scene.id}.png"
            prompt = calibration.scene_prompt(variant, scene)
            if not target.exists():
                log.info("calibrando %s / %s", variant, scene.id)
                await provider.generate(
                    ImageRequest(prompt=prompt, width=size[0], height=size[1], seed=use_seed),
                    target,
                    step="calibracao",
                )
            images[(scene.id, variant)] = target
            log_rows.append({"variante": variant, "cena": scene.id, "prompt": prompt})
    (out_dir / "prompts.json").write_text(
        json.dumps(
            {"semente": use_seed, "criado_em": datetime.now().isoformat(), "itens": log_rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return build_sheet(calibration, scenes, chosen, images, out_dir / "folha.jpg")
