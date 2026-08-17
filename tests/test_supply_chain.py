import tomllib
from importlib.metadata import distribution, version
from pathlib import Path

from predictor_ops.provenance import collect_provenance
from predictor_ops.redaction import redact, redact_command, redact_text, sensitive_values

ROOT = Path(__file__).resolve().parents[1]


def _locked_wheel_hash(package: str) -> str:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    for pkg in lock["package"]:
        if pkg["name"] == package:
            return pkg["wheels"][0]["hash"]
    raise AssertionError(f"{package} not found in uv.lock")


def test_predictor_ops_300_is_installed_from_site_packages_and_hash_matches():
    # predictor-ops is distributed as a published GitHub Release asset (see
    # [tool.uv.sources] in pyproject.toml), not a wheel vendored in this repo.
    # uv itself enforces this hash on every sync; this test cross-checks that
    # the lockfile still points at the known-good, canonical release.
    assert _locked_wheel_hash("predictor-ops") == (
        "sha256:490ece696f9173bbaa56c2c53a1ff6e5ffab1a7625fb00ac0a5f896c37081b37"
    )
    dist = distribution("predictor-ops")
    assert version("predictor-ops") == "3.1.0"
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
