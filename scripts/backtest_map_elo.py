"""Backtest PREQUENTIAL do Elo POR MAPA (H3-CS) — banco read-only.

Mesma disciplina do backtest de série (Fase 1): mapa a mapa em ordem
cronológica, PREVER antes de ATUALIZAR, sem lookahead. Testa se o Elo
(time, mapa) prevê o vencedor de um mapa individual melhor que o Elo de
SÉRIE aplicado uniformemente a qualquer mapa (a suposição i.i.d. da
Fase 0/1).

H3-CS: Brier do Elo por mapa < Brier do Elo de série (mesmo par de times,
mesmo jogo) + Diebold-Mariano p<0.05. Burn-in por data (como no H1) fora
da janela de medição; requer que os DOIS times já tenham >= min_map_obs
observações NAQUELE MAPA especificamente (senão a semente = Elo de série
e a comparação seria com ela mesma).

Somente com ``--write-artifacts`` materializa data/ratings_maps.json.

Saída: data/map_elo_summary.json + relatório no stdout.
"""
import json
import argparse
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from src import db                                     # noqa: E402
from src.config import load_config                     # noqa: E402
from src.model import EloModel, K_FACTORS, infer_format, win_probability  # noqa: E402
from src.model_maps import MapEloModel                  # noqa: E402
from predictor_core.measurement.metrics import (        # noqa: E402
    brier, diebold_mariano, log_loss)

MIN_MAP_OBS = 3   # observações mínimas NAQUELE (time, mapa) pra entrar na medição


def _ln(p, eps=1e-12):
    import math
    return math.log(min(max(p, eps), 1.0))


def run(cfg, conn):
    default = float(cfg.get("backtest", {}).get("default_seed_elo", 1400.0))
    matches = conn.execute(
        "SELECT match_id, date, ts, team_a, team_b, score_a, score_b, format "
        "FROM matches ORDER BY date, ts, match_id").fetchall()
    if not matches:
        sys.exit("matches vazio — rode python -m src.ingest_hltv")
    teams = {name for row in matches for name in (row[3], row[4])}
    # Elo neutro e reconstruído cronologicamente. Não carrega ratings.json nem
    # o Top 30 futuro como semente do histórico.
    base = EloModel(ratings_file=ROOT / "data" / ".backtest-neutral-missing.json")
    base.ratings = {team: default for team in teams}
    base.platt = None
    mp = MapEloModel(base=base)
    mp.ratings = {}                            # zera: recomputa do zero aqui

    seen_map = defaultdict(int)                # (team,map) -> observações vistas

    map_rows = conn.execute(
        "SELECT match_id, seq, map_name, team_a, team_b, score_a, score_b "
        "FROM match_maps ORDER BY match_id, seq").fetchall()
    if not map_rows:
        sys.exit("match_maps vazio — rode python -m src.ingest_hltv_maps")
    maps_by_match = defaultdict(list)
    for row in map_rows:
        maps_by_match[row[0]].append(row[1:])
    burnin = int(cfg.get("backtest", {}).get("burnin_days", 0))
    cut = (datetime.fromisoformat(matches[0][1])
           + timedelta(days=burnin)).strftime("%Y-%m-%d")

    probs_map, probs_serie, outs, loss_map, loss_serie = [], [], [], [], []
    for mid, d, _ts, a, b, series_a, series_b, stored_fmt in matches:
        ea, eb = base.ratings[a], base.ratings[b]
        p_serie = win_probability(ea, eb)
        for _seq, mapa, map_a, map_b, sa, sb in maps_by_match.get(mid, []):
            if sa == sb:
                continue
            y = 1.0 if sa > sb else 0.0
            p_map_model = mp.win_probability(map_a, map_b, mapa)
            # O baseline usa o Elo pré-série na mesma orientação do mapa.
            if (map_a, map_b) == (a, b):
                p_series_map = p_serie
            elif (map_a, map_b) == (b, a):
                p_series_map = 1.0 - p_serie
            else:
                raise ValueError(f"times do mapa não correspondem à série {mid}")
            ka, kb = seen_map[(map_a, mapa)], seen_map[(map_b, mapa)]
            if d >= cut and ka >= MIN_MAP_OBS and kb >= MIN_MAP_OBS:
                probs_map.append([p_map_model, 1 - p_map_model])
                probs_serie.append([p_series_map, 1 - p_series_map])
                outs.append(0 if y == 1.0 else 1)
                loss_map.append(-_ln(p_map_model if y == 1.0 else 1 - p_map_model))
                loss_serie.append(-_ln(p_series_map if y == 1.0 else 1 - p_series_map))
            mp.update(map_a, map_b, mapa, sa, sb)
            seen_map[(map_a, mapa)] += 1
            seen_map[(map_b, mapa)] += 1
        # Só depois de prever/atualizar todos os mapas a série entra no Elo-base.
        if series_a != series_b:
            fmt = infer_format(series_a, series_b, stored_fmt)
            delta = K_FACTORS[fmt] * ((1.0 if series_a > series_b else 0.0) - p_serie)
            base.ratings[a], base.ratings[b] = ea + delta, eb - delta

    return {"probs_map": probs_map, "probs_serie": probs_serie, "outs": outs,
            "loss_map": loss_map, "loss_serie": loss_serie,
            "mp": mp, "n_total": len(map_rows), "seed": f"neutral {default:.0f}"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backtest prequential H3 (read-only por padrão)")
    parser.add_argument("--write-artifacts", action="store_true",
                        help="autoriza atualizar ratings_maps.json e map_elo_summary.json")
    args = parser.parse_args(argv)
    cfg = load_config()
    conn = db.connect(str(ROOT / cfg.get("database", "data/cs.db")), read_only=True)
    r = run(cfg, conn)
    n = len(r["outs"])
    print(f"PREQUENTIAL MAPA — {r['n_total']} mapas processados, "
          f"{n} na janela de medição (min {MIN_MAP_OBS} obs/par time-mapa)")

    summary = {"n_total": r["n_total"], "n_medidos": n}
    if n == 0:
        print("\n[aviso] janela de medição vazia — pouco histórico ainda "
              "por (time, mapa); materializando ratings_maps.json mesmo assim")
    else:
        br_map = brier(r["probs_map"], r["outs"])
        br_serie = brier(r["probs_serie"], r["outs"])
        ll_map = log_loss(r["probs_map"], r["outs"])
        ll_serie = log_loss(r["probs_serie"], r["outs"])
        acc = st.mean(1 if (p[0] >= 0.5) == (y == 0) else 0
                      for p, y in zip(r["probs_map"], r["outs"]))
        dm_stat, dm_p = diebold_mariano(r["loss_map"], r["loss_serie"])[:2]
        ok = br_map < br_serie and dm_p < 0.05
        print(f"\nH3-CS (vencedor do MAPA): Brier elo-mapa {br_map:.4f} vs "
              f"elo-serie {br_serie:.4f} (coin-flip 0.5000)")
        print(f"  log-loss {ll_map:.4f} vs {ll_serie:.4f} | acerto {acc:.1%} | "
              f"DM stat {dm_stat:+.2f} p={dm_p:.4f}")
        print(f"  VEREDITO H3-CS: {'COMPROVADA' if ok else 'REFUTADA'} "
              f"(Brier menor E DM p<0.05)")
        summary["h3"] = {"brier_mapa": round(br_map, 4),
                          "brier_serie": round(br_serie, 4),
                          "logloss_mapa": round(ll_map, 4),
                          "logloss_serie": round(ll_serie, 4),
                          "acerto": round(acc, 4),
                          "dm_stat": round(dm_stat, 3), "dm_p": round(dm_p, 5),
                          "verdict": "COMPROVADA" if ok else "REFUTADA"}

    if args.write_artifacts:
        r["mp"].save()
        print(f"\nserving materializado: ratings_maps.json "
              f"({len(r['mp'].ratings)} pares time-mapa)")
        (ROOT / "data" / "map_elo_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("artefato: map_elo_summary.json")
    else:
        print("\nread-only: nenhum rating/artefato escrito; use --write-artifacts com autorização")


if __name__ == "__main__":
    main()
