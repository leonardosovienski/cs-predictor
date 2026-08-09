from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from scripts.protocol_db import PROTOCOL_SCHEMA_VERSION, create_protocol, main


def _database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE matches ("
        "match_id INTEGER, date TEXT, score_a INTEGER, score_b INTEGER, format TEXT)"
    )
    conn.executemany(
        "INSERT INTO matches VALUES (?, ?, ?, ?, ?)",
        [
            (1, "2025-01-01", 2, 0, "BO3"),
            (2, "2025-01-02", 1, 1, "bo3"),
            (2, "2025-01-03", 1, 0, "bo1"),
        ],
    )
    conn.execute("CREATE TABLE match_maps (match_id INTEGER)")
    conn.commit()
    conn.close()


def test_protocol_is_read_only_and_records_dataset_identity(tmp_path: Path):
    db_path = tmp_path / "cs.db"
    _database(db_path)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    protocol = create_protocol(db_path, repo_root=tmp_path)

    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
    assert protocol["schema_version"] == PROTOCOL_SCHEMA_VERSION
    database = protocol["database"]
    assert database["sha256"] == before
    assert database["integrity_check"] == ["ok"]
    assert database["integrity_ok"] is True
    assert database["tables"] == ["match_maps", "matches"]
    assert database["match_count"] == 3
    assert database["date_min"] == "2025-01-01"
    assert database["date_max"] == "2025-01-03"
    assert database["ties"] == 1
    assert database["duplicate_match_ids"] == 1
    assert database["format_distribution"] == {"bo1": 1, "bo3": 2}


def test_cli_writes_protocol_and_does_not_overwrite_by_default(tmp_path: Path):
    db_path, output = tmp_path / "cs.db", tmp_path / "protocol.json"
    _database(db_path)

    assert main(
        [str(db_path), "--output", str(output), "--repo-root", str(tmp_path)]
    ) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["database"]["integrity_ok"]
    assert main(
        [str(db_path), "--output", str(output), "--repo-root", str(tmp_path)]
    ) == 2
    assert main(
        [
            str(db_path),
            "--output",
            str(output),
            "--repo-root",
            str(tmp_path),
            "--force",
        ]
    ) == 0


def test_protocol_handles_database_without_matches_table(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    conn.close()

    protocol = create_protocol(db_path, repo_root=tmp_path)

    assert protocol["database"]["integrity_ok"] is True
    assert protocol["database"]["tables"] == []
    assert protocol["database"]["match_count"] is None
