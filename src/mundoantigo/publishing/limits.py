"""Limites do YouTube, conferidos antes do pacote e nao na hora do upload.

- Descricao: 5.000 bytes (a API conta bytes, e acento em UTF-8 ocupa dois).
- Titulo: 100 caracteres; acima de ~70 a busca corta.
- Tags: 500 caracteres somando as virgulas, e cada tag com espaco conta as
  aspas que o YouTube poe em volta dela.
- `<` e `>` sao recusados em titulo e descricao.

A descricao que nao cabe e encurtada em cascata (`fit_description`), do corte
mais barato para o mais caro: titulos das fontes e dos creditos encurtados,
fontes so com o link e, por ultimo, os creditos das ilustracoes no comentario
fixado. A musica nunca sai da descricao: a atribuicao da faixa CC BY tem de
estar nela.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .description import (
    DescriptionParts,
    DescriptionTexts,
    Layout,
    RenderedDescription,
    render_description,
)

DESCRIPTION_MAX_BYTES = 5000
TITLE_MAX = 100
TITLE_SEARCH = 70
TAGS_MAX = 500
SHORT_TITLE = 40

CASCADE = (
    Layout(),
    Layout(title_max=SHORT_TITLE),
    Layout(title_max=SHORT_TITLE, bare_sources=True),
    Layout(title_max=SHORT_TITLE, bare_sources=True, credits_in_comment=True),
)

#  Palavras que em PT sempre levam acento: achar uma delas sem acento e sinal
#  de texto escrito sem acentuacao, como o aviso do pacote antigo.
_ALWAYS_ACCENTED = frozenset(
    {
        "nao", "voce", "voces", "tambem", "entao", "ate", "ja", "sao", "alem",
        "video", "videos",
        "atraves", "historia", "historias", "seculo", "seculos", "imperio",
        "exercito", "agua", "aguas", "possivel", "impossivel", "publico",
        "unico", "unica", "ultimo", "ultima", "pratica", "tecnica", "tecnicas",
        "construcao", "construcoes", "populacao", "civilizacao", "informacao",
        "narracao", "ilustracoes", "revisao", "divulgacao", "direcao",
    }
)  # fmt: skip


def byte_length(text: str) -> int:
    return len(text.encode("utf-8"))


def strip_forbidden(text: str) -> str:
    return text.replace("<", "").replace(">", "")


@dataclass(frozen=True, slots=True)
class FittedDescription:
    text: str
    pinned_comment: str | None
    layout: Layout
    warnings: tuple[str, ...] = field(default_factory=tuple)


def fit_description(parts: DescriptionParts, texts: DescriptionTexts) -> FittedDescription:
    """A primeira forma da cascata que cabe em 5.000 bytes."""
    rendered: RenderedDescription | None = None
    for layout in CASCADE:
        rendered = render_description(parts, texts, layout)
        text = strip_forbidden(rendered.text)
        if byte_length(text) <= DESCRIPTION_MAX_BYTES:
            warnings: tuple[str, ...] = ()
            if layout.credits_in_comment:
                warnings = (
                    "os créditos das ilustrações não couberam na descrição: "
                    "fixe o comentário de comentario_fixado.txt",
                )
            return FittedDescription(text, rendered.pinned_comment, layout, warnings)

    assert rendered is not None
    text = strip_forbidden(rendered.text)
    return FittedDescription(
        text,
        rendered.pinned_comment,
        CASCADE[-1],
        (
            f"descrição com {byte_length(text)} bytes mesmo depois dos cortes "
            f"(limite {DESCRIPTION_MAX_BYTES}): encurte os parágrafos ou as fontes à mão",
        ),
    )


def fit_title(title: str) -> tuple[str, list[str]]:
    clean = " ".join(strip_forbidden(title).split())
    warnings: list[str] = []
    if len(clean) > TITLE_MAX:
        cut = clean[:TITLE_MAX]
        clean = cut[: cut.rfind(" ")] if " " in cut else cut
        warnings.append(f"título cortado em {TITLE_MAX} caracteres")
    if len(clean) > TITLE_SEARCH:
        warnings.append(f"título com {len(clean)} caracteres: a busca mostra ~{TITLE_SEARCH}")
    return clean, warnings


def tags_length(tags: list[str]) -> int:
    quoted = sum(len(tag) + (2 if " " in tag else 0) for tag in tags)
    return quoted + max(len(tags) - 1, 0)


def fit_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    """Tags limpas, sem repetir, e as ultimas (as mais genericas) cortadas ate caber."""
    clean: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = " ".join(strip_forbidden(str(raw)).replace(",", " ").replace("#", "").split())
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold())
            clean.append(tag)
    warnings: list[str] = []
    dropped = 0
    while clean and tags_length(clean) > TAGS_MAX:
        clean.pop()
        dropped += 1
    if dropped:
        warnings.append(f"{dropped} tag(s) cortada(s) para caber em {TAGS_MAX} caracteres")
    return clean, warnings


def unaccented_pt(text: str) -> list[str]:
    """Palavras que deveriam ter acento e vieram sem, na ordem em que aparecem."""
    found: list[str] = []
    for word in re.findall(r"[A-Za-zÀ-ÿ]+", text):
        lower = word.lower()
        if lower in _ALWAYS_ACCENTED and lower not in found:
            found.append(lower)
    return found
