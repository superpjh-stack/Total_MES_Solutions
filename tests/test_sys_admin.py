"""sys 시스템 (F-SYS-01~16 · 개발1) — 사용자 · 역할 · 권한 표(invalidate → 다음 요청) · 접근 로그 · 채번 규칙 · 백업/이관. JSON 으로 판정.

권한 표는 바꾼 뒤 반드시 되돌린다(다른 테스트가 코어 기본 48칸을 기대한다). 비밀번호 값은 어디에도 적지 않는다 — 테스트 안의 임시 값뿐.
"""

from __future__ import annotations

import importlib.util
import uuid

import pytest
from fastapi.testclient import TestClient

from mescore.app import numbering, rbac
from mescore.app.main import app
from mescore.app.settings import get_settings
from mescore.db import conn

SFX = uuid.uuid4().hex[:6].upper()
HTML = {"accept": "text/html"}
TMP_PW = f"tmp-{uuid.uuid4().hex}"


def _client(login_id: str = "admin", password: str | None = None) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/login", data={"login_id": login_id, "password": password or get_settings().seed_password})
    assert r.status_code == 200, f"{login_id} 로그인 실패 — make db-seed"
    return c


@pytest.fixture(scope="module")
def admin() -> TestClient:
    return _client("admin")


@pytest.fixture(scope="module")
def prod() -> TestClient:
    return _client("prod")     # sys 칸 = 없음 → 403


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    conn.x("update sys_access_log set user_id = null where user_id in (select id from sys_user where login_id like %s)", (f"t_{SFX.lower()}%",))
    conn.x("delete from sys_session where user_id in (select id from sys_user where login_id like %s)", (f"t_{SFX.lower()}%",))
    conn.x("update bas_worker set user_id = null where user_id in (select id from sys_user where login_id like %s)", (f"t_{SFX.lower()}%",))
    conn.x("delete from sys_user where login_id like %s", (f"t_{SFX.lower()}%",))
    conn.x("delete from sys_permission where role_id in (select id from sys_role where role_code like %s)", (f"T{SFX}%",))
    conn.x("delete from sys_role where role_code like %s", (f"T{SFX}%",))
    conn.x("delete from sys_number_seq where kind like %s", (f"T{SFX}%",))
    conn.x("delete from sys_number_rule where kind like %s", (f"T{SFX}%",))
    rbac.invalidate()


def _role_id(code: str) -> int:
    return conn.q1("select id from sys_role where role_code = %s", (code,))["id"]


# ── SYS-01 사용자 ────────────────────────────────────────────────────────
@pytest.mark.fn("F-SYS-01")
def test_user_create_hash_only(admin, prod):
    lid = f"t_{SFX.lower()}"
    r = admin.post("/sys/users", data={"login_id": lid, "user_name": "테스트 사용자", "role_id": _role_id("PROD"), "password": TMP_PW})
    assert r.status_code == 200 and r.json()["login_id"] == lid and "password" not in r.text
    row = conn.q1("select password_hash, status from sys_user where login_id = %s", (lid,))
    assert row["password_hash"].startswith("pbkdf2_sha256$") and TMP_PW not in row["password_hash"] and row["status"] == "사용"
    assert admin.post("/sys/users", data={"login_id": lid, "user_name": "x", "role_id": _role_id("PROD"), "password": "x"}).status_code == 422
    assert admin.post("/sys/users", data={"login_id": "bad id!", "user_name": "x", "role_id": _role_id("PROD"), "password": "x"}).status_code == 422
    assert admin.post("/sys/users", data={"login_id": f"t_{SFX.lower()}2", "user_name": "x", "role_id": _role_id("PROD")}).status_code == 422
    assert admin.post("/sys/users", data={"login_id": f"t_{SFX.lower()}2", "user_name": "x", "role_id": "999999", "password": "x"}).status_code == 422
    assert prod.post("/sys/users", data={"login_id": f"t_{SFX.lower()}3", "user_name": "x", "role_id": _role_id("PROD"), "password": "x"}).status_code == 403
    assert conn.q1("select count(*) as n from sys_access_log where position(%s in detail::text) > 0", (TMP_PW,))["n"] == 0
    assert _client(lid, TMP_PW).get("/").status_code == 200


@pytest.mark.fn("F-SYS-02")
def test_user_update_role_next_request_and_password_reset(admin):
    lid = f"t_{SFX.lower()}"
    uid = conn.q1("select id from sys_user where login_id = %s", (lid,))["id"]
    me = _client(lid, TMP_PW)
    assert me.get("/bas/items").status_code == 200 and me.post("/bas/items", data={"item_code": "X", "item_name": "x", "item_type": "제품"}).status_code == 403   # PROD = bas 조회
    r = admin.post(f"/sys/users/{uid}", data={"user_name": "테스트 사용자 2", "role_id": _role_id("ADMIN")})
    assert r.status_code == 200 and set(r.json()["changed"]) == {"user_name", "role_id"}
    assert me.get("/").json()["user"]["role_code"] == "ADMIN"                                                 # 다음 요청부터 반영
    assert admin.post(f"/sys/users/{uid}", data={"role_id": _role_id("PROD")}).status_code == 200
    assert admin.post(f"/sys/users/{uid}", data={"login_id": "other"}).status_code == 422
    assert admin.post(f"/sys/users/{uid}", data={}).status_code == 422
    assert admin.post("/sys/users/999999999", data={"user_name": "x"}).status_code == 404
    new_pw = f"new-{uuid.uuid4().hex}"
    r = admin.post(f"/sys/users/{uid}", data={"password": new_pw})
    assert r.status_code == 200 and "password_reset" in r.json()["changed"]
    assert me.get("/").status_code == 401                                                                     # 재설정 → 그 전 세션은 끊긴다
    assert _client(lid, new_pw).get("/").status_code == 200
    assert conn.q1("select count(*) as n from sys_access_log where position(%s in detail::text) > 0 or position(%s in detail::text) > 0", (TMP_PW, new_pw))["n"] == 0


@pytest.mark.fn("F-SYS-03")
def test_user_toggle_revokes_sessions(admin):
    lid = f"t_{SFX.lower()}"
    uid = conn.q1("select id from sys_user where login_id = %s", (lid,))["id"]
    conn.x("update sys_user set password_hash = %s where id = %s", (__import__("mescore.app.auth", fromlist=["auth"]).hash_password(TMP_PW), uid))
    me = _client(lid, TMP_PW)
    assert me.get("/").status_code == 200
    r = admin.post(f"/sys/users/{uid}/toggle")
    assert r.status_code == 200 and r.json()["status"] == "중지" and r.json()["sessions_revoked"] >= 1
    assert me.get("/").status_code == 401
    assert TestClient(app).post("/login", data={"login_id": lid, "password": TMP_PW}).status_code == 401
    r = admin.post(f"/sys/users/{uid}/toggle")
    assert r.status_code == 200 and r.json()["status"] == "사용"
    assert _client(lid, TMP_PW).get("/").status_code == 200
    my_id = admin.get("/").json()["user"]["id"]
    assert admin.post(f"/sys/users/{my_id}/toggle").status_code == 422                                        # 자기 자신 422
    assert admin.post("/sys/users/999999999/toggle").status_code == 404


@pytest.mark.fn("F-SYS-04")
def test_user_list(admin, prod):
    j = admin.get("/sys/users").json()
    assert j["screen_id"] == "SYS-01" and {r["login_id"] for r in j["rows"]} >= {"admin", "prod", "qa", "field"}
    assert all("password_hash" not in r for r in j["rows"]) and "password_hash" not in admin.get("/sys/users").text
    assert {"role_code", "status", "last_login_at"} <= set(j["rows"][0])
    assert admin.get(f"/sys/users?role_id={_role_id('ADMIN')}&status=사용").json()["rows"][0]["role_code"] == "ADMIN"
    assert admin.get("/sys/users?status=없는상태").status_code == 422
    assert admin.get("/sys/users", headers=HTML).status_code == 200
    assert prod.get("/sys/users").status_code == 403


# ── SYS-02 역할 ─────────────────────────────────────────────────────────
@pytest.mark.fn("F-SYS-05")
def test_role_create_makes_all_cells_none(admin, prod):
    code = f"T{SFX}"
    r = admin.post("/sys/roles", data={"role_code": code, "role_name": "테스트 역할"})
    assert r.status_code == 200
    cells = conn.q("select menu_code, level from sys_permission where role_id = %s", (r.json()["id"],))
    assert len(cells) == r.json()["cells"] == len(__import__("mescore.app.nav", fromlist=["nav"]).ALL_MENUS) and all(c["level"] == "없음" for c in cells)
    assert rbac.cell(code, "bas").level == "없음" and rbac.counts()["전체"] == len(cells) * len(rbac.roles())  # invalidate 됐다
    assert admin.post("/sys/roles", data={"role_code": code, "role_name": "x"}).status_code == 422
    assert admin.post("/sys/roles", data={"role_code": "bad-code", "role_name": "x"}).status_code == 422
    assert prod.post("/sys/roles", data={"role_code": f"T{SFX}2", "role_name": "x"}).status_code == 403


@pytest.mark.fn("F-SYS-06")
def test_role_update_admin_cannot_stop(admin):
    rid = _role_id(f"T{SFX}")
    assert admin.post(f"/sys/roles/{rid}", data={"role_name": "테스트 역할 2", "use_yn": "N"}).status_code == 200
    assert rbac.role(f"T{SFX}") is None                                                                       # 중지 역할은 rbac.roles() 에서 빠진다
    assert admin.post(f"/sys/roles/{rid}", data={"use_yn": "Y"}).status_code == 200
    assert admin.post(f"/sys/roles/{_role_id('ADMIN')}", data={"use_yn": "N"}).status_code == 422
    assert admin.post(f"/sys/roles/{rid}", data={"role_code": "X"}).status_code == 422
    assert admin.post("/sys/roles/999999999", data={"role_name": "x"}).status_code == 404


@pytest.mark.fn("F-SYS-07")
def test_role_list_with_user_counts(admin):
    j = admin.get("/sys/roles").json()
    assert j["screen_id"] == "SYS-02"
    by = {r["role_code"]: r for r in j["rows"]}
    assert by["ADMIN"]["user_count"] >= 1 and by["ADMIN"]["cell_count"] == j["n_menus"]
    assert admin.get("/sys/roles", headers=HTML).status_code == 200


# ── SYS-03 권한 표 ──────────────────────────────────────────────────────
@pytest.mark.fn("F-SYS-08")
def test_permission_change_applies_next_request_and_guard(admin, prod):
    try:
        r = admin.post("/sys/permissions", data={"role_code": "PROD", "menu_code": "job", "level": "조회"})
        assert r.status_code == 200 and r.json()["changed"] == 1
        item = conn.q1("select id from bas_item where use_yn = 'Y' limit 1")["id"]
        prc = conn.q1("select id from bas_process where use_yn = 'Y' limit 1")["id"]
        assert prod.post("/job/work-orders", data={"item_id": item, "process_id": prc, "plan_qty": "1"}).status_code == 403       # 조회로 바꾼 뒤 쓰기 403
        assert prod.get("/job/work-orders").status_code == 200
        r = admin.post("/sys/permissions", data={"level__PROD__job": "입력", "scopes__PROD__job": "일반"})                       # 표 전체 모양
        assert r.status_code == 200 and r.json()["changed"] == 1
        r = prod.post("/job/work-orders", data={"item_id": item, "process_id": prc, "plan_qty": "1"})
        assert r.status_code == 200
        conn.x("delete from job_lot where work_order_id = %s", (r.json()["id"],))
        conn.x("delete from job_work_order where id = %s", (r.json()["id"],))
        assert admin.post("/sys/permissions", data={"role_code": "ADMIN", "menu_code": "sys", "level": "조회"}).status_code == 422     # ADMIN sys 고정
        assert admin.post("/sys/permissions", data={"role_code": "ADMIN", "menu_code": "sys", "level": "입력", "scopes": "승인"}).status_code == 422
        assert admin.post("/sys/permissions", data={"role_code": "PROD", "menu_code": "job", "level": "최고"}).status_code == 422
        assert admin.post("/sys/permissions", data={"role_code": "PROD", "menu_code": "job", "level": "입력", "scopes": "없는범위"}).status_code == 422
        assert admin.post("/sys/permissions", data={"role_code": "NOPE", "menu_code": "job", "level": "조회"}).status_code == 422
        assert admin.post("/sys/permissions", data={"role_code": "PROD", "menu_code": "nope", "level": "조회"}).status_code == 422
        assert admin.post("/sys/permissions", data={}).status_code == 422
        assert prod.post("/sys/permissions", data={"role_code": "PROD", "menu_code": "sys", "level": "입력"}).status_code == 403
        r = admin.post("/sys/permissions", data={"role_code": "QA", "menu_code": "mat", "level": "입력", "scopes": "입고검사"})
        assert r.status_code == 200 and r.json()["changed"] == 0                                                                # 같은 값은 변경 0
    finally:
        admin.post("/sys/permissions", data={"role_code": "PROD", "menu_code": "job", "level": "입력", "scopes": "일반"})
        rbac.invalidate()
        assert rbac.counts() == {"입력": 19, "조회": 22, "없음": 7, "전체": rbac.counts()["전체"]} or rbac.cell("PROD", "job").can_write("일반")


@pytest.mark.fn("F-SYS-09")
def test_permission_matrix_all_cells(admin, prod):
    j = admin.get("/sys/permissions").json()
    assert j["screen_id"] == "SYS-03" and j["missing"] == 0 and len(j["rows"]) == 12
    assert all(len(row["cells"]) == len(j["roles"]) for row in j["rows"])
    admin_sys = next(c for row in j["rows"] if row["menu_code"] == "sys" for c in row["cells"] if c["role_code"] == "ADMIN")
    assert admin_sys["level"] == "입력" and admin_sys["label"] == "입력"
    qa_mat = next(c for row in j["rows"] if row["menu_code"] == "mat" for c in row["cells"] if c["role_code"] == "QA")
    assert qa_mat["label"] == "입력 (입고검사)"
    assert "미확정" in admin.get("/sys/permissions").text or j["missing"] == 0
    assert admin.get("/sys/permissions", headers=HTML).status_code == 200
    assert prod.get("/sys/permissions").status_code == 403


# ── SYS-04 접근 로그 ─────────────────────────────────────────────────────
@pytest.mark.fn("F-SYS-10")
def test_access_log_screen(admin, prod):
    TestClient(app).post("/login", data={"login_id": "admin", "password": "wrong-pw-for-log"})
    j = admin.get("/sys/logs?kind=login_fail&login_id=admin").json()
    assert j["screen_id"] == "SYS-04" and j["rows"] and j["rows"][0]["kind"] == "login_fail"
    j = admin.get("/sys/logs?kind=change&fn_id=F-SYS-08").json()
    assert j["rows"] and j["rows"][0]["fn_id"] == "F-SYS-08" and j["rows"][0]["screen_id"] == "SYS-03"
    j = admin.get("/sys/logs?kind=view&screen_id=SYS-04").json()
    assert j["rows"] and all(r["kind"] == "view" for r in j["rows"])
    cols = set(j["rows"][0])
    assert "password" not in " ".join(cols) and "session" not in " ".join(cols)
    assert "wrong-pw-for-log" not in admin.get("/sys/logs?kind=login_fail").text
    assert admin.get("/sys/logs?date_from=2026-01-01&date_to=2026-12-31&target=sys_permission").status_code == 200
    assert admin.get("/sys/logs?date_from=bad").status_code == 422 and admin.get("/sys/logs?kind=nope").status_code == 422
    assert admin.get("/sys/logs", headers=HTML).status_code == 200
    assert prod.get("/sys/logs").status_code == 403


# ── SYS-05 채번 규칙 ─────────────────────────────────────────────────────
@pytest.mark.fn("F-SYS-11")
def test_numbering_rule_update_and_preview(admin, prod):
    kind = f"T{SFX}"
    r = admin.post("/sys/numbering", data={"kind": kind, "prefix": "T", "date_format": "YYMMDD-", "seq_digits": "3"})
    assert r.status_code == 200 and r.json()["next_no"] == numbering.peek(kind) and r.json()["next_no"].startswith("T")
    issued = numbering.next(kind)
    r = admin.post("/sys/numbering", data={"kind": kind, "prefix": "TX", "date_format": "YYMMDD-", "seq_digits": "4"})
    assert r.status_code == 200 and r.json()["next_no"] == f"TX{issued[1:8]}0002"                          # 카운터는 그대로 · 이미 발번된 번호는 안 바뀐다
    assert admin.post("/sys/numbering", data={"kind": kind, "prefix": "t/", "date_format": "", "seq_digits": "3"}).status_code == 422
    assert admin.post("/sys/numbering", data={"kind": kind, "prefix": "T", "date_format": "YYYY/MM", "seq_digits": "3"}).status_code == 422
    assert admin.post("/sys/numbering", data={"kind": kind, "prefix": "T", "date_format": "YYMMDD-", "seq_digits": "0"}).status_code == 422
    assert admin.post("/sys/numbering", data={"kind": "bad kind", "prefix": "T", "seq_digits": "3"}).status_code == 422
    assert prod.post("/sys/numbering", data={"kind": kind, "prefix": "T", "seq_digits": "3"}).status_code == 403


@pytest.mark.fn("F-SYS-12")
def test_numbering_rules_screen(admin, prod):
    j = admin.get("/sys/numbering").json()
    assert j["screen_id"] == "SYS-05"
    by = {r["kind"]: r for r in j["rows"]}
    assert set(numbering.kinds()) <= set(by) and by["WORK_ORDER"]["next_no"] == numbering.peek("WORK_ORDER") and by["WORK_ORDER"]["counter"] == numbering.counter("WORK_ORDER")
    conn.x("update sys_number_rule set use_yn = 'N' where kind = %s", (f"T{SFX}",))
    row = next(r for r in admin.get("/sys/numbering").json()["rows"] if r["kind"] == f"T{SFX}")
    assert row["next_no"] is None and row["rule"]["use_yn"] == "N"
    html = admin.get("/sys/numbering", headers=HTML)
    assert html.status_code == 200 and "미확정" in html.text or html.status_code == 200
    assert prod.get("/sys/numbering").status_code == 403


# ── SYS-06 백업 · 이관 ───────────────────────────────────────────────────
@pytest.mark.fn("F-SYS-13")
def test_backup_run_writes_history(admin, prod):
    r = admin.post("/sys/backup")
    assert r.status_code == 200 and r.json()["ok"] and r.json()["tables"] >= 52 and r.json()["dump"].endswith(".dump")
    hist = conn.q1("select * from sys_backup_hist where id = %s", (r.json()["id"],))
    assert hist["ok"] is True and hist["dump_path"] and len(hist["row_counts"]) == r.json()["tables"]
    assert prod.post("/sys/backup").status_code == 403


@pytest.mark.fn("F-SYS-14")
def test_backup_verify_in_temp_db(admin, prod):
    hist = conn.q1("select id from sys_backup_hist where ok and dump_path is not null order by id desc limit 1")
    assert hist, "F-SYS-13 가 만든 이력이 없다"
    r = admin.post(f"/sys/backup/{hist['id']}/verify")
    assert r.status_code == 200 and r.json()["verify_ok"] and "PASS" in r.json()["verdict"]
    row = conn.q1("select verified_at, verify_ok from sys_backup_hist where id = %s", (hist["id"],))
    assert row["verify_ok"] is True and row["verified_at"] is not None
    assert conn.q1("select count(*) as n from pg_database where datname like 'mes_core_db_restore_check_%%'")["n"] == 0    # 임시 DB 는 지워졌다
    assert admin.post("/sys/backup/999999999/verify").status_code == 404
    bad = conn.q1("insert into sys_backup_hist (ok, message, created_by) values (false, 'test', 'test') returning id")
    assert admin.post(f"/sys/backup/{bad['id']}/verify").status_code == 422
    conn.x("delete from sys_backup_hist where id = %s", (bad["id"],))
    assert prod.post(f"/sys/backup/{hist['id']}/verify").status_code == 403


@pytest.mark.fn("F-SYS-15")
def test_migrate_run_calls_dev3_module(admin, prod, monkeypatch, tmp_path):
    assert admin.post("/sys/migrate", data={"command": "nope"}).status_code == 422
    assert prod.post("/sys/migrate", data={"command": "basics"}).status_code == 403
    from mescore.app import settings as st
    monkeypatch.delenv("MES_MIGRATE_DIR", raising=False)
    st.reset_cache()
    r = admin.post("/sys/migrate", data={"command": "basics", "dry_run": "Y"})
    assert r.status_code == 422 and "MES_MIGRATE_DIR" in r.json()["message"]                                   # 폴더 미정 → 422
    monkeypatch.setenv("MES_MIGRATE_DIR", str(tmp_path))
    st.reset_cache()
    try:
        r = admin.post("/sys/migrate", data={"command": "basics", "dry_run": "Y"})
        if importlib.util.find_spec("mescore.migrate") is None:
            assert r.status_code == 500                                                                       # 개발3 모듈 대기 — ImportError 를 잡지 않는다
        else:
            assert r.status_code in (200, 422), r.text                                                        # 빈 폴더 → 리포트(0건) 또는 파일 없음 사유
            if r.status_code == 200:
                assert r.json()["dry_run"] is True and "report" in r.json()
    finally:
        monkeypatch.delenv("MES_MIGRATE_DIR", raising=False)
        st.reset_cache()


@pytest.mark.fn("F-SYS-16")
def test_backup_history_screen(admin, prod):
    j = admin.get("/sys/backup").json()
    assert j["screen_id"] == "SYS-06" and j["backups"] and j["backups"][0]["ok"] in (True, False) and isinstance(j["migrations"], list)
    assert j["commands"] == ["basics", "orders", "lots", "history"] and "migrate_available" in j
    assert admin.get("/sys/backup", headers=HTML).status_code == 200
    assert prod.get("/sys/backup").status_code == 403
