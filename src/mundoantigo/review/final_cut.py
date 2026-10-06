"""Comentarios do corte final (a segunda revisao humana), por momento do video.

O revisor assiste na pagina e clica "Comentar neste momento": o tempo do
player vira a cena daquele instante (pelos tempos de `montagem/props.<idioma>.json`,
que sao diferentes em PT e EN), e ele escreve o que nao gostou. Enviados, os
comentarios vao para a sessao do Claude, que decide o que refazer (uma
imagem, o roteiro, a voz, os metadados) e responde cada um.

Os cortes do TikTok (ADR 0010) aparecem na mesma pagina. Um comentario num
corte leva o numero dele (`corte`), e o tempo e o do corte, com a cena tirada
de `cortes/props.<idioma>.<n>.json`.

Arquivo: `revisao/comentarios.json`, escrito pelo painel e pela CLI com
`locked_update`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactStore
from ..artifacts.jsonfile import locked_update, read_json_or

STAGE = "revisao"
FILENAME = "comentarios.json"
LANGUAGES = ("pt-br", "en")


class CommentError(ValueError):
    """Comentario invalido. A mensagem vai para o revisor."""


def comments_file(store: ArtifactStore) -> Path:
    return store.path(STAGE, FILENAME)


def load(store: ArtifactStore) -> list[dict[str, Any]]:
    data = read_json_or(comments_file(store), {"comentarios": []})
    return list(data.get("comentarios", [])) if isinstance(data, dict) else []


def _update(store: ArtifactStore, change: Any) -> Any:
    def apply(data: dict[str, Any]) -> Any:
        return change(data.setdefault("comentarios", []))

    return locked_update(comments_file(store), apply, {"comentarios": []})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _video_and_props(language: str, clip: int | None) -> tuple[tuple[str, str], tuple[str, str]]:
    """Onde estao o mp4 e as props do video inteiro, ou de um corte do TikTok."""
    if clip is None:
        return ("montagem", f"video.{language}.mp4"), ("montagem", f"props.{language}.json")
    return ("cortes", f"corte-{clip}.{language}.mp4"), ("cortes", f"props.{language}.{clip}.json")


def cut_version(store: ArtifactStore, language: str, clip: int | None = None) -> str | None:
    """Qual render o comentario viu (o corte muda a cada refacao)."""
    video, _ = _video_and_props(language, clip)
    sidecar = store.read_sidecar(store.path(*video))
    return sidecar.created_at if sidecar else None


def scene_at(props: dict[str, Any], seconds: float) -> dict[str, Any] | None:
    """A cena na tela naquele instante: a ultima que comecou antes dele."""
    scenes = sorted(props.get("scenes", []), key=lambda s: float(s.get("start", 0)))
    if not scenes:
        return None
    current = scenes[0]
    for scene in scenes:
        if float(scene.get("start", 0)) <= seconds:
            current = scene
        else:
            break
    return current


def _scene_context(
    store: ArtifactStore, language: str, seconds: float, clip: int | None = None
) -> dict[str, Any]:
    _, props_path = _video_and_props(language, clip)
    props = read_json_or(store.path(*props_path), {})
    scene = scene_at(props, seconds) if isinstance(props, dict) else None
    if scene is None:
        return {"cena": None, "chave": None, "imagem": None, "narracao": None}
    index = int(scene.get("index", 0))
    storyboard = read_json_or(store.path("cenas", "storyboard.json"), {})
    narration = next(
        (
            s.get("narracao")
            for s in storyboard.get("cenas", [])
            if int(s.get("indice", -1)) == index
        ),
        None,
    )
    return {
        "cena": index,
        "chave": f"cena-{index:03d}",
        #  Cartao: o fundo e a cena anterior; a miniatura mostra o que estava atras.
        "imagem": scene.get("background"),
        "narracao": narration,
    }


def add(
    store: ArtifactStore, language: str, seconds: float, clip: int | None = None
) -> dict[str, Any]:
    """Novo comentario no instante do player, ja com a cena daquele momento.

    `clip` e o numero do corte do TikTok; sem ele, o comentario e no video
    inteiro.
    """
    if language not in LANGUAGES:
        raise CommentError(f"idioma desconhecido: {language}")
    if clip is not None and not store.path(*_video_and_props(language, clip)[0]).exists():
        raise CommentError(f"o corte {clip} nao existe")
    context = _scene_context(store, language, max(0.0, float(seconds)), clip)
    version = cut_version(store, language, clip)

    def change(comments: list[dict[str, Any]]) -> dict[str, Any]:
        entry = {
            "id": max((int(c.get("id", 0)) for c in comments), default=0) + 1,
            "versao_corte": version,
            "idioma": language,
            "corte": clip,
            "tempo_s": round(max(0.0, float(seconds)), 1),
            **context,
            "texto": "",
            "link": None,
            "estado": "rascunho",
            "criado_em": _now(),
            "atualizado_em": _now(),
            "enviado_em": None,
            "resolvido_em": None,
            "resposta": None,
            "visto_pelo_claude_em": None,
        }
        comments.append(entry)
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def _find(comments: list[dict[str, Any]], comment_id: int) -> dict[str, Any]:
    for entry in comments:
        if int(entry.get("id", 0)) == comment_id:
            return entry
    raise CommentError(f"comentario {comment_id} nao existe")


def update(
    store: ArtifactStore, comment_id: int, *, text: str | None, link: str | None
) -> dict[str, Any]:
    def change(comments: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _find(comments, comment_id)
        if entry.get("estado") != "rascunho":
            raise CommentError("este comentario ja foi enviado")
        entry["texto"] = (text or "").strip()
        entry["link"] = (link or "").strip() or None
        entry["atualizado_em"] = _now()
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def delete(store: ArtifactStore, comment_id: int) -> None:
    def change(comments: list[dict[str, Any]]) -> None:
        entry = _find(comments, comment_id)
        if entry.get("estado") != "rascunho":
            raise CommentError("comentario enviado nao pode ser apagado")
        comments.remove(entry)

    _update(store, change)


def submit(store: ArtifactStore) -> int:
    """Envia os rascunhos com texto para a sessao. Rascunho vazio e descartado."""

    def change(comments: list[dict[str, Any]]) -> int:
        sent = 0
        for entry in list(comments):
            if entry.get("estado") != "rascunho":
                continue
            if not entry.get("texto") and not entry.get("link"):
                comments.remove(entry)
                continue
            entry["estado"] = "pendente"
            entry["enviado_em"] = _now()
            sent += 1
        if not sent:
            raise CommentError("escreva o que mudar em pelo menos um comentario")
        return sent

    result: int = _update(store, change)
    return result


def resolve(
    store: ArtifactStore, comment_id: int, reply: str, *, discard: bool = False
) -> dict[str, Any]:
    """A sessao tratou o comentario (ou decidiu nao mexer) e responde ao revisor."""

    def change(comments: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _find(comments, comment_id)
        entry["estado"] = "descartado" if discard else "resolvido"
        entry["resposta"] = " ".join(reply.split()) or None
        entry["resolvido_em"] = _now()
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def pending(store: ArtifactStore) -> list[dict[str, Any]]:
    return [c for c in load(store) if c.get("estado") == "pendente"]


def drafts(store: ArtifactStore) -> list[dict[str, Any]]:
    return [c for c in load(store) if c.get("estado") == "rascunho"]


def unseen_comments(store: ArtifactStore) -> list[dict[str, Any]]:
    return [c for c in pending(store) if not c.get("visto_pelo_claude_em")]


def mark_seen(store: ArtifactStore) -> int:
    def change(comments: list[dict[str, Any]]) -> int:
        seen = 0
        for entry in comments:
            if entry.get("estado") == "pendente" and not entry.get("visto_pelo_claude_em"):
                entry["visto_pelo_claude_em"] = _now()
                seen += 1
        return seen

    result: int = _update(store, change)
    return result


def can_approve(store: ArtifactStore) -> tuple[bool, str]:
    """O corte pode ser aprovado? Nao com comentario aberto (rascunho ou enviado)."""
    if drafts(store):
        return False, "ha comentarios ainda nao enviados (envie ou apague)"
    if pending(store):
        return False, f"{len(pending(store))} comentario(s) esperando o Claude"
    return True, ""
