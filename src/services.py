"""Application services separated from providers, persistence and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from predictor_core import ScientificState
from predictor_ops import RunStatus

from .event_store import EventRepository
from .observability import increment
from .transports import UpstreamTransport


@dataclass(frozen=True)
class ServiceResult:
    run_status: RunStatus
    outcome: str
    accepted: int = 0
    duplicates: int = 0
    detail: str | None = None


class ArchivalCollectionService:
    def __init__(self, transport: UpstreamTransport, repository: EventRepository):
        self.transport, self.repository = transport, repository

    def collect(self) -> ServiceResult:
        try:
            events = list(self.transport.receive())
        except (OSError, TimeoutError, ConnectionError) as exc:
            increment("collection_runs_total", state="SOURCE_UNAVAILABLE")
            return ServiceResult(RunStatus.SOURCE_UNAVAILABLE, "SOURCE_UNAVAILABLE", detail=type(exc).__name__)
        if not events:
            increment("collection_runs_total", state="NO_UPSTREAM_EVENTS")
            return ServiceResult(RunStatus.SUCCEEDED, "NO_UPSTREAM_EVENTS")
        accepted = duplicates = 0
        for event in events:
            if self.repository.put(event):
                accepted += 1
            else:
                duplicates += 1
            self.transport.acknowledge(event)
        increment("collection_runs_total", state="SUCCEEDED")
        increment("collection_events_total", accepted, result="accepted")
        increment("collection_events_total", duplicates, result="duplicate")
        return ServiceResult(RunStatus.SUCCEEDED, "SUCCEEDED", accepted, duplicates)


class PredictionService:
    def predict(self, request: dict[str, Any]) -> dict[str, Any]:
        from .model import EloModel

        model = EloModel()
        return model.predict_match(
            request["team_a"], request["team_b"], request.get("format", "bo3")
        )


class IngestionService:
    def __init__(self, provider: Any):
        self.provider = provider

    def ingest(self, until_date: str) -> list[dict[str, Any]]:
        return [row for page in self.provider.fetch_results(until_date) for row in page]


class SettlementService:
    """Sports-only settlement boundary. Market shadow can never be reopened here."""

    SCIENTIFIC_STATUS = ScientificState.CLOSED_BY_HUMAN_DECISION

    def settle(self, event_id: str, result: dict[str, Any]) -> dict[str, Any]:
        return {"event_id": event_id, "result": result, "market_shadow": self.SCIENTIFIC_STATUS}
