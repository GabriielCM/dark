"""Persistencia: SQLite via SQLAlchemy 2 (ADR 0001)."""

from .models import (
    Base,
    Book,
    BookChunk,
    CostEntry,
    FactItem,
    StepRecord,
    Video,
)
from .session import get_engine, init_db, session_scope

__all__ = [
    "Base",
    "Book",
    "BookChunk",
    "CostEntry",
    "FactItem",
    "StepRecord",
    "Video",
    "get_engine",
    "init_db",
    "session_scope",
]
