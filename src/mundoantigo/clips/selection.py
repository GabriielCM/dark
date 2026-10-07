"""Conferencia da escolha do LLM (ADR 0010).

O LLM escolhe entre os candidatos medidos por codigo e escreve o gancho na
tela, a legenda do post e as hashtags. Nada disso vai para o render sem passar
por aqui: candidato que existe, cortes sem sobreposicao, gancho curto e de 3 a
5 hashtags com a fixa do canal.

Desde 06/10/2026, cada conta tem os proprios cortes, de trechos diferentes
(`"conta": "pt"` ou `"en"`): as duas contas nao postam as mesmas imagens, o
que o TikTok pode marcar como conteudo nao original. Uma escolha sem `conta`
(o formato anterior) vale para os dois idiomas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .candidates import LANGS, Candidate, ClipsConfig

#  O prompt usa "pt" e "en"; o pipeline, o id do canal.
_PROMPT_KEY = {"pt-br": "pt", "en": "en"}
_ACCOUNT = {"pt": "pt-br", "pt-br": "pt-br", "en": "en"}


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


def _for_lang(raw: Any, lang: str, single: bool) -> Any:
    """O valor de um idioma: `{"pt": ...}`, ou o valor puro num corte de uma conta."""
    if isinstance(raw, dict):
        return raw.get(_PROMPT_KEY[lang]) or raw.get(lang)
    return raw if single else None


def _text(raw: Any, lang: str, single: bool = False) -> str:
    return " ".join(str(_for_lang(raw, lang, single) or "").split())


def _caption(raw: Any, lang: str, single: bool = False) -> str:
    """Legenda do post: paragrafos preservados, espacos acertados."""
    value = str(_for_lang(raw, lang, single) or "")
    lines = [" ".join(line.split()) for line in value.strip().splitlines()]
    return "\n".join(lines).strip()


@dataclass(frozen=True, slots=True)
class Clip:
    """Um corte escolhido: o trecho, os idiomas em que e postado e os textos."""

    number: int
    candidate: Candidate
    hook: dict[str, str]
    caption: dict[str, str]
    hashtags: dict[str, list[str]]
    #  As contas que postam este corte. O formato anterior postava nas duas.
    langs: tuple[str, ...] = LANGS

    def to_dict(self) -> dict[str, Any]:
        return {
            "numero": self.number,
            "idiomas": list(self.langs),
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
            langs=tuple(lang for lang in LANGS if lang in (raw.get("idiomas") or LANGS)),
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

    def for_lang(self, lang: str) -> list[Clip]:
        """Os cortes que a conta deste idioma posta, na ordem do video."""
        return [clip for clip in self.clips if lang in clip.langs]


def _accounts(item: dict[str, Any]) -> tuple[str, ...]:
    """Os idiomas de um corte: a `conta` dele, ou os dois no formato anterior."""
    account = str(item.get("conta") or "").strip().lower()
    if not account:
        return LANGS
    if account not in _ACCOUNT:
        raise SelectionError(f"conta desconhecida: {item.get('conta')!r} (use pt ou en)")
    return (_ACCOUNT[account],)


def validate_selection(
    raw: Any,
    candidates: list[Candidate],
    config: ClipsConfig,
    fixed_hashtags: dict[str, str | None],
    full_langs: tuple[str, ...] = LANGS,
) -> Selection:
    """Confere a resposta do LLM e devolve os cortes na ordem do video.

    `config.count` e a quantidade por conta. Nenhum corte divide um instante
    com outro, nem entre as contas. `full_langs` sao as contas que postam o
    video inteiro e precisam da legenda dele.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("cortes"), list):
        raise SelectionError("resposta sem a lista `cortes`")
    by_id = {c.id: c for c in candidates}
    warnings: list[str] = []
    chosen: list[tuple[Candidate, dict[str, Any], tuple[str, ...]]] = []
    per_lang = dict.fromkeys(LANGS, 0)

    for item in raw["cortes"]:
        if not isinstance(item, dict):
            continue
        candidate = by_id.get(str(item.get("candidato") or "").strip())
        if candidate is None:
            raise SelectionError(f"candidato desconhecido: {item.get('candidato')!r}")
        langs = _accounts(item)
        if all(per_lang[lang] >= config.count for lang in langs):
            continue
        if any(candidate.overlaps(other) for other, _, _ in chosen):
            raise SelectionError(f"o candidato {candidate.id} se sobrepoe a outro corte escolhido")
        chosen.append((candidate, item, langs))
        for lang in langs:
            per_lang[lang] += 1

    if not chosen:
        raise SelectionError("nenhum corte escolhido")
    for lang, count in per_lang.items():
        if count < config.count:
            warnings.append(f"so {count} corte(s) em {lang}, o pedido era {config.count}")

    clips: list[Clip] = []
    ordered = sorted(chosen, key=lambda trio: trio[0].span("pt-br").start)
    for number, (candidate, item, langs) in enumerate(ordered, start=1):
        single = len(langs) == 1
        hook: dict[str, str] = {}
        caption: dict[str, str] = {}
        hashtags: dict[str, list[str]] = {}
        for lang in langs:
            hook[lang] = _text(item.get("gancho"), lang, single)
            caption[lang] = _caption(item.get("legenda"), lang, single)
            if not hook[lang]:
                raise SelectionError(f"corte {number} sem gancho em {lang}")
            if not caption[lang]:
                raise SelectionError(f"corte {number} sem legenda em {lang}")
            if len(hook[lang].split()) > config.hook_max_words:
                warnings.append(
                    f"corte {number}: gancho {lang} com mais de {config.hook_max_words} palavras"
                )
            raw_tags = _for_lang(item.get("hashtags"), lang, single)
            hashtags[lang], tag_warnings = _hashtags(raw_tags, fixed_hashtags.get(lang), config)
            warnings += [f"corte {number} ({lang}): {w}" for w in tag_warnings]
        clips.append(
            Clip(
                number=number,
                candidate=candidate,
                hook=hook,
                caption=caption,
                hashtags=hashtags,
                langs=langs,
            )
        )

    full_raw = raw.get("video_inteiro")
    full: dict[str, Any] = full_raw if isinstance(full_raw, dict) else {}
    full_video: dict[str, dict[str, Any]] = {}
    for lang in full_langs:
        text = _caption(full.get("legenda"), lang)
        tags, tag_warnings = _hashtags(
            (full.get("hashtags") or {}).get(_PROMPT_KEY[lang]), fixed_hashtags.get(lang), config
        )
        if not text:
            warnings.append(f"video inteiro sem legenda em {lang}")
        warnings += [f"video inteiro ({lang}): {w}" for w in tag_warnings]
        full_video[lang] = {"legenda": text, "hashtags": tags}

    return Selection(clips=clips, full_video=full_video, warnings=warnings)
