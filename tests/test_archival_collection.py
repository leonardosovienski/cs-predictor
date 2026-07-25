from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_archival_collection import _source_unavailable
from src.archival_collection import ArchivalCollection, ArchivalCollectionError, canonical_event_id


NOW = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)


def row(**changes):
    value = {"source": "hltv", "source_record_id": "100", "scheduled_at": "2030-01-02T12:00:00Z",
             "team_a": "Example Academy", "team_b": "Example", "competition": "Cup", "format": "bo3", "scope": "series"}
    value.update(changes); return value


def test_collection_only_lifecycle_complete_is_idempotent_and_isolated(tmp_path):
    service = ArchivalCollection(tmp_path)
    finished = row(scheduled_at="2030-01-01T10:00:00Z", official_result={"winner": "Example", "score": [0, 2], "validated_at": "2030-01-01T11:00:00Z"})
    assert service.ingest([finished], observed_at=NOW) == {"accepted": 1, "ambiguous": 0, "invalid": 0, "complete": 1}
    assert service.ingest([finished], observed_at=NOW)["complete"] == 1
    history = list(service.archive._events())
    assert [x["state"] for x in history] == ["DISCOVERED", "VALIDATED", "SNAPSHOT_RECORDED", "EVENT_STARTED", "OFFICIAL_RESULT_FOUND", "COMPLETE"]
    assert all(x["collection_only"] is True for x in history)


def test_rejects_map_series_mix_identity_collision_and_invalid_format(tmp_path):
    service = ArchivalCollection(tmp_path)
    counts = service.ingest([row(scope="map"), row(team_b="Example Academy"), row(format="bo2"), row(identity_ambiguous=True)], observed_at=NOW)
    assert counts["invalid"] == 3 and counts["ambiguous"] == 1
    assert canonical_event_id(row(team_a="Example Academy", team_b="Example")) != canonical_event_id(row(team_a="Example", team_b="Example Academy"))


def test_past_without_official_result_stalls_and_no_events_alert(tmp_path):
    service = ArchivalCollection(tmp_path)
    assert service.status(now=NOW)["alerts"] == ["NO_UPSTREAM_EVENTS"]
    service.ingest([row(scheduled_at="2030-01-01T10:00:00Z")], observed_at=NOW)
    assert "RESULT_INGESTION_STALLED" in service.status(now=NOW)["alerts"]
    later = NOW + timedelta(hours=49)
    assert "COLLECTION_STALLED_48H" in service.status(now=later)["alerts"]


def test_missing_upstream_is_structured_not_an_empty_success(tmp_path):
    payload = _source_unavailable(tmp_path / "missing.json", "UPSTREAM_INPUT_MISSING")
    assert payload["status"] == "SOURCE_UNAVAILABLE"
    assert payload["accepted"] == 0 and payload["input_present"] is False
