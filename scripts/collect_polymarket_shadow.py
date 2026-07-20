"""Coleta uma moneyline CS do Polymarket em shadow; nunca envia ordens."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.polymarket_provider import PolymarketProvider  # noqa: E402
from src.predict import run as predict_match                 # noqa: E402


def enrich_with_frozen_model(quote: dict, team_a: str, team_b: str) -> dict:
    prediction = predict_match(team_a, team_b,
                               fmt=quote.get("format") or "bo3", dry_run=True)
    ratings = ROOT / "data" / "ratings.json"
    if not ratings.exists():
        raise RuntimeError("data/ratings.json ausente; não há modelo vivido para congelar")
    return {**quote,
            "model_probability_a": prediction["prob_team_a"],
            "model_probability_b": prediction["prob_team_b"],
            "model_name": prediction["model"],
            "ratings_sha256": hashlib.sha256(ratings.read_bytes()).hexdigest()}


def append_once(path: Path, quote: dict) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("coleta shadow concorrente em andamento") from exc
    os.close(descriptor)
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line and json.loads(line).get("quote_id") == quote["quote_id"]:
                    return False
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(quote, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        return True
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Polymarket CS shadow read-only")
    parser.add_argument("team_a"); parser.add_argument("team_b")
    parser.add_argument("--event-id", required=True,
                        help="ID Gamma explícito; evita casamento ambíguo")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "data" / "market_shadow.jsonl")
    args = parser.parse_args(argv)
    quote = PolymarketProvider().fetch_match(args.team_a, args.team_b,
                                             event_id=args.event_id)
    quote = enrich_with_frozen_model(quote, args.team_a, args.team_b)
    inserted = append_once(args.output, quote)
    print(json.dumps({"inserted": inserted, "quote": quote},
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
