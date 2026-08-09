"""Derive an immutable replay database up to an inclusive historical cutoff."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DEPENDENT_TABLES = ("match_maps", "sports_series_metadata")


def derive(source: Path, destination: Path, cutoff: str) -> tuple[int, str | None, str | None]:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    target_conn = sqlite3.connect(destination)
    try:
        source_conn.execute("PRAGMA query_only=ON")
        source_conn.backup(target_conn)
        tables = {
            row[0]
            for row in target_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "matches" not in tables:
            raise ValueError("source database has no matches table")
        for table in DEPENDENT_TABLES:
            if table in tables:
                target_conn.execute(
                    f"DELETE FROM {table} WHERE match_id NOT IN "
                    "(SELECT match_id FROM matches WHERE date <= ?)",
                    (cutoff,),
                )
        target_conn.execute("DELETE FROM matches WHERE date > ?", (cutoff,))
        target_conn.commit()
        target_conn.execute("VACUUM")
        integrity = [row[0] for row in target_conn.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise sqlite3.DatabaseError(f"derived database failed integrity check: {integrity}")
        return target_conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM matches"
        ).fetchone()
    except Exception:
        target_conn.close()
        source_conn.close()
        destination.unlink(missing_ok=True)
        raise
    finally:
        if source_conn:
            source_conn.close()
        if target_conn:
            target_conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a replay DB with an inclusive cutoff")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--cutoff", required=True, help="inclusive ISO date, e.g. 2026-07-11")
    args = parser.parse_args(argv)
    try:
        count, date_min, date_max = derive(args.source, args.destination, args.cutoff)
    except (OSError, ValueError, sqlite3.DatabaseError) as exc:
        print(f"cutoff derivation failed: {exc}")
        return 2
    print(f"derived matches: {count} ({date_min} .. {date_max})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
