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
_NEED = {"bo1": 1, "bo3": 2, "bo5": 3}


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


def predict_series_with_maps(mp: "MapEloModel", team_a: str, team_b: str,
                             maps: list[str], fmt: str) -> dict:
    """Previsão de série usando o Elo POR MAPA nos mapas reais do
    veto/pool (em vez do Elo de série único tratando todo mapa como
    igual). `maps` na ordem em que serão jogados (ou pool restante, se a
    ordem exata ainda não é conhecida — a prob. de série não depende da
    ordem, só o placar mapa-a-mapa individual reportado depende)."""
    fmt = fmt.lower()
    if fmt not in _NEED:
        raise ValueError(f"formato desconhecido: {fmt!r} (use bo1/bo3/bo5)")
    need = _NEED[fmt]
    required = 2 * need - 1
    if len(maps) != required:
        raise ValueError(f"{fmt} precisa de exatamente {required} mapa(s) potenciais "
                         f"informado(s), recebi {len(maps)}")
    a, _ = mp.base._elo(team_a)
    b, _ = mp.base._elo(team_b)
    if a == b:
        raise ValueError("um time não joga contra si mesmo")
    p_por_mapa = [mp.win_probability(a, b, m) for m in maps]
    dist = series_probs_hetero(p_por_mapa, need)
    prob_a = sum(pr for placar, pr in dist.items()
                 if int(placar.split("-")[0]) > int(placar.split("-")[1]))
    mapas_esp = sum((int(s.split("-")[0]) + int(s.split("-")[1])) * pr
                    for s, pr in dist.items())
    prob_cal = mp.base.platt.apply(prob_a) if mp.base.platt else prob_a
    return {"team_a": a, "team_b": b, "format": fmt,
            "maps": list(maps),
            "elo_por_mapa": {m: {a: round(mp.elo(a, m), 1),
                                  b: round(mp.elo(b, m), 1)} for m in maps},
            "p_por_mapa": {m: round(p, 4) for m, p in zip(maps, p_por_mapa)},
            "prob_team_a": round(prob_cal, 4),
            "prob_team_b": round(1.0 - prob_cal, 4),
            "prob_team_a_raw": round(prob_a, 4),
            "mapas_esperados": round(mapas_esp, 2),
            "score_probs": {s: round(pr, 4) for s, pr in dist.items()},
            "model": "elo-mapa-platt-h3" if mp.base.platt else "elo-mapa-h3"}


def series_probs_hetero(probs: list[float], need: int) -> dict:
    """Distribuição exata do placar de uma série dado o mapa a mapa JÁ
    ORDENADO (probs[i] = P(A vence o mapa i+1), heterogêneo — generaliza
    model.series_probs, que assume p igual em todo mapa). `need` = mapas
    para fechar (1=bo1, 2=bo3, 3=bo5). Combinatória exata via DP: estado
    (vitórias de A, vitórias de B) após cada mapa jogado na ORDEM dada.

    Retorna {"wa-wb": probabilidade} na perspectiva de A, só placares
    finais (onde um dos dois lados chega em `need`)."""
    if not isinstance(need, int) or isinstance(need, bool) or need < 1:
        raise ValueError("need deve ser inteiro positivo")
    required = 2 * need - 1
    if len(probs) != required:
        raise ValueError(f"série até {need} exige exatamente {required} probabilidades")
    if any(isinstance(p, bool) or not isinstance(p, (int, float)) or not 0.0 <= p <= 1.0
           for p in probs):
        raise ValueError("probabilidades devem estar entre 0 e 1")
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
