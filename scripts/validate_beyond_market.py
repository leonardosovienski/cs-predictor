"""Executa a comparação temporal mercado x modelo sem habilitar capital."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market_db import ContractError, beyond_market_validate  # noqa: E402
from src.beyond_market_closure import BeyondMarketClosedError, assert_beyond_market_open  # noqa: E402


def _rows(path: Path) -> list[dict]:
    try:
        raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"dataset Beyond Market ilegível: {exc}") from exc
    out = []
    for row in raw:
        # Formato canônico do Market DB; os aliases abaixo permitem inspecionar
        # a amostra retrospectiva sem promovê-la a gate prospectivo.
        price_at = row.get("captured_at", row.get("price_observed_at", row.get("observed_at", row.get("price_ts"))))
        start_at = row.get("match_start_at", row.get("scheduled_at", row.get("match_ts")))
        if isinstance(price_at, (int, float)):
            from datetime import datetime, timezone
            price_at = datetime.fromtimestamp(price_at, timezone.utc).isoformat()
        if isinstance(start_at, (int, float)):
            from datetime import datetime, timezone
            start_at = datetime.fromtimestamp(start_at, timezone.utc).isoformat()
        out.append({"captured_at": price_at,
                    "match_start_at": start_at,
                    "outcome": row.get("outcome", row.get("outcome_a")),
                    "market_probability": row.get("market_probability", row.get("market_probability_a")),
                    "model_probability": row.get("model_probability", row.get("model_probability_a"))})
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Beyond Market CS, temporal e fail-closed")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--train-end", required=True)
    parser.add_argument("--minimum-test-rows", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        assert_beyond_market_open()
        result = beyond_market_validate(_rows(args.input), train_end_at=args.train_end,
                                        minimum_test_rows=args.minimum_test_rows)
    except (ContractError, BeyondMarketClosedError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result["schema_version"] = "cs-beyond-market/1.0"
    result["financial_capital_authorized"] = False
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
