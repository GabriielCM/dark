"""A caixa de entrada da sessao do Claude, e o sinal de que ela esta de vigia.

`mundoantigo aguardar <id>` roda em segundo plano na sessao e acorda quando
o revisor responde uma pergunta, envia pedidos de refacao com motivo ou
comentarios do corte final. Enquanto espera, grava um sinal de presenca: a
pagina mostra "o Claude esta acompanhando" ou "chame o Claude no chat".
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactStore
from ..paths import get_paths
from ..review import images as review
from . import questions

#  Sem sinal ha mais que isso, a sessao nao esta acompanhando.
PRESENCE_FRESH = timedelta(seconds=90)
HEARTBEAT_EVERY_S = 30.0


def presence_file(video_id: str) -> Path:
    return get_paths().data / "run" / f"claude.{video_id}.json"


def heartbeat(video_id: str) -> None:
    path = presence_file(video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    data: dict[str, Any] = {"pid": os.getpid(), "atualizado_em": now}
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
        data["desde"] = previous.get("desde", now) if previous.get("pid") == os.getpid() else now
    except (OSError, ValueError):
        data["desde"] = now
    path.write_text(json.dumps(data), encoding="utf-8")


def presence(video_id: str) -> dict[str, Any]:
    """acompanhando (vigia ativo), visto (ja passou por aqui) ou ausente."""
    try:
        data = json.loads(presence_file(video_id).read_text(encoding="utf-8"))
        seen = datetime.fromisoformat(data["atualizado_em"])
    except (OSError, ValueError, KeyError):
        return {"estado": "ausente", "visto_em": None}
    fresh = datetime.now(UTC) - seen < PRESENCE_FRESH
    return {"estado": "acompanhando" if fresh else "visto", "visto_em": seen.isoformat()}


def inbox(store: ArtifactStore) -> dict[str, list[dict[str, Any]]]:
    """O que chegou para a sessao e ela ainda nao viu."""
    from ..review import final_cut

    return {
        "respostas": questions.answered_unseen(store),
        "pedidos_imagens": [
            r for r in review.claude_pending(store) if not r.get("visto_pelo_claude_em")
        ],
        "comentarios_corte": final_cut.unseen_comments(store),
    }


def is_empty(box: dict[str, list[dict[str, Any]]]) -> bool:
    return not any(box.values())


def mark_seen(store: ArtifactStore, box: dict[str, list[dict[str, Any]]]) -> None:
    from ..review import final_cut

    if box.get("respostas"):
        questions.mark_seen(store, [int(q["id"]) for q in box["respostas"]])
    if box.get("pedidos_imagens"):
        review.mark_seen(store)
    if box.get("comentarios_corte"):
        final_cut.mark_seen(store)


def wait(
    store: ArtifactStore,
    *,
    timeout_s: float,
    poll_s: float = 3.0,
    check: Callable[[ArtifactStore], dict[str, list[dict[str, Any]]]] = inbox,
) -> dict[str, list[dict[str, Any]]]:
    """Espera ate chegar algo (ou o tempo acabar), mantendo o sinal de presenca."""
    deadline = time.monotonic() + timeout_s
    last_beat = 0.0
    while True:
        now = time.monotonic()
        if now - last_beat >= HEARTBEAT_EVERY_S:
            heartbeat(store.video_id)
            last_beat = now
        box = check(store)
        if not is_empty(box) or now >= deadline:
            heartbeat(store.video_id)
            return box
        time.sleep(poll_s)
