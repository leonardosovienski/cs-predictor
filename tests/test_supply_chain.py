import hashlib
from importlib.metadata import distribution, version
from pathlib import Path

from predictor_ops.provenance import collect_provenance
from predictor_ops.redaction import redact, redact_command, redact_text, sensitive_values

ROOT = Path(__file__).resolve().parents[1]


def test_predictor_ops_201_is_installed_from_site_packages_and_hash_matches():
    wheel = ROOT / "wheelhouse" / "predictor_ops-2.0.1-py3-none-any.whl"
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == (
        "37de983718b318fc1ccadc6b299db9fccdbea946080a2b710d6dd6a939a7e766"
    )
    dist = distribution("predictor-ops")
    assert version("predictor-ops") == "2.0.1"
    assert "site-packages" in str(dist.locate_file("")).replace("\\", "/")
    assert collect_provenance(strict=True)["identity_status"] == "VALIDATED"


def test_redaction_never_emits_secret_values():
    environment = {"API_KEY": "super-secret", "NORMAL": "visible"}
    secrets = sensitive_values(environment)
    assert "super-secret" not in redact_text("api_key=super-secret", secrets)
    assert (
        redact({"password": "super-secret", "ok": "visible"}, secrets)["password"] == "[REDACTED]"
    )
    command = redact_command(["tool", "--token", "super-secret"], secrets)
    assert command == ["tool", "--token", "[REDACTED]"]
