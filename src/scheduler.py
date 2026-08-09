"""Portable scheduler entry point backed exclusively by predictor_ops."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from predictor_ops import JobConfig, run_job
from predictor_ops.config import FileJobConfigSource

from .observability import increment
from .settings import Settings

DEFAULT_JOBS = Path(__file__).with_name("jobs.json")


def load_collection_job(config: Path = DEFAULT_JOBS, settings: Settings | None = None) -> JobConfig:
    cfg = settings or Settings()
    jobs = FileJobConfigSource(config).load().jobs
    job = next(item for item in jobs if item.id == "cs-archival-collection")
    job.command = [sys.executable if part == "{python}" else part for part in job.command]
    job.runtime.root = cfg.scheduler_runtime_dir
    job.environment.update(
        CS_ARCHIVE_PATH=str(cfg.archive_path),
        CS_UPSTREAM_FILE=str(cfg.upstream_file),
    )
    return job


def execute(
    *,
    config: Path = DEFAULT_JOBS,
    settings: Settings | None = None,
    shutdown: threading.Event | None = None,
):
    result = run_job(load_collection_job(config, settings), shutdown=shutdown)
    increment("scheduler_runs_total", status=result.run_status)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cs-scheduler")
    parser.add_argument("--config", type=Path, default=DEFAULT_JOBS)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv)
    if args.validate:
        job = load_collection_job(args.config)
        print(json.dumps({"valid": True, "job": job.id}))
        return 0
    result = execute(config=args.config)
    print(json.dumps(result.record, default=str, sort_keys=True))
    return result.exit_code
