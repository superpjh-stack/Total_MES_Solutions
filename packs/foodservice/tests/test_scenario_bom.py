"""S5 레시피 활성 버전 2건 금지 · 배치 기준인분 필수 · 메뉴에만 — validate_bas_bom (gates.yaml S5)."""

from __future__ import annotations

import uuid

import pytest

from mescore.db import conn

from _helpers import MENU, ONION, PORK, client, hook_rejected, item_id, ok


def _bom_data(item: str, version: str, use_yn: str = "Y", serve=100) -> dict:
    d = {"item_id": item_id(item), "version": version, "use_yn": use_yn, "component_item_id": [item_id(PORK), item_id(ONION)], "qty": ["12.000", "3.500"],
         "unit": ["kg", "kg"], "loss_rate": ["", ""]}
    if serve is not None:
        d["attr_batch_serve_qty"] = str(serve)
    return d


@pytest.mark.fn("F-BAS-05")
def test_single_active():
    admin = client("admin")
    v1 = conn.q1("select id from bas_bom where item_id = %s and version = 'V1.0'", (item_id(MENU),))
    assert v1 and conn.q1("select use_yn from bas_bom where id = %s", (v1["id"],))["use_yn"] == "Y", "시드 레시피 V1.0 (활성) — seed/bom_example.csv (seed_dev1)"
    ver = f"T-{uuid.uuid4().hex[:6].upper()}"
    # V1.0 활성인데 새 버전을 Y 로 → 422 hook_rejected
    r = admin.post("/bas/bom", data=_bom_data(MENU, ver))
    assert hook_rejected(r) and "활성 레시피는 1건" in r.json()["message"], r.text
    # 배치 기준인분 없이 → 422 (required attrs → 코어 422 또는 훅 422 — 둘 다 거부)
    r = admin.post("/bas/bom", data=_bom_data(MENU, ver, "N", serve=None))
    assert r.status_code == 422, r.text
    r = admin.post("/bas/bom", data=_bom_data(MENU, ver, "N", serve=0))
    assert hook_rejected(r), r.text
    # 원재료에 레시피 → 422
    r = admin.post("/bas/bom", data={**_bom_data(PORK, ver), "component_item_id": [item_id(ONION)], "qty": ["1"], "unit": ["kg"], "loss_rate": [""]})
    assert hook_rejected(r) and "메뉴에만" in r.json()["message"], r.text
    # V1.0 을 N 으로 → 새 버전 Y 200 · ext 에 기준인분 복사 → 되돌린다 (다른 테스트 · 화면은 V1.0 활성을 전제)
    ok(admin.post(f"/bas/bom/{v1['id']}", data={"use_yn": "N"}), "V1.0 비활성")
    try:
        created = ok(admin.post("/bas/bom", data=_bom_data(MENU, ver, serve=120)), "새 버전")
        assert conn.q1("select batch_serve_qty from x_foodservice_bom_ext where id = %s", (created["id"],))["batch_serve_qty"] == 120
        r = admin.post(f"/bas/bom/{v1['id']}", data={"use_yn": "Y"})
        assert hook_rejected(r), r.text                                                     # 두 버전 동시 활성 금지 — 수정 경로도
        ok(admin.post(f"/bas/bom/{created['id']}", data={"use_yn": "N"}), "새 버전 비활성")
        ok(admin.post(f"/bas/bom/{created['id']}/delete"), "새 버전 삭제")
    finally:
        ok(admin.post(f"/bas/bom/{v1['id']}", data={"use_yn": "Y"}), "V1.0 복구")
    assert conn.q1("select count(*) as n from bas_bom where item_id = %s and use_yn = 'Y'", (item_id(MENU),))["n"] == 1
