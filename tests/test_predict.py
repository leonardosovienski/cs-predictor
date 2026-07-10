"""Serving (src/predict.py) — 3 confrontos, log isolado, PredictionPoint."""
import json
from datetime import datetime, timezone

import pytest

from src import predict

PARES = [("Vitality", "MOUZ"), ("Falcons", "Spirit"), ("FURIA", "paiN")]


@pytest.fixture(autouse=True)
def _isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("PREDICTIONS_LOG_PATH", str(tmp_path / "pred.jsonl"))
    monkeypatch.setenv("PREDICTOR_EVENTS_PATH", str(tmp_path / "events.jsonl"))
    yield


@pytest.mark.parametrize("a,b", PARES)
def test_saida_consistente(a, b):
    r = predict.run(a, b, fmt="bo3")
    assert abs(r["prob_team_a"] + r["prob_team_b"] - 1.0) < 1e-6
    assert 2.0 <= r["total_mapas_projetado"] <= 3.0
    assert "handicap_recomendado" in r


def test_carimbo_prediction_point_por_formato():
    now = datetime(2026, 7, 10, 22, 0, tzinfo=timezone.utc)
    r3 = predict.run("Vitality", "MOUZ", fmt="bo3", now=now)
    assert r3["matures_at"] == "2026-07-11T01:00:00+00:00"    # +3h
    r1 = predict.run("Vitality", "MOUZ", fmt="bo1", now=now)
    assert r1["matures_at"] == "2026-07-10T23:30:00+00:00"    # +1h30


def test_cli_json_valido(capsys):
    rc = predict.main(["Vitality", "MOUZ", "--format", "bo3", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert {"prob_team_a", "prob_team_b", "total_mapas_projetado",
            "handicap_recomendado"} <= set(out)


def test_cli_handicap_consultado(capsys):
    rc = predict.main(["FURIA", "paiN", "--handicap", "-1.5", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["handicap_consultado"]["handicap"] == -1.5


def test_cli_time_desconhecido_sai_2():
    assert predict.main(["Timeburgo", "MOUZ", "--json"]) == 2
