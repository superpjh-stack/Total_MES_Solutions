"""G-P03 추적표 도구 `tools/import_design.py --pack` (개발1 · CR-10) — design.json · 설계도 HTML 두 원본.

근거 사업 폴더(읽기 전용)가 없으면 건너뛴다. 매핑표 한 행을 지우면 고아 1 → FAIL 이어야 한다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("import_design", ROOT / "src/mescore/tools/import_design.py")
imp = importlib.util.module_from_spec(_spec)
sys.modules["import_design"] = imp
_spec.loader.exec_module(imp)  # type: ignore[union-attr]


def _source(pack: str) -> Path:
    src = imp.pack_settings(pack).get("design_source")
    p = (ROOT / str(src)).resolve() if src else None
    if p is None or not p.exists():
        pytest.skip(f"{pack} 설계 원본 없음")
    return p


@pytest.mark.parametrize("pack", ["kimchi", "foodservice", "printfilm"])
def test_pack_trace_passes(pack, capsys, monkeypatch):
    _source(pack)
    monkeypatch.delenv("MES_PACK", raising=False)
    rc = imp.main(["--pack", pack, "--no-nav"])
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc == 0 and last.startswith(f"G-P03  [{pack}] 추적표  PASS  산출물 "), last
    assert " · 고아 0" in last


def test_html_source_orphan_fails(tmp_path, capsys, monkeypatch):
    src = _source("printfilm")
    readme = (ROOT / "packs/printfilm/README.md").read_text(encoding="utf-8")
    cut = "\n".join(ln for ln in readme.splitlines() if not ln.startswith("| 18 | CLR-01"))
    (tmp_path / "README.md").write_text(cut, encoding="utf-8")
    monkeypatch.delenv("MES_PACK", raising=False)
    rc = imp.main(["--pack", "printfilm", "--design", str(src), "--mapping", str(tmp_path / "README.md"), "--no-nav"])
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert rc == 1 and "FAIL" in last and " · 고아 1" in last, last


def test_html_names_ignore_brackets():
    assert imp.norm_name("추적 (정방향, 역방향, LOT 검색)") == imp.norm_name("추적")
    assert imp.is_out_of_scope("**밖**") and imp.is_out_of_scope("범위 밖") and not imp.is_out_of_scope("1:1")

