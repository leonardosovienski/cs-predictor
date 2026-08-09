"""Clone/install hygiene without conditional skips."""

import shutil
import subprocess
import tomllib
from pathlib import Path

from src.plugin import CsPredictorPlugin

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_and_shared_dependencies_do_not_drift():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == "3.1.0"
    assert CsPredictorPlugin.version == project["version"]

    expected_urls = {
        "https://github.com/leonardosovienski/core-predictor/releases/download/v2.2.1/predictor_core-2.2.1-py3-none-any.whl",
        "https://github.com/leonardosovienski/tools-predictor/releases/download/v3.0.0/predictor_ops-3.0.0-py3-none-any.whl",
    }
    for relative_path in ("Dockerfile", ".github/workflows/ci.yml"):
        contents = (ROOT / relative_path).read_text(encoding="utf-8")
        for url in expected_urls:
            assert url in contents
        assert "releases/download/v2.1.0/predictor_core-2.1.0" not in contents
        assert "releases/download/v2.0.1/predictor_ops-2.0.1" not in contents


def test_no_code_file_is_gitignored():
    git = shutil.which("git")
    assert git and (ROOT / ".git").is_dir(), "repository tests require Git"
    files = [
        path.relative_to(ROOT).as_posix()
        for base in (ROOT / "src", ROOT / "scripts", ROOT / "tests")
        for path in base.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    ignored = []
    for index in range(0, len(files), 100):
        result = subprocess.run(
            [git, "-C", str(ROOT), "check-ignore", *files[index : index + 100]],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            ignored.extend(result.stdout.splitlines())
    assert not ignored


def test_shared_wheels_match_canonical_hashes_and_are_visible_to_git():
    # predictor-core/predictor-ops are consumed from their published GitHub
    # Release (see [tool.uv.sources] in pyproject.toml), not from a wheel
    # vendored under wheelhouse/ in this repo (that path is .gitignore'd and
    # was never actually committed - a fresh clone never had these files).
    # The portable, git-visible source of truth is the lockfile itself.
    expected = {
        "predictor-core": (
            "https://github.com/leonardosovienski/core-predictor/releases/download/v2.2.1/predictor_core-2.2.1-py3-none-any.whl",
            "sha256:e9ff0783d451ba63f06540ca7e89368b83449953ad3bc005ab777e48d14a9095",
        ),
        "predictor-ops": (
            "https://github.com/leonardosovienski/tools-predictor/releases/download/v3.0.0/predictor_ops-3.0.0-py3-none-any.whl",
            "sha256:9574d5fa4d17232a9d7dbd1aaff0131b65f341974508c5457b8d570bf41e8945",
        ),
    }
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {pkg["name"]: pkg for pkg in lock["package"]}
    for name, (url, digest) in expected.items():
        wheel = packages[name]["wheels"][0]
        assert wheel["url"] == url
        assert wheel["hash"] == digest
    git = shutil.which("git")
    ignored = subprocess.run(
        [git, "-C", str(ROOT), "check-ignore", "uv.lock"], capture_output=True, check=False
    )
    assert ignored.returncode != 0
