"""Registro de prompts versionados em arquivo.

CLAUDE.md: "prompts versionados em arquivo, nunca hardcoded". O nome do arquivo
carrega a versao (`dossie.v1.md`), e o sidecar de cada artefato guarda qual
versao gerou aquilo — e assim que se descobre, dois meses depois, por que um
roteiro saiu diferente.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..errors import ConfigError
from ..paths import get_paths

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_FILENAME = re.compile(r"^(?P<name>.+)\.v(?P<version>\d+)\.md$")


@dataclass(frozen=True, slots=True)
class Prompt:
    id: str
    version: int
    template: str
    metadata: dict[str, Any]
    path: Path

    @property
    def ref(self) -> str:
        """Identificador que vai para o sidecar: `roteiro/roteiro_ptbr@v1`."""
        return f"{self.id}@v{self.version}"

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.template.encode("utf-8")).hexdigest()[:12]

    @property
    def suggested_model(self) -> str:
        return str(self.metadata.get("modelo_sugerido", "principal"))

    @property
    def prefers_fast_model(self) -> bool:
        return self.suggested_model == "rapido"

    def render(self, **variables: Any) -> str:
        """Preenche as variaveis do template.

        Usa `str.format`, entao chave literal no texto precisa ser dobrada —
        os prompts que pedem JSON ja escrevem `{{` e `}}`.
        """
        try:
            return self.template.format(**variables)
        except KeyError as exc:
            declared = self.metadata.get("variaveis", [])
            raise ConfigError(
                f"prompt {self.ref}: variavel {exc} nao fornecida (declaradas: {declared})"
            ) from exc
        except IndexError as exc:
            raise ConfigError(
                f"prompt {self.ref}: chave literal sem escape. "
                "Use {{ e }} para chaves que devem aparecer no texto."
            ) from exc


class PromptRegistry:
    """Carrega prompts do disco e resolve a versao mais recente de cada id."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_paths().prompts
        self._cache: dict[str, Prompt] = {}

    def _scan(self) -> dict[str, list[Prompt]]:
        found: dict[str, list[Prompt]] = {}
        if not self.root.is_dir():
            raise ConfigError(f"diretorio de prompts ausente: {self.root}")
        for path in sorted(self.root.rglob("*.v*.md")):
            match = _FILENAME.match(path.name)
            if not match:
                continue
            prompt = self._parse(path, int(match.group("version")))
            found.setdefault(prompt.id, []).append(prompt)
        return found

    def _parse(self, path: Path, version_from_name: int) -> Prompt:
        raw = path.read_text(encoding="utf-8")
        match = _FRONTMATTER.match(raw)
        if not match:
            raise ConfigError(f"prompt sem frontmatter: {path}")
        meta = yaml.safe_load(match.group(1)) or {}
        if not isinstance(meta, dict):
            raise ConfigError(f"frontmatter invalido em {path}")

        prompt_id = str(meta.get("id") or path.relative_to(self.root).with_suffix("").as_posix())
        version = int(meta.get("version", version_from_name))
        if version != version_from_name:
            raise ConfigError(
                f"{path.name}: versao {version} no frontmatter difere do nome do arquivo "
                f"(v{version_from_name}). O nome do arquivo e a verdade."
            )
        return Prompt(
            id=prompt_id,
            version=version,
            template=match.group(2).strip(),
            metadata=meta,
            path=path,
        )

    def get(self, prompt_id: str, version: int | None = None) -> Prompt:
        """Prompt por id. Sem versao, devolve a mais recente."""
        key = f"{prompt_id}@{version or 'latest'}"
        if key in self._cache:
            return self._cache[key]

        candidates = self._scan().get(prompt_id)
        if not candidates:
            known = ", ".join(sorted(self._scan())) or "nenhum"
            raise ConfigError(f"prompt desconhecido: {prompt_id!r} (existentes: {known})")

        if version is None:
            chosen = max(candidates, key=lambda p: p.version)
        else:
            matches = [p for p in candidates if p.version == version]
            if not matches:
                available = sorted(p.version for p in candidates)
                raise ConfigError(f"prompt {prompt_id} nao tem v{version} (tem: {available})")
            chosen = matches[0]

        self._cache[key] = chosen
        return chosen

    def all_ids(self) -> list[str]:
        return sorted(self._scan())


@lru_cache(maxsize=1)
def get_prompts() -> PromptRegistry:
    return PromptRegistry()


def reset_prompts_cache() -> None:
    get_prompts.cache_clear()
