import json
from pathlib import Path
import sqlite3

import pytest

from src.backup_restore import BackupError, create_backup, restore_backup, verify_backup


def _root(path: Path) -> Path:
    (path / "data").mkdir(parents=True)
    conn = sqlite3.connect(path / "data" / "cs.db")
    conn.execute("create table matches (match_id integer primary key, team text)")
    conn.execute("insert into matches values (1, 'Vitality')")
    conn.commit(); conn.close()
    (path / "data" / "ratings.json").write_text('{"Vitality": 1900}', encoding="utf-8")
    (path / "snapshots" / "pre_event").mkdir(parents=True)
    (path / "snapshots" / "pre_event" / "one.json").write_text("{}", encoding="utf-8")
    return path


def test_backup_verify_and_restore_roundtrip(tmp_path):
    source = _root(tmp_path / "source")
    backup = create_backup(tmp_path / "backup", root=source)
    assert verify_backup(backup)["schema_version"] == "cs-backup/1.0"
    assert not list((backup / "data").glob("cs.db-*"))
    restored = restore_backup(backup, tmp_path / "restored")
    conn = sqlite3.connect(restored / "data" / "cs.db")
    assert conn.execute("select * from matches").fetchall() == [(1, "Vitality")]
    conn.close()
    assert json.loads((restored / "data" / "ratings.json").read_text()) == {"Vitality": 1900}
    assert (restored / "snapshots" / "pre_event" / "one.json").is_file()


def test_backup_rejects_tamper_and_overwrite(tmp_path):
    source = _root(tmp_path / "source")
    backup = create_backup(tmp_path / "backup", root=source)
    (backup / "data" / "ratings.json").write_text("{}", encoding="utf-8")
    with pytest.raises(BackupError, match="diverge"):
        verify_backup(backup)
    clean = create_backup(tmp_path / "clean", root=source)
    with pytest.raises(BackupError, match="já existe"):
        restore_backup(clean, tmp_path)
