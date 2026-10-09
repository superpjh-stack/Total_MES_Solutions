"""데이터 허브 (선택 모듈 meshub · D-53) — 저장 현황 · 정형 카탈로그/내보내기 · 비정형 파일 · 실시간 집계 · 역할 · RAG 연결."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from mescore.db import conn

from _dev2_helpers import HTML


@pytest.fixture
def hub_app(monkeypatch, tmp_path):
    from mescore.app import settings
    from mescore.app.main import create_app
    monkeypatch.setenv("MES_ADDONS", "agent,hub")
    monkeypatch.setenv("MES_HUB_DIR", str(tmp_path))
    settings.reset_cache()
    app = create_app()
    yield app
    monkeypatch.undo()
    settings.reset_cache()


def _login(app, login_id=None):
    from mescore.app.settings import get_settings
    c = TestClient(app, raise_server_exceptions=False)
    if login_id:
        assert c.post("/login", data={"login_id": login_id, "password": get_settings().seed_password}).json()["ok"]
    return c


def test_menu_under_agent_and_pages(hub_app):
    assert [m["code"] for m in hub_app.state.addon_menus] == ["agent", "hub"]           # MES AI Agent 아래
    c = _login(hub_app, "admin")
    html = c.get("/hub", headers=HTML).text
    assert "데이터 허브" in html and 'href="/hub/realtime"' in html and "정형 데이터" in html and "비정형 데이터" in html
    for p in ("/hub/structured", "/hub/structured/bas_item", "/hub/files", "/hub/realtime"):
        assert c.get(p, headers=HTML).status_code == 200, p
    assert _login(hub_app).get("/hub").status_code in (401, 303)


def test_overview_counts_match_database(hub_app):
    c = _login(hub_app, "admin")
    d = c.get("/hub").json()
    n_tables = conn.q1("select count(*)::int as n from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE'"
                       " and table_name not in ('sys_session', 'sys_user', 'sys_number_seq')")["n"]
    assert d["s"]["tables"] == n_tables
    assert d["rt"]["values"]["total"] == conn.q1("select count(*)::int as n from eqp_collect")["n"]
    assert conn.q1("select to_regclass('hub.file') is not null as ok")["ok"]                      # 허브 테이블은 hub 스키마
    assert not conn.q1("select count(*)::int as n from information_schema.tables where table_schema = 'public' and table_name like 'hub%'")["n"]


def test_structured_export_and_guards(hub_app):
    c = _login(hub_app, "admin")
    r = c.get("/hub/structured/bas_item.csv")
    rows = r.text.lstrip("﻿").splitlines()
    assert r.status_code == 200 and rows[0].startswith("id,item_code") and int(r.headers["x-rows"]) == len(rows) - 1
    assert int(r.headers["x-rows"]) == conn.q1("select count(*)::int as n from bas_item")["n"]
    for never in ("sys_user", "sys_session", "sys_number_seq"):
        assert c.get(f"/hub/structured/{never}.csv").status_code == 403
    assert c.get("/hub/structured/no_such_table.csv").status_code == 404
    assert c.get("/hub/structured/bas_item%3Bdrop.csv").status_code == 404                   # 이름은 화이트리스트만


def test_role_filters_tables_and_realtime(hub_app):
    field = _login(hub_app, "field")
    names = {t["name"] for t in field.get("/hub/structured").json()["tables"]}
    assert "pop_work_result" in names and "bas_item" in names and "bas_partner" not in names and "sys_role" not in names
    assert field.get("/hub/structured/bas_partner.csv").status_code == 403
    qa = _login(hub_app, "qa")
    assert qa.get("/hub/realtime/live").status_code in (200, 403)                              # 설비 메뉴 권한을 그대로 따른다
    assert field.post("/hub/realtime/rollup", data={"hours": "24"}).status_code == 403          # 집계는 관리자만


def test_files_upload_search_download_delete(hub_app):
    c = _login(hub_app, "admin")
    item = conn.q1("select item_code from bas_item order by id limit 1")["item_code"]
    doc = "세척 공정 표준 (예시)\n세척수 온도는 45도 이상 유지하고 10분마다 기록한다.".encode()
    r = c.post("/hub/files", data={"title": "세척 공정 표준 (예시)", "category": "작업표준서", "link_kind": "item", "link_ref": item, "tags": "세척, 표준"},
               files={"file": ("wash.txt", doc, "text/plain")})
    assert r.status_code == 200 and r.json()["text_chars"] > 10
    fid, no = r.json()["id"], r.json()["file_no"]
    hits = c.get("/hub/files", params={"q": "10분마다"}).json()["rows"]
    assert [h["file_no"] for h in hits][:1] == [no] and hits[0]["link_ref"] == item and hits[0]["tags"] == ["세척", "표준"]
    d = c.get(f"/hub/files/{fid}/download")
    assert d.content == doc and d.headers["content-disposition"].startswith("attachment") and d.headers["x-content-type-options"] == "nosniff"
    assert c.get(f"/hub/files/{fid}/download?inline=1").headers["content-disposition"].startswith("attachment")   # 텍스트는 늘 내려받기
    log = conn.q1("select count(*)::int as n from sys_access_log where kind = 'change' and screen_id = 'HUB' and target = %s", (no,))
    assert log["n"] == 1
    other = _login(hub_app, "prod")
    assert other.post(f"/hub/files/{fid}/delete").status_code == 403                           # 올린 사람 · 관리자만
    assert c.post(f"/hub/files/{fid}/delete").json()["ok"]
    assert no not in [h["file_no"] for h in c.get("/hub/files", params={"q": "10분마다"}).json()["rows"]]


@pytest.mark.parametrize("name,data,field", [
    ("run.exe", b"MZ", "file"), ("empty.txt", b"", "file"), ("a.txt", b"hi", "category"),
])
def test_files_rejects_bad_input(hub_app, name, data, field):
    c = _login(hub_app, "admin")
    form = {"category": "" if field == "category" else "기타"}
    r = c.post("/hub/files", data=form, files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 422 and field in r.json()["errors"]


def test_files_link_must_exist_and_size_limit(hub_app, monkeypatch):
    c = _login(hub_app, "admin")
    r = c.post("/hub/files", data={"category": "기타", "link_kind": "lot", "link_ref": "NO-SUCH-LOT"}, files={"file": ("a.txt", b"hi", "text/plain")})
    assert r.status_code == 422 and "link_ref" in r.json()["errors"]
    monkeypatch.setenv("MES_HUB_MAX_MB", "0.001")
    r = c.post("/hub/files", data={"category": "기타"}, files={"file": ("big.txt", b"x" * 5000, "text/plain")})
    assert r.status_code == 422 and "너무 큽니다" in r.json()["message"]


def test_office_and_text_extraction():
    from meshub import files
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>점검 항목 윤활</w:t></w:r></w:p></w:body></w:document>")
    assert "점검 항목 윤활" in files.extract_text("docx", buf.getvalue())
    assert files.extract_text("txt", "가나다".encode("cp949")) == "가나다"
    assert files.extract_text("png", b"\x89PNG") == "" and files.extract_text("pdf", b"not a pdf") == ""


def test_uploaded_text_reaches_agent_rag(hub_app):
    from mesagent import rag
    c = _login(hub_app, "admin")
    r = c.post("/hub/files", data={"title": "포장 기준 (예시)", "category": "작업표준서"},
               files={"file": ("pack.md", "# 포장 기준\n박스당 적재 단수는 다섯 단을 넘기지 않는다.".encode(), "text/markdown")})
    no = r.json()["file_no"]
    assert any(d["source"] == f"hub:{no}" for d in rag.search("박스 적재 단수 포장 기준", 5))
    c.post(f"/hub/files/{r.json()['id']}/delete")
    assert not any(d["source"] == f"hub:{no}" for d in rag.search("박스 적재 단수 포장 기준", 5))


def test_realtime_rollup_is_idempotent(hub_app):
    c = _login(hub_app, "admin")
    a = c.post("/hub/realtime/rollup", data={"hours": "720"}).json()["rows"]
    b = c.post("/hub/realtime/rollup", data={"hours": "720"}).json()["rows"]
    series = conn.q1("""select count(*)::int as n from (select distinct equipment_id, tag, date_trunc('hour', ts) from eqp_collect
                         where value_num is not null and ts >= date_trunc('hour', now() - interval '720 hours')) x""")["n"]
    assert a == b == series
    live = c.get("/hub/realtime/live").json()
    assert live["values"]["total"] == conn.q1("select count(*)::int as n from eqp_collect")["n"]
    csv_ = c.get("/hub/realtime.csv", params={"hours": 24 * 31})
    assert csv_.status_code == 200 and csv_.text.lstrip("﻿").startswith("설비코드,")


def test_core_without_hub_has_no_hub_routes():
    import os
    from mescore.app import settings
    from mescore.app.main import create_app
    old = os.environ.get("MES_ADDONS")
    os.environ["MES_ADDONS"] = "agent"
    settings.reset_cache()
    try:
        app = create_app()
        assert not any(getattr(r, "path", "").startswith("/hub") for r in app.routes)
    finally:
        if old is None:
            os.environ.pop("MES_ADDONS", None)
        else:
            os.environ["MES_ADDONS"] = old
        settings.reset_cache()
