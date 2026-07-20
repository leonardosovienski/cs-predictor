from concurrent.futures import ThreadPoolExecutor

from scripts.collect_polymarket_shadow import append_once


def test_shadow_dedupes_under_concurrency(tmp_path):
    path = tmp_path / "shadow.jsonl"
    quote = {"quote_id": "q1", "read_only": True}

    def attempt():
        try:
            return append_once(path, quote)
        except RuntimeError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _value: attempt(), range(8)))
    assert outcomes.count(True) == 1
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
