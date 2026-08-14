"""CS market-shadow readiness; maturity requires a validated settlement.

Reads `data/market_shadow.db` by default (shadow, SHADOW_ONLY_NO_CAPITAL).
Never reads or writes the production `data/market.db`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.beyond_market_closure import (  # noqa: E402
    BeyondMarketClosedError,
    assert_market_shadow_collection_open,
    is_shadow_market_db,
)
from src.prospective_market import ProspectiveStore  # noqa: E402


def status(path: Path, now: datetime | None = None, market_db: Path | None = None) -> dict:
    if market_db and is_shadow_market_db(Path(market_db)):
        try:
            assert_market_shadow_collection_open()
        except BeyondMarketClosedError as exc:
            return {
                "scientific_status": "SHADOW_COLLECTION_CLOSED",
                "operational_status": "NO_GO",
                "reason": str(exc),
                "decision_ready": False,
            }
    if market_db and Path(market_db).exists():
        store = ProspectiveStore(market_db)
        conn = store.connect()
        try:
            return store.status(conn, now=now)
        finally:
            conn.close()
    rows = (
        [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        if path.exists()
        else []
    )
    eligible = [
        r
        for r in rows
        if all(
            k in r
            for k in (
                "model_probability_a",
                "model_probability_b",
                "ratings_sha256",
                "observed_at",
                "scheduled_at",
            )
        )
    ]
    latest: dict = {}
    for r in eligible:
        key = r.get("market_id") or r.get("quote_id")
        if key not in latest or r["observed_at"] > latest[key]["observed_at"]:
            latest[key] = r
    observed = now or datetime.now(UTC)
    passed = sum(datetime.fromisoformat(r["scheduled_at"]) < observed for r in latest.values())
    return {
        "raw_quotes": len(rows),
        "legacy_ineligible": len(rows) - len(eligible),
        "eligible_quotes": len(eligible),
        "eligible_matches": len(latest),
        "event_time_passed": passed,
        "matured_matches": 0,
        "required_matured_matches": 50,
        "required_calendar_days": 30,
        "decision_ready": False,
        "verdict": "BLOCKED_BY_MARKET_DATA",
        "reason": "Market DB shadow/resultado/closing/settlement ausentes",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--quotes", type=Path, default=ROOT / "data" / "market_shadow.jsonl")
    p.add_argument("--market-db", type=Path, default=ROOT / "data" / "market_shadow.db")
    a = p.parse_args()
    result = status(a.quotes, market_db=a.market_db)
    print(json.dumps(result, sort_keys=True))
    return 3 if result.get("scientific_status") == "SHADOW_COLLECTION_CLOSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
