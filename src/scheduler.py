"""Portable scheduler entry point backed exclusively by predictor_ops."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from predictor_ops import JobConfig, run_job
from predictor_ops.config import FileJobConfigSource

from .config import ROOT
from .observability import increment
from .settings import Settings

DEFAULT_JOBS = Path(__file__).with_name("jobs.json")
DEFAULT_JOB_ID = "cs-archival-collection"
SHADOW_JOB_IDS = {"cs-market-shadow-collect", "cs-market-shadow-import", "cs-market-shadow-settle"}


def load_job(
    job_id: str, config: Path = DEFAULT_JOBS, settings: Settings | None = None
) -> JobConfig:
    cfg = settings or Settings()
    jobs = FileJobConfigSource(config).load().jobs
    job = next(item for item in jobs if item.id == job_id)
    job.command = [sys.executable if part == "{python}" else part for part in job.command]
    job.runtime.root = cfg.scheduler_runtime_dir
    if job_id == DEFAULT_JOB_ID:
        job.environment.update(
            CS_ARCHIVE_PATH=str(cfg.archive_path),
            CS_UPSTREAM_FILE=str(cfg.upstream_file),
        )
    if job_id in SHADOW_JOB_IDS:
        # As scripts shadow não são um pacote instalado; precisam do
        # checkout como cwd para resolver `scripts/`, `src/` e os
        # registros de governança em `docs/records/`.
        job.cwd = ROOT
    return job


def load_collection_job(config: Path = DEFAULT_JOBS, settings: Settings | None = None) -> JobConfig:
    return load_job(DEFAULT_JOB_ID, config, settings)


def execute(
    *,
    job_id: str = DEFAULT_JOB_ID,
    config: Path = DEFAULT_JOBS,
    settings: Settings | None = None,
    shutdown: threading.Event | None = None,
):
    result = run_job(load_job(job_id, config, settings), shutdown=shutdown)
    increment("scheduler_runs_total", status=result.run_status, job_id=job_id)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cs-scheduler")
    parser.add_argument("--config", type=Path, default=DEFAULT_JOBS)
    parser.add_argument(
        "--job",
        default=DEFAULT_JOB_ID,
        help="job id declarado em jobs.json (default: cs-archival-collection)",
    )
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv)
    if args.validate:
        job = load_job(args.job, args.config)
        print(json.dumps({"valid": True, "job": job.id}))
        return 0
    result = execute(job_id=args.job, config=args.config)
    print(json.dumps(result.record, default=str, sort_keys=True))
    return result.exit_code
