"""Generate a read-only provenance protocol for a CS sports database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_SCHEMA_VERSION = "cs-db-protocol/1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _git(root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _repository_identity(root: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "commit": _git(root, "rev-parse", "HEAD"),
        "dirty": bool(result.stdout.strip()) if result.returncode == 0 else None,
    }


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    escaped = table.replace('"', '""')
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{escaped}")')}


def _database_metrics(conn: sqlite3.Connection, tables: list[str]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "match_count": None,
        "date_min": None,
        "date_max": None,
        "ties": None,
        "duplicate_match_ids": None,
        "format_distribution": None,
    }
    if "matches" not in tables:
        return metrics

    columns = _table_columns(conn, "matches")
    if {"date", "match_id"}.issubset(columns):
        count, date_min, date_max = conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM matches"
        ).fetchone()
        metrics.update(match_count=count, date_min=date_min, date_max=date_max)
        metrics["duplicate_match_ids"] = conn.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT match_id FROM matches GROUP BY match_id HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    if {"score_a", "score_b"}.issubset(columns):
        metrics["ties"] = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE score_a = score_b"
        ).fetchone()[0]
    if "format" in columns:
        metrics["format_distribution"] = {
            (row[0] if row[0] is not None else "<NULL>"): row[1]
            for row in conn.execute(
                "SELECT LOWER(format), COUNT(*) FROM matches "
                "GROUP BY LOWER(format) ORDER BY LOWER(format)"
            )
        }
    return metrics


def create_protocol(db_path: Path, *, repo_root: Path = ROOT) -> dict[str, Any]:
    db_path = db_path.resolve(strict=True)
    if not db_path.is_file():
        raise ValueError(f"database is not a regular file: {db_path}")

    before = _sha256(db_path)
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        integrity_rows = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        metrics = _database_metrics(conn, tables)
    finally:
        conn.close()

    after = _sha256(db_path)
    if after != before:
        raise RuntimeError("database changed during read-only protocol generation")

    inputs = {}
    for name in ("uv.lock", "config.yaml"):
        path = repo_root / name
        inputs[name] = _sha256(path) if path.is_file() else None

    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "database": {
            "path": str(db_path),
            "sha256": before,
            "size_bytes": db_path.stat().st_size,
            "integrity_check": integrity_rows,
            "integrity_ok": integrity_rows == ["ok"],
            "tables": tables,
            **metrics,
        },
        "environment": {
            "python": sys.version.split()[0],
            "predictor_core": _package_version("predictor-core"),
            "predictor_ops": _package_version("predictor-ops"),
        },
        "repository": _repository_identity(repo_root),
        "input_hashes": inputs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a read-only, SHA-256-sealed protocol for cs.db"
    )
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, help="write JSON to this new file")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="repository whose commit, status, lock and config identify the replay",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing output")
    args = parser.parse_args(argv)

    try:
        protocol = create_protocol(args.database, repo_root=args.repo_root.resolve(strict=True))
        rendered = json.dumps(protocol, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            output = args.output.resolve()
            if output.exists() and not args.force:
                print(
                    f"protocol generation failed: output already exists: {output}; "
                    "use --force to replace it",
                    file=sys.stderr,
                )
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0 if protocol["database"]["integrity_ok"] else 2
    except (OSError, sqlite3.DatabaseError, ValueError, RuntimeError) as exc:
        print(f"protocol generation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
