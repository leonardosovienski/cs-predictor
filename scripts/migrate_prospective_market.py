"""Materializa contratos Sports/Market sem sobrescrever dados de origem."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from src.backup_restore import create_backup  # noqa: E402
from src.prospective_market import ProspectiveStore, migrate_sports_db  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Migra Sports DB e coorte Market prospectiva")
    p.add_argument("--migration-id", default="sports-market/2026-07-22")
    p.add_argument("--quotes", type=Path, default=ROOT / "data" / "market_shadow.jsonl")
    p.add_argument("--market-db", type=Path, default=ROOT / "data" / "market.db")
    p.add_argument("--backup-dir", type=Path, required=True)
    p.add_argument("--report", type=Path, default=ROOT / "data" / "sports_market_migration_report.json")
    a = p.parse_args(argv)
    backup = create_backup(a.backup_dir)
    sports = sqlite3.connect(ROOT / "data" / "cs.db")
    try: sports_report = migrate_sports_db(sports, migration_id=a.migration_id)
    finally: sports.close()
    rows = [json.loads(line) for line in a.quotes.read_text(encoding="utf-8").splitlines() if line.strip()] if a.quotes.exists() else []
    store = ProspectiveStore(a.market_db); conn = store.connect()
    try:
        quote_report = store.import_quotes(conn, rows, batch_id=a.migration_id)
        status = store.status(conn)
    finally: conn.close()
    report = {"schema_version": "cs-prospective-migration/1.0", "migration_id": a.migration_id,
              "backup": str(backup), "sports": sports_report, "market": quote_report,
              "status": status, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
