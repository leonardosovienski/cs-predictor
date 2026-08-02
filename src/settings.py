"""Typed operational settings and storage-boundary invariants."""

import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CS_", env_file=".env", extra="forbid")
    environment: str = "development"
    sports_db_url: str = "sqlite:///data/cs.db"
    market_db_url: str = "sqlite:///data/market.db"
    archive_path: Path = Path("data/collection_only/archive.jsonl")
    raw_cache_dir: Path = Path("data/cache/hltv")
    hltv_delay_seconds: float = Field(2.0, ge=0.5)
    hltv_timeout_seconds: float = Field(30.0, gt=0, le=120)
    hltv_max_retries: int = Field(3, ge=0, le=8)
    hltv_circuit_failure_threshold: int = Field(3, ge=1)
    hltv_circuit_recovery_seconds: float = Field(300.0, gt=0)
    upstream_transport: Literal["file", "object-storage", "queue"] = "file"
    upstream_file: Path = Path("data/collection_only/upstream_events.json")
    object_bucket: str | None = None
    object_key: str | None = None
    queue_url: str | None = None
    queue_name: str | None = None
    scheduler_runtime_dir: Path = Path("runtime")
    otel_endpoint: str | None = None

    @model_validator(mode="after")
    def isolated_databases(self) -> "Settings":
        if canonical_database_target(self.sports_db_url) == canonical_database_target(
            self.market_db_url
        ):
            raise ValueError("Sports DB and Market DB must be different physical databases")
        return self


def settings() -> Settings:
    return Settings()


def canonical_database_target(url: str) -> str:
    """Resolve SQLite aliases without opening either database."""
    prefix = "sqlite:///"
    if not url.casefold().startswith(prefix):
        return url.strip().casefold()
    raw = url[len(prefix) :]
    # ``os.path.expandvars`` only understands ``%VAR%`` on Windows. Accept the
    # form explicitly so database-alias isolation has identical semantics in
    # Linux containers and Windows operator environments.
    raw = re.sub(
        r"%([^%]+)%",
        lambda match: os.environ.get(match.group(1), match.group(0)),
        raw,
    )
    raw = os.path.expandvars(os.path.expanduser(raw))
    path = Path(raw)
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = Path(os.path.abspath(os.path.normpath(raw)))
    return os.path.normcase(str(resolved)).casefold()
