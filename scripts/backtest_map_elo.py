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

Ao final materializa data/ratings_maps.json.

Saída: data/map_elo_summary.json + relatório no stdout.
"""
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor"))

from src import db                                     # noqa: E402
from src.config import load_config                     # noqa: E402
from src.model import EloModel, win_probability         # noqa: E402
from src.model_maps import MapEloModel                  # noqa: E402
from predictor_core.measurement.metrics import (        # noqa: E402
    brier, diebold_mariano, log_loss)

MIN_MAP_OBS = 3   # observações mínimas NAQUELE (time, mapa) pra entrar na medição


def _ln(p, eps=1e-12):
    import math
    return math.log(min(max(p, eps), 1.0))


def run(cfg, conn):
    base = EloModel()                          # Elo de série vivido (baseline)
    mp = MapEloModel(base=base)
    mp.ratings = {}                            # zera: recomputa do zero aqui

    seen_map = defaultdict(int)                # (team,map) -> observações vistas

    rows = conn.execute(
        "SELECT mm.match_id, m.date, m.ts, mm.seq, mm.map_name, "
        "mm.team_a, mm.team_b, mm.score_a, mm.score_b "
        "FROM match_maps mm JOIN matches m ON m.match_id = mm.match_id "
        "ORDER BY m.date, m.ts, mm.match_id, mm.seq").fetchall()
    if not rows:
        sys.exit("match_maps vazio — rode python -m src.ingest_hltv_maps")
    burnin = int(cfg.get("backtest", {}).get("burnin_days", 0))
    cut = (datetime.fromisoformat(rows[0][1])
           + timedelta(days=burnin)).strftime("%Y-%m-%d")

    probs_map, probs_serie, outs, loss_map, loss_serie = [], [], [], [], []
    for mid, d, ts, seq, mapa, a, b, sa, sb in rows:
        if sa == sb:
            continue
        y = 1.0 if sa > sb else 0.0
        p_map_model = mp.win_probability(a, b, mapa)
        try:
            _, ea = base._elo(a)
            _, eb = base._elo(b)
            p_serie = win_probability(ea, eb)
        except ValueError:
            p_serie = 0.5

        ka, kb = seen_map[(a, mapa)], seen_map[(b, mapa)]
        if d >= cut and ka >= MIN_MAP_OBS and kb >= MIN_MAP_OBS:
            probs_map.append([p_map_model, 1 - p_map_model])
            probs_serie.append([p_serie, 1 - p_serie])
            outs.append(0 if y == 1.0 else 1)
            loss_map.append(-_ln(p_map_model if y == 1.0 else 1 - p_map_model))
            loss_serie.append(-_ln(p_serie if y == 1.0 else 1 - p_serie))

        mp.update(a, b, mapa, sa, sb)
        seen_map[(a, mapa)] += 1
        seen_map[(b, mapa)] += 1

    return {"probs_map": probs_map, "probs_serie": probs_serie, "outs": outs,
            "loss_map": loss_map, "loss_serie": loss_serie,
            "mp": mp, "n_total": len(rows)}


def main():
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

    r["mp"].save()
    print(f"\nserving materializado: ratings_maps.json "
          f"({len(r['mp'].ratings)} pares time-mapa)")
    (ROOT / "data" / "map_elo_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("artefato: map_elo_summary.json")


if __name__ == "__main__":
    main()
