import pytest

from src.calibration import PlattCalibrator
from src.model import series_probs, win_probability
from src.model_maps import series_probs_hetero


def test_golden_elo():
    assert win_probability(1600, 1500) == pytest.approx(0.6400649998028851, abs=1e-15)


def test_golden_series():
    assert series_probs(0.6, "bo3") == pytest.approx(
        {"2-0": 0.36, "2-1": 0.288, "1-2": 0.192, "0-2": 0.16}, abs=1e-15
    )


def test_golden_map_series():
    assert series_probs_hetero([0.7, 0.4, 0.6], 2) == pytest.approx(
        {"2-0": 0.28, "2-1": 0.324, "1-2": 0.216, "0-2": 0.18}, abs=1e-15
    )


def test_golden_calibration():
    assert PlattCalibrator(a=0.68, b=0.1).apply(0.8) == pytest.approx(0.7196407203219027, abs=1e-15)
