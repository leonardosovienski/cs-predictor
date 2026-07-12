"""Elo POR MAPA (extensão Fase 1+ prevista em model.py) — força de cada
time em cada mapa individual (Mirage, Inferno, Ancient, ...), separado do
Elo de série usado no serving atual.

Por que não é só o Elo de série replicado: dois times podem ter Elo de
série parecido mas força bem diferente mapa a mapa (ex.: time forte em
Mirage e fraco em Anubis). O Elo de série trata todo mapa como i.i.d.
(mesma p em qualquer mapa) — aqui cada (time, mapa) tem seu próprio rating.

Semente: quando um (time, mapa) ainda não tem histórico, herda o Elo de
SÉRIE do time (data/ratings.json) — não parte de zero. K único por mapa
(não por formato — o mapa é o evento atômico aqui): MAP_K.

Persistência: data/ratings_maps.json = {"Time||Mapa": elo}.
"""
import json
from pathlib import Path

from .config import ROOT, load_config
from .model import EloModel, win_probability

MAP_K = 32
_SEP = "||"


def _key(team: str, map_name: str) -> str:
    return f"{team}{_SEP}{map_name}"


class MapEloModel:
    """Ratings Elo por (time, mapa). `base` é o EloModel de série — usado
    só como semente para pares (time, mapa) nunca vistos."""

    def __init__(self, ratings_file: Path | str | None = None,
                 base: EloModel | None = None):
        cfg = load_config()
        self.base = base or EloModel()
        self.path = Path(ratings_file) if ratings_file else (
            ROOT / cfg.get("ratings_maps_file", "data/ratings_maps.json"))
        self.ratings: dict[str, float] = {}
        if self.path.exists():
            self.ratings = json.loads(self.path.read_text(encoding="utf-8"))

    def _seed(self, team: str) -> float:
        try:
            _, elo = self.base._elo(team)
            return elo
        except ValueError:
            return float(self.base.ratings and
                         next(iter(self.base.ratings.values())) or 1400.0)

    def elo(self, team: str, map_name: str) -> float:
        k = _key(team, map_name)
        if k in self.ratings:
            return self.ratings[k]
        return self._seed(team)

    def win_probability(self, team_a: str, team_b: str, map_name: str) -> float:
        return win_probability(self.elo(team_a, map_name),
                               self.elo(team_b, map_name))

    def update(self, team_a: str, team_b: str, map_name: str,
              score_a: int, score_b: int) -> None:
        """Atualiza o rating (time, mapa) dos dois lados após UM mapa
        jogado. y=1 se A venceu o mapa (mais rounds)."""
        if score_a == score_b:
            return
        ea = self.elo(team_a, map_name)
        eb = self.elo(team_b, map_name)
        y = 1.0 if score_a > score_b else 0.0
        e_a = win_probability(ea, eb)
        delta = MAP_K * (y - e_a)
        self.ratings[_key(team_a, map_name)] = ea + delta
        self.ratings[_key(team_b, map_name)] = eb - delta

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({k: round(v, 1) for k, v in sorted(self.ratings.items())},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def series_probs_hetero(probs: list[float], need: int) -> dict:
    """Distribuição exata do placar de uma série dado o mapa a mapa JÁ
    ORDENADO (probs[i] = P(A vence o mapa i+1), heterogêneo — generaliza
    model.series_probs, que assume p igual em todo mapa). `need` = mapas
    para fechar (1=bo1, 2=bo3, 3=bo5). Combinatória exata via DP: estado
    (vitórias de A, vitórias de B) após cada mapa jogado na ORDEM dada.

    Retorna {"wa-wb": probabilidade} na perspectiva de A, só placares
    finais (onde um dos dois lados chega em `need`)."""
    from collections import defaultdict
    dist = {(0, 0): 1.0}
    final: dict[tuple[int, int], float] = defaultdict(float)
    for p in probs:
        nxt: dict[tuple[int, int], float] = defaultdict(float)
        for (wa, wb), pr in dist.items():
            if wa == need or wb == need:
                final[(wa, wb)] += pr
                continue
            nxt[(wa + 1, wb)] += pr * p
            nxt[(wa, wb + 1)] += pr * (1 - p)
        dist = nxt
    for st, pr in dist.items():
        final[st] += pr
    return {f"{wa}-{wb}": pr for (wa, wb), pr in final.items() if pr > 0}
