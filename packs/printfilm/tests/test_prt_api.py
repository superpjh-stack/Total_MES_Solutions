"""prt — F-X-PRT-01~12 를 TestClient(JSON) 로 한 기능씩 (개발2). 권한: 관리자 · 생산 입력, 품질 · 현장 조회."""

from __future__ import annotations

import pytest

from mescore.db import conn

from _helpers import HTML, P, client, item_id, new_job, uniq

PL, AN, IK = P["X-PRT-01"], P["X-PRT-02"], P["X-PRT-03"]


@pytest.mark.fn("F-X-PRT-01")
def test_plate_create():
    c = client("admin")
    code = uniq("T-PL")
    r = c.post(PL, data={"plate_code": code, "plate_name": "판 (예시)", "item_id": item_id("EX-FG-01")})
    assert r.status_code == 200 and r.json()["plate_code"] == code
    assert c.post(PL, data={"plate_code": code, "plate_name": "x"}).status_code == 422                                   # 중복
    assert c.post(PL, data={"plate_code": uniq("T-PL"), "plate_name": "x", "item_id": item_id("EX-RM-01")}).status_code == 422   # 제품 아님
    assert c.post(PL, data={"plate_code": "", "plate_name": "x"}).status_code == 422                                      # 필수
    assert client("qc").post(PL, data={"plate_code": uniq("T-PL"), "plate_name": "x"}).status_code == 403
    assert client("prod").post(PL, data={"plate_code": uniq("T-PL"), "plate_name": "x"}).status_code == 200


@pytest.mark.fn("F-X-PRT-02")
def test_plate_update():
    c = client("admin")
    pid = c.post(PL, data={"plate_code": uniq("T-PL"), "plate_name": "판 (예시)"}).json()["id"]
    assert c.post(f"{PL}/{pid}", data={"plate_name": "판 B (예시)", "color_count": "4", "use_yn": "N"}).status_code == 200
    assert conn.q1("select plate_name, color_count, use_yn from x_printfilm_plate where id = %s", (pid,)) == {"plate_name": "판 B (예시)", "color_count": 4, "use_yn": "N"}
    assert c.post(f"{PL}/{pid}", data={"plate_code": "OTHER"}).status_code == 422                                          # 코드 변경 불가
    assert c.post(f"{PL}/999999", data={"plate_name": "x"}).status_code == 404
    assert client("field").post(f"{PL}/{pid}", data={"plate_name": "x"}).status_code == 403


@pytest.mark.fn("F-X-PRT-03")
def test_plate_delete_blocked_by_job():
    c = client("admin")
    code = uniq("T-PL")
    pid = c.post(PL, data={"plate_code": code, "plate_name": "판 (예시)"}).json()["id"]
    new_job(plate=code)
    r = c.post(f"{PL}/{pid}/delete")
    assert r.status_code == 422 and "사용 중" in r.json()["message"]
    pid2 = c.post(PL, data={"plate_code": uniq("T-PL"), "plate_name": "판 (예시)"}).json()["id"]
    assert c.post(f"{PL}/{pid2}/delete").status_code == 200 and conn.q1("select 1 from x_printfilm_plate where id = %s", (pid2,)) is None
    assert c.post(f"{PL}/{pid2}/delete").status_code == 404


@pytest.mark.fn("F-X-PRT-04")
def test_plates_screen():
    c = client("admin")
    body = c.get(PL, params={"code": "EX-PL"}).json()
    assert body["template"] == "prt/plates.html" and {r["plate_code"] for r in body["rows"]} >= {"EX-PL-01", "EX-PL-02"}
    assert c.get(PL, params={"code": "NOPE-X"}).json()["rows"] == []
    html = c.get(PL, headers=HTML).text
    assert "판사양" in html and "미수집" not in html and "EX-PL-01" in html
    assert c.get(PL, params={"use_yn": "Z"}).status_code == 422
    assert client("field").get(PL).status_code == 200                                                                      # 조회 이상


@pytest.mark.fn("F-X-PRT-05")
def test_anilox_create():
    c = client("prod")
    code = uniq("T-AN")
    assert c.post(AN, data={"anilox_code": code, "anilox_name": "아니록스 (예시)", "line_count": "400", "cell_volume": "3.5"}).status_code == 200
    assert conn.q1("select line_count, cell_volume from x_printfilm_anilox where anilox_code = %s", (code,)) == {"line_count": 400, "cell_volume": 3.5}
    assert c.post(AN, data={"anilox_code": code, "anilox_name": "x"}).status_code == 422
    assert c.post(AN, data={"anilox_code": uniq("T-AN"), "anilox_name": "x", "line_count": "-1"}).status_code == 422
    assert client("field").post(AN, data={"anilox_code": uniq("T-AN"), "anilox_name": "x"}).status_code == 403


@pytest.mark.fn("F-X-PRT-06")
def test_anilox_update():
    c = client("admin")
    aid = c.post(AN, data={"anilox_code": uniq("T-AN"), "anilox_name": "a"}).json()["id"]
    assert c.post(f"{AN}/{aid}", data={"anilox_name": "b", "use_yn": "N", "note": "(예시)"}).status_code == 200
    assert conn.q1("select anilox_name, use_yn, note from x_printfilm_anilox where id = %s", (aid,)) == {"anilox_name": "b", "use_yn": "N", "note": "(예시)"}
    assert c.post(f"{AN}/{aid}", data={"anilox_code": "X"}).status_code == 422
    assert c.post(f"{AN}/999999", data={"anilox_name": "x"}).status_code == 404


@pytest.mark.fn("F-X-PRT-07")
def test_anilox_delete():
    c = client("admin")
    code = uniq("T-AN")
    aid = c.post(AN, data={"anilox_code": code, "anilox_name": "a"}).json()["id"]
    new_job(anilox=code)
    assert c.post(f"{AN}/{aid}/delete").status_code == 422
    aid2 = c.post(AN, data={"anilox_code": uniq("T-AN"), "anilox_name": "a"}).json()["id"]
    assert c.post(f"{AN}/{aid2}/delete").status_code == 200 and conn.q1("select 1 from x_printfilm_anilox where id = %s", (aid2,)) is None


@pytest.mark.fn("F-X-PRT-08")
def test_anilox_screen():
    body = client("qc").get(AN, params={"code": "EX-AN"}).json()
    assert body["template"] == "prt/anilox.html" and len(body["rows"]) >= 2
    assert client("admin").get(AN, params={"name": "없는이름-X"}).json()["rows"] == []


@pytest.mark.fn("F-X-PRT-09")
def test_ink_create_with_components():
    c = client("admin")
    code = uniq("T-INK")
    r = c.post(IK, data={"ink_code": code, "ink_name": "잉크 (예시)", "color_name": "색 (예시)", "target_l": "50", "target_a": "1.5", "target_b": "-2",
                         "component_name": ["성분 1", "성분 2"], "ratio_pct": ["33.3334", "66.666"]})
    assert r.status_code == 200 and r.json()["components"] == 2
    rows = conn.q("select seq_no, component_name, ratio_pct from x_printfilm_ink_formula_component c join x_printfilm_ink_formula k on k.id = c.ink_formula_id where k.ink_code = %s order by seq_no", (code,))
    assert [float(x["ratio_pct"]) for x in rows] == [33.333, 66.666]                                                       # 소수 셋째 자리 · 합 100 강제 안 함
    assert c.post(IK, data={"ink_code": code, "ink_name": "x"}).status_code == 422
    assert c.post(IK, data={"ink_code": uniq("T-INK"), "ink_name": "x", "component_name": ["a"], "ratio_pct": ["101"]}).status_code == 422
    assert c.post(IK, data={"ink_code": uniq("T-INK"), "ink_name": "x", "component_name": ["a"], "ratio_pct": ["0"]}).status_code == 422
    assert c.post(IK, data={"ink_code": uniq("T-INK"), "ink_name": "x"}).status_code == 200                                # 조성 행 0 허용


@pytest.mark.fn("F-X-PRT-10")
def test_ink_update_replaces_components():
    c = client("admin")
    iid = c.post(IK, data={"ink_code": uniq("T-INK"), "ink_name": "a", "component_name": ["a", "b"], "ratio_pct": ["50", "50"]}).json()["id"]
    assert c.post(f"{IK}/{iid}", data={"ink_name": "b", "component_name": ["c"], "ratio_pct": ["100"]}).status_code == 200
    rows = conn.q("select component_name from x_printfilm_ink_formula_component where ink_formula_id = %s", (iid,))
    assert [x["component_name"] for x in rows] == ["c"]
    assert c.post(f"{IK}/{iid}", data={"color_name": "z"}).status_code == 200 and len(conn.q("select 1 from x_printfilm_ink_formula_component where ink_formula_id = %s", (iid,))) == 1
    assert c.post(f"{IK}/{iid}", data={"ink_code": "X"}).status_code == 422


@pytest.mark.fn("F-X-PRT-11")
def test_ink_delete_blocked_by_job_and_record():
    c = client("admin")
    code = uniq("T-INK")
    iid = c.post(IK, data={"ink_code": code, "ink_name": "a", "component_name": ["a"], "ratio_pct": ["100"]}).json()["id"]
    job = new_job(ink=code)
    assert c.post(f"{IK}/{iid}/delete").status_code == 422
    code2 = uniq("T-INK")
    iid2 = c.post(IK, data={"ink_code": code2, "ink_name": "a"}).json()["id"]
    assert client("field").post(P["X-CLR-01"], data={"work_order_no": job["work_order_no"], "color_name": "색 (예시)", "ink_code": code2}).status_code == 200
    assert c.post(f"{IK}/{iid2}/delete").status_code == 422                                                              # 조색 기록 참조
    iid3 = c.post(IK, data={"ink_code": uniq("T-INK"), "ink_name": "a", "component_name": ["a"], "ratio_pct": ["100"]}).json()["id"]
    assert c.post(f"{IK}/{iid3}/delete").status_code == 200
    assert conn.q1("select count(*) as n from x_printfilm_ink_formula_component where ink_formula_id = %s", (iid3,))["n"] == 0   # cascade


@pytest.mark.fn("F-X-PRT-12")
def test_inks_screen_opens_components():
    c = client("admin")
    ink = conn.q1("select id from x_printfilm_ink_formula where ink_code = 'EX-INK-01'")
    body = c.get(IK, params={"id": ink["id"]}).json()
    assert body["opened"]["ink_code"] == "EX-INK-01" and [x["ratio_pct"] for x in body["components"]] == [60, 40]
    assert c.get(IK, params={"color": "없는색-X"}).json()["rows"] == []
    assert c.get(IK, params={"id": "999999"}).status_code == 404
