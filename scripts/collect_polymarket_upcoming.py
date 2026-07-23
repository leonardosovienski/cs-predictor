"""Descobre e coleta todas as moneylines CS futuras nas próximas 48h."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.collect_polymarket_shadow import append_once, enrich_with_frozen_model  # noqa: E402
from src.beyond_market_closure import assert_beyond_market_open_for_root  # noqa: E402
from src.data.polymarket_provider import DataUnavailableError, PolymarketProvider  # noqa: E402


def main() -> int:
    assert_beyond_market_open_for_root(ROOT)
    provider = PolymarketProvider()
    output = ROOT / "data" / "market_shadow.jsonl"
    matches = provider.list_upcoming_matches(horizon_hours=48)
    inserted = failures = 0
    for match in matches:
        try:
            quote = provider.fetch_match(match["team_a"], match["team_b"],
                                         event_id=match["event_id"])
            quote = enrich_with_frozen_model(quote, match["team_a"], match["team_b"])
            inserted += append_once(output, quote)
        except (DataUnavailableError, RuntimeError, ValueError) as exc:
            failures += 1
            print(f"SKIP {match['event_id']}: {exc}")
    print(f"upcoming={len(matches)} inserted={inserted} failures={failures}")
    return 0 if failures == 0 or inserted > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
