from pathlib import Path

import pytest

from src.data.hltv_provider import HltvCircuitOpenError, HltvProvider, HltvSchemaError
from src.observability import metrics, reset_metrics
from src.settings import Settings


class Response:
    def __init__(self, status_code, text):
        self.status_code, self.text = status_code, text

    def raise_for_status(self):
        if self.status_code >= 400:
            error = RuntimeError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class Session:
    def __init__(self, responses):
        self.responses, self.calls, self.headers = list(responses), 0, {}

    def get(self, *_args, **_kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def config(tmp_path, **changes):
    return Settings(raw_cache_dir=tmp_path, hltv_delay_seconds=0.5, **changes)


def test_retry_selective_and_raw_cache(tmp_path):
    html = Path("data/fixtures/hltv_results_v1.html").read_text(encoding="utf-8")
    session = Session([Response(503, "maintenance"), Response(200, html)])
    provider = HltvProvider(
        settings=config(tmp_path, hltv_max_retries=1), session=session, sleep=lambda _seconds: None
    )
    assert provider.fetch_results_page(0)[0]["match_id"] == 2372513
    assert session.calls == 2
    assert len(list(tmp_path.glob("results-0-*.html"))) == 2


def test_html_change_fails_explicitly(tmp_path):
    session = Session([Response(200, '<div class="result-con">new schema</div>')])
    provider = HltvProvider(
        settings=config(tmp_path, hltv_max_retries=0), session=session, sleep=lambda _seconds: None
    )
    with pytest.raises(HltvSchemaError, match="HTML_CHANGED"):
        provider.fetch_results_page(0)


def test_timeout_retry_circuit_breaker_and_metrics(tmp_path):
    reset_metrics()
    session = Session([TimeoutError("slow"), TimeoutError("still slow")])
    provider = HltvProvider(
        settings=config(
            tmp_path,
            hltv_max_retries=1,
            hltv_circuit_failure_threshold=1,
            hltv_circuit_recovery_seconds=60,
        ),
        session=session,
        sleep=lambda _seconds: None,
    )
    with pytest.raises(TimeoutError):
        provider.fetch_results_page(0)
    with pytest.raises(HltvCircuitOpenError):
        provider.fetch_results_page(0)
    snapshot = metrics()
    assert snapshot["provider_retries_total|provider=hltv"] == 1
    assert snapshot["provider_circuit_open_total|provider=hltv"] == 1


def test_non_retryable_4xx_and_cache_is_content_addressed(tmp_path):
    session = Session([Response(404, "missing"), Response(200, "same"), Response(200, "same")])
    provider = HltvProvider(
        settings=config(tmp_path, hltv_max_retries=3), session=session, sleep=lambda _seconds: None
    )
    with pytest.raises(RuntimeError, match="404"):
        provider._get("https://example.invalid/404", cache_key="not-found")
    assert session.calls == 1
    provider._get("https://example.invalid/a", cache_key="raw")
    provider._get("https://example.invalid/a", cache_key="raw")
    assert len(list(tmp_path.glob("raw-*.html"))) == 1
