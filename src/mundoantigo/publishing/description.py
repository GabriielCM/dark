"""Descricao do YouTube montada por codigo (fase B8).

O modelo escreve so o que e texto de verdade: os dois paragrafos. O resto sai
dos artefatos, porque era ai que o pacote antigo errava
(tests/fixtures/pacote_exemplo.txt):
- capitulos: do tempo real de cada bloco na narracao, com o mesmo titulo que
  aparece na tela;
- fontes: as citadas pelo relatorio de fatos aprovado, em "Titulo (ano): link";
- aviso de conteudo sintetico: texto fixo do canal, com acento;
- creditos das ilustracoes: do sidecar de cada cenario, nunca digitados, e
  sem as licencas contraditorias que a etapa de referencias ja recusa.

A ordem das secoes e a do pacote antigo: paragrafos, capitulos, fontes, aviso,
creditos das ilustracoes e, depois, os da musica (fase D).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import ConfigError

#  Regras do YouTube para os carimbos de tempo virarem capitulos.
MIN_CHAPTERS = 3
MIN_CHAPTER_S = 10
ELLIPSIS = "..."
DASH = " — "

_TEXT_KEYS = (
    "fontes",
    "divulgacao",
    "creditos_imagens",
    "creditos_musica",
    "autor_desconhecido",
    "creditos_no_comentario",
    "dominio_publico",
)

#  A etapa de referencias grava "Domínio público" no sidecar; na descricao,
#  o rotulo e o do canal (references/licensing.py).
_PUBLIC_DOMAIN = frozenset({"domínio público", "dominio publico", "public domain"})


def _one_line(text: Any) -> str:
    return " ".join(str(text or "").split())


def shorten(text: str, limit: int | None) -> str:
    """Corta no limite, de preferencia entre palavras, e marca com reticencias."""
    if limit is None or len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + ELLIPSIS


@dataclass(frozen=True, slots=True)
class DescriptionTexts:
    """Os textos fixos de cada canal (`publicacao.textos` em config/canais)."""

    sources: str
    disclosure: str
    image_credits: str
    music_credits: str
    unknown_author: str
    credits_in_comment: str
    public_domain: str

    @classmethod
    def for_channel(cls, publishing: dict[str, Any]) -> DescriptionTexts:
        raw = publishing.get("textos") or {}
        missing = [key for key in _TEXT_KEYS if not _one_line(raw.get(key))]
        if missing:
            raise ConfigError(f"canal sem publicacao.textos: {', '.join(missing)}")
        return cls(*(_one_line(raw[key]) for key in _TEXT_KEYS))


@dataclass(frozen=True, slots=True)
class Chapter:
    start_s: int
    title: str


def format_timestamp(seconds: float, *, with_hours: bool = False) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if with_hours or hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def chapters_from_timings(blocks: list[dict[str, Any]], duration_s: float) -> list[Chapter]:
    """Um capitulo por bloco, no inicio real da primeira frase dele.

    O YouTube so aceita os capitulos se o primeiro for 00:00, se houver pelo
    menos tres e se cada um durar 10 s ou mais. Um bloco curto demais passa a
    fazer parte do capitulo anterior. O tempo e truncado no segundo, para o
    capitulo abrir junto com o titulo na tela, nunca depois.
    """
    ordered = sorted(
        (b for b in blocks if _one_line(b.get("titulo"))),
        key=lambda b: float(b.get("inicio_s") or 0.0),
    )
    chapters: list[Chapter] = []
    for block in ordered:
        start = int(float(block.get("inicio_s") or 0.0)) if chapters else 0
        if chapters and start - chapters[-1].start_s < MIN_CHAPTER_S:
            continue
        chapters.append(Chapter(start, _one_line(block["titulo"])))
    while len(chapters) > 1 and int(duration_s) - chapters[-1].start_s < MIN_CHAPTER_S:
        chapters.pop()
    return chapters


@dataclass(frozen=True, slots=True)
class SourceRef:
    title: str | None
    year: int | None
    url: str | None

    @property
    def key(self) -> str:
        return self.url or self.title or ""


def _source_from(raw: Any) -> SourceRef | None:
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith(("http://", "https://")):
            return SourceRef(None, None, text)
        return SourceRef(text, None, None) if text else None
    if not isinstance(raw, dict):
        return None
    year = str(raw.get("ano") or "").strip()
    source = SourceRef(
        title=_one_line(raw.get("titulo")) or None,
        year=int(year) if year.isdigit() else None,
        url=_one_line(raw.get("url")) or None,
    )
    return source if source.key else None


def sources_that_passed(report: dict[str, Any], dossier: dict[str, Any]) -> list[SourceRef]:
    """As fontes citadas pelas afirmacoes do relatorio aprovado.

    O relatorio cita pelo id da fonte no dossie ou pela URL. A ordem e a da
    primeira citacao. Uma URL citada que nao esta no dossie entra so com o
    link. Sem citacao nenhuma (relatorio antigo), vale o dossie inteiro.
    """
    known: dict[str, SourceRef] = {}
    listed: list[SourceRef] = []
    for raw in dossier.get("fontes", []) or []:
        source = _source_from(raw)
        if source is None:
            continue
        listed.append(source)
        if isinstance(raw, dict) and raw.get("id"):
            known[str(raw["id"])] = source
        if source.url:
            known[source.url] = source

    picked: list[SourceRef] = []
    seen: set[str] = set()
    for item in report.get("itens", []) or []:
        for cited in item.get("fontes", []) or []:
            source = known.get(str(cited)) or _source_from(cited)
            if source is None or not source.url or source.key in seen:
                continue
            seen.add(source.key)
            picked.append(source)
    if picked:
        return picked

    unique: list[SourceRef] = []
    for source in listed:
        if source.key not in seen:
            seen.add(source.key)
            unique.append(source)
    return unique


def format_source(source: SourceRef, *, title_max: int | None = None, bare: bool = False) -> str:
    title = shorten(source.title, title_max) if source.title else ""
    if bare and source.url:
        return f"- {source.url}"
    label = f"{title} ({source.year})" if title and source.year else title
    if label and source.url:
        return f"- {label}: {source.url}"
    return f"- {label or source.url}"


@dataclass(frozen=True, slots=True)
class Credit:
    """Uma foto de referencia usada como base do img2img."""

    title: str
    author: str | None
    license: str | None
    url: str
    #  Falso para o link colado pelo revisor, de fora do Commons (fase C2).
    verified: bool = True


def credits_from_provenance(provenances: list[dict[str, Any] | None]) -> list[Credit]:
    """Um credito por foto, na ordem das cenas, sem repetir a mesma foto."""
    credits: list[Credit] = []
    seen: set[str] = set()
    for item in provenances:
        if not item or not item.get("url"):
            continue
        url = str(item["url"])
        if url in seen:
            continue
        seen.add(url)
        credits.append(
            Credit(
                title=_one_line(item.get("titulo")) or url,
                author=_one_line(item.get("autor")) or None,
                license=_one_line(item.get("licenca")) or None,
                url=url,
                verified=bool(item.get("verificada", True)),
            )
        )
    return credits


def format_credit(
    credit: Credit, *, unknown_author: str, public_domain: str, title_max: int | None = None
) -> str:
    parts = [shorten(credit.title, title_max), credit.author or unknown_author]
    if credit.license:
        is_public_domain = credit.license.casefold() in _PUBLIC_DOMAIN
        parts.append(public_domain if is_public_domain else credit.license)
    parts.append(credit.url)
    return "- " + DASH.join(parts)


@dataclass(frozen=True, slots=True)
class DescriptionParts:
    paragraphs: tuple[str, ...]
    chapters: tuple[Chapter, ...]
    sources: tuple[SourceRef, ...]
    credits: tuple[Credit, ...]
    #  Linhas prontas dos creditos de musica (fase D). Ficam sempre na
    #  descricao: a atribuicao da faixa CC BY precisa estar nela.
    music: tuple[str, ...]
    discloses: bool
    duration_s: float


@dataclass(frozen=True, slots=True)
class Layout:
    """Quanto a descricao foi encurtada para caber no limite do YouTube."""

    title_max: int | None = None
    bare_sources: bool = False
    credits_in_comment: bool = False


@dataclass(frozen=True, slots=True)
class RenderedDescription:
    text: str
    #  Os creditos das ilustracoes, quando nao couberam na descricao.
    pinned_comment: str | None


def render_description(
    parts: DescriptionParts, texts: DescriptionTexts, layout: Layout | None = None
) -> RenderedDescription:
    layout = layout or Layout()
    sections: list[str] = [p.strip() for p in parts.paragraphs if p.strip()]

    if parts.chapters:
        with_hours = parts.duration_s >= 3600
        sections.append(
            "\n".join(
                f"{format_timestamp(c.start_s, with_hours=with_hours)} {c.title}"
                for c in parts.chapters
            )
        )
    if parts.sources:
        lines = [
            format_source(s, title_max=layout.title_max, bare=layout.bare_sources)
            for s in parts.sources
        ]
        sections.append("\n".join([texts.sources, *lines]))
    if parts.discloses:
        sections.append(texts.disclosure)

    comment = None
    if parts.credits:
        credits = "\n".join(
            [
                texts.image_credits,
                *(
                    format_credit(
                        c,
                        unknown_author=texts.unknown_author,
                        public_domain=texts.public_domain,
                        title_max=layout.title_max,
                    )
                    for c in parts.credits
                ),
            ]
        )
        if layout.credits_in_comment:
            sections.append(texts.credits_in_comment)
            comment = credits
        else:
            sections.append(credits)
    if parts.music:
        sections.append("\n".join([texts.music_credits, *parts.music]))

    return RenderedDescription("\n\n".join(sections), comment)
