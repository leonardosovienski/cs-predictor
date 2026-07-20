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
from .config import ROOT, identity_key, load_config, load_teams, resolve_team

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
    if result_a == result_b:
        # 1-1 seria um BO2 (formato sem vencedor, fora do escopo bo1/bo3/bo5);
        # qualquer outro empate é série anulada/abandonada — nunca atualizar Elo
        raise ValueError(
            f"placar {result_a}-{result_b} sem vencedor (BO2/empate não suportado)")
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


def _wins(placar: str) -> tuple[int, int]:
    wa, wb = placar.split("-")
    return int(wa), int(wb)


def series_win_prob(score_probs: dict) -> float:
    """P(A vence a série) = soma dos placares em que A fecha."""
    return sum(pr for placar, pr in score_probs.items()
               if _wins(placar)[0] > _wins(placar)[1])


def expected_maps(score_probs: dict) -> float:
    """Total esperado de mapas jogados sob a distribuição de placares."""
    return sum(sum(_wins(placar)) * pr for placar, pr in score_probs.items())


def cover_probability(score_probs: dict, handicap: float,
                      *, side_a: bool = True) -> tuple[float, float]:
    """(P cobrir, P push) do lado escolhido para `handicap` de mapas.

    score_probs na perspectiva de A ("wa-wb"). side_a=False cobre para B —
    NÃO é o complemento de side_a=True (A cobrir -1.5 é vencer 2-0, B cobrir
    -1.5 também é vencer 2-0). Push (empate exato no handicap) só existe em
    linha inteira (ex.: -1.0 com 2-1) e não conta como coberto."""
    covered = push = 0.0
    for placar, pr in score_probs.items():
        wa, wb = _wins(placar)
        w, l = (wa, wb) if side_a else (wb, wa)
        margin = w + handicap - l
        if margin > 0:
            covered += pr
        elif margin == 0:
            push += pr
    return covered, push


def calibrate_score_probs(score_probs: dict, prob_raw: float,
                          prob_cal: float) -> dict:
    """Reescala a distribuição de placares para que P(A vence a série)
    calibrada (Platt) e a combinatória contem a MESMA história: placares em
    que A fecha são multiplicados por prob_cal/prob_raw e os demais por
    (1-prob_cal)/(1-prob_raw) — a forma condicional ao vencedor é preservada.
    Sem isso, handicap/mapas esperados derivariam da distribuição crua e
    contradiriam a probabilidade servida."""
    eps = 1e-9
    scale_a = prob_cal / max(prob_raw, eps)
    scale_b = (1.0 - prob_cal) / max(1.0 - prob_raw, eps)
    return {placar: pr * (scale_a if _wins(placar)[0] > _wins(placar)[1]
                          else scale_b)
            for placar, pr in score_probs.items()}


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
        # (times que só entram na base pelo histórico real de partidas).
        # Caixa exata primeiro: o HLTV tem organizações DISTINTAS cujos nomes
        # diferem só pela caixa (LEO/Leo, CHAOS/Chaos, WINNERS/Winners) —
        # casamento case-insensitive aqui só é aceito quando é único.
        stripped = name.strip()
        if stripped in self.ratings:
            return stripped, self.ratings[stripped]
        low = identity_key(stripped)
        exact_ci = [official for official in self.ratings
                    if identity_key(official) == low]
        if len(exact_ci) == 1:
            return exact_ci[0], self.ratings[exact_ci[0]]
        if len(exact_ci) > 1:
            raise ValueError(
                f"nome ambíguo: {name!r} corresponde a entidades distintas "
                f"{exact_ci} — use a caixa exata")
        hits = [official for official in self.ratings
                if low in identity_key(official)]
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
        raw = series_probs(p_map, fmt)
        prob_a = series_win_prob(raw)
        # O Platt foi ajustado na PROBABILIDADE DE SÉRIE; a distribuição de
        # placares é reescalada para contar a mesma história (handicap e
        # mapas esperados coerentes com a probabilidade servida)
        prob_cal = self.platt.apply(prob_a) if self.platt else prob_a
        dist = (calibrate_score_probs(raw, prob_a, prob_cal)
                if self.platt else raw)
        out = {"team_a": a, "team_b": b, "format": fmt,
               "elo_a": round(elo_a, 1), "elo_b": round(elo_b, 1),
               "p_map_a": round(p_map, 4),
               "prob_team_a": round(prob_cal, 4),
               "prob_team_b": round(1.0 - prob_cal, 4),
               "prob_team_a_raw": round(prob_a, 4),
               "mapas_esperados": round(expected_maps(dist), 2),
               "score_probs": {s: round(pr, 4) for s, pr in dist.items()},
               "model": "elo-platt-fase1" if self.platt else "elo-fase0"}
        if self.platt:
            out["score_probs_raw"] = {s: round(pr, 4) for s, pr in raw.items()}
        return out

    def predict_handicap(self, team_a: str, team_b: str,
                         handicap: float, format: str = "bo3") -> dict:
        """P(team_a cobrir o handicap de MAPAS). Ex.: −1.5 em BO3 = vencer
        2-0; +1.5 = não perder 0-2. Só faz sentido em série (bo3/bo5)."""
        fmt = format.lower()
        if fmt == "bo1":
            raise ValueError("handicap de mapas não se aplica a BO1")
        r = self.predict_match(team_a, team_b, fmt)
        covered, push = cover_probability(r["score_probs"], handicap)
        out = {"team_a": r["team_a"], "team_b": r["team_b"], "format": fmt,
               "handicap": handicap, "p_cover": round(covered, 4),
               "p_not_cover": round(1.0 - covered - push, 4)}
        if push > 0:
            out["p_push"] = round(push, 4)
        return out

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
