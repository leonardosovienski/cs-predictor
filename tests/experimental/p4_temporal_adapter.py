"""P4-CS test-only adapter for canonical PRE_EVENT/MATURED snapshots."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from predictor_core.data.contracts import PredictionPoint
from predictor_core.measurement.replay import replay


class ExperimentalTemporalError(ValueError):
    """A synthetic CS temporal invariant was violated."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ExperimentalTemporalError("value must be finite canonical JSON") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExperimentalTemporalError(f"invalid {field}") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ExperimentalTemporalError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ExperimentalCsTemporalRecord:
    schema_version: str
    prediction_id: str
    predicted_at: str
    cutoff_at: str
    event_start_at: str
    matures_at: str
    result_available_at: str
    matured_at: str
    prediction_payload_hash: str
    result_payload_hash: str
    metric_name: str
    metric_scale: str
    metric_value: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def adapt_snapshots(pre: dict[str, Any], matured: dict[str, Any]) -> ExperimentalCsTemporalRecord:
    """Validate and adapt an already verified canonical snapshot pair."""
    if pre.get("status") != "PRE_EVENT" or matured.get("status") != "MATURED":
        raise ExperimentalTemporalError("expected PRE_EVENT/MATURED pair")
    forbidden = {"official_result", "result_retrieved_at_utc", "metrics", "matured_at_utc"}
    if forbidden.intersection(pre):
        raise ExperimentalTemporalError("PRE_EVENT contains post-event data")
    if pre.get("event_id") != matured.get("event_id"):
        raise ExperimentalTemporalError("prediction identity mismatch")
    if pre.get("payload_hash") != matured.get("pre_event_payload_hash"):
        raise ExperimentalTemporalError("PRE_EVENT payload hash link mismatch")

    predicted = _time(pre.get("generated_at_utc"), "generated_at_utc")
    event_start = _time(pre.get("scheduled_start_utc"), "scheduled_start_utc")
    available = _time(matured.get("result_retrieved_at_utc"), "result_retrieved_at_utc")
    matured_at = _time(matured.get("matured_at_utc"), "matured_at_utc")
    if predicted >= event_start:
        raise ExperimentalTemporalError("prediction must precede event cutoff")
    if available < event_start or available <= predicted:
        raise ExperimentalTemporalError("result availability violates temporal order")
    if matured_at < available:
        raise ExperimentalTemporalError("premature maturation")
    point = PredictionPoint(
        predicted_at=predicted, matures_at=available, value=pre.get("final_probability")
    )
    if not point.is_mature(matured_at):
        raise ExperimentalTemporalError("premature maturation")

    result = matured.get("official_result")
    metric = matured.get("metrics", {}).get("winner_brier")
    if not isinstance(result, dict) or result.get("winner") not in {
        pre.get("team_a"),
        pre.get("team_b"),
    }:
        raise ExperimentalTemporalError("valid observed result is required")
    if not isinstance(metric, (int, float)) or not math.isfinite(float(metric)):
        raise ExperimentalTemporalError("native metric must be finite")
    prediction_hash = _hash(
        {
            "event_id": pre["event_id"],
            "generated_at_utc": pre["generated_at_utc"],
            "scheduled_start_utc": pre["scheduled_start_utc"],
            "format": pre["format"],
            "team_a": pre["team_a"],
            "team_b": pre["team_b"],
            "ratings": pre["ratings"],
            "final_probability": pre["final_probability"],
        }
    )

    def text(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    return ExperimentalCsTemporalRecord(
        schema_version="p4-cs-temporal-experiment/1",
        prediction_id=pre["event_id"],
        predicted_at=text(predicted),
        cutoff_at=text(event_start),
        event_start_at=text(event_start),
        matures_at=text(available),
        result_available_at=text(available),
        matured_at=text(matured_at),
        prediction_payload_hash=prediction_hash,
        result_payload_hash=_hash(result),
        metric_name="winner_brier",
        metric_scale="cs-native-winning-outcome-squared-error",
        metric_value=float(metric),
    )


def replay_record(record: ExperimentalCsTemporalRecord, *, input_hash: str) -> dict[str, Any]:
    if input_hash != record.prediction_payload_hash:
        raise ExperimentalTemporalError("replay input hash mismatch")
    event = {"input_hash": input_hash, "record": record.to_dict()}
    return replay([event], lambda past: past.latest, key=lambda row: row["record"]["predicted_at"])[
        0
    ]
