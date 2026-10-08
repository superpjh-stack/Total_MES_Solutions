"""G-P05 용어 치환 · 팩 병합본 · 어댑터 — 화면 · 메뉴 · 라벨에 '작업지시' '생산 LOT' '성적서' '분할' '합병' '거래처' 날것 0, 'Job' 'Roll' 'COA' 노출 (개발2)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from mescore.app import nav, packs, printing

from _helpers import HTML, P, client

PACK_DIR = Path(__file__).resolve().parents[1]
GATES = yaml.safe_load((PACK_DIR / "gates.yaml").read_text(encoding="utf-8"))


def _plain(html: str) -> str:
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    return re.sub(r"<[^>]*>", " ", html)


@pytest.mark.fn("F-X-RLL-06")
def test_pack_manifest_merged():
    p = packs.current()
    assert p.name == "printfilm" and len(p.pack_screens) == GATES["screens"] and len(p.pack_modules) == 3
    assert "eqp" in p.hidden and [m.code for m in nav.MENUS][:4] == ["kpi", "ord", "job", "mat"]
    assert {k["kind"] for k in p.lineage["lot_kinds"]} >= {"ROLL"} and {r["name"] for r in p.lineage["relations"]} >= {"splice", "후가공", "슬리팅"}
    assert p.numbering["LOT_PRODUCT"]["prefix"] == "R" and p.numbering["LOT_PRODUCT"]["digits"] == 4 and p.numbering["WORK_ORDER"]["prefix"] == "J"
    assert [r["code"] for r in p.roles] == ["ADMIN", "PROD", "QC", "FIELD"] and p.permission("rll", "FIELD")["level"] == "입력" and p.permission("eqp", "ADMIN")["level"] == "없음"
    assert set(GATES["terms_sample"]) <= set(p.terms)
    assert packs.t("작업지시") == "Job" and packs.t("생산 LOT") == "Roll" and packs.t("성적서") == "COA" and packs.t("분할") == "슬리팅" and packs.t("합병") == "splice"
    assert packs.t("LOT 추적") == "LOT 추적" and packs.t("생산실적") == "생산실적"                                       # 겹말이 나는 용어는 뺐다


@pytest.mark.fn("F-X-PRT-04")
def test_terms_not_exposed_on_screens():
    """관리자(+ 현장 POP)로 화면 전부 — terms 키 날것 0 · 메뉴에 Job · Roll · COA · 인쇄 기준 · 조색 · 후가공."""
    keys = sorted(GATES["terms_sample"], key=len, reverse=True)
    admin, field = client("admin"), client("field", device="pop", fresh=True)
    seen, bad = 0, []
    for s in nav.COMMON + nav.SCREENS:
        if not s.auth:
            continue
        if s.screen_id == "SYS-04":
            # 접근 로그 화면은 기능명(function-list.md 계약 문구 — '작업지시 등록' 등)을 t() 없이 그대로 찍는다 — 코어 화면(개발1) · progress-dev2.md §3 요청.
            # 게이트(check_terms --pack)의 판정 규칙(키가 보이고 값이 안 보일 때만 FAIL)으로만 확인한다.
            r = admin.get(s.path, headers=HTML)
            if r.status_code == 200:
                plain = _plain(r.text)
                assert not [k for k in keys if k in plain and packs.t(k) not in plain], "SYS-04 치환 안 된 키"
            continue
        for c in (admin, field):
            r = c.get(s.probe or s.path, headers=HTML)
            if r.status_code != 200:
                continue
            seen += 1
            plain = _plain(r.text)
            for k in keys:
                for m in re.finditer(re.escape(k), plain):
                    ctx = plain[max(0, m.start() - 12): m.end() + 12]
                    if k == "분할" and ("분할 순번" in ctx or "분할 수" in ctx):      # 슬리팅 화면의 '분할 순번' · '분할 수' 는 팩 용어 (엘컴화인 F-RLL-04)
                        continue
                    bad.append(f"{s.screen_id} `{k}` …{ctx.strip()}…")
                    break
    assert seen >= 40 and not bad, bad[:10]
    main = _plain(admin.get("/", headers=HTML).text)
    for word in ("Job", "인쇄 기준 관리", "조색 기록", "후가공 · 슬리팅 롤 이력", "영업관리", "실적 현황"):
        assert word in main, word
    assert "설비" not in [m.name for m in nav.MENUS] and admin.get(nav.path_of("EQP-01"), headers=HTML).status_code == 403


@pytest.mark.fn("F-X-RLL-07")
def test_print_adapter_is_pack_html():
    printing.reset_adapter()
    a = printing.adapter()
    assert type(a).__name__ == "PrintAdapter" and a.name == "browser-html"
    res = a.send(printing.PrintJob(kind="label_lot", template="label_lot", data={}, copies=3))
    assert res.sent is False and "× 3" in res.message
    with pytest.raises(ValueError):
        a.send(printing.PrintJob(kind="x", template="nope"))
    over = packs.overridden_templates()
    assert over == sorted(GATES["isolation"]["template_overrides"])
    readme = (PACK_DIR / "README.md").read_text(encoding="utf-8")
    assert all(t in readme for t in over)


@pytest.mark.fn("F-X-CLR-05")
def test_pop_screens_show_roll_not_lot():
    c = client("field", device="pop", fresh=True)
    html = c.get(P["POP-04"], headers=HTML).text
    assert "Roll" in html and "생산 LOT" not in _plain(html)
    html = c.get(P["POP-02"], headers=HTML).text
    assert "Job" in html and "작업지시" not in _plain(html)
