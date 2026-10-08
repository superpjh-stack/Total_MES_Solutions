"""G-P05 용어 — gates.yaml: terms_sample 의 코어 중립어가 팩 화면(코어 + 팩 8)에 치환 안 된 채 보이지 않는다 · 메뉴 순서 · 역할 6 (개발3)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from _helpers import client
from mescore.app import nav, packs

PACK_DIR = Path(__file__).resolve().parents[1]


def _plain(html: str) -> str:
    html = re.sub(r"<code>.*?</code>", " ", html, flags=re.S)
    return re.sub(r"<[^>]*>", " ", html)


def test_terms_sample_not_exposed_on_pack_screens():
    gates = yaml.safe_load((PACK_DIR / "gates.yaml").read_text(encoding="utf-8"))
    terms = packs.current().terms
    admin = client("admin")
    bad = []
    for s in nav.PACK_SCREENS + [x for x in nav.CORE_SCREENS if x.module in ("pop", "qua", "shp", "trc", "mat")]:
        r = admin.get(s.path, headers={"accept": "text/html"})
        if r.status_code != 200:
            continue
        plain = _plain(r.text)
        for k in gates["terms_sample"]:
            if k in plain and terms[k] not in plain:
                bad.append(f"{s.screen_id} `{k}`")
    assert not bad, bad


def test_menu_order_roles_and_pack_screens():
    p = packs.current()
    assert [m.code for m in nav.ALL_MENUS][:7] == ["bas", "ord", "job", "mat", "cond", "wsh", "tank"]
    assert [r["code"] for r in p.roles] == ["PM", "PROD", "QA", "FIELD", "ADMIN", "VENDOR"]
    assert len(nav.PACK_SCREENS) == 8 and len(nav.CORE_SCREENS) == 51
    assert packs.t("생산 LOT") == "배치" and packs.t("합병") == "혼합" and packs.t("측정값") == "공정 조건"
    main = client("admin").get("/", headers={"accept": "text/html"}).text
    assert "공정 조건 기준" in main and "절임통 운영" in main and "알람 이력" in main


@pytest.mark.parametrize("login_id, path, status", [
    ("field", "/trc/backward", 403), ("field", "/kpi/summary", 403), ("field", "/cond/item-standards", 200), ("qa", "/alm/alarms", 200),
    ("prod", "/alm/alarms", 200), ("field", "/alm/alarms", 200), ("qa", "/tank/operations", 200),
])
def test_role_screen_access(login_id, path, status):
    assert client(login_id).get(path).status_code == status
