"""Modelo Elo — Fase 0. Ratings em tmp_path (nunca tocam data/ real)."""

import pytest

from src.model import EloModel, series_probs, update_series_pair


@pytest.mark.parametrize("elo_a", [1100.0, 1400.0, 1750.0])
@pytest.mark.parametrize("elo_b", [1150.0, 1400.0, 1800.0])
@pytest.mark.parametrize("score_a", [0.0, 1.0])
@pytest.mark.parametrize("expected_a", [0.01, 0.25, 0.5, 0.75, 0.99])
@pytest.mark.parametrize("k", [32.0, 40.0, 48.0])
def test_rating_book_adapter_is_exactly_compatible_with_legacy_update(
    elo_a, elo_b, score_a, expected_a, k
):
    new_a, new_b = update_series_pair(
        "A", "B", elo_a, elo_b, score_a=score_a, expected_a=expected_a, k=k
    )
    delta = k * (score_a - expected_a)
    assert new_a == elo_a + delta
    assert new_b == elo_b - delta


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
    assert abs((model.ratings["Vitality"] + model.ratings["MOUZ"]) - (antes_a + antes_b)) < 1e-9


def test_update_ratings_zebra_move_mais_que_favorito_vencendo(model):
    """Vitória do azarão desloca mais pontos que a do favorito (mesmo K)."""
    m1 = EloModel(ratings_file=model.path.with_name("r1.json"))
    fav = m1.update_ratings("Falcons", "Lynn Vision", 2, 0)  # esperado
    m2 = EloModel(ratings_file=model.path.with_name("r2.json"))
    zebra = m2.update_ratings("Lynn Vision", "Falcons", 2, 0)  # upset
    assert abs(zebra["delta"]) > abs(fav["delta"])


def test_update_persiste_e_recarrega(model, tmp_path):
    model.update_ratings("Vitality", "MOUZ", 2, 0)
    recarregado = EloModel(ratings_file=model.path)
    assert recarregado.ratings["Vitality"] == model.ratings["Vitality"]


def test_k_por_formato_inferido(model):
    assert model.update_ratings("BIG", "Liquid", 1, 0)["k"] == 32  # bo1
    assert model.update_ratings("BIG", "Liquid", 3, 2)["k"] == 48  # bo5


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
        model.predict_match("MOUZ", "mouz")  # mesmo time


def test_infer_format_rejeita_empate():
    """Empate nunca é placar terminal (1-1 seria BO2, fora do escopo);
    guard protege update_ratings de punir o time A como derrotado."""
    from src.model import infer_format

    for placar in ((1, 1), (12, 12), (0, 0)):
        with pytest.raises(ValueError):
            infer_format(*placar)


def test_update_ratings_rejeita_empate(model):
    antes = dict(model.ratings)
    with pytest.raises(ValueError):
        model.update_ratings("Vitality", "MOUZ", 1, 1)
    assert model.ratings == antes  # nada mutado


def test_calibrate_score_probs_consistente():
    """Distribuição reescalada soma 1 e sua prob de série é a calibrada."""
    from src.model import calibrate_score_probs, series_probs, series_win_prob

    raw = series_probs(0.7, "bo3")
    p_raw = series_win_prob(raw)
    p_cal = 0.62  # Platt achatou
    dist = calibrate_score_probs(raw, p_raw, p_cal)
    assert abs(sum(dist.values()) - 1.0) < 1e-9
    assert abs(series_win_prob(dist) - p_cal) < 1e-9
    # forma condicional ao vencedor preservada
    assert abs(dist["2-0"] / dist["2-1"] - raw["2-0"] / raw["2-1"]) < 1e-9


def test_handicap_inteiro_tem_push(model):
    """Linha inteira: 2-1 empata o handicap -1.0 (push, não coberto)."""
    hc = model.predict_handicap("Vitality", "MOUZ", -1.0, "bo3")
    r = model.predict_match("Vitality", "MOUZ", "bo3")
    assert abs(hc["p_push"] - r["score_probs"]["2-1"]) < 1e-6
    assert abs(hc["p_cover"] + hc["p_not_cover"] + hc["p_push"] - 1.0) < 1e-3


def test_handicap_meio_nao_tem_push(model):
    hc = model.predict_handicap("Vitality", "MOUZ", -1.5, "bo3")
    assert "p_push" not in hc
    assert abs(hc["p_cover"] + hc["p_not_cover"] - 1.0) < 1e-6
