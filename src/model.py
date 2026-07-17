"""Modelo Elo de CS2 — Fase 0 (esqueleto).

Por que Elo e não Poisson: CS é disputado em rounds (first to 13 no MR12),
mas modelar round a round exige dado detalhado que o esqueleto não tem. Elo
captura força relativa com base no histórico:

    P(A vence um MAPA) = 1 / (1 + 10^((elo_B − elo_A)/400))

O rating é interpretado POR MAPA; as probabilidades de série (BO1/BO3/BO5),
o total esperado de mapas e o handicap saem da combinatória da série com
mapas i.i.d. — simplificação declarada da Fase 0 (pontos fortes por mapa,
fator CT/TR e forma recente são extensões da Fase 1+).

K-factor por formato (prompt de criação): BO1=32, BO3=40, BO5=48.
"""
import json
from pathlib import Path

from .calibration import PlattCalibrator
from .config import ROOT, load_config, load_teams, resolve_team

K_FACTORS = {"bo1": 32, "bo3": 40, "bo5": 48}


def infer_format(result_a: int, result_b: int,
                 advertised: str | None = None) -> str:
    """Normaliza o formato usando placar terminal e rótulo da fonte.

    O HLTV pode mostrar o nome de um mapa no lugar de ``bo3``/``bo5`` na
    listagem. Placares 2-x e 3-x são, respectivamente, séries BO3 e BO5;
    placares maiores são rounds de um BO1 e preservam o rótulo BO1.
    """
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in (result_a, result_b)):
        raise ValueError("placar inválido")
    fmt = advertised.lower() if isinstance(advertised, str) else None
    if fmt not in K_FACTORS:
        fmt = None
    maximum = max(result_a, result_b)
    if maximum == 2:
        return "bo3"
    if maximum == 3:
        return "bo5"
    if fmt is not None:
        return fmt
    return "bo1"
# duração típica de parede de relógio por formato (matures_at do serving)
FORMAT_HOURS = {"bo1": 1.5, "bo3": 3.0, "bo5": 5.0}


def win_probability(elo_a: float, elo_b: float) -> float:
    """P(A vence um mapa) — logística clássica do Elo."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def series_probs(p: float, fmt: str) -> dict:
    """Distribuição exata do placar da série dado p = P(A vence um mapa).

    BO3:  2-0 = p²          | 2-1 = 2p²(1−p)        (espelhado para B)
    BO5:  3-0 = p³          | 3-1 = 3p³(1−p) | 3-2 = 6p³(1−p)²
    Retorna {placar: prob} com placares na perspectiva de A.
    """
    q = 1.0 - p
    if fmt == "bo1":
        return {"1-0": p, "0-1": q}
    if fmt == "bo3":
        return {"2-0": p * p, "2-1": 2 * p * p * q,
                "1-2": 2 * q * q * p, "0-2": q * q}
    if fmt == "bo5":
        return {"3-0": p ** 3, "3-1": 3 * p ** 3 * q,
                "3-2": 6 * p ** 3 * q * q,
                "2-3": 6 * q ** 3 * p * p, "1-3": 3 * q ** 3 * p,
                "0-3": q ** 3}
    raise ValueError(f"formato desconhecido: {fmt!r} (use bo1/bo3/bo5)")


class EloModel:
    """Ratings Elo dos times Tier 1/2 (semente = ranking HLTV linear).

    `ratings_file` (data/ratings.json), quando existir, sobrepõe as sementes —
    é onde update_ratings persiste a evolução após partidas reais."""

    def __init__(self, ratings_file: Path | str | None = None):
        cfg = load_config()
        self.ratings = {t["name"]: float(t["initial_elo"]) for t in load_teams()}
        self.path = Path(ratings_file) if ratings_file else (
            ROOT / cfg.get("ratings_file", "data/ratings.json"))
        if self.path.exists():
            self.ratings.update(json.loads(self.path.read_text(encoding="utf-8")))
        # Platt (tentativa N+1 comprovada): materializado por
        # scripts/backtest_calibracao.py; ausente → identidade (Fase 0/1 crua)
        self.platt = PlattCalibrator.load(
            ROOT / "data" / "calibration_platt.json")

    def _elo(self, name: str) -> tuple[str, float]:
        try:
            official = resolve_team(name)["name"]
            return official, self.ratings[official]
        except ValueError:
            pass
        # fora do Top 30 semeado, mas com Elo vivido em ratings.json
        # (times que só entram na base pelo histórico real de partidas)
        low = name.strip().lower()
        for official, elo in self.ratings.items():
            if official.lower() == low:
                return official, elo
        hits = [official for official in self.ratings
                if low in official.lower()]
        if len(hits) == 1:
            return hits[0], self.ratings[hits[0]]
        raise ValueError(f"time desconhecido: {name!r}"
                         + (f" — você quis dizer {hits}?" if hits else ""))

    def predict_match(self, team_a: str, team_b: str, format: str = "bo3") -> dict:
        fmt = format.lower()
        if fmt not in K_FACTORS:
            raise ValueError(f"formato desconhecido: {format!r} (use bo1/bo3/bo5)")
        a, elo_a = self._elo(team_a)
        b, elo_b = self._elo(team_b)
        if a == b:
            raise ValueError("um time não joga contra si mesmo")
        p_map = win_probability(elo_a, elo_b)
        dist = series_probs(p_map, fmt)
        prob_a = sum(pr for placar, pr in dist.items()
                     if int(placar.split("-")[0]) > int(placar.split("-")[1]))
        mapas = sum((int(s.split("-")[0]) + int(s.split("-")[1])) * pr
                    for s, pr in dist.items())
        # Platt calibra a PROBABILIDADE DE SÉRIE (o número apostável) — a
        # distribuição de placares e os mapas esperados seguem crus
        # (declarado: a sobreconfiança foi medida na prob de série)
        prob_cal = self.platt.apply(prob_a) if self.platt else prob_a
        return {"team_a": a, "team_b": b, "format": fmt,
                "elo_a": round(elo_a, 1), "elo_b": round(elo_b, 1),
                "p_map_a": round(p_map, 4),
                "prob_team_a": round(prob_cal, 4),
                "prob_team_b": round(1.0 - prob_cal, 4),
                "prob_team_a_raw": round(prob_a, 4),
                "mapas_esperados": round(mapas, 2),
                "score_probs": {s: round(pr, 4) for s, pr in dist.items()},
                "model": "elo-platt-fase1" if self.platt else "elo-fase0"}

    def predict_handicap(self, team_a: str, team_b: str,
                         handicap: float, format: str = "bo3") -> dict:
        """P(team_a cobrir o handicap de MAPAS). Ex.: −1.5 em BO3 = vencer
        2-0; +1.5 = não perder 0-2. Só faz sentido em série (bo3/bo5)."""
        fmt = format.lower()
        if fmt == "bo1":
            raise ValueError("handicap de mapas não se aplica a BO1")
        r = self.predict_match(team_a, team_b, fmt)
        dist = r["score_probs"]
        covered = 0.0
        for placar, pr in dist.items():
            wa, wb = (int(x) for x in placar.split("-"))
            if wa + handicap > wb:
                covered += pr
        return {"team_a": r["team_a"], "team_b": r["team_b"], "format": fmt,
                "handicap": handicap, "p_cover": round(covered, 4),
                "p_not_cover": round(1.0 - covered, 4)}

    def update_ratings(self, team_a: str, team_b: str,
                       result_a: int, result_b: int,
                       format: str | None = None) -> dict:
        """Atualiza o Elo após partida real, normalizando formato pelo placar
        terminal e pelo rótulo opcional da fonte. Persiste em ratings_file."""
        a, elo_a = self._elo(team_a)
        b, elo_b = self._elo(team_b)
        fmt = infer_format(result_a, result_b, format)
        k = K_FACTORS[fmt]
        s_a = 1.0 if result_a > result_b else 0.0
        e_a = win_probability(elo_a, elo_b)
        delta = k * (s_a - e_a)
        self.ratings[a] = elo_a + delta
        self.ratings[b] = elo_b - delta
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.ratings, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        return {"team_a": a, "team_b": b, "format": fmt, "k": k,
                "delta": round(delta, 2),
                "elo_a": round(self.ratings[a], 1),
                "elo_b": round(self.ratings[b], 1)}
