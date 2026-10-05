"""JSON gravado por mais de um processo: painel, worker e a sessao do Claude.

Os pedidos de refacao, os comentarios do corte e as perguntas da sessao sao
escritos pelo painel (o revisor digitando), pelo worker (aplicando um pedido)
e pela CLI (a sessao respondendo). Sem trava, duas gravacoes simultaneas
perdem uma delas. `locked_update` serializa: le, aplica a mudanca e troca o
arquivo de uma vez, com um arquivo de trava ao lado.

Sem sidecar de proposito: estes arquivos sao estado de revisao, nao artefato
de etapa, e nunca decidem se uma etapa e pulada.
"""

from __future__ import annotations

import copy
import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

from .store import write_text_atomic

T = TypeVar("T")

#  Uma trava mais velha que isso e de um processo que morreu no meio.
STALE_LOCK_S = 30.0
LOCK_WAIT_S = 0.02
LOCK_TIMEOUT_S = 10.0


class LockTimeout(RuntimeError):
    """Outro processo segurou a trava por tempo demais."""


def read_json_or(path: Path, default: Any) -> Any:
    """O JSON do arquivo, ou `default` se ele nao existe ou esta ilegivel."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        #  Copia: quem altera o resultado nao pode mudar o padrao de quem chamou.
        return copy.deepcopy(default)


def _lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def _acquire(lock: Path) -> None:
    deadline = time.monotonic() + LOCK_TIMEOUT_S
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > STALE_LOCK_S:
                lock.unlink(missing_ok=True)
                continue
            if time.monotonic() > deadline:
                raise LockTimeout(f"trava presa em {lock}") from None
            time.sleep(LOCK_WAIT_S)


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Trava de um arquivo entre processos (`<arquivo>.lock` ao lado)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(path)
    _acquire(lock)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def locked_update(path: Path, change: Callable[[Any], T], default: Any) -> T:
    """Le o JSON, aplica `change` (que altera o objeto no lugar) e grava.

    Devolve o que `change` devolver. Se `change` levantar excecao, nada e
    gravado e a trava e liberada.
    """
    with file_lock(path):
        data = read_json_or(path, default)
        result = change(data)
        write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
        return result
