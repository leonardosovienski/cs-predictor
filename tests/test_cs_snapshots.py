"""Forward-only CS snapshot contract; all artifacts are under tmp_path."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src import cs_snapshots as snapshots
from src.config import ROOT


NOW = datetime(2030, 1, 1, 10, tzinfo=timezone.utc)
START = "2030-01-02T12:00:00Z"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def strict_provenance(monkeypatch):
    monkeypatch.setattr(snapshots, "_tools_provenance", lambda: {
        "version": "1.1.0", "commit": "2c3d501189cf031bb140203cc9ceb6b835b929d8",
        "content_hash": "40b8a99d28138842090b951fac1158255d231e73260033cb8dd57142db7effa6",
        "worktree_clean": True, "generated_at_utc": "2030-01-01T10:00:00Z"})
    monkeypatch.setattr(snapshots, "_git", lambda _root, *args: {"rev-parse": "a" * 40, "branch": "main", "status": ""}[args[0]])


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
             "maps": [{"name": "Mirage", "score_a": 13, "score_b": 10}], "result_source": "fixture",
             "result_retrieved_at_utc": "2030-01-02T16:00:00Z"} | changes
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_valid_pre_event_is_read_only_and_complete(tmp_path: Path):
    before = (_hash(ROOT / "data" / "cs.db"), _hash(ROOT / "data" / "ratings.json"))
    path = _pre(tmp_path)
    payload = snapshots.load_and_verify_snapshot(path)
    assert payload["status"] == snapshots.PRE_EVENT
    assert payload["tools_provenance"]["version"] == "1.1.0"
    assert payload["consumer_provenance"]["project_worktree_clean"] is True
    assert payload["aliases_resolved"]["team_a"]["canonical"] == "Vitality"
    assert before == (_hash(ROOT / "data" / "cs.db"), _hash(ROOT / "data" / "ratings.json"))


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


def test_matured_links_pre_event_without_model_or_state_changes(tmp_path: Path, monkeypatch):
    pre = _pre(tmp_path)
    before = (_hash(ROOT / "data" / "cs.db"), _hash(ROOT / "data" / "ratings.json"))
    monkeypatch.setattr(snapshots.EloModel, "predict_match", lambda *_: pytest.fail("maturity must not re-run model"))
    matured = snapshots.mature_snapshot(event_id="test-cs-2030-bo3", year=2030, result_file=_result(tmp_path / "result.json"), snapshots_root=tmp_path / "snapshots", now=datetime(2030, 1, 2, 17, tzinfo=timezone.utc))
    payload = json.loads(matured.read_text(encoding="utf-8"))
    assert payload["status"] == snapshots.MATURED and payload["pre_event_payload_hash"] == snapshots.load_and_verify_snapshot(pre)["payload_hash"]
    assert payload["audit_metadata"]["model_reexecuted"] is False
    assert before == (_hash(ROOT / "data" / "cs.db"), _hash(ROOT / "data" / "ratings.json"))
    with pytest.raises(snapshots.SnapshotError, match="já existe"):
        snapshots.mature_snapshot(event_id="test-cs-2030-bo3", year=2030, result_file=_result(tmp_path / "result.json"), snapshots_root=tmp_path / "snapshots")


def test_maturity_requires_pre_event_and_status_transitions(tmp_path: Path):
    with pytest.raises(snapshots.SnapshotError, match="sem PRE_EVENT"):
        snapshots.mature_snapshot(event_id="missing", year=2030, result_file=_result(tmp_path / "result.json", event_id="missing"), snapshots_root=tmp_path / "snapshots")
    _pre(tmp_path)
    pending = snapshots.snapshot_status(year=2030, snapshots_root=tmp_path / "snapshots")
    assert pending["entries"][0]["status"] == "PENDING"
    snapshots.mature_snapshot(event_id="test-cs-2030-bo3", year=2030, result_file=_result(tmp_path / "result.json"), snapshots_root=tmp_path / "snapshots")
    assert snapshots.snapshot_status(year=2030, snapshots_root=tmp_path / "snapshots")["entries"][0]["status"] == "MATURED"
