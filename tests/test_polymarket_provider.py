from datetime import datetime, timezone

import pytest

from src.data.polymarket_provider import DataUnavailableError, PolymarketProvider


EVENT = {"id": "1", "startTime": "2030-01-02T12:00:00Z", "markets": [{
    "id": "m1", "sportsMarketType": "moneyline",
    "question": "Counter-Strike: Vitality vs MOUZ (BO3)",
    "outcomes": '["Vitality", "MOUZ"]', "clobTokenIds": '["a", "b"]',
    "liquidity": "1000",
}]}


def _transport(url):
    if "/events/1" in url:
        return EVENT
    if "token_id=a" in url:
        return {"timestamp": "2030-01-01T10:00:00Z", "bids": [{"price": ".69"}], "asks": [{"price": ".71"}]}
    return {"timestamp": "2030-01-01T10:00:00Z", "bids": [{"price": ".29"}], "asks": [{"price": ".31"}]}


def test_read_only_pre_event_quote():
    quote = PolymarketProvider(get_json=_transport).fetch_match(
        "Vitality", "MOUZ", event_id="1",
        observed_at=datetime(2030, 1, 1, 11, tzinfo=timezone.utc))
    assert quote["source_kind"] == "prediction_market" and quote["read_only"] is True
    assert quote["probability_a"] == .7 and quote["probability_b"] == .3
    assert quote["format"] == "bo3"


def test_rejects_post_event_and_identity_mismatch():
    provider = PolymarketProvider(get_json=_transport)
    with pytest.raises(DataUnavailableError, match="PRE_EVENT"):
        provider.fetch_match("Vitality", "MOUZ", event_id="1",
                             observed_at=datetime(2030, 1, 2, 12, tzinfo=timezone.utc))
    with pytest.raises(DataUnavailableError, match="encontrados 0"):
        provider.fetch_match("Vitality", "Spirit", event_id="1",
                             observed_at=datetime(2030, 1, 1, 11, tzinfo=timezone.utc))
