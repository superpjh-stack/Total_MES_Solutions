"""팩 스모크 — 팩을 올린 채로 코어가 기동하고(병합 규칙 통과) 용어 · 메뉴 · 계보 선언이 병합본에 들어갔는지.

실행: `MES_PACK=<팩> uv run pytest -q packs/<팩>/tests`. 코어 테스트(`tests/`)는 어떤 팩에서도 그대로 통과해야 한다(R9).
시나리오 테스트는 gates.yaml: scenarios[].test 가 가리키는 파일에 `@pytest.mark.fn("F-X-…")` 를 붙여 따로 만든다.
"""

import os
from pathlib import Path

import pytest
import yaml

PACK_DIR = Path(__file__).resolve().parents[1]
PACK = PACK_DIR.name


@pytest.fixture(scope="module")
def pack():
    os.environ["MES_PACK"] = PACK
    from mescore.app import packs
    packs.reset()
    p = packs.load(PACK)
    from mescore.app import nav
    nav.rebuild()
    return p


def test_pack_yaml_loads_without_pack_error(pack):
    assert pack.name == PACK
    assert pack.requires_core


def test_terms_keys_are_core_neutral_words(pack):
    assert set(pack.terms) <= set(pack.terms_keys)


def test_core_menus_and_screens_survive(pack):
    from mescore.app import nav
    assert len([m for m in nav.ALL_MENUS if not m.is_pack]) == 12
    assert len(nav.CORE_SCREENS) == 51


def test_gates_yaml_shape():
    g = yaml.safe_load((PACK_DIR / "gates.yaml").read_text(encoding="utf-8"))
    assert {"screens", "tables", "functions", "scenarios", "terms_sample"} <= set(g)


def test_lineage_declarations_resolve_to_core_bases(pack):
    for k in pack.lineage["lot_kinds"]:
        assert k["base"] in ("MATERIAL", "PRODUCT", "SHIPMENT")
    for r in pack.lineage["relations"]:
        assert r["base"] in ("투입", "생산", "분할", "합병", "출하")
