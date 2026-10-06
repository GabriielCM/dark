"""Conferencia da escolha do LLM (ADR 0010).

O LLM escolhe entre os candidatos medidos por codigo e escreve, nos dois
idiomas, o gancho na tela, a legenda do post e as hashtags. Nada disso vai
para o render sem passar por aqui: candidato que existe, cortes sem
sobreposicao, gancho curto e de 3 a 5 hashtags com a fixa do canal.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .candidates import LANGS, Candidate, ClipsConfig

#  O prompt usa "pt" e "en"; o pipeline, o id do canal.
_PROMPT_KEY = {"pt-br": "pt", "en": "en"}


class SelectionError(ValueError):
    """A resposta do LLM nao serve. A mensagem diz o que faltou."""


def normalize_hashtag(tag: str) -> str | None:
    """`#Império Romano` vira `#imperioromano`: o que as pessoas digitam."""
    plain = unicodedata.normalize("NFKD", str(tag)).encode("ascii", "ignore").decode()
    word = re.sub(r"[^a-z0-9]", "", plain.lower())
    return f"#{word}" if word else None


def _hashtags(raw: Any, fixed: str | None, config: ClipsConfig) -> tuple[list[str], list[str]]:
    tags: list[str] = []
    for item in raw if isinstance(raw, list) else str(raw or "").split():
        tag = normalize_hashtag(item)
        if tag and tag not in tags:
            tags.append(tag)
    if fixed:
        fixed_tag = normalize_hashtag(fixed)
        if fixed_tag:
            tags = [fixed_tag, *(t for t in tags if t != fixed_tag)]
    warnings: list[str] = []
    if len(tags) > config.hashtags_max:
        tags = tags[: config.hashtags_max]
    if len(tags) < config.hashtags_min:
        warnings.append(f"so {len(tags)} hashtag(s), o minimo e {config.hashtags_min}")
    return tags, warnings


def _text(raw: Any, lang: str) -> str:
    if not isinstance(raw, dict):
        return ""
    value = raw.get(_PROMPT_KEY[lang]) or raw.get(lang) or ""
    return " ".join(str(value).split())


def _caption(raw: Any, lang: str) -> str:
    """Legenda do post: paragrafos preservados, espacos acertados."""
    if not isinstance(raw, dict):
        return ""
    value = str(raw.get(_PROMPT_KEY[lang]) or raw.get(lang) or "")
    lines = [" ".join(line.split()) for line in value.strip().splitlines()]
    return "\n".join(lines).strip()


@dataclass(frozen=True, slots=True)
class Clip:
    """Um corte escolhido: o trecho e os textos de cada idioma."""

    number: int
    candidate: Candidate
    hook: dict[str, str]
    caption: dict[str, str]
    hashtags: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "numero": self.number,
            "candidato": self.candidate.to_dict(),
            "gancho": dict(self.hook),
            "legenda": dict(self.caption),
            "hashtags": {lang: list(tags) for lang, tags in self.hashtags.items()},
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Clip:
        return cls(
            number=int(raw["numero"]),
            candidate=Candidate.from_dict(raw["candidato"]),
            hook={lang: str(raw["gancho"].get(lang) or "") for lang in LANGS},
            caption={lang: str(raw["legenda"].get(lang) or "") for lang in LANGS},
            hashtags={lang: list(raw["hashtags"].get(lang) or []) for lang in LANGS},
        )


@dataclass(slots=True)
class Selection:
    clips: list[Clip]
    #  Legenda e hashtags do video inteiro, postado tambem no TikTok.
    full_video: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cortes": [clip.to_dict() for clip in self.clips],
            "video_inteiro": self.full_video,
            "avisos": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Selection:
        return cls(
            clips=[Clip.from_dict(c) for c in raw.get("cortes", [])],
            full_video=dict(raw.get("video_inteiro") or {}),
            warnings=list(raw.get("avisos") or []),
        )

    def clip(self, number: int) -> Clip:
        for clip in self.clips:
            if clip.number == number:
                return clip
        raise SelectionError(f"o corte {number} nao existe (ha {len(self.clips)})")


def validate_selection(
    raw: Any,
    candidates: list[Candidate],
    config: ClipsConfig,
    fixed_hashtags: dict[str, str | None],
) -> Selection:
    """Confere a resposta do LLM e devolve os cortes na ordem do video."""
    if not isinstance(raw, dict) or not isinstance(raw.get("cortes"), list):
        raise SelectionError("resposta sem a lista `cortes`")
    by_id = {c.id: c for c in candidates}
    warnings: list[str] = []
    chosen: list[tuple[Candidate, dict[str, Any]]] = []

    for item in raw["cortes"]:
        if not isinstance(item, dict):
            continue
        candidate = by_id.get(str(item.get("candidato") or "").strip())
        if candidate is None:
            raise SelectionError(f"candidato desconhecido: {item.get('candidato')!r}")
        if any(candidate.overlaps(other) for other, _ in chosen):
            raise SelectionError(f"o candidato {candidate.id} se sobrepoe a outro corte escolhido")
        chosen.append((candidate, item))
        if len(chosen) == config.count:
            break

    if not chosen:
        raise SelectionError("nenhum corte escolhido")
    if len(chosen) < config.count:
        warnings.append(f"so {len(chosen)} corte(s), o pedido era {config.count}")

    clips: list[Clip] = []
    ordered = sorted(chosen, key=lambda pair: pair[0].span("pt-br").start)
    for number, (candidate, item) in enumerate(ordered, start=1):
        hook: dict[str, str] = {}
        caption: dict[str, str] = {}
        hashtags: dict[str, list[str]] = {}
        for lang in LANGS:
            hook[lang] = _text(item.get("gancho"), lang)
            caption[lang] = _caption(item.get("legenda"), lang)
            if not hook[lang]:
                raise SelectionError(f"corte {number} sem gancho em {lang}")
            if not caption[lang]:
                raise SelectionError(f"corte {number} sem legenda em {lang}")
            if len(hook[lang].split()) > config.hook_max_words:
                warnings.append(
                    f"corte {number}: gancho {lang} com mais de {config.hook_max_words} palavras"
                )
            raw_tags = (item.get("hashtags") or {}).get(_PROMPT_KEY[lang])
            hashtags[lang], tag_warnings = _hashtags(raw_tags, fixed_hashtags.get(lang), config)
            warnings += [f"corte {number} ({lang}): {w}" for w in tag_warnings]
        clips.append(
            Clip(
                number=number,
                candidate=candidate,
                hook=hook,
                caption=caption,
                hashtags=hashtags,
            )
        )

    full_raw = raw.get("video_inteiro")
    full: dict[str, Any] = full_raw if isinstance(full_raw, dict) else {}
    full_video: dict[str, dict[str, Any]] = {}
    for lang in LANGS:
        text = _caption(full.get("legenda"), lang)
        tags, tag_warnings = _hashtags(
            (full.get("hashtags") or {}).get(_PROMPT_KEY[lang]), fixed_hashtags.get(lang), config
        )
        if not text:
            warnings.append(f"video inteiro sem legenda em {lang}")
        warnings += [f"video inteiro ({lang}): {w}" for w in tag_warnings]
        full_video[lang] = {"legenda": text, "hashtags": tags}

    return Selection(clips=clips, full_video=full_video, warnings=warnings)
