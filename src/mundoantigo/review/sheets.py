"""Folhas de miniaturas para a pre-checagem da sessao (ADR 0012).

Com cenas de ~3 s, um video passa de 350 imagens, e a sessao do Claude nao
confere uma a uma: le folhas de 12, na ordem e com os capitulos da grade, e
abre o PNG so das suspeitas. As folhas sao so da sessao: a revisao do usuario
continua na grade da pagina.

Cada folha e refeita do zero a cada pedido: uma imagem refeita depois de
`imagens aplicar` nunca fica com a miniatura velha.
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..artifacts import ArtifactStore
from ..paths import get_paths
from ..style.calibration import fit_into, font
from .images import sections

CELL = (480, 270)
CAPTION_H = 58
HEADER_H = 46
COLUMNS = 4
PER_SHEET = 12


def sheets_dir(video_id: str) -> Path:
    return get_paths().data / "cache" / "folhas" / video_id


def _numbered(store: ArtifactStore) -> list[tuple[int, dict[str, Any]]]:
    """As secoes da grade com o numero que o `--capitulo` usa: 0 e o topo."""
    result: list[tuple[int, dict[str, Any]]] = []
    chapter = 0
    for section in sections(store):
        if section["id"] == "topo":
            result.append((0, section))
        else:
            chapter += 1
            result.append((chapter, section))
    return result


def _caption(item: dict[str, Any]) -> tuple[str, str]:
    kind = item.get("tipo") or item.get("tipo_imagem") or ""
    head = f"{item['chave']}  {kind}"
    if item.get("refacoes"):
        head += f"  (refeita {item['refacoes']}x)"
    return head, " ".join(str(item.get("narracao") or "").split())


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    typeface: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    width: float,
) -> str:
    """Corta o texto na largura da celula, com reticencias."""
    if draw.textlength(text, font=typeface) <= width:
        return text
    while text and draw.textlength(text + "…", font=typeface) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _sheet(
    store: ArtifactStore, title: str, items: list[dict[str, Any]], columns: int
) -> Image.Image:
    rows = math.ceil(len(items) / columns)
    width, height = CELL[0] * columns, HEADER_H + rows * (CELL[1] + CAPTION_H)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    header, label, small = font(22), font(17), font(15)
    draw.text((10, 11), title, fill="black", font=header)
    for n, item in enumerate(items):
        x = (n % columns) * CELL[0]
        y = HEADER_H + (n // columns) * (CELL[1] + CAPTION_H)
        source = store.root / item["imagem"]
        if source.exists():
            with Image.open(source) as image:
                sheet.paste(fit_into(image, CELL), (x, y))
        else:
            draw.rectangle((x, y, x + CELL[0] - 1, y + CELL[1] - 1), fill="#cccccc")
            draw.text((x + 12, y + 12), "sem imagem", fill="black", font=label)
        head, narration = _caption(item)
        room = CELL[0] - 16
        head = _fit_text(draw, head, label, room)
        draw.text((x + 8, y + CELL[1] + 6), head, fill="black", font=label)
        draw.text(
            (x + 8, y + CELL[1] + 30),
            _fit_text(draw, narration, small, room),
            fill="#444444",
            font=small,
        )
    return sheet


def contact_sheets(
    store: ArtifactStore,
    *,
    chapter: int | None = None,
    keys: set[str] | None = None,
    per_sheet: int = PER_SHEET,
    columns: int = COLUMNS,
) -> list[Path]:
    """Grava as folhas e devolve os caminhos, na ordem da grade.

    `chapter` limita a um capitulo (1, 2...; 0 e a thumbnail com as poses).
    `keys` limita as imagens dadas (cena-045, cena-072-peca-1): conferir so as
    refeitas, sem reler os capitulos inteiros.
    """
    out = sheets_dir(store.video_id)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for number, section in _numbered(store):
        if chapter is not None and number != chapter:
            continue
        items = [i for i in section["itens"] if keys is None or i["chave"] in keys]
        if not items:
            continue
        total = math.ceil(len(items) / per_sheet)
        for k in range(total):
            chunk = items[k * per_sheet : (k + 1) * per_sheet]
            title = f"{section['titulo']}  |  folha {k + 1}/{total}"
            destination = out / f"cap-{number:02d}-{k + 1:02d}.jpg"
            _sheet(store, title, chunk, columns).save(destination, quality=85)
            written.append(destination)
    return written
