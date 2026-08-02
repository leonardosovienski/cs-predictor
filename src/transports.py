"""Interchangeable upstream transports with explicit acknowledgement."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from .upstream import UpstreamEvent


class UpstreamTransport(Protocol):
    def receive(self) -> Iterable[UpstreamEvent]: ...
    def acknowledge(self, event: UpstreamEvent) -> None: ...


class FileTransport:
    def __init__(self, path: Path):
        self.path = path

    def receive(self) -> Iterable[UpstreamEvent]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else raw.get("events")
        if not isinstance(rows, list):
            raise ValueError("upstream file must contain a list or {'events': [...]}")
        return [UpstreamEvent.model_validate(row) for row in rows]

    def acknowledge(self, event: UpstreamEvent) -> None:  # immutable input
        del event


class ObjectStorageTransport:
    def __init__(self, client: Any, bucket: str, key: str):
        self.client, self.bucket, self.key = client, bucket, key

    def receive(self) -> Iterable[UpstreamEvent]:
        body = self.client.get_object(Bucket=self.bucket, Key=self.key)["Body"].read()
        rows = json.loads(body)
        return [UpstreamEvent.model_validate(row) for row in rows]

    def acknowledge(self, event: UpstreamEvent) -> None:
        del event


class QueueTransport:
    def __init__(self, client: Any, queue: str):
        self.client, self.queue = client, queue

    def receive(self) -> Iterable[UpstreamEvent]:
        return [UpstreamEvent.model_validate_json(item) for item in self.client.receive(self.queue)]

    def acknowledge(self, event: UpstreamEvent) -> None:
        self.client.acknowledge(self.queue, event.idempotency_key)
