"""Clone/install hygiene without conditional skips."""

import hashlib
import shutil
import subprocess
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
    git = shutil.which("git")
    expected = {
        "wheelhouse/predictor_core-2.1.0-py3-none-any.whl": "83de1d4415700dedaf387bc46dd9685e046de1fa47f37367bf2167462b09761b",
        "wheelhouse/predictor_ops-2.0.1-py3-none-any.whl": "37de983718b318fc1ccadc6b299db9fccdbea946080a2b710d6dd6a939a7e766",
    }
    for relative, digest in expected.items():
        path = ROOT / relative
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        ignored = subprocess.run(
            [git, "-C", str(ROOT), "check-ignore", relative], capture_output=True, check=False
        )
        assert ignored.returncode != 0
