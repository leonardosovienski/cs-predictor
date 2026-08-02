"""Pré-registra trials futuros; não executa nem altera o serving."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent

from predictor_core.measurement.trials import TrialRegistry  # noqa: E402

TRIALS = ROOT / "data" / "trials.json"


def main() -> int:
    registry = TrialRegistry(TRIALS)
    existing = {trial["name"] for trial in registry.load()}
    definitions = [
        {
            "name": "h3-cs-asymmetric-calibration-forward",
            "params": {
                "candidate": "isotonic-or-monotonic-bins",
                "baseline": "canonical symmetric Platt H2",
                "data_policy": "predictions generated after registration only",
                "minimum_eligible_predictions": 1000,
                "minimum_calendar_days": 90,
                "primary_metric": "winner Brier",
                "decision": "Brier lower and paired DM p<0.05; otherwise REFUTADA/INCONCLUSIVA",
                "serving_change_before_verdict": False,
            },
            "notes": "PRÉ-REGISTRADA, NÃO EXECUTADA. Testa correção assimétrica das caudas sem reutilizar a janela histórica já inspecionada.",
        },
        {
            "name": "h4-cs-inactivity-decay-forward",
            "params": {
                "candidate_half_life_days": [30, 60, 90, 120],
                "baseline": "canonical series Elo + symmetric Platt H2",
                "data_policy": "predictions generated after registration only",
                "minimum_eligible_predictions": 1000,
                "minimum_calendar_days": 90,
                "primary_metric": "winner Brier",
                "decision": "single frozen half-life must beat baseline with paired DM p<0.05",
                "roster_proxy": "days since last observed series; no manual roster labels",
                "serving_change_before_verdict": False,
            },
            "notes": "PRÉ-REGISTRADA, NÃO EXECUTADA. Nenhum decay entra no rating canônico antes do veredito forward.",
        },
    ]
    for definition in definitions:
        if definition["name"] in existing:
            continue
        registry.register(definition["name"], params=definition["params"],
                          sharpe=None, notes=definition["notes"],
                          test_period=["2026-07-21", "forward-open"])
    errors = registry.validate()
    if errors:
        raise SystemExit("schema de trials violado: " + "; ".join(errors))
    print("trials registrados:", ", ".join(sorted(
        trial["name"] for trial in registry.load() if trial["name"].startswith(("h3-cs", "h4-cs")))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
