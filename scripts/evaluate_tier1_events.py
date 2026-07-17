"""Read-only prequential evaluation of H1 versus post-veto map Elo on Tier 1 events.

H3 receives the maps that were actually played.  This is intentionally labelled
``post_veto``: it measures the marginal value of map information, not a
pre-event veto forecast.  Every rating is reconstructed chronologically from
matches before the prediction; no materialized runtime rating is read or
written.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.model import K_FACTORS, infer_format, series_probs, win_probability  # noqa: E402
from src.model_maps import MAP_K, series_probs_hetero  # noqa: E402
from src.model_maps_shrunk import HistoricalVetoProxy, ShrunkMapElo, series_probability as shrunk_series_probability  # noqa: E402

DEFAULT_EVENTS = [
    "IEM Kraków 2026", "PGL Cluj-Napoca 2026", "PGL Bucharest 2026",
    "IEM Rio 2026", "PGL Astana 2026", "IEM Cologne Major 2026",
]


def _series_probability(probabilities: list[float]) -> float:
    return sum(probability for score, probability in series_probs_hetero(probabilities, 2).items()
               if int(score.split("-")[0]) > int(score.split("-")[1]))


def _metrics(rows: list[dict[str, Any]], key: str) -> dict[str, float | int]:
    values = [row for row in rows if isinstance(row.get(key), (int, float))]
    n = len(values)
    if not n:
        return {"n": 0}
    brier = sum((row[key] - row["outcome_a"]) ** 2 for row in values) / n
    accuracy = sum((row[key] >= 0.5) == bool(row["outcome_a"]) for row in values) / n
    return {"n": n, "brier": round(brier, 6), "accuracy": round(accuracy, 6)}


def evaluate(conn: sqlite3.Connection, events: set[str]) -> dict[str, Any]:
    cfg = load_config()
    default = float(cfg["backtest"]["default_seed_elo"])
    # Do not seed historical events with the repository's July 2026 Top 30:
    # that ranking is future information for the selected 2026 events.
    series_elo: dict[str, float] = {}
    map_elo: dict[tuple[str, str], float] = {}
    h4 = ShrunkMapElo()
    veto = HistoricalVetoProxy()
    maps_by_match: dict[int, list[tuple[str, str, str, int, int]]] = defaultdict(list)
    for mid, seq, name, a, b, sa, sb in conn.execute(
            "SELECT match_id, seq, map_name, team_a, team_b, score_a, score_b FROM match_maps ORDER BY match_id, seq"):
        maps_by_match[mid].append((name, a, b, sa, sb))

    evaluated: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = conn.execute(
        "SELECT match_id, date, ts, team_a, team_b, score_a, score_b, format, event "
        "FROM matches ORDER BY date, ts, match_id").fetchall()
    for mid, _date, ts, a, b, sa, sb, _stored_format, event in rows:
        now_ts = int(ts or 0)
        # The historical results parser can label a BO3 as ``bo1`` when the
        # result-list HTML exposes a map name instead of the series format.
        # Infer format exactly as EloModel.update_ratings does, from a closed
        # series score, rather than silently discarding the major-event data.
        total_maps = sa + sb
        fmt = infer_format(sa, sb, _stored_format)
        ea, eb = series_elo.get(a, default), series_elo.get(b, default)
        pre_match_elo = {a: ea, b: eb}
        p_map = win_probability(ea, eb)
        p_h1 = sum(probability for score, probability in series_probs(p_map, fmt).items()
                   if int(score.split("-")[0]) > int(score.split("-")[1]))
        maps = maps_by_match.get(mid, [])
        # A valid BO3 has its two or three played maps stored in result order.
        valid_bo3_maps = fmt == "bo3" and len(maps) in {2, 3} and total_maps in {2, 3}
        if event in events and valid_bo3_maps and sa != sb:
            probabilities = []
            for name, _map_a, _map_b, _map_sa, _map_sb in maps:
                ma = map_elo.get((a, name), ea)
                mb = map_elo.get((b, name), eb)
                probabilities.append(win_probability(ma, mb))
            scenarios = veto.scenarios(a, b)
            evaluated[event].append({"outcome_a": 1 if sa > sb else 0, "h1": p_h1,
                                     # Em 2-0 o banco só contém os dois mapas
                                     # jogados, não o decider planejado. Não
                                     # invente a terceira probabilidade.
                                     "h3_post_veto": (_series_probability(probabilities)
                                                       if len(probabilities) == 3 else None),
                                     "h4_pre_veto": shrunk_series_probability(h4, a, b, scenarios,
                                         base_a=ea, base_b=eb, now_ts=now_ts)})

        # Prediction completes before either rating receives this result.
        if sa != sb:
            delta = K_FACTORS[fmt] * ((1.0 if sa > sb else 0.0) - p_map)
            series_elo[a], series_elo[b] = ea + delta, eb - delta
        for name, map_a, map_b, map_sa, map_sb in maps:
            if map_sa == map_sb:
                continue
            # Map-page team order is authoritative for that map's score and
            # need not match the order used by the series results page.
            ma = map_elo.get((map_a, name), pre_match_elo.get(map_a, default))
            mb = map_elo.get((map_b, name), pre_match_elo.get(map_b, default))
            expectation = win_probability(ma, mb)
            delta = MAP_K * ((1.0 if map_sa > map_sb else 0.0) - expectation)
            map_elo[map_a, name], map_elo[map_b, name] = ma + delta, mb - delta
            h4.update(map_a, map_b, name, map_sa, map_sb,
                      base_a=pre_match_elo.get(map_a, default),
                      base_b=pre_match_elo.get(map_b, default), now_ts=now_ts)
            veto.observe(map_a, map_b, name)

    per_event = {}
    all_rows: list[dict[str, Any]] = []
    for event in sorted(events):
        event_rows = evaluated[event]
        all_rows.extend(event_rows)
        h1, h3, h4_metrics = (_metrics(event_rows, "h1"), _metrics(event_rows, "h3_post_veto"),
                               _metrics(event_rows, "h4_pre_veto"))
        per_event[event] = {"h1": h1, "h3_post_veto": h3,
                            "h4_pre_veto": h4_metrics,
                            "delta_brier_h3_minus_h1": None,
                            "delta_brier_h4_minus_h1": round(h4_metrics.get("brier", 0) - h1.get("brier", 0), 6) if event_rows else None}
    h1, h3, h4_metrics = (_metrics(all_rows, "h1"), _metrics(all_rows, "h3_post_veto"),
                           _metrics(all_rows, "h4_pre_veto"))
    return {"protocol": {"mode": "global prequential", "seed": f"neutral {default:.0f}; no future ranking seed",
                         "h1": "series Elo raw (no Platt, to avoid future-fitted calibrator leakage)",
                         "h3_post_veto": "only complete three-map records; outcome-conditioned diagnostic, not evidence", "database_write": False, "ratings_write": False},
            "events": per_event, "aggregate": {"h1": h1, "h3_post_veto": h3,
            "h4_pre_veto": h4_metrics,
            "delta_brier_h3_minus_h1": None,
            "delta_brier_h4_minus_h1": round(h4_metrics["brier"] - h1["brier"], 6) if all_rows else None}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia H1 vs H3 pós-veto em eventos Tier 1")
    parser.add_argument("--event", action="append", dest="events", help="nome exato do evento; repetível")
    parser.add_argument("--output", type=Path, help="JSON opcional; omitido = stdout")
    args = parser.parse_args(argv)
    selected = set(args.events or DEFAULT_EVENTS)
    conn = sqlite3.connect(f"file:{ROOT / 'data' / 'cs.db'}?mode=ro", uri=True)
    try:
        result = evaluate(conn, selected)
    finally:
        conn.close()
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
