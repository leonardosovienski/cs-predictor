"""Append-only forward evidence for CS series predictions.

This is deliberately separate from ``src.predict``: snapshots never append to
the prediction ledger, update ratings, write ``cs.db``, or fetch a network
source.  A result is supplied later as an explicit local JSON document.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any
import uuid

from .config import ROOT, load_config, load_teams, resolve_team
from .model import EloModel

SCHEMA_VERSION = "1.0"
PRE_EVENT = "PRE_EVENT"
MATURED = "MATURED"


class SnapshotError(ValueError):
    """A forward-snapshot invariant was not met."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_file(path: Path) -> str:
    if not path.is_file():
        raise SnapshotError(f"input ausente para hash: {path.name}")
    return _hash_bytes(path.read_bytes())


def _utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotError(f"{field} inválido") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SnapshotError(f"{field} deve ter timezone UTC")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SnapshotError("datetime deve ter timezone UTC")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SnapshotError("provenance Git do projeto indisponível")
    return result.stdout.strip()


def _tools_provenance() -> dict[str, Any]:
    workspace = ROOT.parent
    if str(workspace) not in sys.path:
        sys.path.insert(0, str(workspace))
    try:
        from tools.tools_provenance import collect_tools_provenance
        return collect_tools_provenance(workspace / "tools", strict=True)
    except (ImportError, OSError, RuntimeError) as exc:
        raise SnapshotError(f"tools provenance strict indisponível: {exc}") from exc


def _core_identity(root: Path) -> dict[str, str]:
    vendor = root / "vendor" / "predictor_core"
    version = vendor / "VERSION"
    return {"version": version.read_text(encoding="utf-8").strip(),
            "hash": _hash_file(vendor / "CORE_MANIFEST.json")}


def _resolve(model: EloModel, requested: str) -> dict[str, Any]:
    """Resolve aliases explicitly; ambiguous input never reaches the model."""
    low = requested.strip().lower()
    teams = load_teams()
    exact = [row for row in teams if row["name"].lower() == low]
    if exact:
        canonical = exact[0]["name"]
        return {"requested": requested, "canonical": canonical,
                "team_id": canonical, "confidence": "EXACT"}
    try:
        canonical = resolve_team(requested)["name"]
        return {"requested": requested, "canonical": canonical,
                "team_id": canonical, "confidence": "UNIQUE_ALIAS"}
    except ValueError as exc:
        matches = [name for name in model.ratings if name.lower() == low]
        if len(matches) == 1:
            return {"requested": requested, "canonical": matches[0],
                    "team_id": matches[0], "confidence": "RATINGS_EXACT"}
        raise SnapshotError(f"alias ambíguo ou ausente: {requested!r}") from exc


def _load_event(path: Path) -> dict[str, Any]:
    try:
        event = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"evento ilegível: {exc}") from exc
    required = {"event_id", "competition", "stage", "scheduled_start_utc", "team_a", "team_b"}
    if not isinstance(event, dict) or any(not isinstance(event.get(key), str) or not event[key].strip() for key in required):
        raise SnapshotError(f"evento exige campos: {sorted(required)}")
    if not isinstance(event.get("format"), str) or event["format"].lower() not in {"bo1", "bo3", "bo5"}:
        raise SnapshotError("formato ausente ou inválido")
    return event


def _event_path(root: Path, event_id: str, start: datetime, kind: str, snapshots_root: Path) -> Path:
    safe = "".join(char.lower() if char.isalnum() or char in "-_" else "-" for char in event_id).strip("-")
    if not safe:
        raise SnapshotError("event_id ausente ou inválido")
    return snapshots_root / kind / str(start.year) / f"{safe}.json"


def _event_has_result(root: Path, event: dict[str, Any], a: str, b: str, start: datetime) -> bool:
    db_path = root / "data" / "cs.db"
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT 1 FROM matches WHERE date=? AND event=? AND "
            "((team_a=? AND team_b=?) OR (team_a=? AND team_b=?)) LIMIT 1",
            (start.date().isoformat(), event["competition"], a, b, b, a),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _freshness(root: Path, names: list[str], generated: datetime) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{root / 'data' / 'cs.db'}?mode=ro", uri=True)
    try:
        value: dict[str, Any] = {}
        for name in names:
            count, last = conn.execute("SELECT count(*), max(date) FROM matches WHERE team_a=? OR team_b=?", (name, name)).fetchone()
            value[name] = {"games": count, "last_observed": last,
                           "days_since_last": None if last is None else (generated.date() - datetime.fromisoformat(last).date()).days}
        return value
    finally:
        conn.close()


def _consumer_provenance(root: Path, core: dict[str, str], inputs: dict[str, str], generated: datetime) -> dict[str, Any]:
    clean = not bool(_git(root, "status", "--porcelain"))
    if not clean:
        raise SnapshotError("project worktree suja; provenance strict proibida")
    return {
        "project": "cs-predictor", "project_commit": _git(root, "rev-parse", "HEAD"),
        "project_branch": _git(root, "branch", "--show-current") or None,
        "project_worktree_clean": clean, "predictor_core_version": core["version"],
        "predictor_core_hash": core["hash"], "input_hashes": inputs,
        "artifact_schema_version": "cs-forward-snapshot/1.0",
        "generated_at_utc": _utc_text(generated),
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    return _hash_bytes(_canonical({key: value for key, value in payload.items() if key != "payload_hash"}))


def _atomic_create(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        # Hard-link cria o nome final de forma atômica e falha se ele já
        # existir. Diferente de os.replace, nunca sobrescreve outro snapshot.
        os.link(temporary, path)
    except FileExistsError as exc:
        raise SnapshotError(f"snapshot já existe; overwrite proibido: {path.name}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def create_pre_event_snapshot(*, event_file: Path, snapshots_root: Path, now: datetime | None = None, root: Path = ROOT) -> Path:
    event = _load_event(event_file)
    start = _utc(event["scheduled_start_utc"], "scheduled_start_utc")
    generated = _utc_text(now or datetime.now(timezone.utc))
    generated_at = _utc(generated, "generated_at_utc")
    if generated_at >= start:
        raise SnapshotError("snapshot após o início do evento é proibido")
    model = EloModel(ratings_file=root / "data" / "ratings.json")
    alias_a, alias_b = _resolve(model, event["team_a"]), _resolve(model, event["team_b"])
    if alias_a["canonical"] == alias_b["canonical"]:
        raise SnapshotError("um time não joga contra si mesmo")
    if _event_has_result(root, event, alias_a["canonical"], alias_b["canonical"], start):
        raise SnapshotError("evento já possui resultado; PRE_EVENT proibido")
    destination = _event_path(root, event["event_id"], start, "pre_event", snapshots_root)
    if destination.exists():
        raise SnapshotError("snapshot já existe; overwrite proibido")
    try:
        prediction = model.predict_match(alias_a["canonical"], alias_b["canonical"], event["format"])
    except ValueError as exc:
        raise SnapshotError(f"rating ausente ou previsão inválida: {exc}") from exc
    inputs = {"event": _hash_file(event_file), "database": _hash_file(root / "data" / "cs.db"),
              "ratings": _hash_file(root / "data" / "ratings.json"), "teams": _hash_file(root / "data" / "teams_cs.json"),
              "config": _hash_file(root / "config.yaml"), "calibration": _hash_file(root / "data" / "calibration_platt.json")}
    core = _core_identity(root)
    consumer = _consumer_provenance(root, core, inputs, generated_at)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "status": PRE_EVENT, "event_id": event["event_id"],
        "competition": event["competition"], "stage": event["stage"], "scheduled_start_utc": _utc_text(start),
        "generated_at_utc": generated, "format": prediction["format"], "team_a": prediction["team_a"], "team_b": prediction["team_b"],
        "canonical_team_ids": {"team_a": alias_a["team_id"], "team_b": alias_b["team_id"]},
        "aliases_resolved": {"team_a": alias_a, "team_b": alias_b},
        "alias_confidence": {"team_a": alias_a["confidence"], "team_b": alias_b["confidence"]},
        "ratings": {"team_a": prediction["elo_a"], "team_b": prediction["elo_b"]},
        "freshness": _freshness(root, [prediction["team_a"], prediction["team_b"]], generated_at),
        "raw_elo_probability": prediction["prob_team_a_raw"], "platt_probability": prediction["prob_team_a"],
        "final_probability": {"team_a": prediction["prob_team_a"], "team_b": prediction["prob_team_b"]},
        "favorite": prediction["team_a"] if prediction["prob_team_a"] >= 0.5 else prediction["team_b"],
        "model_version": prediction["model"], "frozen_parameters": {"config": load_config(), "score_probs": prediction["score_probs"]},
        "project_commit": consumer["project_commit"], "project_branch": consumer["project_branch"],
        "project_worktree_clean": consumer["project_worktree_clean"], "predictor_core_version": core["version"], "predictor_core_hash": core["hash"],
        "tools_provenance": _tools_provenance(), "consumer_provenance": consumer,
        "input_hashes": inputs,
    }
    payload["payload_hash"] = _payload_hash(payload)
    _atomic_create(destination, payload)
    return destination


def load_and_verify_snapshot(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"snapshot ilegível: {exc}") from exc
    required = {"schema_version", "status", "event_id", "scheduled_start_utc", "generated_at_utc", "format", "team_a", "team_b", "ratings", "final_probability", "project_commit", "predictor_core_hash", "tools_provenance", "consumer_provenance", "input_hashes", "payload_hash"}
    missing = sorted(required - set(payload))
    if missing or payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != PRE_EVENT:
        raise SnapshotError(f"snapshot PRE_EVENT inválido: campos ausentes {missing}")
    if _payload_hash(payload) != payload["payload_hash"]:
        raise SnapshotError("hash do snapshot inconsistente")
    if _utc(payload["generated_at_utc"], "generated_at_utc") >= _utc(payload["scheduled_start_utc"], "scheduled_start_utc"):
        raise SnapshotError("proteção temporal violada")
    return payload


def _validate_result(result: Any, pre: dict[str, Any]) -> dict[str, Any]:
    required = {"event_id", "winner", "score", "result_source", "result_retrieved_at_utc"}
    if not isinstance(result, dict) or any(key not in result for key in required) or result["event_id"] != pre["event_id"]:
        raise SnapshotError("resultado não corresponde ao PRE_EVENT")
    if result["winner"] not in {pre["team_a"], pre["team_b"]}:
        raise SnapshotError("vencedor não pertence ao evento")
    if (not isinstance(result["score"], dict)
            or not all(isinstance(result["score"].get(key), int)
                       and not isinstance(result["score"].get(key), bool)
                       and result["score"][key] >= 0
                       for key in ("team_a", "team_b"))):
        raise SnapshotError("placar inválido")
    score_a, score_b = result["score"]["team_a"], result["score"]["team_b"]
    need = {"bo1": 1, "bo3": 2, "bo5": 3}[pre["format"]]
    if max(score_a, score_b) != need or score_a == score_b:
        raise SnapshotError(f"placar terminal incompatível com {pre['format']}")
    expected_winner = pre["team_a"] if score_a > score_b else pre["team_b"]
    if result["winner"] != expected_winner:
        raise SnapshotError("vencedor contradiz o placar")
    if not isinstance(result["result_source"], str) or not result["result_source"].strip():
        raise SnapshotError("fonte oficial ausente")
    retrieved = _utc(str(result["result_retrieved_at_utc"]), "result_retrieved_at_utc")
    if retrieved < _utc(pre["scheduled_start_utc"], "scheduled_start_utc"):
        raise SnapshotError("resultado recuperado antes do início do evento")
    maps = result.get("maps")
    if not isinstance(maps, list) or len(maps) != score_a + score_b:
        raise SnapshotError("mapas jogados não correspondem ao placar da série")
    wins_a = wins_b = 0
    for item in maps:
        if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                or not item["name"].strip()
                or any(isinstance(item.get(key), bool) or not isinstance(item.get(key), int)
                       or item[key] < 0 for key in ("score_a", "score_b"))
                or item["score_a"] == item["score_b"]):
            raise SnapshotError("mapa jogado inválido")
        wins_a += item["score_a"] > item["score_b"]
        wins_b += item["score_b"] > item["score_a"]
    if (wins_a, wins_b) != (score_a, score_b):
        raise SnapshotError("vencedores dos mapas contradizem o placar da série")
    return result


def _load_result(path: Path, pre: dict[str, Any]) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"resultado ilegível: {exc}") from exc
    return _validate_result(result, pre)


def mature_snapshot(*, event_id: str, year: int, result_file: Path, snapshots_root: Path, now: datetime | None = None) -> Path:
    pre_path = _event_path(ROOT, event_id, datetime(year, 1, 1, tzinfo=timezone.utc), "pre_event", snapshots_root)
    if not pre_path.is_file():
        raise SnapshotError("maturação sem PRE_EVENT é proibida")
    pre = load_and_verify_snapshot(pre_path)
    target = _event_path(ROOT, event_id, datetime(year, 1, 1, tzinfo=timezone.utc), "matured", snapshots_root)
    if target.exists():
        raise SnapshotError("maturação já existe; overwrite proibido")
    result = _load_result(result_file, pre)
    matured_at = now or datetime.now(timezone.utc)
    if matured_at.tzinfo is None or matured_at.utcoffset() is None:
        raise SnapshotError("matured_at_utc exige timezone")
    matured_at = matured_at.astimezone(timezone.utc)
    retrieved_at = _utc(result["result_retrieved_at_utc"], "result_retrieved_at_utc")
    if matured_at < retrieved_at:
        raise SnapshotError("maturação anterior à recuperação do resultado")
    matured = _utc_text(matured_at)
    winner_probability = pre["final_probability"]["team_a"] if result["winner"] == pre["team_a"] else pre["final_probability"]["team_b"]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "status": MATURED, "event_id": pre["event_id"],
        "pre_event_path": str(Path("pre_event") / str(year) / pre_path.name), "pre_event_payload_hash": pre["payload_hash"],
        "result_source": result["result_source"], "result_retrieved_at_utc": result["result_retrieved_at_utc"],
        "matured_at_utc": matured, "official_result": {"winner": result["winner"], "score": result["score"], "maps": result.get("maps")},
        "metrics": {"winner_probability": winner_probability, "winner_brier": round((1.0 - winner_probability) ** 2, 8),
                    "winner_hit": result["winner"] == pre["favorite"]},
        "tools_provenance": _tools_provenance(), "consumer_provenance": {**pre["consumer_provenance"], "generated_at_utc": matured, "artifact_kind": "matured_snapshot"},
        "audit_metadata": {"model_reexecuted": False, "database_write": False, "ratings_write": False, "network_used": False},
    }
    payload["payload_hash"] = _payload_hash(payload)
    _atomic_create(target, payload)
    return target


def load_and_verify_matured_snapshot(path: Path, *, snapshots_root: Path | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"MATURED ilegível: {exc}") from exc
    required = {"schema_version", "status", "event_id", "pre_event_path",
                "pre_event_payload_hash", "result_source", "result_retrieved_at_utc",
                "matured_at_utc", "official_result", "metrics", "tools_provenance",
                "consumer_provenance", "audit_metadata", "payload_hash"}
    missing = sorted(required - set(payload)) if isinstance(payload, dict) else sorted(required)
    if (not isinstance(payload, dict) or missing
            or payload.get("schema_version") != SCHEMA_VERSION
            or payload.get("status") != MATURED):
        raise SnapshotError(f"snapshot MATURED inválido: campos ausentes {missing}")
    if _payload_hash(payload) != payload["payload_hash"]:
        raise SnapshotError("hash do MATURED inconsistente")
    if not isinstance(payload["pre_event_path"], str) or not payload["pre_event_path"].strip():
        raise SnapshotError("pre_event_path inválido")
    root = (snapshots_root or path.parents[2]).resolve()
    pre_path = (root / payload["pre_event_path"]).resolve()
    try:
        pre_path.relative_to(root)
    except ValueError as exc:
        raise SnapshotError("pre_event_path escapa da raiz de snapshots") from exc
    pre = load_and_verify_snapshot(pre_path)
    if payload["event_id"] != pre["event_id"] or payload["pre_event_payload_hash"] != pre["payload_hash"]:
        raise SnapshotError("vínculo MATURED/PRE_EVENT inconsistente")
    official = payload["official_result"]
    if not isinstance(official, dict):
        raise SnapshotError("official_result inválido")
    result = {"event_id": payload["event_id"], "winner": official.get("winner"),
              "score": official.get("score"), "maps": official.get("maps"),
              "result_source": payload["result_source"],
              "result_retrieved_at_utc": payload["result_retrieved_at_utc"]}
    _validate_result(result, pre)
    matured_at = _utc(payload["matured_at_utc"], "matured_at_utc")
    if matured_at < _utc(payload["result_retrieved_at_utc"], "result_retrieved_at_utc"):
        raise SnapshotError("ordem temporal do MATURED inválida")
    winner_p = (pre["final_probability"]["team_a"] if result["winner"] == pre["team_a"]
                else pre["final_probability"]["team_b"])
    expected = {"winner_probability": winner_p,
                "winner_brier": round((1.0 - winner_p) ** 2, 8),
                "winner_hit": result["winner"] == pre["favorite"]}
    if not isinstance(payload["metrics"], dict) or payload["metrics"] != expected:
        raise SnapshotError("métricas do MATURED inconsistentes")
    return payload


def snapshot_status(*, year: int, snapshots_root: Path) -> dict[str, Any]:
    entries = []
    folder = snapshots_root / "pre_event" / str(year)
    for pre_path in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            pre = load_and_verify_snapshot(pre_path)
            mature = snapshots_root / "matured" / str(year) / pre_path.name
            if mature.exists():
                load_and_verify_matured_snapshot(mature, snapshots_root=snapshots_root)
            entries.append({"event_id": pre["event_id"], "pre_event_payload_hash": pre["payload_hash"],
                            "status": "VALID_FORWARD" if mature.exists() else "VERIFIED", "matured_path": str(Path("matured") / str(year) / mature.name) if mature.exists() else None})
        except SnapshotError as exc:
            entries.append({"snapshot": pre_path.name, "status": "FAILED", "reason": str(exc)})
    return {"year": year, "entries": entries, "tools_provenance": _tools_provenance()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CS forward PRE_EVENT/MATURED snapshots")
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("snapshot-pre-event"); pre.add_argument("--event-file", type=Path, required=True); pre.add_argument("--snapshots-dir", type=Path, default=ROOT / "snapshots")
    verify = sub.add_parser("verify-snapshot"); verify.add_argument("--snapshot", type=Path, required=True)
    mature = sub.add_parser("mature-snapshot"); mature.add_argument("--event-id", required=True); mature.add_argument("--year", type=int, required=True); mature.add_argument("--result-file", type=Path, required=True); mature.add_argument("--snapshots-dir", type=Path, default=ROOT / "snapshots")
    status = sub.add_parser("snapshot-status"); status.add_argument("--year", type=int, default=datetime.now(timezone.utc).year); status.add_argument("--snapshots-dir", type=Path, default=ROOT / "snapshots")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot-pre-event": result: Any = {"path": str(create_pre_event_snapshot(event_file=args.event_file, snapshots_root=args.snapshots_dir))}
        elif args.command == "verify-snapshot":
            raw = json.loads(args.snapshot.read_text(encoding="utf-8"))
            loader = load_and_verify_matured_snapshot if raw.get("status") == MATURED else load_and_verify_snapshot
            result = {"snapshot": loader(args.snapshot), "tools_provenance": _tools_provenance()}
        elif args.command == "mature-snapshot": result = {"path": str(mature_snapshot(event_id=args.event_id, year=args.year, result_file=args.result_file, snapshots_root=args.snapshots_dir))}
        else: result = snapshot_status(year=args.year, snapshots_root=args.snapshots_dir)
    except (SnapshotError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr); return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
