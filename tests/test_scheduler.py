import json
import sys
import threading

from predictor_ops import JobConfig, OperationalState, run_job
from predictor_ops.runtime import LocalBackend

from src.scheduler import execute, load_collection_job, main
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
    assert result.status is OperationalState.COLLECTION_ONLY
    root = cfg.scheduler_runtime_dir / job.id
    heartbeat = json.loads((root / "heartbeat.json").read_text(encoding="utf-8"))
    terminal = json.loads((root / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert heartbeat["finished_at"] and terminal["run_id"] == result.run_id
    assert heartbeat["status"] == "COLLECTION_ONLY"
    capsys.readouterr()
    assert main(["--validate"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_lock_idempotency_timeout_and_shutdown(tmp_path):
    backend = LocalBackend(tmp_path / "runtime")
    held = backend.acquire("locked", "owner", 3600)
    skipped = run_job(
        JobConfig(id="locked", command=[sys.executable, "-c", "print(1)"]), runtime_backend=backend
    )
    assert skipped.status is OperationalState.SKIPPED
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
