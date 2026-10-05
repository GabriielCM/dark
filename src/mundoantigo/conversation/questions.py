"""Perguntas do Claude ao revisor (`videos/<id>/conversa/perguntas.json`).

Escritas pela CLI (a sessao pergunta, marca como vista) e pelo painel (o
revisor responde): toda escrita passa por `locked_update`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactStore
from ..artifacts.jsonfile import locked_update, read_json_or

STAGE = "conversa"
FILENAME = "perguntas.json"


class QuestionError(ValueError):
    """Pergunta inexistente ou resposta invalida. A mensagem vai para quem chamou."""


def questions_file(store: ArtifactStore) -> Path:
    return store.path(STAGE, FILENAME)


def load(store: ArtifactStore) -> list[dict[str, Any]]:
    data = read_json_or(questions_file(store), {"perguntas": []})
    return list(data.get("perguntas", [])) if isinstance(data, dict) else []


def _update(store: ArtifactStore, change: Any) -> Any:
    def apply(data: dict[str, Any]) -> Any:
        return change(data.setdefault("perguntas", []))

    return locked_update(questions_file(store), apply, {"perguntas": []})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _find(questions: list[dict[str, Any]], question_id: int) -> dict[str, Any]:
    for entry in questions:
        if int(entry.get("id", 0)) == question_id:
            return entry
    raise QuestionError(f"pergunta {question_id} nao existe")


def ask(
    store: ArtifactStore,
    text: str,
    *,
    options: list[str] | None = None,
    free_text: bool = True,
    step: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    text = " ".join(text.split())
    if not text:
        raise QuestionError("a pergunta esta vazia")
    choices = [" ".join(o.split()) for o in (options or []) if o.strip()]
    if not choices and not free_text:
        raise QuestionError("sem opcoes, a pergunta precisa aceitar texto livre")

    def change(questions: list[dict[str, Any]]) -> dict[str, Any]:
        entry = {
            "id": max((int(q.get("id", 0)) for q in questions), default=0) + 1,
            "texto": text,
            "opcoes": choices,
            "texto_livre": free_text,
            "etapa": step,
            "alvo": target,
            "estado": "aberta",
            "criada_em": _now(),
            "rascunho": {"opcao": None, "texto": ""},
            "resposta": None,
            "vista_pelo_claude_em": None,
        }
        questions.append(entry)
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def save_draft(
    store: ArtifactStore, question_id: int, *, option: str | None, text: str | None
) -> dict[str, Any]:
    def change(questions: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _find(questions, question_id)
        if entry.get("estado") != "aberta":
            raise QuestionError("esta pergunta ja foi respondida")
        entry["rascunho"] = {"opcao": option or None, "texto": text or ""}
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def answer(
    store: ArtifactStore, question_id: int, *, option: str | None, text: str | None
) -> dict[str, Any]:
    option = (option or "").strip() or None
    text = (text or "").strip()

    def change(questions: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _find(questions, question_id)
        if entry.get("estado") != "aberta":
            raise QuestionError("esta pergunta ja foi respondida")
        if option and option not in entry.get("opcoes", []):
            raise QuestionError(f"opcao desconhecida: {option}")
        if not option and not text:
            raise QuestionError("escolha uma opcao ou escreva a resposta")
        if text and not entry.get("texto_livre", True) and not option:
            raise QuestionError("escolha uma das opcoes")
        entry["estado"] = "respondida"
        entry["resposta"] = {"opcao": option, "texto": text, "em": _now()}
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def cancel(store: ArtifactStore, question_id: int) -> dict[str, Any]:
    def change(questions: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _find(questions, question_id)
        entry["estado"] = "cancelada"
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def open_questions(store: ArtifactStore) -> list[dict[str, Any]]:
    return [q for q in load(store) if q.get("estado") == "aberta"]


def answered_unseen(store: ArtifactStore) -> list[dict[str, Any]]:
    return [
        q
        for q in load(store)
        if q.get("estado") == "respondida" and not q.get("vista_pelo_claude_em")
    ]


def mark_seen(store: ArtifactStore, question_ids: list[int]) -> int:
    wanted = set(question_ids)

    def change(questions: list[dict[str, Any]]) -> int:
        seen = 0
        for entry in questions:
            if int(entry.get("id", 0)) in wanted and not entry.get("vista_pelo_claude_em"):
                entry["vista_pelo_claude_em"] = _now()
                seen += 1
        return seen

    result: int = _update(store, change)
    return result
