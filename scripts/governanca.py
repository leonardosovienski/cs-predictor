"""Governança da Fase 1 do cs-predictor: controle positivo + pré-registro.

Mesmo desenho do lol-predictor (o critério de decisão da fase é idêntico:
Brier menor que o baseline + Diebold-Mariano p<0,05): braço edge = resultados
saem de Elos verdadeiros que o modelo conhece e o baseline não; braço ruído =
modelo sem informação (jitter). Passando, emite o atestado e pré-registra
H1-CS ANTES de qualquer resultado do backtest.

Uso: python scripts/governanca.py
"""
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor"))

from src.model import win_probability                                  # noqa: E402
from predictor_core.measurement.metrics import brier, diebold_mariano  # noqa: E402
from predictor_core.measurement.trials import (                        # noqa: E402
    TrialRegistry, attestation_path_for)
from predictor_core.testing.harness import attest_pipeline_power       # noqa: E402

TRIALS = ROOT / "data" / "trials.json"
SEED = 13
N_MATCHES = 1500


def _series(edge: bool, seed: int):
    rng = random.Random(seed)
    elos_true = {i: 1400 + (100 if i < 10 else 0) + rng.gauss(0, 40)
                 for i in range(30)}
    out = []
    for _ in range(N_MATCHES):
        a, b = rng.sample(range(30), 2)
        p_true = win_probability(elos_true[a], elos_true[b])
        y = 0 if rng.random() < p_true else 1
        p_base = 0.5
        p_model = (p_true if edge
                   else min(0.99, max(0.01, 0.5 + rng.gauss(0, 0.05))))
        lm = -math.log(max(p_model if y == 0 else 1 - p_model, 1e-12))
        lb = -math.log(max(p_base if y == 0 else 1 - p_base, 1e-12))
        out.append((p_model, p_base, y, lm, lb))
    return out


def evaluate(series):
    probs_m = [[p, 1 - p] for p, _pb, _y, _lm, _lb in series]
    probs_b = [[pb, 1 - pb] for _p, pb, _y, _lm, _lb in series]
    outs = [y for _p, _pb, y, _lm, _lb in series]
    bm, bb = brier(probs_m, outs), brier(probs_b, outs)
    _stat, pval = diebold_mariano([s[3] for s in series],
                                  [s[4] for s in series])[:2]
    ok = bm < bb and pval < 0.05
    return {"verdict": "COMPROVADA" if ok else "REFUTADA",
            "brier_m": round(bm, 4), "brier_b": round(bb, 4),
            "dm_p": round(pval, 5)}


def main():
    att = attestation_path_for(TRIALS)
    record = attest_pipeline_power(
        evaluate,
        lambda: _series(edge=True, seed=SEED),
        lambda: _series(edge=False, seed=SEED + 1),
        attestation_path=att,
        # `metric` virou obrigatória no predictor_core 2.0.0 e vai gravada no
        # atestado: toda trial nova registrada contra ele tem que declarar a
        # MESMA régua, senão o registry levanta MetricMismatchError. "brier" é
        # o que este controle de fato mede — o veredito de `evaluate` é
        # `brier(modelo) < brier(baseline)`, com o Diebold-Mariano servindo de
        # teste de significância sobre a log-loss, não de métrica do veredito.
        metric="brier",
        note=f"criterio Brier<baseline + DM p<0.05; edge=+100 Elo oculto; "
             f"ruido=jitter 5pp; {N_MATCHES} series/braço; seed {SEED}")
    print(f"controle positivo OK — atestado em {att.name} ({record['passed_at']})")

    reg = TrialRegistry(TRIALS)
    reg.register(
        "h1-cs-elo-serie-prequential",
        params={"model": "elo-mapa+combinatoria-serie",
                "k_factors": {"bo1": 32, "bo3": 40, "bo5": 48},
                "seed": "hltv-top30-2026-07-06-linear",
                "default_seed_elo": 1400, "burnin_days": 90,
                "min_team_matches": 10,
                "baseline": "elo-semente-congelado (ranking HLTV)",
                "source": "hltv /results (todas as tiers)",
                "period": "2024-12..2026-07"},
        sharpe=None,
        notes="H1-CS: Elo por mapa atualizado por série (K por formato) "
              "prevê o vencedor da série melhor que o ranking-semente "
              "congelado. COMPROVADA = Brier menor E Diebold-Mariano p<0.05 "
              "sobre log-loss. Métrica probabilística (sem odds na Fase 1a).",
        test_period=["2024-12-22", "2026-07-11"])
    errs = reg.validate()
    if errs:
        sys.exit("schema de trials violado: " + "; ".join(errs))
    print(f"pré-registro OK — {len(reg.load())} tentativa(s):")
    for t in reg.load():
        print(f"  - {t['name']}")


if __name__ == "__main__":
    main()
