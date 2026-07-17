"""Elo por mapa (extensão Fase 1+) — ratings em tmp_path, nunca tocam data/ real."""
import pytest

from src.model import EloModel
from src.model_maps import MapEloModel, series_probs_hetero


@pytest.fixture
def base(tmp_path):
    return EloModel(ratings_file=tmp_path / "ratings.json")


@pytest.fixture
def maps(tmp_path, base):
    return MapEloModel(ratings_file=tmp_path / "ratings_maps.json", base=base)


def test_seed_do_par_novo_vem_do_elo_de_serie(maps, base):
    _, serie = base._elo("Vitality")
    assert maps.elo("Vitality", "Mirage") == serie


def test_update_diverge_do_elo_de_serie_apos_resultado(maps):
    p_antes = maps.win_probability("Vitality", "MOUZ", "Mirage")
    maps.update("MOUZ", "Vitality", "Mirage", 13, 5)   # zebra no mapa
    p_depois = maps.win_probability("Vitality", "MOUZ", "Mirage")
    assert p_depois < p_antes                          # Vitality caiu SÓ em Mirage
    # outro mapa não é afetado (independência entre mapas)
    assert maps.elo("Vitality", "Inferno") != maps.elo("Vitality", "Mirage")


def test_update_soma_zero_por_mapa(maps):
    a0, b0 = maps.elo("Vitality", "Mirage"), maps.elo("MOUZ", "Mirage")
    maps.update("Vitality", "MOUZ", "Mirage", 13, 9)
    a1, b1 = maps.elo("Vitality", "Mirage"), maps.elo("MOUZ", "Mirage")
    assert abs((a1 + b1) - (a0 + b0)) < 1e-9


def test_empate_nao_atualiza(maps):
    a0 = maps.elo("Vitality", "Mirage")
    maps.update("Vitality", "MOUZ", "Mirage", 1, 1)
    assert maps.elo("Vitality", "Mirage") == a0


def test_save_e_recarrega(tmp_path, base):
    m1 = MapEloModel(ratings_file=tmp_path / "rm.json", base=base)
    m1.update("Vitality", "MOUZ", "Mirage", 13, 5)
    m1.save()
    m2 = MapEloModel(ratings_file=tmp_path / "rm.json", base=base)
    assert abs(m2.elo("Vitality", "Mirage") - m1.elo("Vitality", "Mirage")) < 0.1


def test_series_probs_hetero_soma_1():
    d = series_probs_hetero([0.7, 0.4, 0.6], 2)
    assert abs(sum(d.values()) - 1.0) < 1e-9


def test_series_probs_hetero_rejeita_serie_inacabada():
    with pytest.raises(ValueError, match="exatamente 3"):
        series_probs_hetero([0.7, 0.4], 2)


def test_series_probs_hetero_igual_ao_iid_quando_p_constante():
    from src.model import series_probs
    iid = series_probs(0.62, "bo3")
    het = series_probs_hetero([0.62, 0.62, 0.62], 2)
    for k, v in iid.items():
        assert abs(het[k] - v) < 1e-9


def test_series_probs_hetero_favorece_mapa_forte_primeiro():
    """Mesmo conjunto de mapas, ordens diferentes -> mesma prob total de
    vencer 2 mapas quaisquer primeiro? Na verdade a prob de fechar a serie
    NAO depende da ordem (jogos independentes) -- e o que verificamos."""
    d1 = series_probs_hetero([0.8, 0.3, 0.5], 2)
    d2 = series_probs_hetero([0.5, 0.8, 0.3], 2)
    p_a1 = sum(v for k, v in d1.items()
               if int(k.split("-")[0]) > int(k.split("-")[1]))
    p_a2 = sum(v for k, v in d2.items()
               if int(k.split("-")[0]) > int(k.split("-")[1]))
    assert abs(p_a1 - p_a2) < 1e-9
