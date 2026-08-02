"""Domain observability built on the installed predictor_ops primitives."""

import logging
from collections import Counter
from threading import Lock
from typing import Any

from predictor_ops.observability import configure_otel
from predictor_ops.observability import logger as ops_logger

_COUNTERS: Counter[str] = Counter()
_LOCK = Lock()


def configure(endpoint: str | None) -> None:
    if endpoint:
        configure_otel(endpoint, service_name="cs-predictor")


def log(event: str, **fields: Any) -> None:
    ops_logger().info(event, extra={"fields": {"domain": "cs", **fields}})


def increment(metric: str, amount: int = 1, **labels: str) -> None:
    key = metric + "|" + ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    with _LOCK:
        _COUNTERS[key] += amount


def metrics() -> dict[str, int]:
    with _LOCK:
        return dict(_COUNTERS)


def reset_metrics() -> None:
    with _LOCK:
        _COUNTERS.clear()


def logger() -> logging.Logger:
    return ops_logger()
