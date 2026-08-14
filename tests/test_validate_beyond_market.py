import json

from scripts.validate_beyond_market import main
from src import beyond_market_closure as bmc


def _dataset(tmp_path, rows):
    path = tmp_path / "dataset.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _row(day, outcome, market_p, model_p):
    return {
        "captured_at": f"2026-07-{day:02d}T10:00:00+00:00",
        "match_start_at": f"2026-07-{day:02d}T12:00:00+00:00",
        "outcome": outcome,
        "market_probability": market_p,
        "model_probability": model_p,
    }


def test_main_prints_result_and_never_authorizes_capital(tmp_path, capsys):
    rows = [
        _row(1, 1, 0.55, 0.60),
        _row(1, 0, 0.45, 0.40),
        _row(2, 1, 0.55, 0.60),
        _row(2, 0, 0.45, 0.40),
    ]
    dataset = _dataset(tmp_path, rows)
    exit_code = main(
        [
            "--input",
            str(dataset),
            "--train-end",
            "2026-07-02T00:00:00+00:00",
            "--minimum-test-rows",
            "2",
        ]
    )
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["financial_capital_authorized"] is False
    assert out["economic_gate"].startswith("NO-GO")


def test_main_writes_output_file_when_requested(tmp_path, capsys):
    rows = [
        _row(1, 1, 0.55, 0.60),
        _row(1, 0, 0.45, 0.40),
        _row(2, 1, 0.55, 0.60),
        _row(2, 0, 0.45, 0.40),
    ]
    dataset = _dataset(tmp_path, rows)
    output = tmp_path / "out" / "result.json"
    exit_code = main(
        [
            "--input",
            str(dataset),
            "--train-end",
            "2026-07-02T00:00:00+00:00",
            "--minimum-test-rows",
            "2",
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    capsys.readouterr()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["financial_capital_authorized"] is False


def test_main_exits_2_on_malformed_dataset(tmp_path, capsys):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("{nao e json", encoding="utf-8")
    exit_code = main(["--input", str(dataset), "--train-end", "2026-07-02T00:00:00+00:00"])
    assert exit_code == 2
    assert "ilegível" in capsys.readouterr().err


def test_main_exits_2_when_shadow_gate_is_closed(tmp_path, capsys, monkeypatch):
    def _closed():
        raise bmc.BeyondMarketClosedError("fixture: shadow fechado")

    monkeypatch.setattr(
        "scripts.validate_beyond_market.assert_market_shadow_collection_open", _closed
    )
    dataset = _dataset(tmp_path, [_row(1, 1, 0.55, 0.60)])
    exit_code = main(["--input", str(dataset), "--train-end", "2026-07-02T00:00:00+00:00"])
    assert exit_code == 2
    assert "fixture: shadow fechado" in capsys.readouterr().err
