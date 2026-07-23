from pathlib import Path

import pytest

from scripts import market_shadow_status
from scripts import collect_polymarket_shadow, collect_polymarket_upcoming
from scripts.validate_beyond_market import main as validate_main
from src.beyond_market_closure import BeyondMarketClosedError, assert_beyond_market_open
from src.prospective_market import ProspectiveStore
import src.prospective_market as prospective_market


ROOT = Path(__file__).resolve().parents[1]


def test_human_closure_blocks_evaluation_and_reports_no_go(tmp_path, capsys):
    with pytest.raises(BeyondMarketClosedError):
        assert_beyond_market_open()
    assert validate_main(["--input", str(tmp_path / "unused.jsonl"), "--train-end", "2030-01-01T00:00:00+00:00"]) == 2
    assert "CLOSED_BY_HUMAN_DECISION" in capsys.readouterr().err
    out = market_shadow_status.status(tmp_path / "quotes.jsonl", market_db=ROOT / "data" / "market.db")
    assert out["scientific_status"] == "CLOSED_BY_HUMAN_DECISION"
    assert out["operational_status"] == "NO_GO"
    assert out["decision_ready"] is False


def test_human_closure_blocks_collection_and_store_mutation(tmp_path, monkeypatch):
    with pytest.raises(BeyondMarketClosedError):
        collect_polymarket_shadow.main([])
    with pytest.raises(BeyondMarketClosedError):
        collect_polymarket_upcoming.main()
    monkeypatch.setattr(prospective_market, "is_production_market_db", lambda _path: True)
    store = ProspectiveStore(tmp_path / "market.db")
    conn = store.connect()
    with pytest.raises(BeyondMarketClosedError):
        store.import_quotes(conn, [], batch_id="blocked")
