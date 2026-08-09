import sqlite3
from pathlib import Path

import pytest

from scripts.derive_cutoff_db import derive


def test_derive_preserves_source_and_filters_dependencies(tmp_path: Path):
    source, destination = tmp_path / "source.db", tmp_path / "cutoff.db"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE matches(match_id INTEGER PRIMARY KEY, date TEXT)")
    conn.execute("CREATE TABLE match_maps(match_id INTEGER)")
    conn.execute("CREATE TABLE sports_series_metadata(match_id INTEGER)")
    conn.executemany("INSERT INTO matches VALUES(?, ?)", [(1, "2026-07-11"), (2, "2026-07-12")])
    conn.executemany("INSERT INTO match_maps VALUES(?)", [(1,), (2,)])
    conn.executemany("INSERT INTO sports_series_metadata VALUES(?)", [(1,), (2,)])
    conn.commit()
    conn.close()
    source_before = source.read_bytes()

    assert derive(source, destination, "2026-07-11") == (1, "2026-07-11", "2026-07-11")
    assert source.read_bytes() == source_before
    derived = sqlite3.connect(destination)
    assert derived.execute("SELECT match_id FROM matches").fetchall() == [(1,)]
    assert derived.execute("SELECT match_id FROM match_maps").fetchall() == [(1,)]
    assert derived.execute("SELECT match_id FROM sports_series_metadata").fetchall() == [(1,)]
    derived.close()


def test_derive_refuses_to_overwrite(tmp_path: Path):
    source, destination = tmp_path / "source.db", tmp_path / "cutoff.db"
    sqlite3.connect(source).close()
    destination.write_bytes(b"keep")
    with pytest.raises(ValueError, match="already exists"):
        derive(source, destination, "2026-07-11")
    assert destination.read_bytes() == b"keep"
