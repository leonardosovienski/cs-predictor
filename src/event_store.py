"""Idempotent append-only store; JSONL is an export/offline adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .upstream import UpstreamEvent


class EventRepository(Protocol):
    def put(self, event: UpstreamEvent) -> bool: ...


class JsonlEventRepository:
    """Single-process adapter. Aggregators should implement EventRepository in PostgreSQL."""

    def __init__(self, path: Path):
        self.path = path

    def put(self, event: UpstreamEvent) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    existing.add(json.loads(line)["idempotency_key"])
        if event.idempotency_key in existing:
            return False
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(event.model_dump_json() + "\n")
            stream.flush()
        return True
