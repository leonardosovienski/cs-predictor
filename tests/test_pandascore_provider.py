from datetime import datetime, timezone

from src.data.pandascore_provider import PandaScoreProvider


def test_pandascore_cs_normalizes_only_two_sided_matches():
    payload = [{"id": 3, "scheduled_at": "2026-07-21T10:00:00Z",
                "number_of_games": 3,
                "opponents": [{"opponent": {"name": "Vitality"}},
                              {"opponent": {"name": "MOUZ"}}]}]
    provider = PandaScoreProvider(token="synthetic", get_json=lambda *_: payload)
    rows = provider.list_upcoming(observed_at=datetime(2026, 7, 20, tzinfo=timezone.utc))
    assert rows[0]["source_event_id"] == "3"
    assert rows[0]["shadow_only"] is True
    assert "synthetic" not in repr(rows)
