"""Executa somente a coleta arquivistica CS2 a partir de fatos esportivos JSON."""
import argparse, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from src.archival_collection import ArchivalCollection


def _write_status(path: Path | None, payload: dict) -> None:
 if path is None: return
 path.parent.mkdir(parents=True, exist_ok=True)
 temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
 temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
 temporary.replace(path)


def _source_unavailable(input_path: Path, reason: str) -> dict:
 # The operational record must not disclose arbitrary filesystem paths.
 return {"collection_only": True, "status": "SOURCE_UNAVAILABLE", "reason": reason,
         "accepted": 0, "ambiguous": 0, "invalid": 0, "complete": 0,
         "input_present": input_path.is_file()}


def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument("--input", type=Path, default=ROOT / "data" / "collection_only" / "upstream_events.json"); p.add_argument("--status", action="store_true"); p.add_argument("--status-output", type=Path); a=p.parse_args(argv)
 if not a.input.is_file():
  payload = _source_unavailable(a.input, "UPSTREAM_INPUT_MISSING")
  _write_status(a.status_output, payload); print(json.dumps(payload, sort_keys=True)); return 2
 try:
  loaded = json.loads(a.input.read_text(encoding="utf-8"))
  rows = loaded if isinstance(loaded, list) else loaded.get("events") if isinstance(loaded, dict) else None
  if not isinstance(rows, list): raise ValueError("events array required")
 except (OSError, json.JSONDecodeError, ValueError):
  payload = _source_unavailable(a.input, "UPSTREAM_INPUT_INVALID")
  _write_status(a.status_output, payload); print(json.dumps(payload, sort_keys=True)); return 2
 service=ArchivalCollection(); payload=service.ingest(rows)
 status = service.status()
 payload.update(collection_only=True, collection_run_id=status["collection_run_id"], status=("NO_UPSTREAM_EVENTS" if not rows else "COLLECTED"))
 _write_status(a.status_output, payload); print(json.dumps(payload, sort_keys=True));
 if a.status: print(json.dumps(status, sort_keys=True))
 return 0
if __name__ == "__main__": raise SystemExit(main())
