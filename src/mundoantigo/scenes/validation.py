"""Confere e completa o que o LLM devolveu para cada cena (fase B3).

O LLM decide o que cada cena mostra; o codigo garante que a decisao cabe no
contrato. Campo invalido nao derruba a etapa: vira um padrao seguro e fica
registrado em `ajustes`, que o revisor ve no corte final.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

TYPES = (
    "atuada", "lugar", "plano_geral", "plano_medio", "plano_detalhe",
    "metafora", "infografico", "antes_depois", "peca", "cartao",
)  # fmt: skip
REFERENCE_TYPES = ("lugar", "peca", "plano_detalhe")
CAMERAS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "estatica")
POSES = ("apontando", "joinha", "pensativo", "apresentando", "maos_para_cima", "explicando")
SIDES = ("esquerda", "direita")
SFX_EVENTS = ("transicao", "impacto", "objeto", "ambiente")


@dataclass
class BlockContext:
    """O que o bloco oferece: textos de tela nos dois idiomas."""

    comments_pt: list[str] = field(default_factory=list)
    comments_en: list[str] = field(default_factory=list)
    tags_pt: list[str] = field(default_factory=list)
    tags_en: list[str] = field(default_factory=list)
    #  Narracao EN do bloco inteiro: a adaptacao nao casa frase a frase com o PT.
    narration_en: str = ""


def _tokens(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", plain)


def grounded(text: str, narration: str) -> bool:
    """Todo termo do texto aparece na narracao.

    Contam numeros e palavras de 3 letras ou mais; plural e singular passam
    pelas 5 primeiras letras. Vale para o texto-chave, o unico texto de tela
    que o storyboard escreve sozinho: tarjas, baloes e titulos vem do roteiro
    revisado. Na amostra de 29/09, o modelo pos "SUB PELLE" na tela para uma
    narracao que dizia "sob as peles", e nada disso passou pelo gate de fatos.
    """
    spoken = set(_tokens(narration))
    terms = [t for t in _tokens(text) if t.isdigit() or len(t) >= 3]

    def said(term: str) -> bool:
        return term in spoken or (
            len(term) >= 5 and any(w.startswith(term[:5]) for w in spoken if len(w) >= 5)
        )

    return bool(terms) and all(said(t) for t in terms)


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return None


def _bilingual(value: Any, *, max_words: int | None = None) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    pt, en = _text(value.get("pt")), _text(value.get("en"))
    if not pt:
        return None
    if max_words is not None:
        pt = " ".join(pt.split()[:max_words])
        en = " ".join((en or pt).split()[:max_words])
    return {"pt": pt, "en": en or pt}


def _pick(
    index: Any, options_pt: list[str], options_en: list[str], used: set[int]
) -> dict[str, str] | None:
    if not isinstance(index, int) or not 0 <= index < len(options_pt) or index in used:
        return None
    used.add(index)
    en = options_en[index] if index < len(options_en) else options_pt[index]
    return {"pt": options_pt[index], "en": en}


def normalize_scene(
    raw: dict[str, Any] | None,
    *,
    fallback_text: str,
    position: int,
    block: BlockContext,
    used_tags: set[int],
    used_comments: set[int],
    notes: list[str],
    index: int,
) -> dict[str, Any]:
    """Uma cena valida, a partir do que o LLM mandou (ou de nada)."""
    raw = raw or {}
    if not raw:
        notes.append(f"cena {index}: o LLM nao descreveu; saiu como lugar")

    kind = raw.get("tipo") if raw.get("tipo") in TYPES else "lugar"
    if raw and kind != raw.get("tipo"):
        notes.append(f"cena {index}: tipo {raw.get('tipo')!r} desconhecido; virou lugar")

    key_text = _bilingual(raw.get("texto_chave"), max_words=4)
    if key_text and not (
        grounded(key_text["pt"], fallback_text)
        and (not block.narration_en or grounded(key_text["en"], block.narration_en))
    ):
        notes.append(
            f"cena {index}: texto-chave {key_text['pt']!r} / {key_text['en']!r} "
            "nao esta na narracao; saiu da tela"
        )
        key_text = None

    scene: dict[str, Any] = {
        "tipo": kind,
        "descricao_visual": _text(raw.get("descricao_visual")) or fallback_text,
        "camera": raw.get("camera") if raw.get("camera") in CAMERAS else CAMERAS[position % 4],
        "personagem": None,
        "referencia": None,
        "texto_chave": key_text,
        "tarja": _pick(raw.get("tarja"), block.tags_pt, block.tags_en, used_tags),
        "balao": _pick(raw.get("balao"), block.comments_pt, block.comments_en, used_comments),
        "mc": None,
        "cartao": None,
        "sfx": None,
    }

    character = raw.get("personagem")
    if kind == "atuada":
        scene["personagem"] = {
            "acao": _text((character or {}).get("acao")) or "listening attentively",
            "expressao": _text((character or {}).get("expressao")) or "attentive",
        }

    reference = raw.get("referencia")
    if kind in REFERENCE_TYPES and isinstance(reference, dict):
        search, target = _text(reference.get("busca")), _text(reference.get("alvo"))
        if search and target:
            scene["referencia"] = {"busca": search, "alvo": target}

    if kind == "cartao":
        card_raw = raw.get("cartao")
        card: dict[str, Any] = card_raw if isinstance(card_raw, dict) else {}
        pieces = []
        for piece in (card.get("pecas") or [])[:2]:
            if not isinstance(piece, dict):
                continue
            description = _text(piece.get("descricao"))
            label = _bilingual(piece.get("rotulo"), max_words=5)
            if description and label:
                pieces.append(
                    {
                        "descricao": description,
                        "rotulo": {k: v.upper() for k, v in label.items()},
                    }
                )
        if pieces:
            scene["cartao"] = {
                "pecas": pieces,
                "comparacao": bool(card.get("comparacao")) and len(pieces) == 2,
            }
        else:
            notes.append(f"cena {index}: cartao sem pecas validas; virou lugar")
            scene["tipo"] = "lugar"

    mc = raw.get("mc")
    wants_mc = scene["tipo"] == "cartao" or (scene["balao"] and scene["tipo"] != "atuada")
    if wants_mc or isinstance(mc, dict):
        pose = (mc or {}).get("pose") if isinstance(mc, dict) else None
        side = (mc or {}).get("lado") if isinstance(mc, dict) else None
        if wants_mc or scene["tipo"] != "atuada":
            scene["mc"] = {
                "pose": pose if pose in POSES else "apontando",
                "lado": side if side in SIDES else "direita",
            }

    sfx = raw.get("sfx")
    if isinstance(sfx, dict) and sfx.get("evento") in SFX_EVENTS and _text(sfx.get("tag")):
        scene["sfx"] = {"evento": sfx["evento"], "tag": _text(sfx.get("tag"))}
    return scene


def move_acted_balloons(scenes: list[dict[str, Any]], notes: list[str]) -> None:
    """Tira o balao das cenas atuadas de um bloco (amostra de 30/09).

    Na cena atuada o MC esta desenhado dentro da imagem, num lugar que o
    codigo nao conhece: o balao ficava num ponto fixo, em cima do rosto dele e
    do titulo do capitulo. Nos videos entregues o balao vinha com o MC
    recortado ao lado. O balao passa para a proxima cena do bloco sem balao,
    que ganha o MC recortado; sem nenhuma, sai com uma nota.
    """
    pending: tuple[int, dict[str, Any]] | None = None
    for scene in scenes:
        if scene["tipo"] == "atuada":
            if scene.get("balao"):
                if pending is not None:
                    notes.append(f"cena {pending[0]}: balao sem cena recortada depois; saiu")
                pending = (int(scene["indice"]), scene["balao"])
                scene["balao"] = None
            continue
        if pending is not None and not scene.get("balao"):
            origin, balloon = pending
            scene["balao"] = balloon
            scene["mc"] = scene.get("mc") or {"pose": "apontando", "lado": "direita"}
            notes.append(f"cena {origin}: balao passou para a cena {scene['indice']}, com o MC")
            pending = None
    if pending is not None:
        notes.append(f"cena {pending[0]}: balao sem cena recortada depois; saiu")
