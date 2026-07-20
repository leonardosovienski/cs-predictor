from src.model_maps_shrunk import HistoricalVetoProxy, ShrunkMapElo, series_probability


def test_shrinkage_and_decay_pull_map_rating_to_series_elo():
    model = ShrunkMapElo(half_life_days=10, prior_maps=2)
    base = 1500.0
    model.update("A", "B", "Mirage", 13, 1, base_a=base, base_b=base, now_ts=0)
    near = model.rating("A", "Mirage", base_elo=base, now_ts=86400)
    far = model.rating("A", "Mirage", base_elo=base, now_ts=86400 * 100)
    assert near > base
    assert abs(far - base) < abs(near - base)


def test_historical_veto_proxy_uses_only_observed_maps_and_normalizes():
    veto = HistoricalVetoProxy()
    assert veto.scenarios("A", "B") == []
    for name in ("Mirage", "Inferno", "Nuke", "Ancient"):
        veto.observe("A", "B", name)
    scenarios = veto.scenarios("A", "B")
    assert scenarios and abs(sum(item["weight"] for item in scenarios) - 1.0) < 1e-9
    assert all(set(item["maps"]) <= {"Mirage", "Inferno", "Nuke", "Ancient"} for item in scenarios)


def test_series_probability_is_neutral_without_history():
    model = ShrunkMapElo()
    assert series_probability(model, "A", "B", [], base_a=1500, base_b=1500, now_ts=1) == 0.5


def test_cold_start_inherits_base_and_tie_does_not_create_state():
    model = ShrunkMapElo()
    assert model.rating("new", "Nuke", base_elo=1475, now_ts=10) == 1475
    model.update("A", "B", "Nuke", 12, 12,
                 base_a=1500, base_b=1500, now_ts=10)
    assert model._ratings == {}
