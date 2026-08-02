"""Coorte arquivistica CS2 COLLECTION_ONLY, isolada de mercados e modelos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
import unicodedata
import uuid

from predictor_core.contracts.collection import CollectionArchive, LifecycleState, ObservationEnvelope

# `pythonw.exe` (executavel de toda tarefa agendada) nao tem console: um
# processo de console filho ganharia janela VISIVEL na tela do dono.
# Saida ja e capturada, entao a flag nao esconde nada.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

ROOT = Path(__file__).resolve().parents[1]
COLLECTION_ROOT = ROOT / "data" / "collection_only"
RUN_FILE = COLLECTION_ROOT / "run.json"
ARCHIVE_FILE = COLLECTION_ROOT / "archive.jsonl"
SNAPSHOTS = COLLECTION_ROOT / "source_snapshots"
VALID_FORMATS = {"bo1", "bo3", "bo5"}


class ArchivalCollectionError(ValueError): pass


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _utc(value: str | datetime) -> datetime:
    value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if value.tzinfo is None or value.utcoffset() is None: raise ArchivalCollectionError("horario UTC obrigatorio")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str: return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _team_id(name: str) -> str:
    # Exato em Unicode: academy e principal, ou LEO/Leo, nunca colapsam.
    return "hltv-team-" + hashlib.sha256(unicodedata.normalize("NFC", name).encode()).hexdigest()[:20]


def canonical_event_id(row: dict[str, Any]) -> str:
    return "cs2-" + _hash({"source": row["source"], "source_record_id": str(row["source_record_id"]),
                              "scheduled_at": _iso(_utc(row["scheduled_at"])), "team_a_id": _team_id(row["team_a"]),
                              "team_b_id": _team_id(row["team_b"]), "format": row["format"],
                              "competition": row["competition"], "scope": "series"})[:32]


def _commit() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, capture_output=True, check=True, creationflags=_NO_WINDOW).stdout.strip()


def ensure_run(*, now: datetime | None = None) -> dict[str, str]:
    COLLECTION_ROOT.mkdir(parents=True, exist_ok=True)
    if RUN_FILE.exists(): return json.loads(RUN_FILE.read_text(encoding="utf-8"))
    created = now or datetime.now(timezone.utc)
    payload = {"collection_run_id": f"cs2-archival-{created:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}",
               "mode": "COLLECTION_ONLY", "created_at_utc": _iso(created), "project": "cs-predictor"}
    tmp = RUN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(RUN_FILE)
    return payload


def normalize_source_row(row: dict[str, Any]) -> dict[str, Any]:
    required = {"source", "source_record_id", "scheduled_at", "team_a", "team_b", "competition", "format", "scope"}
    if missing := sorted(key for key in required if not row.get(key)): raise ArchivalCollectionError(f"campos ausentes: {missing}")
    if row.get("identity_ambiguous"): raise ArchivalCollectionError("identidade ambigua")
    if row["scope"] != "series": raise ArchivalCollectionError("mapa e serie nao podem ser misturados")
    if row["format"].lower() not in VALID_FORMATS: raise ArchivalCollectionError("formato de serie invalido")
    if not isinstance(row["team_a"], str) or not isinstance(row["team_b"], str) or _team_id(row["team_a"]) == _team_id(row["team_b"]):
        raise ArchivalCollectionError("equipes iguais ou identidade invalida")
    clean = dict(row); clean["format"] = clean["format"].lower(); clean["scheduled_at"] = _iso(_utc(clean["scheduled_at"]))
    return clean


class ArchivalCollection:
    def __init__(self, root: Path = ROOT):
        self.root = root; self.archive = CollectionArchive(ARCHIVE_FILE if root == ROOT else root / "archive.jsonl")
        self.run = ensure_run() if root == ROOT else {"collection_run_id": "test-run"}

    def ingest(self, rows: list[dict[str, Any]], *, observed_at: datetime | None = None) -> dict[str, int]:
        run = self.run
        # O archive serializa em segundos; microssegundo sobrevivente quebraria a
        # comparacao com o predecessor relido do log na proxima transicao.
        observed = (observed_at or datetime.now(timezone.utc)).replace(microsecond=0)
        counts = {"accepted": 0, "ambiguous": 0, "invalid": 0, "complete": 0}
        for raw in rows:
            try:
                row = normalize_source_row(raw); event_id = canonical_event_id(row)
                source_hash = _hash(row); snapshot = self._snapshot(event_id, row, source_hash)
                envelope = ObservationEnvelope(collection_run_id=run["collection_run_id"], project="cs-predictor", domain="cs2",
                    canonical_event_id=event_id, observed_at=observed, scheduled_at=_utc(row["scheduled_at"]), source=row["source"],
                    source_record_id=str(row["source_record_id"]), provenance_hash=source_hash, source_snapshot_hash=snapshot,
                    code_commit=_commit(), core_version=version("predictor-core"),
                    participants={"team_a": row["team_a"], "team_a_id": _team_id(row["team_a"]), "team_b": row["team_b"], "team_b_id": _team_id(row["team_b"]), "scope": "series"},
                    competition={"name": row["competition"], "format": row["format"]})
                current = self._latest(run["collection_run_id"], event_id)
                if current is None: current = self.archive.append(envelope)
                current = self._advance(current, row, observed)
                counts["accepted"] += 1; counts["complete"] += current.lifecycle_state == LifecycleState.COMPLETE
            except ArchivalCollectionError as exc:
                counts["ambiguous" if "ambigua" in str(exc) else "invalid"] += 1
        return counts

    def _snapshot(self, event_id: str, row: dict, digest: str) -> str:
        folder = SNAPSHOTS if self.root == ROOT else self.root / "snapshots"; folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{event_id}-{digest[:12]}.json"
        if not target.exists():
            tmp = target.with_suffix(".tmp"); tmp.write_text(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"); tmp.replace(target)
        return hashlib.sha256(target.read_bytes()).hexdigest()

    def _latest(self, run_id: str, event_id: str):
        history = self.archive.history(run_id, event_id); return history[-1] if history else None

    def _advance(self, current, row: dict, observed: datetime):
        if current.is_terminal: return current
        if current.lifecycle_state == LifecycleState.DISCOVERED:
            current = self.archive.append(current.transition(LifecycleState.VALIDATED, at=observed), previous=current)
        if current.lifecycle_state == LifecycleState.VALIDATED:
            current = self.archive.append(current.transition(LifecycleState.SNAPSHOT_RECORDED, at=observed), previous=current)
        if _utc(row["scheduled_at"]) <= observed and current.lifecycle_state == LifecycleState.SNAPSHOT_RECORDED:
            current = self.archive.append(current.transition(LifecycleState.EVENT_STARTED, at=observed), previous=current)
        result = row.get("official_result")
        if result:
            if not isinstance(result, dict) or not result.get("winner") or not result.get("validated_at"):
                raise ArchivalCollectionError("resultado oficial invalido")
            if _utc(result["validated_at"]) < _utc(row["scheduled_at"]): raise ArchivalCollectionError("resultado oficial anterior ao evento")
            if current.lifecycle_state == LifecycleState.SNAPSHOT_RECORDED:
                current = self.archive.append(current.transition(LifecycleState.EVENT_STARTED, at=observed), previous=current)
            current = self.archive.append(current.transition(LifecycleState.OFFICIAL_RESULT_FOUND, at=observed, official_result=result), previous=current)
            current = self.archive.append(current.transition(LifecycleState.COMPLETE, at=observed, official_result=result), previous=current)
        return current

    def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc); run = self.run; events = {}
        for row in self.archive._events():
            env = ObservationEnvelope.from_dict(row["envelope"])
            if env.collection_run_id == run["collection_run_id"]: events[env.canonical_event_id] = env
        alerts = []
        expected = [e for e in events.values() if e.lifecycle_state not in {LifecycleState.COMPLETE, LifecycleState.REJECTED}]
        if not expected: alerts.append("NO_UPSTREAM_EVENTS")
        for item in expected:
            if item.scheduled_at <= now and item.official_result is None: alerts.append("RESULT_INGESTION_STALLED")
            if now - item.updated_at >= timedelta(hours=48): alerts.append("COLLECTION_STALLED_48H")
        return {"collection_only": True, "collection_run_id": run["collection_run_id"], "events": len(events), "alerts": sorted(set(alerts))}
