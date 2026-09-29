"""Artefatos por video e seus sidecars de metadados.

CLAUDE.md, rastreabilidade: "todo artefato gerado guarda um sidecar de
metadados com modelo, provedor, versao do prompt, custo, seed (quando houver)
e data".

O sidecar tambem e o que torna a idempotencia confiavel (ADR 0002): o runner
so considera uma etapa concluida se o artefato existe *e* o sidecar valida.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..paths import get_paths

SIDECAR_SUFFIX = ".meta.json"

#  Subdiretorios de videos/<video_id>/. Um por etapa que produz arquivo.
STAGE_DIRS = (
    "pauta",
    "pesquisa",
    "roteiro",
    "adaptacao",
    "cenas",
    "referencias",
    "assets",
    "pre_checagem",
    "revisao_imagens",
    "narracao",
    "trilha",
    "metadados",
    "montagem",
    "revisao",
    "entrega",
)


@dataclass(slots=True)
class Sidecar:
    """Metadados de um artefato."""

    artifact: str
    step: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    provider: str | None = None
    model: str | None = None
    prompt_ref: str | None = None
    prompt_checksum: str | None = None
    seed: int | None = None
    cost_usd: float | None = None
    #  Hash das entradas: sinaliza no painel quando o artefato ficou defasado.
    input_hash: str | None = None
    sha256: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> Sidecar:
        data = json.loads(raw)
        known = set(cls.__slots__)
        extra = data.pop("extra", {}) or {}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean, extra=extra)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_inputs(*parts: Any) -> str:
    """Hash estavel de um conjunto de entradas, para detectar defasagem."""
    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, Path):
            digest.update(sha256_file(part).encode() if part.exists() else b"<ausente>")
        elif isinstance(part, bytes):
            digest.update(part)
        else:
            digest.update(
                json.dumps(part, sort_keys=True, ensure_ascii=False, default=str).encode()
            )
        digest.update(b"\x1f")
    return digest.hexdigest()[:16]


class ArtifactStore:
    """Leitura e escrita dos artefatos de uma producao."""

    def __init__(self, video_id: str, root: Path | None = None) -> None:
        self.video_id = video_id
        self.root = (root or get_paths().videos) / video_id

    # -- caminhos ----------------------------------------------------------

    def stage(self, name: str) -> Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path(self, stage: str, filename: str) -> Path:
        return self.root / stage / filename

    def sidecar_path(self, artifact: Path) -> Path:
        return artifact.with_name(artifact.name + SIDECAR_SUFFIX)

    def ensure(self) -> None:
        for name in STAGE_DIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    # -- escrita -----------------------------------------------------------

    def write_json(self, stage: str, filename: str, payload: Any, **meta: Any) -> Path:
        target = self.stage(stage) / filename
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        #  A etapa que gerou nem sempre e o diretorio onde o arquivo mora: o
        #  gate escreve em `roteiro/`, a adaptacao EN em `adaptacao/`.
        self.write_sidecar(target, step=meta.pop("step", stage), **meta)
        return target

    def write_text(self, stage: str, filename: str, text: str, **meta: Any) -> Path:
        target = self.stage(stage) / filename
        target.write_text(text, encoding="utf-8")
        self.write_sidecar(target, step=meta.pop("step", stage), **meta)
        return target

    def write_sidecar(self, artifact: Path, *, step: str, **meta: Any) -> Path:
        sidecar = Sidecar(
            artifact=artifact.name,
            step=step,
            sha256=sha256_file(artifact) if artifact.exists() else None,
            **meta,
        )
        target = self.sidecar_path(artifact)
        target.write_text(sidecar.to_json(), encoding="utf-8")
        return target

    # -- leitura -----------------------------------------------------------

    def read_json(self, stage: str, filename: str) -> Any:
        return json.loads(self.path(stage, filename).read_text(encoding="utf-8"))

    def read_text(self, stage: str, filename: str) -> str:
        return self.path(stage, filename).read_text(encoding="utf-8")

    def read_sidecar(self, artifact: Path) -> Sidecar | None:
        target = self.sidecar_path(artifact)
        if not target.exists():
            return None
        try:
            return Sidecar.from_json(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            return None

    # -- integridade -------------------------------------------------------

    def is_complete(self, artifact: Path, *, verify_hash: bool = False) -> bool:
        """Artefato existe, nao esta vazio e tem sidecar valido.

        E este predicado que decide se uma etapa e pulada sem gastar (ADR 0002),
        entao ele e deliberadamente severo: na duvida, refaz.
        """
        if not artifact.exists() or artifact.stat().st_size == 0:
            return False
        sidecar = self.read_sidecar(artifact)
        if sidecar is None:
            return False
        return not (verify_hash and sidecar.sha256 and sidecar.sha256 != sha256_file(artifact))

    def all_complete(self, artifacts: list[Path], *, verify_hash: bool = False) -> bool:
        return bool(artifacts) and all(
            self.is_complete(a, verify_hash=verify_hash) for a in artifacts
        )

    def is_stale(self, artifact: Path, current_input_hash: str) -> bool:
        """Artefato existe mas foi gerado com entradas diferentes das de agora.

        Nao refaz nada sozinho — so sinaliza no painel. Refazer trabalho pago
        sem aviso e o oposto do que o orcamento pede (ADR 0002).
        """
        sidecar = self.read_sidecar(artifact)
        if sidecar is None or sidecar.input_hash is None:
            return False
        return sidecar.input_hash != current_input_hash

    def delete(self, artifact: Path) -> bool:
        """Apaga um artefato e o sidecar dele. Devolve se havia algo a apagar."""
        existed = artifact.exists()
        artifact.unlink(missing_ok=True)
        self.sidecar_path(artifact).unlink(missing_ok=True)
        return existed

    def clear_stage(self, stage: str) -> None:
        """Apaga uma etapa para forcar refazer. E a interface de 'refazer'."""
        import shutil

        target = self.root / stage
        if target.exists():
            shutil.rmtree(target)
