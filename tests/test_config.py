"""Config e times — identidade do domínio CS."""
import pytest

from src.config import load_config, load_teams, resolve_team


def test_config_dominio_cs():
    cfg = load_config()
    assert cfg["game"] == "CS2"
    assert cfg["default_format"] == "bo3"
    assert cfg["k_factor_base"] == 32
    assert cfg["bankroll"] == 1000 and cfg["stake_unit"] == 50


def test_top30_unico_e_elo_decrescente():
    teams = load_teams()
    assert len(teams) == 30
    assert len({t["name"] for t in teams}) == 30
    elos = [t["initial_elo"] for t in sorted(teams, key=lambda t: t["hltv_rank"])]
    assert elos[0] == 1600 and elos[-1] == 1300
    assert all(a >= b for a, b in zip(elos, elos[1:]))   # monotônico


def test_resolve_team_substring_e_erro():
    assert resolve_team("vitality")["hltv_rank"] == 2
    assert resolve_team("Mongol")["name"] == "The MongolZ"
    with pytest.raises(ValueError):
        resolve_team("Time Fantasma")
