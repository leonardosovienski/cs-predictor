"""Contratos temporais dos backtests; banco sempre em memória."""
from copy import deepcopy

from scripts.backtest_map_elo import run as run_map
from scripts.backtest_walkforward import run as run_series
from src import db
from src.config import load_config


def _config():
    cfg = deepcopy(load_config())
    cfg["backtest"]["burnin_days"] = 0
    cfg["backtest"]["min_team_matches"] = 0
    return cfg


def test_series_backtest_corrects_bo3_mislabeled_as_bo1():
    conn = db.connect(":memory:")
    db.upsert_matches(conn, [{"match_id": 1, "date": "2026-01-01", "ts": 1,
                              "team_a": "A", "team_b": "B", "score_a": 2,
                              "score_b": 0, "format": "bo1", "event": "Cup"}])
    result = run_series(_config(), conn)
    assert result["elo"]["A"] == 1420.0  # K=40 de BO3, não K=32 de BO1
    assert result["elo"]["B"] == 1380.0


def test_map_backtest_starts_from_neutral_prequential_seed():
    conn = db.connect(":memory:")
    db.upsert_matches(conn, [{"match_id": 1, "date": "2026-01-01", "ts": 1,
                              "team_a": "Vitality", "team_b": "MOUZ",
                              "score_a": 1, "score_b": 0, "format": "bo1",
                              "event": "Cup"}])
    db.upsert_match_maps(conn, 1, [{"map_name": "Mirage", "team_a": "Vitality",
                                    "team_b": "MOUZ", "score_a": 13,
                                    "score_b": 10}])
    result = run_map(_config(), conn)
    assert result["seed"] == "neutral 1400"
    assert result["mp"].elo("Vitality", "Mirage") == 1416.0
    assert result["mp"].elo("MOUZ", "Mirage") == 1384.0
