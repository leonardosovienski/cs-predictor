"""Forward-only CS snapshot contract; all artifacts are under tmp_path."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src import cs_snapshots as snapshots
from src.config import ROOT


NOW = datetime(2030, 1, 1, 10, tzinfo=timezone.utc)
START = "2030-01-02T12:00:00Z"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_root(path: Path) -> Path:
    """Minimal isolated scientific runtime; tests never require gitignored data."""
    data = path / "data"
    data.mkdir(parents=True)
    conn = sqlite3.connect(data / "cs.db")
    conn.execute("CREATE TABLE matches(date TEXT, event TEXT, team_a TEXT, team_b TEXT)")
    conn.commit(); conn.close()
    (data / "ratings.json").write_text('{"Vitality": 1590, "MOUZ": 1507}', encoding="utf-8")
    (data / "calibration_platt.json").write_text('{"a": 1.0, "b": 0.0}', encoding="utf-8")
    shutil.copy2(ROOT / "config.yaml", path / "config.yaml")
    shutil.copy2(ROOT / "data" / "teams_cs.json", data / "teams_cs.json")
    return path


@pytest.fixture(autouse=True)
def strict_provenance(monkeypatch, tmp_path):
    runtime = _runtime_root(tmp_path / "runtime")
    monkeypatch.setitem(snapshots.create_pre_event_snapshot.__kwdefaults__, "root", runtime)
    monkeypatch.setattr(snapshots, "_tools_provenance", lambda: {
        "version": "1.1.0", "commit": "2c3d501189cf031bb140203cc9ceb6b835b929d8",
        "content_hash": "40b8a99d28138842090b951fac1158255d231e73260033cb8dd57142db7effa6",
        "worktree_clean": True, "generated_at_utc": "2030-01-01T10:00:00Z"})
    monkeypatch.setattr(snapshots, "_git", lambda _root, *args: {"rev-parse": "a" * 40, "branch": "main", "status": ""}[args[0]])
    return runtime


def _event(path: Path, **changes) -> Path:
    value = {"event_id": "test-cs-2030-bo3", "competition": "Test Cup", "stage": "group",
             "scheduled_start_utc": START, "format": "bo3", "team_a": "Vitality", "team_b": "MOUZ"} | changes
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _pre(tmp_path: Path) -> Path:
    return snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "event.json"), snapshots_root=tmp_path / "snapshots", now=NOW)


def _result(path: Path, **changes) -> Path:
    value = {"event_id": "test-cs-2030-bo3", "winner": "Vitality", "score": {"team_a": 2, "team_b": 1},
             "maps": [{"name": "Mirage", "score_a": 13, "score_b": 10},
                      {"name": "Inferno", "score_a": 8, "score_b": 13},
                      {"name": "Nuke", "score_a": 13, "score_b": 7}], "result_source": "fixture",
             "result_retrieved_at_utc": "2030-01-02T16:00:00Z"} | changes
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_valid_pre_event_is_read_only_and_complete(tmp_path: Path, strict_provenance: Path):
    before = (_hash(strict_provenance / "data" / "cs.db"), _hash(strict_provenance / "data" / "ratings.json"))
    path = _pre(tmp_path)
    payload = snapshots.load_and_verify_snapshot(path)
    assert payload["status"] == snapshots.PRE_EVENT
    assert payload["tools_provenance"]["version"] == "1.1.0"
    assert payload["consumer_provenance"]["project_worktree_clean"] is True
    assert payload["aliases_resolved"]["team_a"]["canonical"] == "Vitality"
    assert before == (_hash(strict_provenance / "data" / "cs.db"), _hash(strict_provenance / "data" / "ratings.json"))


def test_rejects_naive_late_missing_format_alias_and_existing_result(tmp_path: Path, monkeypatch):
    with pytest.raises(snapshots.SnapshotError, match="timezone"):
        snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "naive.json", scheduled_start_utc="2030-01-02T12:00:00"), snapshots_root=tmp_path / "s", now=NOW)
    with pytest.raises(snapshots.SnapshotError, match="após"):
        snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "late.json"), snapshots_root=tmp_path / "s", now=datetime(2030, 1, 2, 12, tzinfo=timezone.utc))
    with pytest.raises(snapshots.SnapshotError, match="formato"):
        _pre_bad = snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "fmt.json", format=""), snapshots_root=tmp_path / "s", now=NOW)
    with pytest.raises(snapshots.SnapshotError, match="alias"):
        snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "alias.json", team_a="unknown team"), snapshots_root=tmp_path / "s", now=NOW)
    monkeypatch.setattr(snapshots, "_event_has_result", lambda *_: True)
    with pytest.raises(snapshots.SnapshotError, match="resultado"):
        snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "result.json"), snapshots_root=tmp_path / "s", now=NOW)


def test_overwrite_hash_tampering_and_project_or_tools_failure(tmp_path: Path, monkeypatch):
    path = _pre(tmp_path)
    with pytest.raises(snapshots.SnapshotError, match="overwrite"):
        _pre(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8")); payload["favorite"] = "MOUZ"; path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(snapshots.SnapshotError, match="hash"):
        snapshots.load_and_verify_snapshot(path)
    monkeypatch.setattr(snapshots, "_tools_provenance", lambda: (_ for _ in ()).throw(snapshots.SnapshotError("tools provenance strict indisponível")))
    with pytest.raises(snapshots.SnapshotError, match="tools"):
        snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "tools.json", event_id="tools-fail"), snapshots_root=tmp_path / "other", now=NOW)
    monkeypatch.setattr(snapshots, "_git", lambda _root, *args: " M x" if args[0] == "status" else "main")
    with pytest.raises(snapshots.SnapshotError, match="worktree"):
        snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "dirty.json", event_id="dirty-fail"), snapshots_root=tmp_path / "other", now=NOW)


def test_missing_rating_and_determinism_without_network(tmp_path: Path, monkeypatch):
    original = snapshots.EloModel.predict_match
    monkeypatch.setattr(snapshots.EloModel, "predict_match", lambda *_: (_ for _ in ()).throw(ValueError("rating missing")))
    with pytest.raises(snapshots.SnapshotError, match="rating"):
        snapshots.create_pre_event_snapshot(event_file=_event(tmp_path / "rating.json"), snapshots_root=tmp_path / "missing", now=NOW)
    monkeypatch.setattr(snapshots.EloModel, "predict_match", original)
    monkeypatch.setattr("urllib.request.urlopen", lambda *_: pytest.fail("rede proibida"))
    first, second = _pre(tmp_path / "one"), _pre(tmp_path / "two")
    assert json.loads(first.read_text(encoding="utf-8")) == json.loads(second.read_text(encoding="utf-8"))


def test_matured_links_pre_event_without_model_or_state_changes(tmp_path: Path, monkeypatch, strict_provenance: Path):
    pre = _pre(tmp_path)
    before = (_hash(strict_provenance / "data" / "cs.db"), _hash(strict_provenance / "data" / "ratings.json"))
    monkeypatch.setattr(snapshots.EloModel, "predict_match", lambda *_: pytest.fail("maturity must not re-run model"))
    matured = snapshots.mature_snapshot(event_id="test-cs-2030-bo3", year=2030, result_file=_result(tmp_path / "result.json"), snapshots_root=tmp_path / "snapshots", now=datetime(2030, 1, 2, 17, tzinfo=timezone.utc))
    payload = json.loads(matured.read_text(encoding="utf-8"))
    assert payload["status"] == snapshots.MATURED and payload["pre_event_payload_hash"] == snapshots.load_and_verify_snapshot(pre)["payload_hash"]
    assert snapshots.load_and_verify_matured_snapshot(
        matured, snapshots_root=tmp_path / "snapshots")["payload_hash"] == payload["payload_hash"]
    assert payload["audit_metadata"]["model_reexecuted"] is False
    assert before == (_hash(strict_provenance / "data" / "cs.db"), _hash(strict_provenance / "data" / "ratings.json"))
    with pytest.raises(snapshots.SnapshotError, match="já existe"):
        snapshots.mature_snapshot(event_id="test-cs-2030-bo3", year=2030, result_file=_result(tmp_path / "result.json"), snapshots_root=tmp_path / "snapshots")


def test_maturity_requires_pre_event_and_status_transitions(tmp_path: Path):
    with pytest.raises(snapshots.SnapshotError, match="sem PRE_EVENT"):
        snapshots.mature_snapshot(event_id="missing", year=2030, result_file=_result(tmp_path / "result.json", event_id="missing"), snapshots_root=tmp_path / "snapshots")
    _pre(tmp_path)
    pending = snapshots.snapshot_status(year=2030, snapshots_root=tmp_path / "snapshots")
    assert pending["entries"][0]["status"] == "VERIFIED"
    snapshots.mature_snapshot(event_id="test-cs-2030-bo3", year=2030,
                              result_file=_result(tmp_path / "result.json"),
                              snapshots_root=tmp_path / "snapshots",
                              now=datetime(2030, 1, 2, 17, tzinfo=timezone.utc))
    assert snapshots.snapshot_status(year=2030, snapshots_root=tmp_path / "snapshots")["entries"][0]["status"] == "VALID_FORWARD"


@pytest.mark.parametrize("changes,match", [
    ({"winner": "Vitality", "score": {"team_a": 0, "team_b": 2}}, "vencedor"),
    ({"score": {"team_a": 3, "team_b": 0}}, "terminal"),
    ({"result_source": ""}, "fonte"),
    ({"result_retrieved_at_utc": "2030-01-02T11:00:00Z"}, "antes do início"),
    ({"maps": []}, "mapas jogados"),
])
def test_maturity_rejects_impossible_results(tmp_path: Path, changes, match):
    _pre(tmp_path)
    with pytest.raises(snapshots.SnapshotError, match=match):
        snapshots.mature_snapshot(
            event_id="test-cs-2030-bo3", year=2030,
            result_file=_result(tmp_path / "result.json", **changes),
            snapshots_root=tmp_path / "snapshots",
            now=datetime(2030, 1, 2, 17, tzinfo=timezone.utc))


def test_maturity_rejects_time_travel_and_status_detects_tampering(tmp_path: Path):
    _pre(tmp_path)
    result = _result(tmp_path / "result.json")
    with pytest.raises(snapshots.SnapshotError, match="anterior"):
        snapshots.mature_snapshot(
            event_id="test-cs-2030-bo3", year=2030, result_file=result,
            snapshots_root=tmp_path / "snapshots",
            now=datetime(2030, 1, 2, 15, tzinfo=timezone.utc))
    matured = snapshots.mature_snapshot(
        event_id="test-cs-2030-bo3", year=2030, result_file=result,
        snapshots_root=tmp_path / "snapshots",
        now=datetime(2030, 1, 2, 17, tzinfo=timezone.utc))
    payload = json.loads(matured.read_text(encoding="utf-8"))
    payload["metrics"]["winner_brier"] = 999
    matured.write_text(json.dumps(payload), encoding="utf-8")
    status = snapshots.snapshot_status(year=2030, snapshots_root=tmp_path / "snapshots")
    assert status["entries"][0]["status"] == "FAILED"
    assert "hash" in status["entries"][0]["reason"]


def test_matured_semantic_validation_survives_recomputed_hash(tmp_path: Path):
    _pre(tmp_path)
    matured = snapshots.mature_snapshot(
        event_id="test-cs-2030-bo3", year=2030,
        result_file=_result(tmp_path / "result.json"),
        snapshots_root=tmp_path / "snapshots",
        now=datetime(2030, 1, 2, 17, tzinfo=timezone.utc))
    payload = json.loads(matured.read_text(encoding="utf-8"))
    payload["official_result"]["score"] = {"team_a": 0, "team_b": 2}
    payload["payload_hash"] = snapshots._payload_hash(payload)
    matured.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(snapshots.SnapshotError, match="vencedor"):
        snapshots.load_and_verify_matured_snapshot(
            matured, snapshots_root=tmp_path / "snapshots")


def test_atomic_create_never_overwrites_under_race(tmp_path: Path):
    target = tmp_path / "artifact.json"
    payloads = [{"writer": value} for value in range(8)]

    def create(payload):
        try:
            snapshots._atomic_create(target, payload)
            return True
        except snapshots.SnapshotError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(create, payloads))
    assert outcomes.count(True) == 1
    assert json.loads(target.read_text(encoding="utf-8")) in payloads


def test_truncated_snapshot_is_rejected(tmp_path: Path):
    path = tmp_path / "truncated.json"
    path.write_text('{"status":"PRE_EVENT"', encoding="utf-8")
    with pytest.raises(snapshots.SnapshotError, match="ilegível"):
        snapshots.load_and_verify_snapshot(path)


def test_matured_predecessor_cannot_escape_snapshot_root(tmp_path: Path):
    _pre(tmp_path)
    matured = snapshots.mature_snapshot(
        event_id="test-cs-2030-bo3", year=2030,
        result_file=_result(tmp_path / "result.json"),
        snapshots_root=tmp_path / "snapshots",
        now=datetime(2030, 1, 2, 17, tzinfo=timezone.utc))
    payload = json.loads(matured.read_text(encoding="utf-8"))
    payload["pre_event_path"] = "../../outside.json"
    payload["payload_hash"] = snapshots._payload_hash(payload)
    matured.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(snapshots.SnapshotError, match="escapa"):
        snapshots.load_and_verify_matured_snapshot(
            matured, snapshots_root=tmp_path / "snapshots")
