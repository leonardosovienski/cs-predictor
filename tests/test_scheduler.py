import json
import sys
import threading

from predictor_ops import JobConfig, RunStatus, run_job
from predictor_ops.runtime import LocalBackend

from src.config import ROOT
from src.scheduler import SHADOW_JOB_IDS, execute, load_collection_job, load_job, main
from src.settings import Settings


def scheduler_settings(tmp_path):
    source = tmp_path / "upstream.json"
    source.write_text("[]", encoding="utf-8")
    return Settings(
        upstream_file=source,
        archive_path=tmp_path / "archive.jsonl",
        scheduler_runtime_dir=tmp_path / "runtime",
    )


def test_declarative_job_and_manual_execution_without_systemd(tmp_path, capsys):
    cfg = scheduler_settings(tmp_path)
    job = load_collection_job(settings=cfg)
    assert job.id == "cs-archival-collection"
    assert job.command[:3] == [sys.executable, "-m", "src.scheduler_payload"]
    assert job.timeout_seconds == 900 and job.heartbeat_interval_seconds == 15
    result = execute(settings=cfg)
    assert result.run_status is RunStatus.SUCCEEDED
    assert result.record["scientific_state"] == "COLLECTION_ONLY"
    root = cfg.scheduler_runtime_dir / job.id
    heartbeat = json.loads((root / "heartbeat.json").read_text(encoding="utf-8"))
    terminal = json.loads((root / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert heartbeat["finished_at"] and terminal["run_id"] == result.run_id
    assert heartbeat["run_status"] == "SUCCEEDED"
    assert heartbeat["scientific_state"] == "COLLECTION_ONLY"
    capsys.readouterr()
    assert main(["--validate"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_shadow_jobs_are_declared_with_checkout_cwd_and_no_capital(tmp_path):
    cfg = scheduler_settings(tmp_path)
    assert SHADOW_JOB_IDS == {
        "cs-market-shadow-collect",
        "cs-market-shadow-import",
        "cs-market-shadow-settle",
    }
    for job_id in SHADOW_JOB_IDS:
        job = load_job(job_id, settings=cfg)
        assert job.id == job_id
        assert job.cwd == ROOT
        assert job.provenance["mode"] == "SHADOW_ONLY_NO_CAPITAL"
        assert job.scientific_state == "REOPENED_BY_HUMAN_DECISION_SHADOW_ONLY"
        assert "market.db" not in " ".join(job.command)
        assert (ROOT / job.command[-1]).exists()


def test_cli_validate_accepts_a_shadow_job_id(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(ROOT)
    capsys.readouterr()
    assert main(["--job", "cs-market-shadow-collect", "--validate"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "valid": True,
        "job": "cs-market-shadow-collect",
    }


def test_lock_idempotency_timeout_and_shutdown(tmp_path):
    backend = LocalBackend(tmp_path / "runtime")
    held = backend.acquire("locked", "owner", 3600)
    skipped = run_job(
        JobConfig(id="locked", command=[sys.executable, "-c", "print(1)"]), runtime_backend=backend
    )
    assert skipped.run_status is RunStatus.SKIPPED
    held.release()

    timeout = run_job(
        JobConfig(
            id="timeout",
            command=[sys.executable, "-c", "import time; time.sleep(5)"],
            timeout_seconds=0.1,
            heartbeat_interval_seconds=0.02,
        ),
        runtime_backend=backend,
    )
    assert timeout.exit_code == 124 and timeout.record["termination"]["reason"] == "timeout"

    shutdown = threading.Event()
    shutdown.set()
    stopped = run_job(
        JobConfig(
            id="shutdown",
            command=[sys.executable, "-c", "import time; time.sleep(5)"],
            heartbeat_interval_seconds=0.02,
        ),
        runtime_backend=backend,
        shutdown=shutdown,
    )
    assert stopped.exit_code == 130 and stopped.record["termination"]["reason"] == "shutdown"
    assert not list((tmp_path / "runtime").rglob("run.lock"))
