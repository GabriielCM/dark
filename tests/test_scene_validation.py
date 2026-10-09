"""Validacao do que o LLM devolve para cada cena (fase B3)."""

from __future__ import annotations

from typing import Any

from mundoantigo.scenes.validation import (
    BlockContext,
    grounded,
    move_acted_balloons,
    normalize_scene,
    vary_static_cameras,
)

BLOCO = BlockContext(
    comments_pt=["Isso pesa mais do que parece.", "Todo mundo sabe seu papel."],
    comments_en=["Heavier than it looks.", "Everyone knows their job."],
    tags_pt=["ACAMPAMENTO ROMANO, SÉCULO I"],
    tags_en=["ROMAN CAMP, 1ST CENTURY"],
)


def _normalize(raw: dict[str, Any] | None, **kw: Any) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    scene = normalize_scene(
        raw,
        fallback_text=kw.get("narration", "texto da narracao"),
        position=0,
        block=kw.get("block", BLOCO),
        used_tags=kw.get("used_tags", set()),
        used_comments=kw.get("used_comments", set()),
        notes=notes,
        index=1,
    )
    return scene, notes


def test_a_complete_acted_scene_passes_through() -> None:
    scene, notes = _normalize(
        {
            "tipo": "atuada",
            "descricao_visual": "the host rolls a leather tent at dawn",
            "personagem": {"acao": "rolling a tent", "expressao": "focused"},
            "camera": "zoom_in",
            "tarja": 0,
            "balao": 1,
        }
    )
    assert notes == []
    assert scene["personagem"]["acao"] == "rolling a tent"
    assert scene["tarja"] == {"pt": "ACAMPAMENTO ROMANO, SÉCULO I", "en": "ROMAN CAMP, 1ST CENTURY"}
    assert scene["balao"]["en"] == "Everyone knows their job."
    assert scene["mc"] is None, "na cena atuada o protagonista ja esta na imagem"


def test_unknown_type_and_missing_fields_get_safe_defaults() -> None:
    scene, notes = _normalize({"tipo": "cinematico", "camera": "voar"})
    assert scene["tipo"] == "lugar"
    assert scene["camera"] == "zoom_in"
    assert scene["descricao_visual"] == "texto da narracao"
    assert notes


def test_references_only_on_real_places_and_objects() -> None:
    reference = {"busca": "Pantheon Rome interior", "alvo": "coffered dome"}
    place, _ = _normalize({"tipo": "lugar", "referencia": reference})
    metaphor, _ = _normalize({"tipo": "metafora", "referencia": reference})
    assert place["referencia"] == reference
    assert metaphor["referencia"] is None


def test_each_tag_and_comment_is_used_once() -> None:
    used_tags: set[int] = set()
    used_comments: set[int] = set()
    first, _ = _normalize(
        {"tipo": "lugar", "tarja": 0, "balao": 0},
        used_tags=used_tags,
        used_comments=used_comments,
    )
    second, _ = _normalize(
        {"tipo": "lugar", "tarja": 0, "balao": 0},
        used_tags=used_tags,
        used_comments=used_comments,
    )
    assert first["tarja"] and first["balao"]
    assert second["tarja"] is None and second["balao"] is None


def test_a_balloon_outside_an_acted_scene_brings_the_cutout_host() -> None:
    scene, _ = _normalize({"tipo": "lugar", "balao": 0})
    assert scene["mc"] == {"pose": "apontando", "lado": "direita"}


def test_cards_need_pieces_and_always_show_the_host() -> None:
    card, _ = _normalize(
        {
            "tipo": "cartao",
            "cartao": {
                "pecas": [
                    {"descricao": "a Roman pickaxe", "rotulo": {"pt": "dolabra", "en": "dolabra"}},
                    {"descricao": "a modern pickaxe", "rotulo": {"pt": "hoje", "en": "today"}},
                ],
                "comparacao": True,
            },
            "mc": {"pose": "joinha", "lado": "esquerda"},
        }
    )
    assert card["cartao"]["comparacao"] is True
    assert card["cartao"]["pecas"][0]["rotulo"] == {"pt": "DOLABRA", "en": "DOLABRA"}
    assert card["mc"] == {"pose": "joinha", "lado": "esquerda"}

    empty, notes = _normalize({"tipo": "cartao", "cartao": {"pecas": []}})
    assert empty["tipo"] == "lugar"
    assert notes


def test_key_text_is_trimmed_to_four_words() -> None:
    scene, _ = _normalize(
        {"tipo": "lugar", "texto_chave": {"pt": "quase dezesseis mil e oitocentos homens"}},
        narration="Eram quase dezesseis mil e oitocentos homens em marcha.",
    )
    assert scene["texto_chave"]["pt"] == "quase dezesseis mil e"
    assert scene["texto_chave"]["en"] == scene["texto_chave"]["pt"]


def test_key_text_must_come_from_the_narration() -> None:
    #  Amostra de 29/09: "SUB PELLE" na tela para "viver sob as peles".
    block = BlockContext(narration_en="The Romans had a phrase for it: living under the hides.")
    narration = "Os romanos tinham uma expressão para o soldado em campanha: viver sob as peles."
    wrong, notes = _normalize(
        {"tipo": "peca", "texto_chave": {"pt": "SUB PELLE", "en": "UNDER THE SKIN"}},
        narration=narration,
        block=block,
    )
    assert wrong["texto_chave"] is None
    assert any("saiu da tela" in n for n in notes)

    right, _ = _normalize(
        {"tipo": "peca", "texto_chave": {"pt": "SOB AS PELES", "en": "UNDER THE HIDES"}},
        narration=narration,
        block=block,
    )
    assert right["texto_chave"] == {"pt": "SOB AS PELES", "en": "UNDER THE HIDES"}


def test_grounding_accepts_plurals_and_digits() -> None:
    assert grounded("QUATRO VIGÍLIA", "cortada em quatro vigílias de três horas")
    assert grounded("752 HOMENS", "No papel, ela tem 752 homens.")
    assert not grounded("800 HOMENS", "No papel, ela tem 752 homens.")
    assert not grounded("", "qualquer coisa")


def _scene(index: int, kind: str, balloon: dict[str, str] | None = None) -> dict[str, Any]:
    return {"indice": index, "tipo": kind, "balao": balloon, "mc": None}


def test_a_balloon_leaves_the_acted_scene_for_the_next_cutout() -> None:
    """Na atuada o balao cobria o rosto do MC e o titulo (amostra de 30/09)."""
    joke = {"pt": "Ronco garantido.", "en": "Snoring guaranteed."}
    scenes = [_scene(1, "atuada", joke), _scene(2, "atuada"), _scene(3, "plano_medio")]
    notes: list[str] = []
    move_acted_balloons(scenes, notes)
    assert scenes[0]["balao"] is None
    assert scenes[2]["balao"] == joke
    assert scenes[2]["mc"] == {"pose": "apontando", "lado": "direita"}
    assert "cena 3" in notes[0]


def test_a_balloon_with_no_scene_after_it_is_dropped() -> None:
    scenes = [
        _scene(1, "lugar", {"pt": "a", "en": "a"}),
        _scene(2, "atuada", {"pt": "b", "en": "b"}),
    ]
    notes: list[str] = []
    move_acted_balloons(scenes, notes)
    assert scenes[0]["balao"] == {"pt": "a", "en": "a"}
    assert scenes[1]["balao"] is None
    assert notes and "saiu" in notes[0]


def test_a_balloon_leaves_a_scene_too_short_to_read_it() -> None:
    """Com cenas de ~3 s (ADR 0012), o balao numa cena de 2 s some antes de ser lido."""
    joke = {"pt": "Ninguem reclamou.", "en": "Nobody complained."}
    short = {**_scene(1, "plano_medio", joke), "duracao_s": 2.0}
    short["mc"] = {"pose": "joinha", "lado": "esquerda"}
    longer = {**_scene(2, "lugar"), "duracao_s": 3.2}
    notes: list[str] = []
    move_acted_balloons([short, longer], notes, min_seconds=2.5)
    assert short["balao"] is None and short["mc"] is None
    assert longer["balao"] == joke and longer["mc"]


def test_no_more_than_two_static_cameras_in_a_row() -> None:
    scenes = [{"camera": "estatica"} for _ in range(7)] + [{"camera": "pan_left"}]
    vary_static_cameras(scenes)
    cameras = [s["camera"] for s in scenes]
    assert cameras == [
        "estatica",
        "estatica",
        "zoom_in",
        "estatica",
        "estatica",
        "zoom_out",
        "estatica",
        "pan_left",
    ]
