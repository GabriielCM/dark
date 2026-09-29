"""Preparo da foto de referencia de uma peca para o img2img.

A cena de peca mostra um objeto inteiro, isolado em fundo branco. A foto do
Commons chega com mesa, vitrine ou grama em volta, e em qualquer proporcao;
o img2img recorta a imagem de entrada no centro para 16:9, e na calibracao
de 29/09 uma anfora em retrato perdeu a boca e o pe. Por isso o objeto e
recortado, centralizado num quadro branco do tamanho da cena e so entao vai
para o gerador.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

#  Quanto do quadro o objeto ocupa. Grande de proposito: objeto fino (gladio,
#  anfora) com pouca area perde a forma para o que o modelo conhece
#  (calibracao de 29/09); 92% ainda deixa margem para o traco.
FILL = 0.92


def letterbox(image: Image.Image, size: tuple[int, int], *, fill: float = FILL) -> Image.Image:
    """O objeto inteiro e centralizado num quadro branco de `size`."""
    canvas = Image.new("RGB", size, "white")
    box = (max(1, int(size[0] * fill)), max(1, int(size[1] * fill)))
    fitted = ImageOps.contain(image, box, Image.Resampling.LANCZOS)
    position = ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2)
    mask = fitted.getchannel("A") if fitted.mode == "RGBA" else None
    canvas.paste(fitted.convert("RGB"), position, mask)
    return canvas


def object_on_white(photo: Path, target: Path, size: tuple[int, int], *, model: str) -> Path:
    """Recorta o objeto da foto (rembg, modelo de licenca comercial) e o
    centraliza em branco no tamanho da cena."""
    from rembg import remove

    from ..style.character import rembg_session

    with Image.open(photo) as image:
        cut = remove(image.convert("RGB"), session=rembg_session(model))
    assert isinstance(cut, Image.Image)
    box = cut.getchannel("A").getbbox()
    subject = cut.crop(box) if box else cut
    letterbox(subject, size).save(target)
    return target
