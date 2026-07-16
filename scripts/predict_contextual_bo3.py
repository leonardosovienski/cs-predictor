"""Read-only CLI for the experimental map/veto/contextual BO3 forecast."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.contextual_bo3 import ContextError, predict_contextual_bo3  # noqa: E402
from src.model import EloModel  # noqa: E402
from src.model_maps import MapEloModel  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Laboratório contextual read-only de BO3")
    parser.add_argument("--input", type=Path, required=True,
                        help="JSON com team_a, team_b, veto_scenarios e contexto opcional")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ContextError("input deve ser objeto JSON")
        for field in ("team_a", "team_b", "veto_scenarios"):
            if field not in payload:
                raise ContextError(f"input exige {field}")
        model = MapEloModel(base=EloModel())
        result = predict_contextual_bo3(model=model, team_a=payload["team_a"], team_b=payload["team_b"],
                                        veto_scenarios=payload["veto_scenarios"], context=payload.get("context"))
    except (OSError, json.JSONDecodeError, ContextError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
