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
    rbac.invalidate()
    p = packs.current()
    assert rbac.counts()["전체"] == len(p.modules) * len(p.roles)
    if p.is_core_only:
        assert rbac.counts() == {"입력": 19, "조회": 22, "없음": 7, "전체": 48}   # goal.md §6 표 그대로 (D-13)


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
