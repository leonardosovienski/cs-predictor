from __future__ import annotations

import copy
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from src import cs_snapshots
from src.config import ROOT
from tests.experimental.p4_temporal_adapter import (
    ExperimentalTemporalError,
    adapt_snapshots,
    replay_record,
)

HERE = Path(__file__).parent
CASE = json.loads((HERE / "fixtures" / "cs_temporal_case.json").read_text())


def _dt(name: str) -> datetime:
    return datetime.fromisoformat(CASE[name].replace("Z", "+00:00"))


def _pair(tmp_path: Path, monkeypatch) -> tuple[dict, dict]:
    runtime = tmp_path / "runtime"
    data = runtime / "data"
    data.mkdir(parents=True)
    connection = sqlite3.connect(data / "cs.db")
    connection.execute("CREATE TABLE matches(date TEXT, event TEXT, team_a TEXT, team_b TEXT)")
    connection.commit()
    connection.close()
    (data / "ratings.json").write_text('{"Vitality":1590,"MOUZ":1507}')
    (data / "calibration_platt.json").write_text('{"a":1.0,"b":0.0}')
    shutil.copy2(ROOT / "config.yaml", runtime / "config.yaml")
    shutil.copy2(ROOT / "data" / "teams_cs.json", data / "teams_cs.json")
    monkeypatch.setitem(cs_snapshots.create_pre_event_snapshot.__kwdefaults__, "root", runtime)
    monkeypatch.setattr(cs_snapshots, "_tools_provenance", lambda: {"version": "3.0.0"})
    monkeypatch.setattr(
        cs_snapshots,
        "_git",
        lambda _root, *args: {"rev-parse": "a" * 40, "branch": "main", "status": ""}[args[0]],
    )
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "event_id": CASE["event_id"],
                "competition": "Synthetic Cup",
                "stage": "group",
                "scheduled_start_utc": CASE["scheduled_at"],
                "format": "bo3",
                "team_a": CASE["team_a"],
                "team_b": CASE["team_b"],
            }
        )
    )
    snapshots = tmp_path / "snapshots"
    pre_path = cs_snapshots.create_pre_event_snapshot(
        event_file=event, snapshots_root=snapshots, now=_dt("predicted_at")
    )
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "event_id": CASE["event_id"],
                "winner": "Vitality",
                "score": {"team_a": 2, "team_b": 1},
                "maps": [
                    {"name": "A", "score_a": 13, "score_b": 9},
                    {"name": "B", "score_a": 9, "score_b": 13},
                    {"name": "C", "score_a": 13, "score_b": 8},
                ],
                "result_source": "synthetic",
                "result_retrieved_at_utc": CASE["result_available_at"],
            }
        )
    )
    matured_path = cs_snapshots.mature_snapshot(
        event_id=CASE["event_id"],
        year=2030,
        result_file=result,
        snapshots_root=snapshots,
        now=_dt("matured_at"),
    )
    return cs_snapshots.load_and_verify_snapshot(
        pre_path
    ), cs_snapshots.load_and_verify_matured_snapshot(matured_path, snapshots_root=snapshots)


def test_canonical_flow_is_deterministic_and_matches_golden(tmp_path: Path, monkeypatch) -> None:
    pre, matured = _pair(tmp_path / "one", monkeypatch)
    record = adapt_snapshots(pre, matured)
    golden = json.loads((HERE / "golden" / "cs_temporal_expected.json").read_text())
    assert record.to_dict() == golden["record"]
    assert pre["final_probability"] == golden["prediction"]
    assert matured["official_result"] == golden["observed"]
    assert matured["metrics"]["winner_brier"] == pytest.approx(
        golden["record"]["metric_value"], abs=golden["tolerance"], rel=golden["tolerance"]
    )
    assert (
        replay_record(record, input_hash=record.prediction_payload_hash)["record"]
        == golden["record"]
    )


def test_invalid_temporal_identity_hash_and_leak_fail(tmp_path: Path, monkeypatch) -> None:
    pre, matured = _pair(tmp_path, monkeypatch)
    for field in ("generated_at_utc", "scheduled_start_utc"):
        invalid = copy.deepcopy(pre)
        invalid[field] = invalid[field].removesuffix("Z")
        with pytest.raises(ExperimentalTemporalError, match="timezone-aware"):
            adapt_snapshots(invalid, matured)
    invalid = copy.deepcopy(matured)
    invalid["matured_at_utc"] = "2030-01-02T15:00:00Z"
    with pytest.raises(ExperimentalTemporalError, match="premature"):
        adapt_snapshots(pre, invalid)
    invalid = copy.deepcopy(matured)
    invalid["result_retrieved_at_utc"] = "2030-01-02T11:59:59Z"
    with pytest.raises(ExperimentalTemporalError, match="availability"):
        adapt_snapshots(pre, invalid)
    invalid = copy.deepcopy(matured)
    invalid["event_id"] = "other"
    with pytest.raises(ExperimentalTemporalError, match="identity"):
        adapt_snapshots(pre, invalid)
    invalid = copy.deepcopy(matured)
    invalid["pre_event_payload_hash"] = "0" * 64
    with pytest.raises(ExperimentalTemporalError, match="hash link"):
        adapt_snapshots(pre, invalid)
    invalid = copy.deepcopy(pre)
    invalid["official_result"] = matured["official_result"]
    with pytest.raises(ExperimentalTemporalError, match="post-event"):
        adapt_snapshots(invalid, matured)


def test_nonfinite_metric_and_replay_mismatch_fail(tmp_path: Path, monkeypatch) -> None:
    pre, matured = _pair(tmp_path, monkeypatch)
    invalid = copy.deepcopy(matured)
    invalid["metrics"]["winner_brier"] = float("inf")
    with pytest.raises(ExperimentalTemporalError, match="finite"):
        adapt_snapshots(pre, invalid)
    with pytest.raises(ExperimentalTemporalError, match="replay input hash"):
        replay_record(adapt_snapshots(pre, matured), input_hash="f" * 64)
