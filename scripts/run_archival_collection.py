"""Executa somente a coleta arquivistica CS2 a partir de fatos esportivos JSON."""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from src.archival_collection import ArchivalCollection
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument("--input", type=Path, default=ROOT / "data" / "collection_only" / "upstream_events.json"); p.add_argument("--status", action="store_true"); a=p.parse_args(argv)
 rows=json.loads(a.input.read_text(encoding="utf-8")) if a.input.exists() else []
 rows=rows if isinstance(rows,list) else rows.get("events",[])
 service=ArchivalCollection(); print(json.dumps(service.ingest(rows), sort_keys=True));
 if a.status: print(json.dumps(service.status(), sort_keys=True))
 return 0
if __name__ == "__main__": raise SystemExit(main())
