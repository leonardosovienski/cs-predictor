"""Clone/install hygiene without conditional skips."""

import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
            "https://github.com/leonardosovienski/core-predictor/releases/download/v2.1.0/predictor_core-2.1.0-py3-none-any.whl",
            "sha256:83de1d4415700dedaf387bc46dd9685e046de1fa47f37367bf2167462b09761b",
        ),
        "predictor-ops": (
            "https://github.com/leonardosovienski/tools-predictor/releases/download/v2.0.1/predictor_ops-2.0.1-py3-none-any.whl",
            "sha256:77ca2eb3f1090226dfef23b84d7fb2f9a61bd858c970d433d28303e637a8903e",
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
