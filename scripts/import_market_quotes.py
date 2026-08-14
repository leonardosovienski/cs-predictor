"""Importa as cotações coletadas (JSONL) para o Market DB shadow prospectivo.

Grava exclusivamente em `data/market_shadow.db` (nunca `data/market.db`, que
permanece sob o encerramento original). Reaberto em modo
SHADOW_ONLY_NO_CAPITAL por `docs/records/beyond_market_shadow_reopening.json`.

A proveniência temporal vive na própria cotação (`observed_at`/`published_at`
gravados na coleta, antes do evento), então importar depois não a corrompe — o
contrato de `import_quotes` valida sobre esses campos, não sobre a hora desta
execução.

Uso:
    python scripts/import_market_quotes.py
    python scripts/import_market_quotes.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.beyond_market_closure import BeyondMarketClosedError  # noqa: E402
from src.prospective_market import ProspectiveStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quotes", type=Path, default=ROOT / "data" / "market_shadow.jsonl")
    ap.add_argument("--market-db", type=Path, default=ROOT / "data" / "market_shadow.db")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.quotes.exists():
        print(json.dumps({"status": "NO_QUOTES", "quotes": str(args.quotes)}))
        return 0
    rows = [
        json.loads(line)
        for line in args.quotes.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN", "linhas_no_jsonl": len(rows)}))
        return 0

    # batch_id carimba a rodada; o contrato dedupe por hash da cotação, então
    # reimportar o JSONL inteiro é idempotente e não infla a coorte.
    batch = "import/" + datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    store = ProspectiveStore(args.market_db)
    try:
        conn = store.connect()
    except BeyondMarketClosedError as exc:
        print(json.dumps({"status": "SHADOW_COLLECTION_CLOSED", "reason": str(exc)}))
        return 0
    try:
        relatorio = store.import_quotes(conn, rows, batch_id=batch)
        status = store.status(conn)
    finally:
        conn.close()
    print(
        json.dumps(
            {
                "status": "OK",
                "batch_id": batch,
                "linhas_no_jsonl": len(rows),
                "import": relatorio,
                "matured": status.get("matured_matches"),
                "accepted": status.get("accepted_mappings"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
