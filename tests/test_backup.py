"""Backup local (ADR 0009): banco consistente, espelho de pastas, manifesto."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from mundoantigo.ops import backup_database, mirror, run_backup


def _db_with_rows(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table t (n integer)")
    con.executemany("insert into t values (?)", [(i,) for i in range(rows)])
    con.commit()
    con.close()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestDatabase:
    def test_copies_a_database_in_use(self, tmp_path: Path) -> None:
        db = tmp_path / "data" / "mundoantigo.sqlite3"
        _db_with_rows(db, 50)
        #  Uma conexao aberta, com transacao pendente, nao impede a copia.
        busy = sqlite3.connect(db)
        busy.execute("insert into t values (999)")

        result = backup_database(db, tmp_path / "bkp" / "banco" / db.name)
        busy.close()

        assert result.ok
        copy = sqlite3.connect(tmp_path / "bkp" / "banco" / db.name)
        assert copy.execute("select count(*) from t").fetchone()[0] == 50
        copy.close()

    def test_missing_database_is_not_an_error(self, tmp_path: Path) -> None:
        result = backup_database(tmp_path / "nada.sqlite3", tmp_path / "bkp" / "x.sqlite3")
        assert result.ok
        assert result.detail == "banco ausente"


class TestMirror:
    def test_copies_updates_and_removes(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "src", tmp_path / "dst"
        _write(src / "a.txt", "um")
        _write(src / "sub" / "b.txt", "dois")
        mirror("teste", src, dst, use_robocopy=False)
        assert (dst / "sub" / "b.txt").read_text(encoding="utf-8") == "dois"

        _write(src / "a.txt", "um, alterado")
        (src / "sub" / "b.txt").unlink()
        (src / "sub").rmdir()
        result = mirror("teste", src, dst, use_robocopy=False)

        assert result.ok
        assert (dst / "a.txt").read_text(encoding="utf-8") == "um, alterado"
        assert not (dst / "sub").exists()
        assert result.files == 1

    def test_never_copies_raw_sqlite_files(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "src", tmp_path / "dst"
        _write(src / "mundoantigo.sqlite3", "cru")
        _write(src / "mundoantigo.sqlite3-wal", "cru")
        _write(src / "logs" / "x.log", "ok")
        mirror("data", src, dst, use_robocopy=False)
        assert (dst / "logs" / "x.log").exists()
        assert not (dst / "mundoantigo.sqlite3").exists()
        assert not (dst / "mundoantigo.sqlite3-wal").exists()

    @pytest.mark.parametrize(
        "use_robocopy",
        [
            False,
            pytest.param(
                True,
                marks=pytest.mark.skipif(
                    sys.platform != "win32", reason="robocopy so existe no Windows"
                ),
            ),
        ],
    )
    def test_skips_the_delivery_hard_link(self, tmp_path: Path, use_robocopy: bool) -> None:
        #  O video do pacote e hard link do da montagem: o original ja vai.
        src, dst = tmp_path / "src", tmp_path / "dst"
        _write(src / "v1" / "montagem" / "video.pt-br.mp4", "video")
        (src / "v1" / "entrega" / "pt-br").mkdir(parents=True)
        os.link(
            src / "v1" / "montagem" / "video.pt-br.mp4",
            src / "v1" / "entrega" / "pt-br" / "video.mp4",
        )
        _write(src / "v1" / "entrega" / "pt-br" / "legendas.srt", "1")
        result = mirror("videos", src, dst, use_robocopy=use_robocopy)
        assert result.ok, result.detail
        assert (dst / "v1" / "montagem" / "video.pt-br.mp4").exists()
        assert (dst / "v1" / "entrega" / "pt-br" / "legendas.srt").exists()
        assert not (dst / "v1" / "entrega" / "pt-br" / "video.mp4").exists()

    def test_missing_source_is_reported_not_failed(self, tmp_path: Path) -> None:
        result = mirror("x", tmp_path / "nao-existe", tmp_path / "dst")
        assert result.ok
        assert result.detail == "origem ausente"

    @pytest.mark.skipif(sys.platform != "win32", reason="robocopy so existe no Windows")
    def test_robocopy_mirror(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "src", tmp_path / "dst com espaco"
        _write(src / "a b.txt", "um")
        _write(dst / "sobra.txt", "sai")
        result = mirror("teste", src, dst, use_robocopy=True)
        assert result.ok, result.detail
        assert (dst / "a b.txt").exists()
        assert not (dst / "sobra.txt").exists()


def test_run_backup_writes_manifest_and_history(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root / ".env", "OPENROUTER_API_KEY=x")
    _db_with_rows(root / "data" / "mundoantigo.sqlite3", 3)
    _write(root / "videos" / "v1" / "roteiro" / "roteiro.json", "{}")
    _write(root / "entregas anteriores" / "pacote.txt", "pacote")
    destination = tmp_path / "backup"

    for _ in range(2):
        report = run_backup(
            root=root,
            db_file=root / "data" / "mundoantigo.sqlite3",
            folders={"videos": root / "videos", "data": root / "data"},
            extras=[Path("entregas anteriores")],
            destination=destination,
            use_robocopy=False,
        )

    assert report.ok
    assert (destination / "banco" / "mundoantigo.sqlite3").exists()
    assert (destination / "videos" / "v1" / "roteiro" / "roteiro.json").exists()
    assert (destination / "config-local" / ".env").exists()
    assert (destination / "extras" / "entregas_anteriores" / "pacote.txt").exists()
    manifest = json.loads((destination / "manifesto.json").read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert {i["name"] for i in manifest["itens"]} >= {"banco", "videos", ".env"}
    history = (destination / "historico.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(history) == 2


def test_backup_destination_comes_from_env(tmp_project: Path, monkeypatch) -> None:
    from mundoantigo.config import load_settings

    monkeypatch.setenv("MA_BACKUP_DESTINO", os.fspath(tmp_project / "outro-disco"))
    assert load_settings().backup.destination == os.fspath(tmp_project / "outro-disco")
