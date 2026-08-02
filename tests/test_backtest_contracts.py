"""Contratos temporais dos backtests; banco sempre em memória."""

from copy import deepcopy
import sqlite3

from scripts.backtest_map_elo import run as run_map
from scripts.backtest_walkforward import run as run_series
from scripts.evaluate_tier1_events import evaluate as evaluate_events
from src import db
from src.config import load_config


def _config():
    cfg = deepcopy(load_config())
    cfg["backtest"]["burnin_days"] = 0
    cfg["backtest"]["min_team_matches"] = 0
    return cfg


def test_series_backtest_corrects_bo3_mislabeled_as_bo1():
    conn = db.connect(":memory:")
    db.upsert_matches(
        conn,
        [
            {
                "match_id": 1,
                "date": "2026-01-01",
                "ts": 1,
                "team_a": "A",
                "team_b": "B",
                "score_a": 2,
                "score_b": 0,
                "format": "bo1",
                "event": "Cup",
            }
        ],
    )
    result = run_series(_config(), conn)
    assert result["elo"]["A"] == 1420.0  # K=40 de BO3, não K=32 de BO1
    assert result["elo"]["B"] == 1380.0
    conn.close()


def test_map_backtest_starts_from_neutral_prequential_seed():
    conn = db.connect(":memory:")
    db.upsert_matches(
        conn,
        [
            {
                "match_id": 1,
                "date": "2026-01-01",
                "ts": 1,
                "team_a": "Vitality",
                "team_b": "MOUZ",
                "score_a": 1,
                "score_b": 0,
                "format": "bo1",
                "event": "Cup",
            }
        ],
    )
    db.upsert_match_maps(
        conn,
        1,
        [
            {
                "map_name": "Mirage",
                "team_a": "Vitality",
                "team_b": "MOUZ",
                "score_a": 13,
                "score_b": 10,
            }
        ],
    )
    result = run_map(_config(), conn)
    assert result["seed"] == "neutral 1400"
    assert result["mp"].elo("Vitality", "Mirage") == 1416.0
    assert result["mp"].elo("MOUZ", "Mirage") == 1384.0
    conn.close()


def test_event_evaluator_skips_tie_before_format_inference():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        create table matches (match_id integer, date text, ts integer,
          team_a text, team_b text, score_a integer, score_b integer,
          format text, event text);
        create table match_maps (match_id integer, seq integer, map_name text,
          team_a text, team_b text, score_a integer, score_b integer);
        insert into matches values (1,'2026-01-01',1,'A','B',12,12,'bo1','Cup');
    """)
    result = evaluate_events(conn, {"Cup"})
    assert result["events"]["Cup"]["h1"] == {"n": 0}
    conn.close()
