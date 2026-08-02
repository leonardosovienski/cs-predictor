"""Versioned upstream-event contract and deterministic identity."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "cs.upstream-event/1.0"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    source_uri: str | None = None
    collector: str = Field(min_length=1)
    collector_version: str = Field(min_length=1)


class UpstreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["cs.upstream-event/1.0"] = SCHEMA_VERSION
    event_id: str = Field(pattern=r"^cs2-[a-f0-9]{32}$")
    observed_at: datetime
    available_at: datetime
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    idempotency_key: str = Field(pattern=r"^cs-upstream-v1:[a-f0-9]{64}$")
    provenance: Provenance
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_integrity(self) -> UpstreamEvent:
        if self.observed_at.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("observed_at and available_at must be timezone-aware")
        expected_hash = "sha256:" + hashlib.sha256(_canonical(self.payload)).hexdigest()
        if self.content_hash != expected_hash:
            raise ValueError("content_hash does not match payload")
        identity = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "content_hash": self.content_hash,
            "source": self.provenance.source,
            "source_record_id": self.provenance.source_record_id,
        }
        expected_key = "cs-upstream-v1:" + hashlib.sha256(_canonical(identity)).hexdigest()
        if self.idempotency_key != expected_key:
            raise ValueError("idempotency_key does not match event identity")
        return self

    @classmethod
    def create(
        cls,
        *,
        payload: dict[str, Any],
        provenance: Provenance,
        observed_at: datetime,
        available_at: datetime | None = None,
    ) -> UpstreamEvent:
        event_seed = {"source": provenance.source, "source_record_id": provenance.source_record_id}
        event_id = "cs2-" + hashlib.sha256(_canonical(event_seed)).hexdigest()[:32]
        content_hash = "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()
        identity = {
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id,
            "content_hash": content_hash,
            "source": provenance.source,
            "source_record_id": provenance.source_record_id,
        }
        key = "cs-upstream-v1:" + hashlib.sha256(_canonical(identity)).hexdigest()
        return cls(
            event_id=event_id,
            observed_at=observed_at.astimezone(UTC),
            available_at=(available_at or observed_at).astimezone(UTC),
            content_hash=content_hash,
            idempotency_key=key,
            provenance=provenance,
            payload=payload,
        )
