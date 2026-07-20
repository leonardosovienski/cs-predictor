"""Backtest retrospectivo CS x Polymarket, estritamente sem lookahead.

Esta amostra e' evidência auxiliar e nunca incrementa os gates forward-only.
Para cada moneyline encerrada, casa uma única série HLTV pela identidade exata
do par e por uma janela temporal de 36 h, usa o estado Elo imediatamente antes
da série e o último preço CLOB publicado antes do timestamp HLTV.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor"))

from src.config import identity_key, load_config  # noqa: E402
from src.calibration import PlattCalibrator  # noqa: E402
from src.data.polymarket_provider import (CLOB, GAMMA, DataUnavailableError,
                                          PolymarketProvider, _array, _timestamp)  # noqa: E402
from src.model import (FORMAT_HOURS, K_FACTORS, infer_format, series_probs,
                       win_probability)  # noqa: E402

CS2_TAG_ID = "100780"


def select_pre_event_price(history: list[dict], cutoff_ts: int) -> dict | None:
    """Último preço finito estritamente anterior ao evento."""
    valid = []
    for point in history:
        try:
            ts, price = int(point["t"]), float(point["p"])
        except (KeyError, TypeError, ValueError):
            continue
        if ts < cutoff_ts and math.isfinite(price) and 0 < price < 1:
            valid.append({"t": ts, "p": price})
    return max(valid, key=lambda point: point["t"], default=None)


def _series_probability(elo_a: float, elo_b: float, fmt: str) -> float:
    dist = series_probs(win_probability(elo_a, elo_b), fmt)
    return sum(p for score, p in dist.items()
               if int(score.split("-")[0]) > int(score.split("-")[1]))


def replay_states(conn: sqlite3.Connection, cfg: dict) -> tuple[list[tuple], dict[int, dict]]:
    rows = conn.execute(
        "SELECT match_id,date,ts,team_a,team_b,score_a,score_b,format "
        "FROM matches ORDER BY date,ts,match_id").fetchall()
    seed = float(cfg["backtest"]["default_seed_elo"])
    minimum = int(cfg["backtest"]["min_team_matches"])
    elo: dict[str, float] = {}
    seen = defaultdict(int)
    hist_p: list[float] = []
    hist_y: list[int] = []
    calibrator = PlattCalibrator()
    fitted = False
    states = {}
    for mid, date, ts, a, b, sa, sb, advertised in rows:
        if sa == sb:
            continue
        fmt = infer_format(sa, sb, advertised)
        ea, eb = elo.get(a, seed), elo.get(b, seed)
        raw_probability = _series_probability(ea, eb, fmt)
        eligible = seen[a] >= minimum and seen[b] >= minimum
        states[mid] = {"elo_a": ea, "elo_b": eb,
                       "seen_a": seen[a], "seen_b": seen[b],
                       "eligible": eligible,
                       "platt_a": calibrator.a if fitted else 1.0}
        outcome_a = 1.0 if sa > sb else 0.0
        if eligible:
            hist_p.append(raw_probability); hist_y.append(int(outcome_a))
            if len(hist_p) >= 300 and (not fitted or len(hist_p) % 200 == 0):
                calibrator = PlattCalibrator().fit(hist_p, hist_y)
                fitted = True
        delta = K_FACTORS[fmt] * (outcome_a - win_probability(ea, eb))
        elo[a], elo[b] = ea + delta, eb - delta
        seen[a] += 1; seen[b] += 1
    return rows, states


def _closed_events(provider: PolymarketProvider, max_pages: int) -> list[dict]:
    events = {}
    for page in range(max_pages):
        query = urlencode({"tag_id": CS2_TAG_ID, "closed": "true", "limit": 100,
                           "offset": page * 100, "order": "endDate",
                           "ascending": "false"})
        try:
            payload = provider.get_json(f"{GAMMA}/events?{query}")
        except DataUnavailableError:
            break
        if not isinstance(payload, list) or not payload:
            break
        for event in payload:
            events[str(event.get("id"))] = event
        if len(payload) < 100:
            break
    return list(events.values())


def build_candidates(events: list[dict], rows: list[tuple], states: dict[int, dict]) -> list[dict]:
    by_pair: dict[frozenset[str], list[tuple]] = defaultdict(list)
    for row in rows:
        mid, _date, _ts, a, b, sa, sb, _fmt = row
        if sa != sb and states.get(mid, {}).get("eligible"):
            by_pair[frozenset((identity_key(a), identity_key(b)))].append(row)
    candidates = []
    for event in events:
        try:
            scheduled_ts = int(_timestamp(event.get("endDate") or event.get("startTime")).timestamp())
        except DataUnavailableError:
            continue
        for market in event.get("markets") or []:
            if market.get("sportsMarketType") != "moneyline":
                continue
            try:
                outcomes = _array(market.get("outcomes"), "outcomes")
                tokens = _array(market.get("clobTokenIds"), "clobTokenIds")
                resolved = [float(x) for x in _array(market.get("outcomePrices"), "outcomePrices")]
            except (DataUnavailableError, ValueError):
                continue
            fmt_match = re.search(r"\(BO([135])\)", market.get("question") or "", re.I)
            if len(outcomes) != 2 or len(tokens) != 2 or not fmt_match:
                continue
            if sorted(resolved) != [0.0, 1.0]:
                continue
            matches = [row for row in by_pair.get(frozenset(map(identity_key, outcomes)), [])
                       if abs(int(row[2]) - scheduled_ts) <= 36 * 3600]
            if len(matches) != 1:
                continue
            row = matches[0]
            mid, date, ts, db_a, db_b, sa, sb, _stored_fmt = row
            market_a = next(i for i, name in enumerate(outcomes)
                            if identity_key(name) == identity_key(db_a))
            candidates.append({
                "event_id": str(event.get("id")), "market_id": str(market.get("id")),
                "token_id": tokens[market_a], "match_id": mid, "date": date,
                "match_ts": int(ts), "scheduled_ts": scheduled_ts,
                "team_a": db_a, "team_b": db_b,
                "score_a": sa, "score_b": sb, "format": f"bo{fmt_match.group(1)}",
                "outcome_a": 1 if sa > sb else 0, "resolved_a": int(resolved[market_a]),
                **states[mid],
            })
    unique = {row["match_id"]: row for row in candidates}
    return sorted(unique.values(), key=lambda row: row["match_ts"], reverse=True)


def _enrich(provider: PolymarketProvider, row: dict) -> dict | None:
    # O timestamp do /results do HLTV pode ser o início anunciado ou a hora de
    # publicação/conclusão. Para nunca usar preço in-play, recue a duração de
    # parede máxima do formato a partir do MAIS ANTIGO entre HLTV e Polymarket.
    safety_seconds = int(FORMAT_HOURS[row["format"]] * 3600)
    cutoff_ts = min(row["match_ts"], row["scheduled_ts"]) - safety_seconds
    start = cutoff_ts - 7 * 24 * 3600
    query = urlencode({"market": row["token_id"], "startTs": start,
                       "endTs": cutoff_ts, "fidelity": 10})
    payload = provider.get_json(f"{CLOB}/prices-history?{query}")
    history = payload.get("history") if isinstance(payload, dict) else None
    if not isinstance(history, list):
        return None
    point = select_pre_event_price(history, cutoff_ts)
    if point is None:
        return None
    market_p = point["p"]
    model_raw = _series_probability(row["elo_a"], row["elo_b"], row["format"])
    model_p = PlattCalibrator(a=row["platt_a"]).apply(model_raw)
    return {**row, "price_ts": point["t"], "price_cutoff_ts": cutoff_ts,
            "safety_horizon_hours": FORMAT_HOURS[row["format"]],
            "price_age_minutes": round((cutoff_ts - point["t"]) / 60, 2),
            "market_probability_a": round(market_p, 8),
            "model_probability_a_raw": round(model_raw, 8),
            "model_probability_a": round(model_p, 8),
            "model_calibration": "symmetric-platt-prequential",
            "retrospective_only": True, "counts_toward_forward_gate": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backtest histórico CS x Polymarket")
    parser.add_argument("--target", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=25)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "data" / "historical_market_sample.jsonl")
    args = parser.parse_args(argv)
    if args.target < 1 or args.max_pages < 1 or not 1 <= args.workers <= 16:
        parser.error("target/max-pages devem ser positivos e workers deve estar entre 1 e 16")
    cfg = load_config()
    conn = sqlite3.connect(f"file:{(ROOT / cfg['database']).as_posix()}?mode=ro", uri=True)
    rows, states = replay_states(conn, cfg)
    provider = PolymarketProvider(timeout=30)
    events = _closed_events(provider, args.max_pages)
    candidates = build_candidates(events, rows, states)
    selected = candidates[:args.target]
    enriched = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_enrich, PolymarketProvider(timeout=30), row): row
                   for row in selected}
        for future in as_completed(futures):
            try:
                value = future.result()
            except DataUnavailableError:
                value = None
            if value is not None and value["outcome_a"] == value["resolved_a"]:
                enriched.append(value)
    enriched.sort(key=lambda row: row["match_ts"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                   for row in enriched), encoding="utf-8")
    n = len(enriched)
    if n:
        brier_model = sum((r["model_probability_a"] - r["outcome_a"]) ** 2 for r in enriched) / n
        brier_market = sum((r["market_probability_a"] - r["outcome_a"]) ** 2 for r in enriched) / n
        accuracy_model = sum((r["model_probability_a"] >= .5) == bool(r["outcome_a"])
                             for r in enriched) / n
        accuracy_market = sum((r["market_probability_a"] >= .5) == bool(r["outcome_a"])
                              for r in enriched) / n
    else:
        brier_model = brier_market = None
        accuracy_model = accuracy_market = None
    summary = {"schema_version": "cs-historical-market-summary/1.0",
               "retrospective_only": True, "counts_toward_forward_gate": False,
               "events_scanned": len(events),
               "matched_candidates": len(candidates), "requested": args.target,
               "eligible": n, "brier_model": brier_model, "brier_market": brier_market,
               "brier_delta_model_minus_market": (brier_model - brier_market
                                                   if n else None),
               "accuracy_model": accuracy_model, "accuracy_market": accuracy_market,
               "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if n else 2


if __name__ == "__main__":
    raise SystemExit(main())
