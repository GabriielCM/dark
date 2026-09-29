"""Thumbnails por idioma, com e sem texto (fase B8, brief 5.4).

A arte base sai do gerador junto com os cenarios (etapa assets), sem texto,
como toda imagem do canal: o gerador escreve letras tortas. O texto entra
aqui, com a fonte e as cores das camadas do video (render/src/components/
overlays/style.ts), para a thumb e o video terem a mesma cara.

Com e sem texto porque as duas versoes vao para o "Testar e comparar" do
YouTube. Sai em 1280x720, JPEG abaixo de 2 MB, o limite do upload.
"""

from __future__ import annotations

import itertools
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..paths import get_paths

SIZE = (1280, 720)
MAX_BYTES = 2 * 1024 * 1024
MAX_WORDS = 4

INK = (34, 32, 29)
PAPER = (245, 239, 226)

#  A versao em negrito da fonte das camadas (app.yaml, render.fonte), a mesma
#  copia que o Remotion embute: render/src/fonts/.
FONT_FILES = {
    "Comic Relief": "ComicRelief-Bold.ttf",
    "Comic Neue": "ComicNeue-Bold.ttf",
    "Baloo 2": "Baloo2-Variable.ttf",
}

#  Caixa do texto: um lado da imagem, com margem.
BOX_WIDTH = 0.46
BOX_HEIGHT = 0.74
MARGIN = 0.05


def font_file(family: str, root: Path | None = None) -> Path:
    name = FONT_FILES.get(family, FONT_FILES["Comic Relief"])
    return (root or get_paths().render_project / "src" / "fonts") / name


def base_image(art: Path) -> Image.Image:
    """A arte em 16:9 exato, recortada no centro (a geracao sai em 1920x1088)."""
    with Image.open(art) as image:
        return ImageOps.fit(image.convert("RGB"), SIZE, Image.Resampling.LANCZOS)


def thumb_text(text: str) -> str:
    """Caixa alta, sem cortar: cortar palavra muda o sentido ("QUE NAO")."""
    return " ".join(text.split()).upper()


def too_many_words(text: str) -> bool:
    return len(text.split()) > MAX_WORDS


def _layouts(words: list[str]) -> list[list[str]]:
    """Todas as quebras em 1 a 3 linhas, sem mudar a ordem das palavras."""
    options: list[list[str]] = []
    for lines in range(1, min(3, len(words)) + 1):
        for cuts in itertools.combinations(range(1, len(words)), lines - 1):
            bounds = [0, *cuts, len(words)]
            options.append([" ".join(words[a:b]) for a, b in itertools.pairwise(bounds)])
    return options


def _fit(
    lines: list[str], font_path: Path, box: tuple[int, int]
) -> tuple[int, ImageFont.FreeTypeFont]:
    """Maior corpo em que as linhas cabem na caixa, contando o contorno."""
    low, high = 40, 260
    best = low
    while low <= high:
        size = (low + high) // 2
        font = ImageFont.truetype(str(font_path), size)
        stroke = max(4, size // 10)
        width = max(font.getbbox(line, stroke_width=stroke)[2] for line in lines)
        height = int(size * 1.08) * len(lines)
        if width <= box[0] and height <= box[1]:
            best, low = size, size + 1
        else:
            high = size - 1
    return best, ImageFont.truetype(str(font_path), best)


def _shade(image: Image.Image, side: str) -> Image.Image:
    """Escurece o lado do texto em degrade, para ler sobre qualquer fundo."""
    width, height = image.size
    #  O degrade nasce preto em cima; girado, fica forte na borda do texto.
    ramp = Image.linear_gradient("L").rotate(-90 if side == "esquerda" else 90, expand=True)
    mask = ramp.resize((int(width * 0.62), height))
    alpha = mask.point(lambda v: int(v * 0.62))
    layer = Image.new("L", (width, height), 0)
    layer.paste(alpha, (0 if side == "esquerda" else width - mask.width, 0))
    return Image.composite(Image.new("RGB", image.size, INK), image, layer)


def with_text(base: Image.Image, text: str, *, side: str, font_path: Path) -> Image.Image:
    words = thumb_text(text).split()
    if not words:
        return base.copy()
    side = "direita" if side == "direita" else "esquerda"
    width, height = base.size
    box = (int(width * BOX_WIDTH), int(height * BOX_HEIGHT))

    best_lines, best_size, best_font = [" ".join(words)], 0, None
    for lines in _layouts(words):
        size, font = _fit(lines, font_path, box)
        #  Maior corpo vence; no empate, menos linhas.
        if size > best_size:
            best_lines, best_size, best_font = lines, size, font
    assert best_font is not None

    image = _shade(base, side)
    draw = ImageDraw.Draw(image)
    stroke = max(4, best_size // 10)
    shadow = max(3, best_size // 16)
    line_height = int(best_size * 1.08)
    top = (height - line_height * len(best_lines)) // 2
    margin = int(width * MARGIN)
    for n, line in enumerate(best_lines):
        line_width = best_font.getbbox(line, stroke_width=stroke)[2]
        x = margin if side == "esquerda" else width - margin - line_width
        y = top + n * line_height
        draw.text(
            (x + shadow, y + shadow),
            line,
            font=best_font,
            fill=INK,
            stroke_width=stroke,
            stroke_fill=INK,
        )
        draw.text((x, y), line, font=best_font, fill=PAPER, stroke_width=stroke, stroke_fill=INK)
    return image


def save_jpeg(image: Image.Image, destination: Path, *, max_bytes: int = MAX_BYTES) -> int:
    """Grava no maior JPEG de qualidade que fica abaixo do limite; devolve a qualidade."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    quality = 92
    while True:
        image.save(destination, "JPEG", quality=quality, optimize=True, progressive=True)
        if destination.stat().st_size <= max_bytes or quality <= 50:
            return quality
        quality -= 6
