"""Engine e sessao do SQLite.

WAL ligado: o worker escreve enquanto o painel le, sem travar. E o motivo de
SQLite bastar para o cenario de hoje (ADR 0001).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..paths import get_paths
from .models import Base


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        #  Espera ate 10 s por um lock em vez de estourar na cara do usuario.
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()


@lru_cache(maxsize=4)
def get_engine(db_path: Path | None = None) -> Engine:
    path = db_path or get_paths().db_file
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", future=True)
    _configure_sqlite(engine)
    return engine


def get_sessionmaker(db_path: Path | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(db_path), expire_on_commit=False, future=True)


def init_db(db_path: Path | None = None) -> Engine:
    """Cria as tabelas que faltam. Idempotente."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(db_path: Path | None = None) -> Iterator[Session]:
    """Sessao transacional: commit no fim, rollback em excecao."""
    factory = get_sessionmaker(db_path)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_cache() -> None:
    """Usado por testes que trocam o caminho do banco."""
    get_engine.cache_clear()
