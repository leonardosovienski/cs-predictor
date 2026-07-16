"""Experimental pre-event map model with temporal shrinkage and veto proxy.

This is deliberately independent from ``MapEloModel`` and canonical H1/H2.
Map ratings decay toward the current series Elo and are shrunk when a team has
few observations on that map.  The veto proxy only sees maps played before the
current series; it is an approximation, not a record of picks and bans.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from math import exp, log

from .model import win_probability
from .model_maps import MAP_K, series_probs_hetero


@dataclass
class _Rating:
    value: float
    last_ts: int
    observations: int


class ShrunkMapElo:
    def __init__(self, *, half_life_days: float = 60.0, prior_maps: float = 12.0):
        if half_life_days <= 0 or prior_maps <= 0:
            raise ValueError("half_life_days e prior_maps devem ser positivos")
        self.half_life_days = half_life_days
        self.prior_maps = prior_maps
        self._ratings: dict[tuple[str, str], _Rating] = {}

    def rating(self, team: str, map_name: str, *, base_elo: float, now_ts: int) -> float:
        row = self._ratings.get((team, map_name))
        if row is None:
            return base_elo
        days = max(0.0, (now_ts - row.last_ts) / 86400.0)
        decayed = base_elo + (row.value - base_elo) * exp(-log(2) * days / self.half_life_days)
        weight = row.observations / (row.observations + self.prior_maps)
        return base_elo + weight * (decayed - base_elo)

    def probability(self, team_a: str, team_b: str, map_name: str, *, base_a: float,
                    base_b: float, now_ts: int) -> float:
        return win_probability(self.rating(team_a, map_name, base_elo=base_a, now_ts=now_ts),
                               self.rating(team_b, map_name, base_elo=base_b, now_ts=now_ts))

    def update(self, team_a: str, team_b: str, map_name: str, score_a: int, score_b: int,
               *, base_a: float, base_b: float, now_ts: int) -> None:
        if score_a == score_b:
            return
        ra = self.rating(team_a, map_name, base_elo=base_a, now_ts=now_ts)
        rb = self.rating(team_b, map_name, base_elo=base_b, now_ts=now_ts)
        delta = MAP_K * ((1.0 if score_a > score_b else 0.0) - win_probability(ra, rb))
        old_a, old_b = self._ratings.get((team_a, map_name)), self._ratings.get((team_b, map_name))
        self._ratings[team_a, map_name] = _Rating(ra + delta, now_ts, 1 + (old_a.observations if old_a else 0))
        self._ratings[team_b, map_name] = _Rating(rb - delta, now_ts, 1 + (old_b.observations if old_b else 0))


class HistoricalVetoProxy:
    """Turns past map occurrence into explicitly labelled veto scenarios."""
    def __init__(self) -> None:
        self.team_maps: dict[str, Counter[str]] = defaultdict(Counter)
        self.global_maps: Counter[str] = Counter()

    def observe(self, team_a: str, team_b: str, map_name: str) -> None:
        self.team_maps[team_a][map_name] += 1
        self.team_maps[team_b][map_name] += 1
        self.global_maps[map_name] += 1

    def scenarios(self, team_a: str, team_b: str, *, max_maps: int = 7) -> list[dict]:
        pool = [name for name, _count in self.global_maps.most_common(max_maps)]
        if len(pool) < 3:
            return []
        total_a, total_b = sum(self.team_maps[team_a].values()), sum(self.team_maps[team_b].values())
        affinity = {name: ((self.team_maps[team_a][name] + 1) / (total_a + len(pool)) +
                           (self.team_maps[team_b][name] + 1) / (total_b + len(pool))) / 2
                    for name in pool}
        raw = [(list(combo), affinity[combo[0]] * affinity[combo[1]] * affinity[combo[2]])
               for combo in combinations(pool, 3)]
        norm = sum(weight for _maps, weight in raw)
        return [{"maps": maps, "weight": weight / norm} for maps, weight in raw]


def series_probability(model: ShrunkMapElo, team_a: str, team_b: str, scenarios: list[dict],
                       *, base_a: float, base_b: float, now_ts: int) -> float:
    if not scenarios:
        return 0.5
    total = 0.0
    for scenario in scenarios:
        probs = [model.probability(team_a, team_b, name, base_a=base_a, base_b=base_b, now_ts=now_ts)
                 for name in scenario["maps"]]
        p_series = sum(value for score, value in series_probs_hetero(probs, 2).items()
                       if int(score.split("-")[0]) > int(score.split("-")[1]))
        total += scenario["weight"] * p_series
    return total
