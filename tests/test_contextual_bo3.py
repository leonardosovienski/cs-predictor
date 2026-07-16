from __future__ import annotations

import pytest

from src.contextual_bo3 import ContextError, predict_contextual_bo3
from src.model import EloModel
from src.model_maps import MapEloModel, predict_series_with_maps


@pytest.fixture
def maps(tmp_path):
    base = EloModel(ratings_file=tmp_path / "ratings.json")
    return MapEloModel(ratings_file=tmp_path / "maps.json", base=base)


def _context(**changes):
    base = {"team_a": {"lineup_status": "confirmed", "days_since_last": 2, "core_matches": 10},
            "team_b": {"lineup_status": "confirmed", "days_since_last": 3, "core_matches": 8}}
    base.update(changes)
    return base


def test_single_veto_scenario_matches_map_model_and_is_read_only(maps):
    before = dict(maps.ratings)
    direct = predict_series_with_maps(maps, "Vitality", "MOUZ", ["Mirage", "Inferno", "Nuke"], "bo3")
    result = predict_contextual_bo3(model=maps, team_a="Vitality", team_b="MOUZ",
                                    veto_scenarios=[{"maps": ["Mirage", "Inferno", "Nuke"], "weight": 1.0}],
                                    context=_context())
    assert result["prob_team_a"] == direct["prob_team_a"]
    assert result["context"]["context_status"] == "VERIFIED"
    assert result["audit_metadata"]["ratings_write"] is False
    assert maps.ratings == before


def test_aggregates_veto_scenarios_and_context_flags(maps):
    maps.update("Vitality", "MOUZ", "Mirage", 13, 5)
    result = predict_contextual_bo3(
        model=maps, team_a="Vitality", team_b="MOUZ",
        veto_scenarios=[{"maps": ["Mirage", "Inferno", "Nuke"], "weight": 0.6},
                        {"maps": ["Ancient", "Anubis", "Nuke"], "weight": 0.4}],
        context=_context(team_b={"lineup_status": "changed", "days_since_last": 25, "core_matches": 2}),
    )
    assert abs(sum(result["score_probs"].values()) - 1.0) < 1e-3
    assert result["context"]["context_status"] == "BLOCKED"
    assert len(result["context"]["warnings"]) == 3
    assert result["context"]["model_adjustment_applied"] is False


@pytest.mark.parametrize("scenarios", [[], [{"maps": ["Mirage", "Nuke"], "weight": 1.0}],
                                         [{"maps": ["Mirage", "Nuke", "Inferno"], "weight": 0.9}]])
def test_rejects_invalid_veto_scenarios(maps, scenarios):
    with pytest.raises(ContextError):
        predict_contextual_bo3(model=maps, team_a="Vitality", team_b="MOUZ", veto_scenarios=scenarios)
