"""Backup verificável dos artefatos científicos locais do CS.

O backup usa a API online do SQLite, copia ratings e snapshots e grava hashes
SHA-256. A restauração sempre exige uma raiz nova: nunca sobrescreve produção.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any
import uuid

from .config import ROOT


class BackupError(RuntimeError):
    pass


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*")
                  if path.is_file() and path.name != "BACKUP_MANIFEST.json")


def create_backup(destination: Path, *, root: Path = ROOT) -> Path:
    destination = destination.resolve()
    if destination.exists():
        raise BackupError(f"destino já existe: {destination}")
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True)
    try:
        data = temporary / "data"
        data.mkdir()
        source_db = root / "data" / "cs.db"
        if not source_db.is_file():
            raise BackupError("data/cs.db ausente")
        source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
        target = sqlite3.connect(data / "cs.db")
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        ratings = root / "data" / "ratings.json"
        if ratings.is_file():
            shutil.copy2(ratings, data / "ratings.json")
        snapshots = root / "snapshots"
        if snapshots.is_dir():
            shutil.copytree(snapshots, temporary / "snapshots")
        files = {path.relative_to(temporary).as_posix(): _hash(path)
                 for path in _files(temporary)}
        manifest: dict[str, Any] = {
            "schema_version": "cs-backup/1.0",
            "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "files": files,
        }
        (temporary / "BACKUP_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        temporary.rename(destination)
        return destination
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify_backup(backup: Path) -> dict[str, Any]:
    backup = backup.resolve()
    try:
        manifest = json.loads((backup / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError(f"manifesto ilegível: {exc}") from exc
    if manifest.get("schema_version") != "cs-backup/1.0" or not isinstance(manifest.get("files"), dict):
        raise BackupError("manifesto inválido")
    declared = manifest["files"]
    actual = {path.relative_to(backup).as_posix(): _hash(path) for path in _files(backup)}
    if actual != declared:
        raise BackupError("conteúdo do backup diverge do manifesto")
    db = backup / "data" / "cs.db"
    # immutable evita que a própria verificação crie -wal/-shm no backup.
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("integrity_check do SQLite falhou")
    finally:
        conn.close()
    return manifest


def restore_backup(backup: Path, destination_root: Path) -> Path:
    verify_backup(backup)
    destination_root = destination_root.resolve()
    if destination_root.exists():
        raise BackupError(f"raiz de restauração já existe: {destination_root}")
    shutil.copytree(backup.resolve(), destination_root)
    (destination_root / "BACKUP_MANIFEST.json").unlink()
    return destination_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backup/restore verificável do cs-predictor")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create"); create.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify"); verify.add_argument("--backup", type=Path, required=True)
    restore = sub.add_parser("restore"); restore.add_argument("--backup", type=Path, required=True); restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create": result = {"backup": str(create_backup(args.output))}
        elif args.command == "verify": result = {"verified": str(args.backup), "manifest": verify_backup(args.backup)}
        else: result = {"restored": str(restore_backup(args.backup, args.destination))}
    except (BackupError, OSError, sqlite3.Error) as exc:
        print(str(exc)); return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
