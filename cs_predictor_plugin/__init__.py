"""Collision-free gateway entry point for the legacy ``src`` package."""

from __future__ import annotations

import sys
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_RUNTIME_NAME = "cs_predictor_runtime"
_SOURCE_DIR = Path(__file__).resolve().parent.parent / "src"


def _load_runtime():
    existing = sys.modules.get(_RUNTIME_NAME)
    if existing is not None:
        return existing
    spec = spec_from_file_location(
        _RUNTIME_NAME,
        _SOURCE_DIR / "__init__.py",
        submodule_search_locations=[str(_SOURCE_DIR)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load CS runtime package from {_SOURCE_DIR}")
    module = module_from_spec(spec)
    sys.modules[_RUNTIME_NAME] = module
    spec.loader.exec_module(module)
    return module


_load_runtime()
Plugin = import_module(f"{_RUNTIME_NAME}.plugin").CsPredictorPlugin

__all__ = ["Plugin"]
