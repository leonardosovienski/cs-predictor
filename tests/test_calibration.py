"""Platt scaling (tentativa N+1) — módulo e integração com o serving."""
import random

import pytest

from src.calibration import PlattCalibrator
from src.model import EloModel


def _amostra_sobreconfiante(n=2000, seed=13):
    """p previsto extremo demais: verdade = sigmoid(0.6·logit(p))."""
    import math
    rng = random.Random(seed)
    probs, outs = [], []
    for _ in range(n):
        p = rng.uniform(0.05, 0.95)
        z = math.log(p / (1 - p))
        p_true = 1 / (1 + math.exp(-0.6 * z))
        probs.append(p)
        outs.append(1 if rng.random() < p_true else 0)
    return probs, outs


def test_fit_recupera_achatamento():
    probs, outs = _amostra_sobreconfiante()
    cal = PlattCalibrator().fit(probs, outs)
    assert 0.4 < cal.a < 0.8          # recupera a≈0.6 (achatamento)
    # calibrado aproxima a verdade: extremo 0.9 tem que descer
    assert cal.apply(0.9) < 0.87


def test_apply_monotonico_e_identidade():
    cal = PlattCalibrator()           # sem fit = identidade
    assert cal.apply(0.7) == pytest.approx(0.7, abs=1e-9)
    cal2 = PlattCalibrator(a=0.68, b=0.1)
    ps = [cal2.apply(p) for p in (0.1, 0.3, 0.5, 0.7, 0.9)]
    assert ps == sorted(ps)           # monotônico


def test_save_load_roundtrip(tmp_path):
    cal = PlattCalibrator(a=0.6823, b=0.0958)
    cal.save(tmp_path / "p.json", meta={"trial": "teste"})
    carregado = PlattCalibrator.load(tmp_path / "p.json")
    assert carregado.a == pytest.approx(cal.a)
    assert PlattCalibrator.load(tmp_path / "nao_existe.json") is None


def test_fit_amostra_curta_erro():
    with pytest.raises(ValueError):
        PlattCalibrator().fit([0.5] * 5, [1] * 5)


def test_serving_aplica_platt_quando_materializado(tmp_path):
    """calibration_platt.json existe no repo (comprovada 2026-07-11):
    o predict_match reporta o modelo calibrado e preserva a prob crua."""
    m = EloModel(ratings_file=tmp_path / "r.json")
    r = m.predict_match("Vitality", "MOUZ", "bo3")
    if m.platt is None:
        pytest.skip("calibration_platt.json ausente neste checkout")
    assert r["model"] == "elo-platt-fase1"
    assert "prob_team_a_raw" in r
    # a<1: prob calibrada é MENOS extrema que a crua
    if r["prob_team_a_raw"] > 0.5:
        assert r["prob_team_a"] <= r["prob_team_a_raw"]
    assert abs(r["prob_team_a"] + r["prob_team_b"] - 1.0) < 1e-6
