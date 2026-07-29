"""Integração real (não-mockada) com tools_provenance — auditoria hostil final.

test_cs_snapshots.py tem uma fixture autouse que substitui
snapshots._tools_provenance() por um stub fixo em TODOS os testes daquele
arquivo. Isso significa que nenhum teste ali exercita de fato a chamada real
a tools.tools_provenance.collect_tools_provenance — se essa integração
quebrasse (assinatura mudou, vendoring incorreto, tools/ com provenance
inválida), a suíte inteira de cs-predictor continuaria verde. Este arquivo
fecha essa lacuna, no mesmo espírito do teste equivalente adicionado ao
f1-predictor (test_expected_tools_version_matches_collect_tools_provenance_independently).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src import cs_snapshots as snapshots
from src.config import ROOT


def test_tools_provenance_real_call_matches_independent_collect_tools_provenance():
    workspace = ROOT.parent
    if not (workspace / "tools" / "tools_provenance.py").is_file():
        pytest.skip("tools-predictor nao esta presente neste clone isolado")
    observed = snapshots._tools_provenance()

    if str(workspace) not in sys.path:
        sys.path.insert(0, str(workspace))
    from tools.tools_provenance import collect_tools_provenance
    independent = collect_tools_provenance(workspace / "tools", strict=True)

    assert observed["version"] == independent["version"]
    assert observed["content_hash"] == independent["content_hash"]
    assert observed["version"] == (workspace / "tools" / "VERSION").read_text(encoding="utf-8").strip()
