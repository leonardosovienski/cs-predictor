import hashlib
import json
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from src.beyond_market_closure import (
    BeyondMarketClosedError,
    assert_beyond_market_open,
    closure_record,
    market_shadow_status,
    reject_market_shadow_operation,
)
from src.plugin import CsPredictorPlugin
from src.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
CLOSURE_HASH = "e30603fae444c7c88aced505a966946e34106f07c17e906c5d8b18c0bdde5903"
EVIDENCE_HASHES = {
    "docs/evidence/market_shadow/src/prospective_market.py": "372881f33f4a475d85628e88b6e38d5e945fd470cad25a8dae58300703de3f72",
    "docs/evidence/market_shadow/scripts/install_market_shadow_task.ps1": "5855ac6eef9ed02e94b0fb574565fad5a77cf4cdb2fbb09fb0da65053a0751ec",
    "docs/evidence/market_shadow/tests/test_beyond_market_closure.py": "dadf0c7f378d2d1f2cdda485775161c59efc544bab3b386416eef983466a416c",
}


def test_closure_is_immutable_and_fail_closed(tmp_path, monkeypatch):
    assert market_shadow_status() == {
        "scientific_status": "CLOSED_BY_HUMAN_DECISION",
        "operational_status": "NO_GO",
        "collection_only": True,
        "trading": False,
        "capital_real": False,
    }
    for name in ("CS_MARKET_SHADOW", "CS_REOPEN_MARKET", "MARKET_SHADOW_ENABLED"):
        monkeypatch.setenv(name, "true")
    assert (
        Settings()
        .model_dump()
        .keys()
        .isdisjoint({"market_shadow", "reopen_market", "trading", "capital_real"})
    )
    with pytest.raises(BeyondMarketClosedError):
        assert_beyond_market_open(tmp_path / "missing.json")
    with pytest.raises(BeyondMarketClosedError):
        reject_market_shadow_operation("direct-call", enabled=True)


def test_no_operational_market_surface_exists():
    scripts = entry_points(group="console_scripts")
    assert not any("market" in item.name or "shadow" in item.name for item in scripts)
    plugin = CsPredictorPlugin()
    assert plugin.capabilities()["market_shadow"] is False
    assert plugin.capabilities()["trading"] is False
    assert not hasattr(plugin, "market_provider")
    assert not (ROOT / "src" / "prospective_market.py").exists()
    assert not (ROOT / "src" / "market_db.py").exists()
    assert not (ROOT / "scripts" / "migrate_prospective_market.py").exists()
    jobs = json.loads((ROOT / "src" / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    assert [job["id"] for job in jobs] == ["cs-archival-collection"]
    assert not any("market" in " ".join(job["command"]).casefold() for job in jobs)


def test_closure_and_historical_evidence_hashes_are_stable():
    closure = ROOT / "docs" / "records" / "beyond_market_closure.json"
    assert hashlib.sha256(closure.read_bytes()).hexdigest() == CLOSURE_HASH
    assert closure_record()["human_decision"]["real_money"].endswith("bloqueada permanentemente.")
    for relative, expected in EVIDENCE_HASHES.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
