"""Backtest PREQUENTIAL do cs-predictor (Fase 1) — banco read-only.

Desenho (sem lookahead por construção):
- séries do HLTV em ordem cronológica (date, ts); para cada uma, PREVER o
  vencedor antes de ATUALIZAR os ratings;
- Elo por MAPA (logística /400); P(série) via combinatória exata
  (model.series_probs) com o formato real da série; update com K por formato
  (32/40/48) sobre o resultado da série — exatamente o contrato do EloModel;
- semente neutra para todos os times (default_seed_elo); rankings publicados
  depois do início do histórico nunca entram no backtest;
- burn-in (backtest.burnin_days) fora da medição; métrica só conta série em
  que ambos os times têm >= min_team_matches de histórico;
- H1-CS: Brier/log-loss/calibração (core) do modelo vs baselines coin-flip
  e "ranking-semente congelado"; Diebold-Mariano modelo vs semente.

Somente com ``--write-artifacts`` materializa data/ratings.json (Elo vivido de
todos os times); por padrão o comando é estritamente read-only.

Saída: data/walkforward_summary.json + relatório no stdout.
"""

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from predictor_core.measurement.metrics import (  # noqa: E402
    brier,
    calibration_table,
    diebold_mariano,
    log_loss,
)

from src import db  # noqa: E402
from src.config import load_config  # noqa: E402
from src.model import (  # noqa: E402
    K_FACTORS,
    infer_format,
    series_probs,
    update_series_pair,
    win_probability,
)


def _ln(p, eps=1e-12):
    import math

    return math.log(min(max(p, eps), 1.0))


def _p_series(elo_a, elo_b, fmt):
    p_map = win_probability(elo_a, elo_b)
    dist = series_probs(p_map, fmt)
    return sum(
        pr for placar, pr in dist.items() if int(placar.split("-")[0]) > int(placar.split("-")[1])
    )


def run(cfg, conn):
    bt = cfg["backtest"]
    seed_default = float(bt["default_seed_elo"])
    min_m = int(bt["min_team_matches"])

    # O Top 30 versionado é de julho/2026 e seria informação futura para o
    # começo deste histórico. Ambos os braços começam neutros.
    elo: dict[str, float] = {}
    banda: dict[str, float] = {}
    seen = defaultdict(int)

    rows = conn.execute(
        "SELECT match_id, date, ts, team_a, team_b, score_a, score_b, format "
        "FROM matches ORDER BY date, ts, match_id"
    ).fetchall()
    if not rows:
        sys.exit("banco vazio — rode python -m src.ingest_hltv")
    cut = (datetime.fromisoformat(rows[0][1]) + timedelta(days=int(bt["burnin_days"]))).strftime(
        "%Y-%m-%d"
    )

    probs_m, probs_b, outs, loss_m, loss_b = [], [], [], [], []
    for _mid, d, _ts, a, b, sa, sb, fmt in rows:
        if sa == sb:
            continue  # série sem vencedor (dado quebrado)
        fmt = infer_format(sa, sb, fmt)
        ea, eb = elo.get(a, seed_default), elo.get(b, seed_default)
        p_model = _p_series(ea, eb, fmt)
        p_banda = _p_series(banda.get(a, seed_default), banda.get(b, seed_default), fmt)
        y = 0 if sa > sb else 1
        if d >= cut and seen[a] >= min_m and seen[b] >= min_m:
            probs_m.append([p_model, 1 - p_model])
            probs_b.append([p_banda, 1 - p_banda])
            outs.append(y)
            loss_m.append(-_ln(p_model if y == 0 else 1 - p_model))
            loss_b.append(-_ln(p_banda if y == 0 else 1 - p_banda))

        # Update por serie: observacao e expectativa usam a mesma unidade.
        k = K_FACTORS[fmt]
        # The observed outcome is a series winner; use the corresponding
        # series probability rather than the latent one-map probability.
        e_a = p_model
        elo[a], elo[b] = update_series_pair(
            a, b, ea, eb, score_a=1.0 if y == 0 else 0.0, expected_a=e_a, k=k
        )
        seen[a] += 1
        seen[b] += 1

    return {
        "probs_m": probs_m,
        "probs_b": probs_b,
        "outs": outs,
        "loss_m": loss_m,
        "loss_b": loss_b,
        "elo": elo,
        "n_total": len(rows),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backtest prequential H1 (read-only por padrão)")
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="autoriza atualizar ratings.json e walkforward_summary.json",
    )
    args = parser.parse_args(argv)
    cfg = load_config()
    conn = db.connect(str(ROOT / cfg["database"]), read_only=True)
    r = run(cfg, conn)
    n = len(r["outs"])
    print(f"PREQUENTIAL CS — {r['n_total']} séries processadas, {n} na janela de medição")

    summary = {"n_series": r["n_total"], "n_medidos": n}
    if n == 0:
        print(
            "\n[aviso] janela de medição vazia (amostra insuficiente para "
            "burn-in/min_team_matches nesta base) — pulando métricas H1, "
            "materializando apenas ratings.json com o Elo atualizado"
        )
    else:
        br_m = brier(r["probs_m"], r["outs"])
        br_b = brier(r["probs_b"], r["outs"])
        ll_m = log_loss(r["probs_m"], r["outs"])
        ll_b = log_loss(r["probs_b"], r["outs"])
        acc = st.mean(
            1 if (p[0] >= 0.5) == (y == 0) else 0
            for p, y in zip(r["probs_m"], r["outs"], strict=True)
        )
        dm_stat, dm_p = diebold_mariano(r["loss_m"], r["loss_b"])[:2]
        ok = br_m < br_b and dm_p < 0.05
        print(
            f"\nH1-CS (vencedor da série): Brier modelo {br_m:.4f} vs "
            f"semente {br_b:.4f} (coin-flip 0.5000)"
        )
        print(
            f"  log-loss {ll_m:.4f} vs {ll_b:.4f} | acerto {acc:.1%} | "
            f"DM stat {dm_stat:+.2f} p={dm_p:.4f}"
        )
        print(f"  VEREDITO H1-CS: {'COMPROVADA' if ok else 'REFUTADA'} (Brier menor E DM p<0.05)")
        calib = calibration_table(
            [p[0] for p in r["probs_m"]], [1 if y == 0 else 0 for y in r["outs"]]
        )
        print("  calibração (P time A):")
        for c in calib:
            print(
                f"    {c['bin_lo']:.1f}-{c['bin_hi']:.1f}: n={c['n']:>5} "
                f"prev {c['mean_pred']:.2f} vs real {c['obs_freq']:.2f}"
            )
        summary["h1"] = {
            "brier_modelo": round(br_m, 4),
            "brier_semente": round(br_b, 4),
            "logloss_modelo": round(ll_m, 4),
            "logloss_semente": round(ll_b, 4),
            "acerto": round(acc, 4),
            "dm_stat": round(dm_stat, 3),
            "dm_p": round(dm_p, 5),
            "verdict": "COMPROVADA" if ok else "REFUTADA",
            "calibracao": calib,
        }

    if args.write_artifacts:
        data = ROOT / "data"
        (data / "ratings.json").write_text(
            json.dumps(
                {t: round(v, 1) for t, v in sorted(r["elo"].items())}, ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nserving materializado: ratings.json ({len(r['elo'])} times)")
        (data / "walkforward_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("artefato: walkforward_summary.json")
    else:
        print("\nread-only: nenhum rating/artefato escrito; use --write-artifacts com autorização")


if __name__ == "__main__":
    main()
