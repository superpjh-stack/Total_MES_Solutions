"""clr — F-X-CLR-01~05 (개발2). 권한: 품질 · 현장 입력, 관리자 · 생산 조회. Job 참조 필수 · 배합비 합 100 (D-209)."""

from __future__ import annotations

import pytest

from mescore.db import conn

from _helpers import HTML, P, client, new_job

CL = P["X-CLR-01"]


@pytest.mark.fn("F-X-CLR-01")
def test_record_create_requires_job():
    c = client("field")
    job = new_job()
    r = c.post(CL, data={"work_order_no": job["work_order_no"], "color_name": "적 (예시)", "color_l": "50", "color_a": "60", "color_b": "40", "ink_code": "EX-INK-01"})
    assert r.status_code == 200 and r.json()["seq_no"] == 1
    r2 = c.post(CL, data={"work_order_no": job["work_order_no"], "color_name": "적 (예시)"})
    assert r2.status_code == 200 and r2.json()["seq_no"] == 2                                                            # 차수 비우면 마지막 + 1
    assert c.post(CL, data={"work_order_no": job["work_order_no"], "color_name": "적 (예시)", "seq_no": "2"}).status_code == 422   # 유니크
    assert c.post(CL, data={"work_order_no": "NOPE", "color_name": "x"}).status_code == 422                                # 없는 Job
    assert c.post(CL, data={"work_order_no": job["work_order_no"], "color_name": "x", "ink_code": "NOPE"}).status_code == 422
    canceled = new_job()
    assert client("prod").post(f"{P['JOB-01']}/{canceled['id']}/cancel").status_code == 200
    assert c.post(CL, data={"work_order_no": canceled["work_order_no"], "color_name": "x"}).status_code == 422             # 취소된 Job
    assert client("prod").post(CL, data={"work_order_no": job["work_order_no"], "color_name": "x"}).status_code == 403


@pytest.mark.fn("F-X-CLR-02")
def test_mix_sum_must_be_100():
    c = client("qc")
    job = new_job()
    rid = c.post(CL, data={"work_order_no": job["work_order_no"], "color_name": "청 (예시)"}).json()["id"]
    ok = c.post(f"{CL}/{rid}/mix", data={"component_name": ["a", "b"], "ratio_pct": ["60", "40"]})
    assert ok.status_code == 200 and ok.json()["total"] == 100
    bad = c.post(f"{CL}/{rid}/mix", data={"component_name": ["a", "b"], "ratio_pct": ["60", "30"]})
    assert bad.status_code == 422 and "100" in bad.json()["message"] and "→" in bad.json()["message"]
    assert [float(x["ratio_pct"]) for x in conn.q("select ratio_pct from x_printfilm_color_record_mix where color_record_id = %s order by seq_no", (rid,))] == [60, 40]   # 실패는 되돌림
    # 반올림 — 33.3334 + 33.3333 + 33.3333 → 33.333 ×3 = 99.999 ≠ 100 → 422 · 33.334 + 33.333 + 33.333 = 100
    assert c.post(f"{CL}/{rid}/mix", data={"component_name": ["a", "b", "c"], "ratio_pct": ["33.3334", "33.3333", "33.3333"]}).status_code == 422
    r3 = c.post(f"{CL}/{rid}/mix", data={"component_name": ["a", "b", "c"], "ratio_pct": ["33.334", "33.333", "33.333"]})
    assert r3.status_code == 200 and [x["ratio_pct"] for x in r3.json()["rows"]] == [33.334, 33.333, 33.333]
    assert c.post(f"{CL}/{rid}/mix", data={"component_name": [], "ratio_pct": []}).status_code == 422
    assert c.post(f"{CL}/999999/mix", data={"component_name": ["a"], "ratio_pct": ["100"]}).status_code == 404


@pytest.mark.fn("F-X-CLR-03")
def test_record_update_keeps_job():
    c = client("field")
    job = new_job()
    rid = c.post(CL, data={"work_order_no": job["work_order_no"], "color_name": "녹 (예시)", "ink_code": "EX-INK-01"}).json()["id"]
    assert c.post(f"{CL}/{rid}", data={"color_name": "녹 B (예시)", "color_l": "10", "ink_code": "EX-INK-02", "note": "(예시)"}).status_code == 200
    row = conn.q1("select r.color_name, r.color_l, k.ink_code, r.note from x_printfilm_color_record r left join x_printfilm_ink_formula k on k.id = r.ink_formula_id where r.id = %s", (rid,))
    assert row == {"color_name": "녹 B (예시)", "color_l": 10, "ink_code": "EX-INK-02", "note": "(예시)"}
    assert c.post(f"{CL}/{rid}", data={"work_order_no": "OTHER"}).status_code == 422
    assert c.post(f"{CL}/999999", data={"color_name": "x"}).status_code == 404


@pytest.mark.fn("F-X-CLR-04")
def test_record_delete_cascades_mix():
    c = client("field")
    job = new_job()
    rid = c.post(CL, data={"work_order_no": job["work_order_no"], "color_name": "황 (예시)"}).json()["id"]
    assert c.post(f"{CL}/{rid}/mix", data={"component_name": ["a"], "ratio_pct": ["100"]}).status_code == 200
    assert c.post(f"{CL}/{rid}/delete").status_code == 200
    assert conn.q1("select count(*) as n from x_printfilm_color_record_mix where color_record_id = %s", (rid,))["n"] == 0
    assert c.post(f"{CL}/{rid}/delete").status_code == 404


@pytest.mark.fn("F-X-CLR-05")
def test_records_screen_scan():
    c = client("field")
    job = new_job()
    c.post(CL, data={"work_order_no": job["work_order_no"], "color_name": "적 (예시)"})
    body = c.get(CL, params={"no": job["work_order_no"]}).json()
    assert body["job"]["work_order_no"] == job["work_order_no"] and len(body["rows"]) == 1 and body["rows"][0]["mix_rows"] == []
    miss = c.get(CL, params={"no": "NOPE-X"})
    assert miss.status_code == 422 and miss.json()["code"] == "validation_error" and miss.json()["screen_id"] == "X-CLR-01"
    html = c.get(CL, params={"no": "NOPE-X"}, headers=HTML)
    assert html.status_code == 422 and html.text.count("data-scan") == 1 and "scan-result" in html.text
    assert c.get(CL).status_code == 200 and client("admin").get(CL).status_code == 200
