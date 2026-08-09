"""Read-only contextual BO3 laboratory, kept separate from canonical serving.

This module never writes ratings, the database, or the prediction ledger.  It
combines pre-specified veto scenarios with the already materialized map Elo
ratings, then exposes lineup/freshness as *risk flags*, not unvalidated
probability adjustments.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .model import series_win_prob
from .model_maps import MapEloModel, predict_series_with_maps, series_probs_hetero


class ContextError(ValueError):
    """The supplied pre-match context is incomplete or inconsistent."""


_LINEUP_STATES = {"confirmed", "changed", "unconfirmed", "unknown"}


def _scenarios(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ContextError("BO3 contextual exige ao menos um cenário de veto")
    parsed: list[dict[str, Any]] = []
    for index, scenario in enumerate(value, 1):
        if not isinstance(scenario, dict):
            raise ContextError(f"cenário {index} inválido")
        maps, weight = scenario.get("maps"), scenario.get("weight")
        if (not isinstance(maps, list) or len(maps) != 3 or
                any(not isinstance(name, str) or not name.strip() for name in maps) or
                len({name.casefold() for name in maps}) != 3):
            raise ContextError(f"cenário {index} exige exatamente três mapas distintos")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            raise ContextError(f"cenário {index} exige peso positivo")
        parsed.append({"maps": [name.strip() for name in maps], "weight": float(weight)})
    total = sum(item["weight"] for item in parsed)
    if abs(total - 1.0) > 1e-9:
        raise ContextError("pesos dos cenários de veto devem somar 1")
    return parsed


def assess_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Validate operational context without tuning a probability by hand."""
    if context is None:
        return {"context_status": "BLOCKED", "warnings": ["contexto de lineup/recência ausente"],
                "model_adjustment_applied": False}
    if not isinstance(context, dict):
        raise ContextError("contexto inválido")
    warnings: list[str] = []
    for side in ("team_a", "team_b"):
        row = context.get(side)
        if not isinstance(row, dict):
            raise ContextError(f"contexto exige {side}")
        lineup = row.get("lineup_status", "unknown")
        days = row.get("days_since_last")
        core = row.get("core_matches")
        if lineup not in _LINEUP_STATES:
            raise ContextError(f"{side}.lineup_status inválido")
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            raise ContextError(f"{side}.days_since_last deve ser inteiro não-negativo")
        if not isinstance(core, int) or isinstance(core, bool) or core < 0:
            raise ContextError(f"{side}.core_matches deve ser inteiro não-negativo")
        if lineup != "confirmed":
            warnings.append(f"{side}: lineup {lineup}")
        if days >= 21:
            warnings.append(f"{side}: inatividade de {days} dias")
        if core < 5:
            warnings.append(f"{side}: somente {core} jogos do core atual")
    return {"context_status": "BLOCKED" if warnings else "VERIFIED", "warnings": warnings,
            "model_adjustment_applied": False}


def predict_contextual_bo3(*, model: MapEloModel, team_a: str, team_b: str,
                           veto_scenarios: list[dict[str, Any]],
                           context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aggregate explicitly supplied BO3 veto scenarios using map Elo.

    The Platt calibrator is applied once to the weighted raw series
    probability.  Applying it separately to each scenario would change the
    calibration contract and is deliberately avoided.
    """
    scenarios = _scenarios(veto_scenarios)
    score_probs: dict[str, float] = defaultdict(float)
    map_probs: dict[str, float] = defaultdict(float)
    raw_probability = 0.0
    expected_maps = 0.0
    rendered: list[dict[str, Any]] = []
    canonical_a = canonical_b = None
    for scenario in scenarios:
        forecast = predict_series_with_maps(model, team_a, team_b, scenario["maps"], "bo3")
        canonical_a, canonical_b = forecast["team_a"], forecast["team_b"]
        weight = scenario["weight"]
        # The rendered forecast intentionally rounds its public values. Using
        # that rounded probability as input to Platt can move the calibrated
        # result by one basis point. Aggregate the underlying map probabilities
        # at full precision so a single scenario is exactly the direct model.
        map_probabilities = [
            model.win_probability(canonical_a, canonical_b, name)
            for name in scenario["maps"]
        ]
        scenario_raw = series_win_prob(series_probs_hetero(map_probabilities, 2))
        raw_probability += weight * scenario_raw
        expected_maps += weight * forecast["mapas_esperados"]
        for score, probability in forecast["score_probs"].items():
            score_probs[score] += weight * probability
        for map_name, probability in forecast["p_por_mapa"].items():
            map_probs[map_name] += weight * probability
        rendered.append({"maps": scenario["maps"], "weight": weight,
                         "prob_team_a_raw": round(scenario_raw, 4)})
    calibrated = model.base.platt.apply(raw_probability) if model.base.platt else raw_probability
    return {
        "team_a": canonical_a, "team_b": canonical_b, "format": "bo3",
        "model": "elo-mapa-h3-veto-contextual-lab",
        "veto_scenarios": rendered,
        "prob_team_a_raw": round(raw_probability, 4),
        "prob_team_a": round(calibrated, 4), "prob_team_b": round(1.0 - calibrated, 4),
        "score_probs": {score: round(probability, 4) for score, probability in sorted(score_probs.items())},
        "map_win_probability_a": {name: round(probability, 4) for name, probability in sorted(map_probs.items())},
        "mapas_esperados": round(expected_maps, 2),
        "context": assess_context(context),
        "audit_metadata": {"database_write": False, "ratings_write": False,
                           "canonical_model_changed": False, "network_used": False},
    }
