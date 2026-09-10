"""Layout de diretorios do projeto.

Uma unica fonte de verdade para "onde fica o que". Nenhum modulo monta caminho
com f-string; todos passam por aqui, o que torna o layout testavel e permite
apontar tudo para um diretorio temporario nos testes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _repo_root() -> Path:
    """Raiz do repositorio: dois niveis acima de src/mundoantigo/."""
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Paths:
    """Diretorios do projeto. Todos absolutos."""

    root: Path
    config: Path
    prompts: Path
    data: Path
    videos: Path
    books: Path
    library: Path
    render_project: Path

    @classmethod
    def from_env(cls, root: Path | None = None) -> Paths:
        base = (root or Path(os.environ.get("MA_ROOT", ""))) or _repo_root()
        base = Path(base).resolve()

        def env_dir(var: str, default: Path) -> Path:
            raw = os.environ.get(var)
            return Path(raw).resolve() if raw else default

        return cls(
            root=base,
            config=env_dir("MA_CONFIG_DIR", base / "config"),
            prompts=env_dir("MA_PROMPTS_DIR", base / "prompts"),
            data=env_dir("MA_DATA_DIR", base / "data"),
            videos=env_dir("MA_VIDEOS_DIR", base / "videos"),
            books=env_dir("MA_BOOKS_DIR", base / "livros"),
            library=env_dir("MA_LIBRARY_DIR", base / "biblioteca"),
            render_project=env_dir("MA_RENDER_DIR", base / "render"),
        )

    # --- derivados ---

    @property
    def db_file(self) -> Path:
        return self.data / "mundoantigo.sqlite3"

    @property
    def logs(self) -> Path:
        return self.data / "logs"

    @property
    def character_library(self) -> Path:
        return self.library / "personagem"

    @property
    def music_library(self) -> Path:
        return self.library / "trilhas"

    @property
    def sfx_library(self) -> Path:
        return self.library / "sfx"

    def video_dir(self, video_id: str) -> Path:
        return self.videos / video_id

    def book_dir(self, book_id: str) -> Path:
        return self.books / book_id

    def ensure(self) -> None:
        """Cria os diretorios que o pipeline escreve. Idempotente."""
        for d in (self.data, self.videos, self.books, self.logs, self.library):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_paths() -> Paths:
    return Paths.from_env()


def reset_paths_cache() -> None:
    """Usado por testes que trocam MA_* no ambiente."""
    get_paths.cache_clear()
