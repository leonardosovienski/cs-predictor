"""Modelo Elo — Fase 0. Ratings em tmp_path (nunca tocam data/ real)."""
import pytest

from src.model import EloModel, series_probs, win_probability


@pytest.fixture
def model(tmp_path):
    return EloModel(ratings_file=tmp_path / "ratings.json")


def test_predict_match_probabilidades_somam_1(model):
    r = model.predict_match("Vitality", "MOUZ", "bo3")
    assert abs(r["prob_team_a"] + r["prob_team_b"] - 1.0) < 1e-6
    # Vitality (#2, 1590) é favorito sobre MOUZ (#10, 1507)
    assert r["prob_team_a"] > 0.5
    assert abs(sum(r["score_probs"].values()) - 1.0) < 1e-6


def test_mapas_esperados_bo3_no_intervalo(model):
    r = model.predict_match("Vitality", "MOUZ", "bo3")
    assert 2.0 <= r["mapas_esperados"] <= 3.0
    r5 = model.predict_match("Vitality", "MOUZ", "bo5")
    assert 3.0 <= r5["mapas_esperados"] <= 5.0


def test_series_probs_fechadas():
    # p=0.5: BO3 → 2-0 25%, 2-1 25% (espelhado); esperados 2.5 mapas
    d = series_probs(0.5, "bo3")
    assert abs(d["2-0"] - 0.25) < 1e-9 and abs(d["2-1"] - 0.25) < 1e-9
    assert abs(sum(d.values()) - 1.0) < 1e-9
    d5 = series_probs(0.5, "bo5")
    assert abs(sum(d5.values()) - 1.0) < 1e-9


def test_favorito_maior_em_bo5_que_bo1(model):
    """Série mais longa favorece o favorito (menos variância)."""
    p1 = model.predict_match("Falcons", "Lynn Vision", "bo1")["prob_team_a"]
    p3 = model.predict_match("Falcons", "Lynn Vision", "bo3")["prob_team_a"]
    p5 = model.predict_match("Falcons", "Lynn Vision", "bo5")["prob_team_a"]
    assert p1 < p3 < p5


def test_update_ratings_vencedor_sobe(model):
    antes_a = model.ratings["Vitality"]
    antes_b = model.ratings["MOUZ"]
    out = model.update_ratings("Vitality", "MOUZ", 2, 1)
    assert out["format"] == "bo3" and out["k"] == 40
    assert model.ratings["Vitality"] > antes_a
    assert model.ratings["MOUZ"] < antes_b
    # soma conservada (Elo é jogo de soma zero)
    assert abs((model.ratings["Vitality"] + model.ratings["MOUZ"])
               - (antes_a + antes_b)) < 1e-9


def test_update_ratings_zebra_move_mais_que_favorito_vencendo(model):
    """Vitória do azarão desloca mais pontos que a do favorito (mesmo K)."""
    m1 = EloModel(ratings_file=model.path.with_name("r1.json"))
    fav = m1.update_ratings("Falcons", "Lynn Vision", 2, 0)      # esperado
    m2 = EloModel(ratings_file=model.path.with_name("r2.json"))
    zebra = m2.update_ratings("Lynn Vision", "Falcons", 2, 0)    # upset
    assert abs(zebra["delta"]) > abs(fav["delta"])


def test_update_persiste_e_recarrega(model, tmp_path):
    model.update_ratings("Vitality", "MOUZ", 2, 0)
    recarregado = EloModel(ratings_file=model.path)
    assert recarregado.ratings["Vitality"] == model.ratings["Vitality"]


def test_k_por_formato_inferido(model):
    assert model.update_ratings("BIG", "Liquid", 1, 0)["k"] == 32       # bo1
    assert model.update_ratings("BIG", "Liquid", 3, 2)["k"] == 48       # bo5


def test_handicap_bo3(model):
    r = model.predict_match("Falcons", "Lynn Vision", "bo3")
    hc = model.predict_handicap("Falcons", "Lynn Vision", -1.5, "bo3")
    # cobrir -1.5 em BO3 = vencer 2-0 exatamente
    assert abs(hc["p_cover"] - r["score_probs"]["2-0"]) < 1e-6
    hc_dog = model.predict_handicap("Lynn Vision", "Falcons", +1.5, "bo3")
    # +1.5 do azarão = complemento do 2-0 do favorito
    assert abs(hc_dog["p_cover"] - (1.0 - r["score_probs"]["2-0"])) < 1e-6
    with pytest.raises(ValueError):
        model.predict_handicap("Falcons", "Lynn Vision", -1.5, "bo1")


def test_time_desconhecido_e_formato_invalido(model):
    with pytest.raises(ValueError):
        model.predict_match("Time Fantasma", "MOUZ")
    with pytest.raises(ValueError):
        model.predict_match("Vitality", "MOUZ", "bo7")
    with pytest.raises(ValueError):
        model.predict_match("MOUZ", "mouz")     # mesmo time
