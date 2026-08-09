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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from predictor_core.data.contracts import PredictionPoint
from predictor_core.kernel.obs import emit_event

from .config import ROOT, load_config
from .model import FORMAT_HOURS, EloModel, cover_probability
from .model_maps import MapEloModel, predict_series_with_maps

_DOMAIN = "cs"


def _log_path() -> Path:
    return Path(os.environ.get("PREDICTIONS_LOG_PATH",
                               ROOT / "data" / "predictions.jsonl"))


def run(team_a: str, team_b: str, *, fmt: str = "bo3",
        handicap: float | None = None, maps: list[str] | None = None,
        now: datetime | None = None, scheduled_start_at: datetime | None = None,
        dry_run: bool = False) -> dict:
    now = now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now exige timezone")
    if scheduled_start_at is None:
        if not dry_run:
            raise ValueError("scheduled_start_at e obrigatorio para previsao persistida")
        scheduled_start_at = now
    if scheduled_start_at.tzinfo is None or scheduled_start_at.utcoffset() is None:
        raise ValueError("scheduled_start_at exige timezone")
    scheduled_start_at = scheduled_start_at.astimezone(UTC)
    if not dry_run and now > scheduled_start_at:
        raise ValueError("previsao persistida exige inicio futuro ou presente")
    model = EloModel()
    if maps:
        mp = MapEloModel(base=model)
        r = predict_series_with_maps(mp, team_a, team_b, maps, fmt)
    else:
        r = model.predict_match(team_a, team_b, fmt)
    # handicap recomendado: lado de −1.5 do favorito se P(cobrir) > 50%,
    # senão +1.5 do azarão — heurística de exibição, NÃO recomendação de aposta
    fav_first = r["prob_team_a"] >= 0.5
    fav, dog = ((r["team_a"], r["team_b"]) if fav_first
                else (r["team_b"], r["team_a"]))
    if fmt != "bo1":
        p_fav_cover, _ = cover_probability(r["score_probs"], -1.5,
                                           side_a=fav_first)
        r["handicap_recomendado"] = (
            {"team": fav, "handicap": -1.5, "p_cover": round(p_fav_cover, 4)}
            if p_fav_cover > 0.5 else
            {"team": dog, "handicap": +1.5,
             "p_cover": round(1.0 - p_fav_cover, 4)})
        if handicap is not None:
            p, push = cover_probability(r["score_probs"], handicap,
                                        side_a=True)
            r["handicap_consultado"] = {
                "team_a": r["team_a"], "team_b": r["team_b"], "format": fmt,
                "handicap": handicap, "p_cover": round(p, 4),
                "p_not_cover": round(1.0 - p - push, 4)}
            if push > 0:    # linha inteira: empate exato devolve a aposta
                r["handicap_consultado"]["p_push"] = round(push, 4)
    r["total_mapas_projetado"] = r["mapas_esperados"]

    point = PredictionPoint(
        predicted_at=now,
        matures_at=scheduled_start_at + timedelta(hours=FORMAT_HOURS[fmt]),
        value={"prob_team_a": r["prob_team_a"], "format": fmt,
               "mapas_esperados": r["mapas_esperados"]},
        metadata={"team_a": r["team_a"], "team_b": r["team_b"],
                  "model": r["model"]})
    r["predicted_at"] = point.predicted_at.isoformat(timespec="seconds")
    r["scheduled_start_at"] = scheduled_start_at.isoformat(timespec="seconds")
    r["matures_at"] = point.matures_at.isoformat(timespec="seconds")

    if dry_run:
        r["dry_run"] = True
        return r

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
    ap.add_argument("--maps", default=None,
                    help="mapas do veto/pool, em ordem, separados por vírgula "
                         "(ex.: Mirage,Inferno,Ancient) — usa Elo POR MAPA "
                         "(H3-CS) em vez do Elo de série")
    ap.add_argument("--json", action="store_true", help="saída estruturada")
    ap.add_argument("--dry-run", action="store_true",
                    help="consulta exploratória: não grava no ledger "
                         "predictions.jsonl nem emite telemetria")
    ap.add_argument("--laboratory", action="store_true",
                    help="confirma execução em ambiente de laboratório")
    ap.add_argument("--scheduled-start", required=True,
                    help="inicio UTC ISO-8601 da serie")
    args = ap.parse_args(argv)
    if not args.laboratory and os.environ.get("CS_LABORATORY") != "1":
        print("cs-predict is laboratory-only; use --laboratory or CS_LABORATORY=1", file=sys.stderr)
        return 2

    cfg = load_config()
    fmt = args.format or cfg.get("default_format", "bo3")
    maps = [m.strip() for m in args.maps.split(",")] if args.maps else None
    try:
        scheduled = datetime.fromisoformat(args.scheduled_start.replace("Z", "+00:00"))
        r = run(args.team_a, args.team_b, fmt=fmt, handicap=args.handicap,
                maps=maps, scheduled_start_at=scheduled, dry_run=args.dry_run)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    print(f"{cfg['game']} {fmt.upper()} — {r['team_a']} vs {r['team_b']}")
    if maps:
        print(f"  mapas: {', '.join(maps)}")
        for m in maps:
            p = r["p_por_mapa"][m]
            elo = r["elo_por_mapa"][m]
            print(f"    {m}: {elo[r['team_a']]:.0f} x {elo[r['team_b']]:.0f} "
                  f"(P {r['team_a']} {p:.1%})")
    else:
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
    if r["model"] in ("elo-platt-fase1", "elo-mapa-platt-h3"):
        rotulo = ("Fase 1: Elo vivido (ratings.json) + Platt calibrado"
                  if r["model"] == "elo-platt-fase1" else
                  "Fase 1+ (H3): Elo POR MAPA (ratings_maps.json) + Platt calibrado")
        print(f"  [{rotulo}]")
    else:
        print("  [Fase 0: Elo semeado pelo ranking HLTV — sem histórico ainda]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
