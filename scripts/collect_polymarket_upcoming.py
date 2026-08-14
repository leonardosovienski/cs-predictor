"""Descobre e coleta todas as moneylines CS futuras nas próximas 48h.

Reaberto em modo SHADOW_ONLY_NO_CAPITAL por
`docs/records/beyond_market_shadow_reopening.json`. Read-only: nunca envia
ordens e nunca toca a produção `data/market.db`.

O resumo vai para stdout E para `logs/operations/collect_polymarket_upcoming.log`.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.collect_polymarket_shadow import append_once, enrich_with_frozen_model  # noqa: E402
from src.beyond_market_closure import assert_market_shadow_collection_open_for_root  # noqa: E402
from src.data.polymarket_provider import DataUnavailableError, PolymarketProvider  # noqa: E402

LOG = ROOT / "logs" / "operations" / "collect_polymarket_upcoming.log"


def log(mensagem: str) -> None:
    """Escreve no stdout e no log. Falha ao logar nunca derruba a coleta."""
    print(mensagem)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {mensagem}\n")
    except OSError:
        pass


def main() -> int:
    assert_market_shadow_collection_open_for_root(ROOT)
    provider = PolymarketProvider()
    output = ROOT / "data" / "market_shadow.jsonl"
    matches = provider.list_upcoming_matches(horizon_hours=48)
    inserted = failures = 0
    for match in matches:
        try:
            quote = provider.fetch_match(
                match["team_a"], match["team_b"], event_id=match["event_id"]
            )
            quote = enrich_with_frozen_model(quote, match["team_a"], match["team_b"])
            inserted += append_once(output, quote)
        except (DataUnavailableError, RuntimeError, ValueError) as exc:
            failures += 1
            log(f"SKIP {match['event_id']}: {exc}")
    log(f"upcoming={len(matches)} inserted={inserted} failures={failures}")
    return 0 if failures == 0 or inserted > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
