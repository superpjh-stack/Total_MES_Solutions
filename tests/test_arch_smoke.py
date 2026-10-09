"""아키텍트 골격 스모크 — 매니페스트 수 · 계약 136줄 · /health · 로그인 401/303 · 권한 없음 403 · placeholder 51 · 채널 · 접근 로그 · 금지어 0.

공통 시드가 들어 있어야 한다(`make db-reset`). 시드 비밀번호는 `.env` 의 `MES_SEED_PASSWORD`.
이 테스트는 코어 단독(MES_PACK=)과 어떤 팩에서도 통과해야 한다(R9) — 기대값은 core.yaml · 계약에서 읽는다.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mescore.app import contracts, nav, packs, rbac
from mescore.app.main import app
from mescore.app.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
HTML = {"accept": "text/html"}


def _client(login_id: str | None = None) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    if login_id:
        r = c.post("/login", data={"login_id": login_id, "password": get_settings().seed_password})
        assert r.status_code == 200 and r.json()["ok"], f"{login_id} 로그인 실패 {r.status_code} — 공통 시드(make db-seed)와 .env 를 확인한다"
    return c


def test_seed_password_is_configured():
    assert get_settings().seed_password, "MES_SEED_PASSWORD 미설정 — make setup"


def test_manifest_counts():
    assert (len([m for m in nav.ALL_MENUS if not m.is_pack]), len(nav.CORE_SCREENS), len(nav.COMMON)) == (12, 51, 5)
    p = packs.current()
    assert len(p.core_modules) == 12 and len(p.roles) >= 1 and "ADMIN" in {r["code"] for r in p.roles}
    assert len(p.numbering) >= 8 and len(p.terms_keys) == 26
    assert [k["kind"] for k in p.lineage["lot_kinds"][:3]] == ["MATERIAL", "PRODUCT", "SHIPMENT"]
    assert [r["name"] for r in p.lineage["relations"][:5]] == ["투입", "생산", "분할", "합병", "출하"]


def test_function_list_136_lines():
    fns = contracts.functions()
    assert sum(1 for f in fns if not f.is_batch) == 132 and sum(1 for f in fns if f.is_batch) == 4
    for code, n in contracts.MODULE_COUNTS.items():
        assert len([f for f in fns if not f.is_batch and f.module == code]) == n, code
    by_owner = {o: sum(1 for f in fns if not f.is_batch and f.owner == o) for o in ("개발1", "개발2", "개발3")}
    assert by_owner == {"개발1": 59, "개발2": 38, "개발3": 35}
    assert contracts.function("F-IFC-01").is_token


def test_permission_matrix_is_data():
    """권한 표는 DB 데이터 — 기대값은 `역할 수(DB · SYS-02 로 늘어난 것 포함) × 메뉴 수`. 코어 역할 4 의 칸은 goal.md §6 표 그대로 (D-13)."""
    rbac.invalidate()
    p = packs.current()
    db_roles = rbac.roles()
    assert rbac.counts()["전체"] == len(db_roles) * len(nav.ALL_MENUS)
    manifest = [r["code"] for r in p.roles]
    assert set(manifest) <= {r.code for r in db_roles}, "매니페스트(core.yaml + pack.yaml) 역할이 DB 에 없다 — make db-seed"
    core = {"입력": 0, "조회": 0, "없음": 0}
    for code in manifest:
        for m in nav.ALL_MENUS:
            core[rbac.cell(code, m.code).level] += 1
    assert sum(core.values()) == len(manifest) * len(nav.ALL_MENUS)
    if p.is_core_only:
        assert core == {"입력": 19, "조회": 22, "없음": 7}   # goal.md §6 표 그대로 (D-13) — 코어 역할 4 × 메뉴 12 = 48


def test_health():
    r = TestClient(app).get("/health")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    assert set(body) == {"status", "system", "pack", "core_version", "db", "menus", "screens", "functions", "placeholders", "pack_screens", "router_include_errors"}
    assert (body["screens"], body["functions"], body["core_version"]) == (51, 132, packs.current().core_version)
    assert body["db"] == {"ok": True} and body["router_include_errors"] == []
    assert "postgresql" not in r.text and "mes_core_db" not in r.text


def test_health_is_503_without_db(monkeypatch):
    monkeypatch.setenv("MES_PG_DSN", "postgresql://u1@arch-db-host.invalid:1/d1?connect_timeout=1")
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/health")
    assert r.status_code == 503 and r.json()["db"] == {"ok": False}
    assert "arch-db-host" not in r.text
    r = c.post("/login", data={"login_id": "x", "password": "y"})
    assert r.status_code == 503 and r.json()["code"] == "db_unavailable"


def test_anonymous_browser_303_and_api_401():
    c = _client()
    r = c.get(nav.path_of("BAS-01"), headers=HTML, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")
    r = c.get(nav.path_of("BAS-01"))
    assert r.status_code == 401 and r.json()["code"] == "unauthorized"
    assert c.get("/login", headers=HTML).status_code == 200 and c.get("/error", headers=HTML).status_code == 200


def test_login_401_then_ok_and_logout_revokes():
    c = _client()
    assert c.post("/login", data={"login_id": "admin", "password": "틀린-비밀번호"}).status_code == 401
    assert c.post("/login", data={"login_id": "없는계정", "password": "x"}).status_code == 401
    r401 = c.post("/login", data={"login_id": "없는계정", "password": "x"}, headers=HTML)      # 실패 재렌더도 GET /login 과 같은 권한 표 요약
    assert r401.status_code == 401 and f"역할 {len(rbac.roles())} ·" in r401.text
    r = c.post("/login", data={"login_id": "admin", "password": get_settings().seed_password}, headers=HTML, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert c.get("/").status_code == 200
    c.post("/logout", follow_redirects=False)
    assert c.get("/").status_code == 401


def test_admin_opens_every_screen_and_placeholders_carry_contract():
    c = _client("admin")
    n_ph = 0
    for s in nav.SCREENS:
        r = c.get(s.path)
        assert r.status_code == 200, s.path
        body = r.json()
        if s.path in app.state.placeholder_paths:
            n_ph += 1
            assert body["placeholder"] and body["owner"] == s.owner and f"담당 {s.owner}" in body["note"], s.path
            assert {f["fn"]["id"] for f in body["functions"]} == {f.id for f in contracts.functions_of(s.screen_id)}, s.path
            html = c.get(s.path, headers=HTML).text
            assert "미구현" in html and f"담당 {s.owner}" in html
    assert n_ph == len(app.state.placeholder_paths)
    for s in nav.COMMON:
        if s.auth:
            assert c.get(s.probe or s.path).status_code == 200, s.screen_id
    assert c.get("/popup/없는종류").status_code == 404


def test_screen_json_and_html_carry_same_data():
    """백엔드 우선 (D-18) — Accept 에 text/html 이 없으면 ctx JSON, 있으면 HTML."""
    c = _client("admin")
    j = c.get("/").json()
    assert j["screen_id"] == "CMN-02" and j["user"]["login_id"] == "admin" and isinstance(j["cards"], list)
    h = c.get("/", headers=HTML)
    assert h.headers["content-type"].startswith("text/html") and 'class="ch-web"' in h.text


@pytest.mark.parametrize("login_id, screen_id", [
    ("field", "BAS-01"),   # 현장 × 기준정보 = 없음
    ("field", "TRC-01"),   # 현장 × LOT 추적 = 없음
    ("field", "SYS-01"),   # 현장 × 시스템 = 없음
    ("prod", "SYS-02"),    # 생산 × 시스템 = 없음
    ("qa", "IFC-01"),      # 품질 × 인터페이스 = 없음
])
def test_no_permission_is_403_and_hidden(login_id, screen_id):
    if not packs.current().is_core_only:
        pytest.skip("코어 기본 권한 표 기준 — 팩이 칸을 바꿀 수 있다")
    c = _client(login_id)
    r = c.get(nav.path_of(screen_id))
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    assert f'href="{nav.path_of(screen_id)}"' not in c.get("/", headers=HTML).text


def test_write_scope_of_bracketed_cells():
    """괄호 조건 4개 (D-13): 입고검사 · 승인 · 지표 · 재전송 — 그 범위 기능만, 일반 기능은 못 한다."""
    if not packs.current().is_core_only:
        pytest.skip("코어 기본 권한 표 기준")
    rbac.invalidate()
    assert rbac.can_do("QA", "F-MAT-04") and not rbac.can_do("QA", "F-MAT-01") and not rbac.can_do("PROD", "F-MAT-04")
    assert rbac.can_do("ADMIN", "F-SHP-07") and not rbac.can_do("ADMIN", "F-SHP-01") and not rbac.can_do("PROD", "F-SHP-07")
    assert rbac.can_do("ADMIN", "F-KPI-06") and not rbac.can_do("PROD", "F-KPI-06") and rbac.can_do("PROD", "F-KPI-02")
    assert rbac.can_do("ADMIN", "F-IFC-04") and not rbac.can_do("PROD", "F-IFC-04") and not rbac.can_do("QA", "F-IFC-03")
    assert not rbac.can_do("QA", "F-BAS-01") and rbac.can_do("QA", "F-BAS-04") and not rbac.can_do("FIELD", "F-BAS-04")
    assert not rbac.can_do("ADMIN", "F-IFC-01")   # 토큰 인증 — 사용자 권한 밖


def test_channel_layout_and_channel_rule():
    c = _client("admin")
    assert 'class="ch-web"' in c.get(nav.path_of("KPI-02"), headers=HTML).text
    board = c.get(nav.path_of("KPI-01") + "?device=board", headers=HTML).text
    assert 'class="ch-board"' in board and 'data-refresh-seconds=' in board and "마지막 갱신" in board
    assert 'class="ch-pop"' in c.get(nav.path_of("POP-01") + "?device=pop", headers=HTML).text
    r = c.get(nav.path_of("BAS-01") + "?device=pop")     # channels.pop 에 없는 화면 → 403
    assert r.status_code == 403 and r.json()["code"] == "forbidden"


def test_unknown_path_is_404_contract():
    r = _client("admin").get("/없는-경로")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_view_and_login_are_logged():
    from mescore.db import conn

    sql_view = "select count(*) as n from sys_access_log where kind = 'view' and screen_id = 'JOB-01'"
    before = conn.q1(sql_view)["n"]
    _client("admin").get(nav.path_of("JOB-01"))
    assert conn.q1(sql_view)["n"] == before + 1
    sql_fail = "select count(*) as n from sys_access_log where kind = 'login_fail' and login_id = 'admin'"
    before = conn.q1(sql_fail)["n"]
    _client().post("/login", data={"login_id": "admin", "password": "틀린-비밀번호"})
    assert conn.q1(sql_fail)["n"] == before + 1
    assert conn.q1("select count(*) as n from sys_access_log where position(%s in detail::text) > 0", (get_settings().seed_password,))["n"] == 0


def test_core_has_no_forbidden_terms():
    sys.path.insert(0, str(ROOT / "src" / "mescore" / "tools"))
    import check_terms
    bad, n = check_terms.scan_core()
    assert n > 20 and bad == []


def test_numbering_rules_seeded_from_core_yaml():
    from mescore.db import conn

    rows = {r["kind"]: r for r in conn.q("select kind, prefix, date_format, seq_digits from sys_number_rule")}
    for kind, rule in packs.current().numbering.items():
        assert kind in rows and rows[kind]["prefix"] == rule["prefix"] and rows[kind]["seq_digits"] == rule["digits"], kind


def test_term_substitution_is_identity_without_pack():
    if packs.current().is_core_only:
        assert packs.t("생산 LOT") == "생산 LOT" and packs.t("없는 말") == "없는 말"


def test_422_form_post_keeps_values_in_flash_and_asset_version_tracks_static():
    """폼 POST 422 → 303 + 알림에 입력값(values · 비밀 칸 제외) · JSON 422 에는 values 없음 · asset_version = static 전체 mtime."""
    import os
    import time

    from mescore.app import templating
    from mescore.app.util import http as h

    c = _client("admin")
    r = c.post(nav.path_of("BAS-01"), data={"item_code": "", "item_name": "값 유지 (예시)", "password": "x"}, headers=HTML, follow_redirects=False)
    assert r.status_code == 303
    import base64
    import json

    from itsdangerous import TimestampSigner
    raw = TimestampSigner(get_settings().session_secret).unsign(c.cookies.get(get_settings().session_cookie).encode())
    flash = json.loads(base64.b64decode(raw))["flash"]     # 세션 쿠키(SessionMiddleware) 안의 알림
    assert flash["values"].get("item_name") == "값 유지 (예시)" and "password" not in flash["values"]
    j = c.post(nav.path_of("BAS-01"), data={"item_code": "", "item_name": "x"})
    assert j.status_code == 422 and "values" not in j.json()
    e = h.validation_error("x", values={"a": "1", "token": "t"})
    assert e.detail["values"] == {"a": "1"}
    probe = templating.STATIC_DIR / "_asset_probe.tmp"
    try:
        before = int(templating.asset_version())
        probe.write_text("x", encoding="utf-8")
        os.utime(probe, (time.time() + 100, time.time() + 100))
        assert int(templating.asset_version()) >= before + 99
    finally:
        probe.unlink(missing_ok=True)


def test_sort_clause_allows_only_declared_columns():
    from fastapi import HTTPException

    from mescore.app.util import http as h

    allowed = {"no": "w.work_order_no", "date": "w.plan_date"}
    assert h.sort_clause(None, allowed, "w.id desc") == "w.id desc" and h.sort_clause(" ", allowed, "w.id desc") == "w.id desc"
    assert h.sort_clause("-date,no", allowed, "x") == "w.plan_date desc, w.work_order_no asc"
    assert h.sort_clause("item_code", ["item_code"], "id") == "item_code asc"
    with pytest.raises(HTTPException) as exc:
        h.sort_clause("id;drop table lot", allowed, "x")
    assert exc.value.status_code == 422 and exc.value.detail["code"] == "validation_error"


def test_dev_login_only_dev_and_loopback(monkeypatch):
    """D-605 · DEF-QA1-001/QA3-001 — `MES_ENV` 기본값은 prod. `POST /login/as` 는 MES_ENV=dev **그리고** 루프백 요청일 때만, 아니면 404."""
    from mescore.app import settings as st

    try:
        monkeypatch.setenv("MES_ENV", "")
        st.reset_cache()
        assert get_settings().env == "prod"
        for env, host, want in (("", "127.0.0.1", 404), ("prod", "127.0.0.1", 404), ("dev", "10.0.0.5", 404),
                                ("dev", "testclient", 404), ("dev", "127.0.0.1", 200), ("dev", "::1", 200)):
            monkeypatch.setenv("MES_ENV", env)
            st.reset_cache()
            c = TestClient(app, raise_server_exceptions=False, client=(host, 50000))
            r = c.post("/login/as", data={"role": "ADMIN"})
            assert r.status_code == want, (env, host, r.status_code, r.text[:120])
            if want == 404:
                assert r.json()["code"] == "not_found" and c.get("/sys/users").status_code == 401
    finally:
        monkeypatch.undo()
        st.reset_cache()


def test_non_numeric_path_key_is_404_but_bad_body_is_422():
    """api-contract §1 · DEF-QA1-004 — 숫자여야 하는 경로 키가 숫자가 아니면 404(없는 대상). 본문 · 쿼리 검증 오류는 422 그대로."""
    from fastapi import APIRouter, Form

    probe = APIRouter()

    @probe.post("/_arch_probe/{item_id}")
    def _p(item_id: int, qty: int = Form(...)):
        return {"id": item_id, "qty": qty}

    app.include_router(probe)
    try:
        c = TestClient(app, raise_server_exceptions=False)
        r = c.post("/_arch_probe/abc", data={"qty": "1"})
        assert r.status_code == 404 and r.json()["code"] == "not_found"
        assert c.post("/_arch_probe/abc", data={"qty": "x"}).status_code == 404
        r = c.post("/_arch_probe/7", data={"qty": "x"})
        assert r.status_code == 422 and r.json()["fields"][0]["name"] == "qty"
        assert c.post("/_arch_probe/7", data={"qty": "2"}).json() == {"id": 7, "qty": 2}
    finally:
        app.router.routes[:] = [rt for rt in app.router.routes if not getattr(rt, "path", "").startswith("/_arch_probe")]


def test_shipment_approved_after_commit_enqueues_erp_by_default():
    """D-39 · DEF-QA1-007 — 팩이 `after_commit_shipment_approved` 를 두지 않으면 코어 기본이 `ifc_outbox` `대기` 1행을 넣는다."""
    from mescore.app import main as m
    from mescore.db import conn

    if packs.has_hook("after_commit_shipment_approved"):
        pytest.skip("팩 훅이 대신한다")
    marker = "S-ARCH-PROBE"
    try:
        m._run_after_commit("shipment_approved", {"shipment_no": marker, "approved_by": "admin", "lots": []})
        rows = conn.q("select status, created_by from ifc_outbox where event = 'shipment_approved' and payload->>'shipment_no' = %s", (marker,))
        assert [(r["status"], r["created_by"]) for r in rows] == [("대기", "admin")]
        m._run_after_commit("no_such_event", {"shipment_no": marker})          # 코어 기본이 없는 이벤트는 아무 일도 없다
        assert conn.q1("select count(*) as n from ifc_outbox where payload->>'shipment_no' = %s", (marker,))["n"] == 1
    finally:
        conn.x("delete from ifc_outbox where payload->>'shipment_no' = %s", (marker,))
