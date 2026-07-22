"""CI minima local do cs-predictor — 3 barreiras (Fase 0).

  1. pytest — a suite inteira tem que passar.
  2. Encoding — qualquer .ps1 do repo precisa ser ASCII puro (licao do wc).
  3. Parse dos arquivos criticos — config.yaml valido com as chaves do
     dominio, teams_cs.json com 30 times unicos e Elo monotonico,
     .env.example presente, e smoke do serving: predict --json com
     probabilidades somando ~1.

Uso:
    python scripts/ci_check.py            # tudo
    python scripts/ci_check.py --fast     # pula o pytest
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
failures: list[str] = []


def check_pytest() -> None:
    print("[1/3] pytest (suite completa)...")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       cwd=ROOT, capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()[-1:] or ["(sem saida)"]
    print(f"      {tail[0]}")
    if r.returncode != 0:
        failures.append(f"pytest falhou (exit {r.returncode}) — rode: python -m pytest tests/")


def check_ps1_ascii() -> None:
    print("[2/3] encoding de scripts .ps1 (ASCII puro)...")
    # Só arquivos versionados pertencem ao contrato do projeto. Worktrees da
    # ferramenta podem existir abaixo da raiz e não devem contaminar este CI.
    tracked = subprocess.run(["git", "ls-files", "*.ps1"], cwd=ROOT,
                             capture_output=True, text=True, check=False)
    ps1 = [ROOT / line for line in tracked.stdout.splitlines() if line]
    for p in ps1:
        try:
            p.read_bytes().decode("ascii")
        except UnicodeDecodeError as e:
            failures.append(f"{p.relative_to(ROOT)}: nao-ASCII no byte {e.start}")
    print(f"      {len(ps1)} arquivo(s) .ps1 verificados")


def check_critical_files() -> None:
    print("[3/3] parse dos arquivos criticos + smoke do serving...")
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        for key in ("game", "default_format", "k_factor_base", "teams_file"):
            if key not in cfg:
                failures.append(f"config.yaml sem a chave obrigatoria '{key}'")
    except Exception as e:
        failures.append(f"config.yaml ilegivel: {e}")

    try:
        data = json.loads((ROOT / "data" / "teams_cs.json").read_text(encoding="utf-8"))
        teams = data["teams"]
        if len(teams) != 30 or len({t["name"] for t in teams}) != 30:
            failures.append(f"teams_cs.json: esperava 30 times unicos, achei {len(teams)}")
        elos = [t["initial_elo"] for t in sorted(teams, key=lambda t: t["hltv_rank"])]
        if any(a < b for a, b in zip(elos, elos[1:])):
            failures.append("teams_cs.json: Elo inicial nao-monotonico no ranking")
    except Exception as e:
        failures.append(f"teams_cs.json ilegivel: {e}")

    if not (ROOT / ".env.example").exists():
        failures.append(".env.example ausente")

    env = dict(os.environ)
    tmp = Path(tempfile.gettempdir())
    env["PREDICTIONS_LOG_PATH"] = str(tmp / "cs_ci_smoke_pred.jsonl")
    env["PREDICTOR_EVENTS_PATH"] = str(tmp / "cs_ci_smoke_events.jsonl")
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "src.predict",
                        "Vitality", "MOUZ", "--format", "bo3", "--json"],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if r.returncode != 0:
        failures.append(f"predict --json saiu com exit {r.returncode}: "
                        f"{(r.stderr or '')[-200:]}")
    else:
        try:
            out = json.loads(r.stdout)
            soma = out["prob_team_a"] + out["prob_team_b"]
            if not 0.999 <= soma <= 1.001:
                failures.append(f"prob_team_a+prob_team_b = {soma:.4f} (esperado ~1)")
            print(f"      smoke: {out['team_a']} {out['prob_team_a']:.1%} x "
                  f"{out['prob_team_b']:.1%} {out['team_b']} | "
                  f"mapas {out['total_mapas_projetado']}")
        except (ValueError, KeyError) as e:
            failures.append(f"predict --json nao produziu o dict esperado ({e})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="pula o pytest")
    args = ap.parse_args()

    if not args.fast:
        check_pytest()
    else:
        print("[1/3] pytest PULADO (--fast)")
    check_ps1_ascii()
    check_critical_files()

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        print(f"\nCI: {len(failures)} falha(s) — commit bloqueado.")
        return 1
    print("CI: todas as barreiras verdes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
