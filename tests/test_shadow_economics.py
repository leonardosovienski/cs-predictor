import pytest

from src.shadow_economics import (
    StrategySpec,
    executable_buy,
    probability_metrics,
    settle_shadow_decision,
    shadow_decision,
)


def _book():
    return ([{"price": .55, "size": 1000}],
            [{"price": .56, "size": 100}, {"price": .57, "size": 1000}])


def test_executable_buy_walks_asks_and_never_uses_midpoint():
    fill = executable_buy(_book()[1], stake=100)
    assert fill["status"] == "FILLED"
    assert fill["average_price"] > .56
    assert fill["decimal_odds"] == pytest.approx(1 / fill["average_price"])


def test_insufficient_book_is_no_fill():
    fill = executable_buy([{"price": .60, "size": 10}], stake=50)
    assert fill["status"] == "NO_FILL" and fill["unfilled_stake"] == 44


def test_veto_01_records_bet_no_bet_and_settlement():
    bids, asks = _book()
    bet = shadow_decision(model_probability=.65, bids=bids, asks=asks,
                          strategy=StrategySpec(stake=50, min_depth_multiple=1))
    assert bet["decision"] == "BET" and bet["net_edge"] >= .04
    assert settle_shadow_decision(bet, won=False)["pnl"] == -50
    no_bet = shadow_decision(model_probability=.57, bids=bids, asks=asks,
                             strategy=StrategySpec(stake=50, min_depth_multiple=1))
    assert no_bet["decision"] == "NO_BET"


def test_pre_and_post_metrics_are_independent():
    rows = [{"outcome": 1, "pre": .55, "post": .65},
            {"outcome": 0, "pre": .45, "post": .35}]
    assert probability_metrics(rows, "post")["brier"] < probability_metrics(rows, "pre")["brier"]
