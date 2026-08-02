import subprocess
import sys

import pytest
from pydantic import ValidationError

from src.settings import Settings, canonical_database_target


def rejected(sports, market):
    with pytest.raises(ValidationError, match="different physical"):
        Settings(sports_db_url=f"sqlite:///{sports}", market_db_url=f"sqlite:///{market}")


def test_identical_normalized_relative_absolute_and_parent_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "db" / "sports.db"
    rejected(target, target)
    rejected("db/sports.db", target)
    rejected("db/../db/sports.db", target)
    rejected(str(target).upper(), str(target).lower())
    assert canonical_database_target(f"sqlite:///{target}") == canonical_database_target(
        "sqlite:///db/../db/sports.db"
    )


def test_environment_aliases_resolve_to_same_file(tmp_path, monkeypatch):
    target = tmp_path / "same.db"
    monkeypatch.setenv("CS_DB_ALIAS", str(target))
    rejected("%CS_DB_ALIAS%", target)


def test_symlink_alias_is_rejected_without_opening_database(tmp_path):
    target = tmp_path / "target.db"
    target.touch()
    alias = tmp_path / "alias.db"
    try:
        alias.symlink_to(target)
    except OSError:
        assert sys.platform == "win32"
        target_dir = tmp_path / "target-dir"
        target_dir.mkdir()
        target = target_dir / "target.db"
        target.touch()
        alias_dir = tmp_path / "alias-dir"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias_dir), str(target_dir)],
            capture_output=True,
            check=False,
        )
        assert created.returncode == 0, created.stderr.decode(errors="replace")
        alias = alias_dir / "target.db"
    rejected(alias, target)
    assert target.stat().st_size == 0


def test_distinct_database_targets_are_accepted(tmp_path):
    cfg = Settings(
        sports_db_url=f"sqlite:///{tmp_path / 'sports.db'}",
        market_db_url=f"sqlite:///{tmp_path / 'market.db'}",
    )
    assert cfg.sports_db_url != cfg.market_db_url
    assert not (tmp_path / "sports.db").exists() and not (tmp_path / "market.db").exists()
