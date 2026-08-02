"""Tentativa N+1: Elo + Platt scaling prequential (Fase 1, calibração).

Reusa o stream medido do backtest da Fase 1 (mesma passada prequential do
Elo) e aplica o calibrador de forma FORWARD-ONLY: a previsão do jogo i é
calibrada com um Platt ajustado só nos pares (p, y) ANTERIORES (refit a
cada `refit_every`, mínimo `min_fit` amostras — antes disso, p cru).

Governança: registra `h2-cs-elo-platt-prequential` no TrialRegistry ANTES
de calcular o veredito (params novos → tentativa nova; atestado do harness
já existe). COMPROVADA = Brier menor que o Elo cru + DM p<0,05.

Se COMPROVADA: ajusta o Platt no histórico COMPLETO e materializa
data/calibration_platt.json — o serving (model.predict_match) passa a
aplicar automaticamente.
"""
import argparse
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from src import db                                     # noqa: E402
from src.calibration import PlattCalibrator            # noqa: E402
from src.config import load_config                     # noqa: E402
from predictor_core.measurement.metrics import (       # noqa: E402
    brier, calibration_table, diebold_mariano)
from predictor_core.measurement.trials import TrialRegistry   # noqa: E402

from backtest_walkforward import run as run_prequential, _ln   # noqa: E402

MIN_FIT = 300
REFIT_EVERY = 200


def calibrated_stream(probs_m, outs):
    """p_raw → p_cal com Platt expanding forward-only."""
    cal = PlattCalibrator()
    fitted = False
    out = []
    hist_p, hist_y = [], []
    for i, (pv, y) in enumerate(zip(probs_m, outs)):
        p = pv[0]
        y_bin = 1 if y == 0 else 0            # evento = "time A vence"
        if fitted:
            out.append(cal.apply(p))
        else:
            out.append(p)
        hist_p.append(p)
        hist_y.append(y_bin)
        if len(hist_p) >= MIN_FIT and (len(hist_p) % REFIT_EVERY == 0
                                       or not fitted):
            cal = PlattCalibrator().fit(hist_p, hist_y)
            fitted = True
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backtest Platt H2 (read-only por padrão)")
    parser.add_argument("--write-artifacts", action="store_true",
                        help="autoriza atualizar trial, calibração e resumo")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()

    # 1) pré-registro da tentativa N+1 (ANTES de qualquer veredito)
    reg = TrialRegistry(ROOT / "data" / "trials.json")
    nome = "h2-cs-elo-platt-symmetric-prequential"
    ja = {t["name"] for t in reg.load()}
    params = {"model": "elo-mapa+combinatoria-serie+platt-simetrico",
              "platt": {"min_fit": MIN_FIT, "refit_every": REFIT_EVERY,
                        "janela": "expanding forward-only", "intercept": 0.0,
                        "invariante": "cal(1-p)=1-cal(p)"},
              "base": "h1-cs-elo-serie-prequential (mesmo Elo, mesma passada)",
              "period": "2024-12..2026-07"}
    if nome not in ja and args.write_artifacts:
        reg.register(nome, params=params, sharpe=None,
                     notes="N+2: correção simétrica do Platt sobre a probabilidade "
                           "de série do Elo; intercepto fixo em zero para impedir "
                           "dependência da ordem team_a/team_b. COMPROVADA = Brier menor "
                           "que o Elo cru + DM p<0.05.",
                     test_period=["2024-12-22", "2026-07-11"])
        print(f"trial {nome} pré-registrada")

    # 2) mesma passada prequential da Fase 1
    conn = db.connect(str(ROOT / cfg["database"]), read_only=True)
    r = run_prequential(cfg, conn)
    outs = r["outs"]
    raw = [p[0] for p in r["probs_m"]]
    cal = calibrated_stream(r["probs_m"], outs)
    n = len(outs)

    br_raw = brier(r["probs_m"], outs)
    br_cal = brier([[p, 1 - p] for p in cal], outs)
    loss_raw = r["loss_m"]
    loss_cal = [-_ln(p if y == 0 else 1 - p) for p, y in zip(cal, outs)]
    dm_stat, dm_p = diebold_mariano(loss_cal, loss_raw)[:2]
    ok = br_cal < br_raw and dm_p < 0.05
    print(f"\nH2-CS (Platt prequential): n={n}")
    print(f"  Brier cru {br_raw:.4f} → calibrado {br_cal:.4f} | "
          f"DM stat {dm_stat:+.2f} p={dm_p:.5f}")
    print(f"  VEREDITO: {'COMPROVADA' if ok else 'REFUTADA'}")
    tab = calibration_table(cal, [1 if y == 0 else 0 for y in outs])
    print("  calibração PÓS-Platt (P time A):")
    for c in tab:
        print(f"    {c['bin_lo']:.1f}-{c['bin_hi']:.1f}: n={c['n']:>5} "
              f"prev {c['mean_pred']:.2f} vs real {c['obs_freq']:.2f}")

    # 3) resultado gravado na trial
    if args.write_artifacts:
        t = next(t for t in reg.load() if t["name"] == nome)
        reg.register(nome, params=t["params"], sharpe=None,
                     notes=t["notes"] + f" | RESULTADO protocolo corrigido 2026-07-16: "
                     f"{'COMPROVADA' if ok else 'REFUTADA'} — Brier {br_raw:.4f} "
                     f"-> {br_cal:.4f}, DM p={dm_p:.5f}, n={n}.",
                     test_period=t.get("test_period"))

    # 4) se comprovada, materializa o Platt do histórico completo p/ serving
    if ok and args.write_artifacts:
        full = PlattCalibrator().fit(raw, [1 if y == 0 else 0 for y in outs])
        full.save(ROOT / "data" / "calibration_platt.json",
                  meta={"fitted_on": n, "brier_raw": round(br_raw, 4),
                        "brier_cal": round(br_cal, 4),
                        "trial": nome})
        print(f"\nserving: calibration_platt.json materializado "
              f"(a={full.a:.4f}, b={full.b:.4f}) — a<1 achata as pontas")
    if args.write_artifacts:
        summary_path = ROOT / "data" / "calibracao_summary.json"
        summary_path.write_text(json.dumps({
            "trial": nome, "n": n, "brier_raw": round(br_raw, 4), "brier_cal": round(br_cal, 4),
            "dm_p": round(dm_p, 6), "verdict": "COMPROVADA" if ok else "REFUTADA",
            "calibracao_pos": tab}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    else:
        print("\nread-only: nenhum artefato escrito; use --write-artifacts com autorização")


if __name__ == "__main__":
    main()
