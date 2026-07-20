from scripts.backtest_market_historical import select_pre_event_price


def test_select_pre_event_price_rejects_future_and_invalid():
    history = [{"t": 90, "p": .4}, {"t": 99, "p": .6},
               {"t": 100, "p": .7}, {"t": 98, "p": float("nan")},
               {"t": 97, "p": 1}]
    assert select_pre_event_price(history, 100) == {"t": 99, "p": .6}


def test_select_pre_event_price_empty():
    assert select_pre_event_price([{"t": 100, "p": .5}], 100) is None
