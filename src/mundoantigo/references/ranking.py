"""Qual candidata mostra melhor o alvo da cena? (fase B4)

O CLIP compara imagem e texto sem custo e roda em CPU (ViT-B-32, ~1 GB, MIT).
Sem ele instalado (CI, maquina sem o extra de GPU), cai no ranking pelas
palavras do titulo do arquivo, que e grosseiro mas deterministico.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)


class Ranker(Protocol):
    name: str

    def score(self, items: list[tuple[Path, str]], text: str) -> list[float]:
        """Uma nota por (imagem, titulo); maior e melhor."""
        ...


def _words(text: str) -> set[str]:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z0-9]{3,}", ascii_text)}


class TitleRanker:
    name = "titulo"

    def score(self, items: list[tuple[Path, str]], text: str) -> list[float]:
        wanted = _words(text)
        return [len(wanted & _words(title)) / max(len(wanted), 1) for _, title in items]


class ClipRanker:
    name = "clip"

    def __init__(self, model: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k") -> None:
        import open_clip
        import torch

        self._torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model, pretrained=pretrained, device="cpu"
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(model)

    def score(self, items: list[tuple[Path, str]], text: str) -> list[float]:
        return [row[0] for row in self.score_texts(items, [text])]

    def score_texts(self, items: list[tuple[Path, str]], texts: list[str]) -> list[list[float]]:
        """Uma linha por imagem, uma coluna por texto (similaridade de cosseno)."""
        from PIL import Image

        if not items:
            return []
        torch = self._torch
        with torch.no_grad():
            images = torch.stack(
                [self.preprocess(Image.open(path).convert("RGB")) for path, _ in items]
            )
            image_features = self.model.encode_image(images)
            text_features = self.model.encode_text(self.tokenizer(texts))
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            scores = image_features @ text_features.T
        return [[round(float(s), 4) for s in row] for row in scores]


@cache
def _clip() -> Any:
    return ClipRanker()


def make_ranker(kind: str) -> Ranker:
    if kind == "clip":
        try:
            ranker: Ranker = _clip()
            return ranker
        except ImportError:
            log.warning("open_clip nao instalado; ranking das referencias pelo titulo")
    return TitleRanker()
