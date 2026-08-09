"""Canonical domain plugin exported through ``predictor.plugins``."""

from __future__ import annotations

from typing import Any

from predictor_ops.provenance import collect_provenance

from .event_store import JsonlEventRepository
from .observability import metrics
from .services import ArchivalCollectionService, PredictionService, SettlementService
from .settings import Settings
from .transports import FileTransport


class CsPredictorPlugin:
    name = "cs"
    domain = "cs"
    version = "3.1.0"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.predictions = PredictionService()
        self.settlements = SettlementService()

    def predict(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.predictions.predict(request)

    def settle(self, event_id: str, result: dict[str, Any]) -> dict[str, Any]:
        return self.settlements.settle(event_id, result)

    def collect(self) -> dict[str, Any]:
        result = ArchivalCollectionService(
            FileTransport(self.settings.upstream_file),
            JsonlEventRepository(self.settings.archive_path),
        ).collect()
        return {
            "state": result.outcome,
            "run_status": result.run_status,
            "accepted": result.accepted,
            "duplicates": result.duplicates,
            "detail": result.detail,
        }

    def capabilities(self) -> dict[str, Any]:
        return {
            # Canonical gateway contract.
            "domain": self.domain,
            "supports_prediction": True,
            "supports_collection": True,
            "supports_settlement": False,
            "extra": {
                "collection_modes": ["file", "object-storage", "queue"],
                "settlement": "disabled-closed-by-human-decision",
                "market_shadow": False,
                "trading": False,
            },
            # Backward-compatible fields used by the domain's existing CLI/tests.
            "prediction": True,
            "collection": ["file", "object-storage", "queue"],
            "settlement": "disabled-closed-by-human-decision",
            "market_shadow": False,
            "trading": False,
            "scientific_status": "CLOSED_BY_HUMAN_DECISION",
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "domain": self.name,
            "version": self.version,
            "provenance": collect_provenance(strict=True),
            "canonical_states": [
                "SUCCEEDED",
                "SOURCE_UNAVAILABLE",
                "NO_UPSTREAM_EVENTS",
                "FAILED",
                "CLOSED_BY_HUMAN_DECISION",
            ],
            "canonical_errors": [
                "ConfigurationError",
                "DataUnavailableError",
                "DataIntegrityError",
                "ProviderRateLimitError",
                "ProviderSchemaError",
                "PredictionError",
                "PersistenceError",
            ],
        }

    def health(self) -> dict[str, Any]:
        details = {
            "collection_only": True,
            "scientific_status": "CLOSED_BY_HUMAN_DECISION",
            "capabilities": self.capabilities(),
            "metrics": metrics(),
        }
        return {
            "status": "SUCCEEDED",
            "domain": self.domain,
            "version": self.version,
            "details": details,
            # Preserve the legacy health payload for existing consumers.
            **details,
        }
