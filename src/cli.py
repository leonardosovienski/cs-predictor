"""Installed command-line adapters."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .event_store import JsonlEventRepository
from .plugin import CsPredictorPlugin
from .services import ArchivalCollectionService
from .settings import Settings
from .transports import FileTransport


def _laboratory_enabled(explicit: bool) -> bool:
    return explicit or os.environ.get("CS_LABORATORY") == "1"


def collect_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cs-collect")
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    cfg = Settings()
    result = ArchivalCollectionService(
        FileTransport(args.input or cfg.upstream_file), JsonlEventRepository(cfg.archive_path)
    ).collect()
    print(
        json.dumps(
            {
                "run_status": result.run_status,
                "outcome": result.outcome,
                "accepted": result.accepted,
                "duplicates": result.duplicates,
                "detail": result.detail,
            }
        )
    )
    return 0 if result.run_status == "SUCCEEDED" else 2


def ingest_main(argv: list[str] | None = None) -> int:
    from .data.hltv_provider import HltvProvider

    parser = argparse.ArgumentParser(prog="cs-ingest-hltv")
    parser.add_argument("--until-date", required=True)
    parser.add_argument("--laboratory", action="store_true")
    args = parser.parse_args(argv)
    if not _laboratory_enabled(args.laboratory):
        print(
            "cs-ingest-hltv is laboratory-only; use --laboratory or CS_LABORATORY=1",
            file=sys.stderr,
        )
        return 2
    count = sum(len(page) for page in HltvProvider().fetch_results(args.until_date))
    print(json.dumps({"state": "SUCCEEDED", "events": count}))
    return 0


def settle_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cs-settle")
    parser.add_argument("event_id")
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)
    del args
    print(
        json.dumps(
            {
                "run_status": "CONFIGURATION_ERROR",
                "scientific_state": "CLOSED_BY_HUMAN_DECISION",
                "detail": "cs-settle is disabled; market settlement cannot be reopened",
            }
        )
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cs-predictor")
    parser.add_argument("command", choices=["health", "collect", "scheduler"])
    args, rest = parser.parse_known_args(argv)
    if args.command == "collect":
        return collect_main(rest)
    if args.command == "scheduler":
        from .scheduler import main as scheduler_main

        return scheduler_main(rest)
    print(json.dumps(CsPredictorPlugin().health()))
    return 0
