"""Serving de previsão de partidas de CS2 — Fase 0.

Uso:
    python -m src.predict Vitality MOUZ --format bo3 --json
    python -m src.predict Falcons Spirit --handicap -1.5

Contratos do core desde o dia zero (padrão da plataforma):
  - PredictionPoint (predicted_at → matures_at = fim estimado da série);
  - emit_event (telemetria JSONL, domínio "cs");
  - log append-only data/predictions.jsonl (PREDICTIONS_LOG_PATH sobrepõe —
    smoke de CI não polui produção).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT, load_config           # injeta vendor/ no sys.path
from .model import FORMAT_HOURS, EloModel

from predictor_core.data.contracts import PredictionPoint
from predictor_core.kernel.obs import emit_event

_DOMAIN = "cs"


def _log_path() -> Path:
    return Path(os.environ.get("PREDICTIONS_LOG_PATH",
                               ROOT / "data" / "predictions.jsonl"))


def run(team_a: str, team_b: str, *, fmt: str = "bo3",
        handicap: float | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    model = EloModel()
    r = model.predict_match(team_a, team_b, fmt)
    # handicap recomendado: lado de −1.5 do favorito se P(cobrir) > 50%,
    # senão +1.5 do azarão — heurística de exibição, NÃO recomendação de aposta
    fav_first = r["prob_team_a"] >= 0.5
    fav, dog = ((r["team_a"], r["team_b"]) if fav_first
                else (r["team_b"], r["team_a"]))
    if fmt != "bo1":
        hc_fav = model.predict_handicap(fav, dog, -1.5, fmt)
        r["handicap_recomendado"] = (
            {"team": fav, "handicap": -1.5, "p_cover": hc_fav["p_cover"]}
            if hc_fav["p_cover"] > 0.5 else
            {"team": dog, "handicap": +1.5,
             "p_cover": round(1.0 - hc_fav["p_cover"], 4)})
        if handicap is not None:
            r["handicap_consultado"] = model.predict_handicap(
                team_a, team_b, handicap, fmt)
    r["total_mapas_projetado"] = r["mapas_esperados"]

    point = PredictionPoint(
        predicted_at=now,
        matures_at=now + timedelta(hours=FORMAT_HOURS[fmt]),
        value={"prob_team_a": r["prob_team_a"], "format": fmt,
               "mapas_esperados": r["mapas_esperados"]},
        metadata={"team_a": r["team_a"], "team_b": r["team_b"],
                  "model": r["model"]})
    r["predicted_at"] = point.predicted_at.isoformat(timespec="seconds")
    r["matures_at"] = point.matures_at.isoformat(timespec="seconds")

    log = _log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

    try:
        emit_event(_DOMAIN, "prediction",
                   metrics={"prob_team_a": r["prob_team_a"],
                            "mapas_esperados": r["mapas_esperados"]},
                   metadata={"team_a": r["team_a"], "team_b": r["team_b"],
                             "format": fmt, "model": r["model"]})
    except Exception:
        pass    # telemetria nunca derruba o serving
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Previsão de partida de CS2 (Elo, Fase 0)")
    ap.add_argument("team_a")
    ap.add_argument("team_b")
    ap.add_argument("--format", default=None, choices=["bo1", "bo3", "bo5"],
                    help="formato da série (default: config default_format)")
    ap.add_argument("--handicap", type=float, default=None,
                    help="handicap de mapas a consultar (ex.: -1.5, +1.5)")
    ap.add_argument("--json", action="store_true", help="saída estruturada")
    args = ap.parse_args(argv)

    cfg = load_config()
    fmt = args.format or cfg.get("default_format", "bo3")
    try:
        r = run(args.team_a, args.team_b, fmt=fmt, handicap=args.handicap)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    print(f"{cfg['game']} {fmt.upper()} — {r['team_a']} vs {r['team_b']}")
    print(f"  Elo: {r['elo_a']:.0f} x {r['elo_b']:.0f} "
          f"(P mapa {r['p_map_a']:.1%})")
    print(f"  série: {r['team_a']} {r['prob_team_a']:.1%} | "
          f"{r['team_b']} {r['prob_team_b']:.1%} | "
          f"mapas esperados {r['total_mapas_projetado']:.2f}")
    if "handicap_recomendado" in r:
        h = r["handicap_recomendado"]
        print(f"  handicap: {h['team']} {h['handicap']:+.1f} "
              f"(P cobrir {h['p_cover']:.1%})")
    if "handicap_consultado" in r:
        h = r["handicap_consultado"]
        print(f"  consultado: {h['team_a']} {h['handicap']:+.1f} → "
              f"P cobrir {h['p_cover']:.1%}")
    print("  [Fase 0: Elo semeado pelo ranking HLTV — sem histórico ainda]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
