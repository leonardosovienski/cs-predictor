from datetime import datetime, timezone
import json
from typing import Any, Protocol, runtime_checkable

import pytest
from pydantic import ValidationError

from src.event_store import JsonlEventRepository
from src.plugin import CsPredictorPlugin
from src.services import ArchivalCollectionService, OperationalState, SettlementService
from src.settings import Settings, settings
from src.transports import FileTransport, ObjectStorageTransport, QueueTransport
from src.upstream import Provenance, UpstreamEvent

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@runtime_checkable
class PluginContract(Protocol):
    name: str

    def predict(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def collect(self) -> dict[str, Any]: ...
    def settle(self, event_id: str, result: dict[str, Any]) -> dict[str, Any]: ...
    def health(self) -> dict[str, Any]: ...
    def capabilities(self) -> dict[str, Any]: ...
    def metadata(self) -> dict[str, Any]: ...


def event():
    return UpstreamEvent.create(
        payload={"team_a": "Vitality", "team_b": "MOUZ", "format": "bo3"},
        provenance=Provenance(
            source="fixture", source_record_id="42", collector="tests", collector_version="1"
        ),
        observed_at=NOW,
    )


def test_contract_detects_tampering():
    raw = event().model_dump(mode="json")
    raw["payload"]["format"] = "bo5"
    with pytest.raises(ValidationError, match="content_hash"):
        UpstreamEvent.model_validate(raw)


def test_reprocessing_does_not_duplicate(tmp_path):
    item = event()
    source = tmp_path / "events.json"
    source.write_text(json.dumps([item.model_dump(mode="json")]), encoding="utf-8")
    service = ArchivalCollectionService(
        FileTransport(source), JsonlEventRepository(tmp_path / "archive.jsonl")
    )
    assert service.collect().accepted == 1
    replay = service.collect()
    assert replay.accepted == 0 and replay.duplicates == 1


def test_no_events_is_not_source_unavailable(tmp_path):
    source = tmp_path / "empty.json"
    source.write_text("[]", encoding="utf-8")
    result = ArchivalCollectionService(
        FileTransport(source), JsonlEventRepository(tmp_path / "a")
    ).collect()
    assert result.state is OperationalState.NO_UPSTREAM_EVENTS
    missing = ArchivalCollectionService(
        FileTransport(tmp_path / "missing"), JsonlEventRepository(tmp_path / "b")
    ).collect()
    assert missing.state is OperationalState.SOURCE_UNAVAILABLE


def test_database_boundary_and_human_closure():
    with pytest.raises(ValidationError, match="different physical"):
        Settings(sports_db_url="sqlite:///same.db", market_db_url="sqlite:///same.db")
    assert SettlementService.SCIENTIFIC_STATUS is OperationalState.CLOSED_BY_HUMAN_DECISION


def test_plugin_health_prediction_and_settlement(tmp_path):
    plugin = CsPredictorPlugin(
        Settings(raw_cache_dir=tmp_path, upstream_file=tmp_path / "missing.json")
    )
    assert isinstance(plugin, PluginContract)
    assert plugin.health()["scientific_status"] == "CLOSED_BY_HUMAN_DECISION"
    prediction = plugin.predict({"team_a": "Vitality", "team_b": "MOUZ", "format": "bo3"})
    assert prediction["prob_team_a"] > 0.5
    assert (
        plugin.settle("event-1", {"winner": "Vitality"})["market_shadow"]
        == "CLOSED_BY_HUMAN_DECISION"
    )
    assert plugin.collect()["state"] == "SOURCE_UNAVAILABLE"
    assert plugin.metadata()["domain"] == "cs"
    assert "ProviderSchemaError" in plugin.metadata()["canonical_errors"]
    assert settings().sports_db_url != settings().market_db_url


def test_object_and_queue_transports():
    item = event()

    class Body:
        def read(self):
            return json.dumps([item.model_dump(mode="json")]).encode()

    class Objects:
        def get_object(self, **_kwargs):
            return {"Body": Body()}

    assert list(ObjectStorageTransport(Objects(), "bucket", "key").receive()) == [item]

    class Queue:
        acknowledged = None

        def receive(self, _queue):
            return [item.model_dump_json()]

        def acknowledge(self, queue, key):
            self.acknowledged = (queue, key)

    client = Queue()
    transport = QueueTransport(client, "events")
    assert list(transport.receive()) == [item]
    transport.acknowledge(item)
    assert client.acknowledged == ("events", item.idempotency_key)


def test_cli_health_and_collection(tmp_path, monkeypatch, capsys):
    from src import cli

    assert cli.main(["health"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "SUCCEEDED"
    source = tmp_path / "events.json"
    source.write_text(json.dumps([event().model_dump(mode="json")]), encoding="utf-8")
    monkeypatch.setenv("CS_ARCHIVE_PATH", str(tmp_path / "archive.jsonl"))
    assert cli.collect_main(["--input", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["accepted"] == 1
    assert cli.main(["collect", "--input", str(source)]) == 0
