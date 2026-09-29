"""Backup local do que nao vai para o git (ADR 0009).

O codigo vive no GitHub. O resto so existe nesta maquina, e ja se perdeu uma
vez (09/2026): banco, videos, bibliotecas, livros, o .env e o que mais estiver
em `backup.extras` (pesos dos modelos, entregas antigas). Tudo isso e
espelhado num disco fisico separado.

- O banco e copiado pela API de backup do SQLite: a copia sai consistente
  mesmo com o worker escrevendo.
- As pastas sao espelhadas (robocopy /MIR no Windows): so o que mudou e
  copiado, e o que foi apagado na origem some do destino.
- Um manifesto registra quando, o que e quanto; o historico acumula.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

#  Padroes que nunca vao para o backup de pastas: o banco vai pela API do
#  SQLite, e copiar o arquivo cru com o worker escrevendo daria uma copia
#  corrompida.
_SKIP_PATTERNS = ("*.sqlite3", "*.sqlite3-journal", "*.sqlite3-wal", "*.sqlite3-shm")


@dataclass(frozen=True, slots=True)
class MirrorResult:
    name: str
    source: str
    destination: str
    files: int
    bytes: int
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BackupReport:
    started_at: str
    finished_at: str
    destination: str
    items: tuple[MirrorResult, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)

    @property
    def total_bytes(self) -> int:
        return sum(item.bytes for item in self.items)

    def to_dict(self) -> dict[str, object]:
        return {
            "inicio": self.started_at,
            "fim": self.finished_at,
            "destino": self.destination,
            "ok": self.ok,
            "bytes": self.total_bytes,
            "itens": [asdict(item) for item in self.items],
        }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _count(path: Path) -> tuple[int, int]:
    if path.is_file():
        return 1, path.stat().st_size
    files = size = 0
    for p in path.rglob("*"):
        if p.is_file():
            files += 1
            size += p.stat().st_size
    return files, size


def backup_database(db_file: Path, destination: Path) -> MirrorResult:
    """Copia consistente do SQLite, mesmo com o banco em uso."""
    if not db_file.exists():
        return MirrorResult("banco", str(db_file), str(destination), 0, 0, True, "banco ausente")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + ".tmp")
    source = sqlite3.connect(f"{db_file.resolve().as_uri()}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(tmp)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    #  Troca atomica: um backup interrompido nunca deixa o anterior pela metade.
    os.replace(tmp, destination)
    return MirrorResult(
        "banco", str(db_file), str(destination), 1, destination.stat().st_size, True
    )


def _skip(name: str) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(name, pattern) for pattern in _SKIP_PATTERNS)


def _python_mirror(source: Path, destination: Path) -> None:
    """Espelho sem robocopy: copia o que mudou e apaga o que sumiu na origem."""
    destination.mkdir(parents=True, exist_ok=True)
    wanted: set[Path] = set()
    for src in source.rglob("*"):
        rel = src.relative_to(source)
        if any(_skip(part) for part in rel.parts):
            continue
        dst = destination / rel
        wanted.add(dst)
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            continue
        stat = src.stat()
        if dst.exists():
            dst_stat = dst.stat()
            if dst_stat.st_size == stat.st_size and int(dst_stat.st_mtime) == int(stat.st_mtime):
                continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    #  Do mais fundo para o mais raso, para esvaziar pastas antes de remove-las.
    for dst in sorted(destination.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if dst in wanted:
            continue
        if dst.is_dir():
            shutil.rmtree(dst, ignore_errors=True)
        else:
            dst.unlink(missing_ok=True)


def _robocopy(source: Path, destination: Path) -> tuple[bool, str]:
    command = [
        "robocopy",
        str(source),
        str(destination),
        "/MIR",
        "/R:2",
        "/W:5",
        "/XJ",
        "/MT:8",
        "/NP",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/XF",
        *_SKIP_PATTERNS,
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    #  robocopy: codigos 0 a 7 sao sucesso (combinacoes de "copiou", "havia
    #  extras", "nada a fazer"); 8 ou mais e falha.
    if done.returncode >= 8:
        return False, f"robocopy {done.returncode}: {(done.stdout + done.stderr)[-500:]}"
    return True, ""


def mirror(
    name: str, source: Path, destination: Path, *, use_robocopy: bool | None = None
) -> MirrorResult:
    """Espelha um arquivo ou pasta em `destination`."""
    if not source.exists():
        return MirrorResult(name, str(source), str(destination), 0, 0, True, "origem ausente")
    try:
        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        else:
            if use_robocopy is None:
                use_robocopy = sys.platform == "win32" and shutil.which("robocopy") is not None
            if use_robocopy:
                ok, detail = _robocopy(source, destination)
                if not ok:
                    return MirrorResult(name, str(source), str(destination), 0, 0, False, detail)
            else:
                _python_mirror(source, destination)
    except OSError as exc:
        return MirrorResult(name, str(source), str(destination), 0, 0, False, str(exc))
    files, size = _count(destination)
    return MirrorResult(name, str(source), str(destination), files, size, True)


def _extra_name(path: Path) -> str:
    """Nome estavel para uma origem extra (ex.: C:/dev/modelos -> modelos)."""
    return path.name.replace(" ", "_") or "raiz"


def run_backup(
    *,
    root: Path,
    db_file: Path,
    folders: dict[str, Path],
    extras: list[Path],
    destination: Path,
    use_robocopy: bool | None = None,
) -> BackupReport:
    """Executa o backup completo e grava o manifesto no destino."""
    started = _now()
    destination.mkdir(parents=True, exist_ok=True)
    items: list[MirrorResult] = [backup_database(db_file, destination / "banco" / db_file.name)]
    for name, folder in folders.items():
        log.info("espelhando %s", folder)
        items.append(mirror(name, folder, destination / name, use_robocopy=use_robocopy))
    env_file = root / ".env"
    if env_file.exists():
        items.append(mirror(".env", env_file, destination / "config-local" / ".env"))
    for extra in extras:
        path = extra if extra.is_absolute() else root / extra
        target = destination / "extras" / _extra_name(path)
        log.info("espelhando %s", path)
        items.append(mirror(str(extra), path, target, use_robocopy=use_robocopy))

    report = BackupReport(started, _now(), str(destination), tuple(items))
    payload = report.to_dict()
    (destination / "manifesto.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (destination / "historico.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return report
