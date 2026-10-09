"""G-C24 측정값 — `bas_process_param` 행 3개(필수 1 · 범위 1 · collect 1)만으로 코어 수정 없이: POP 종료 폼 칸 3 · 필수 누락 422 · 범위 이탈 저장 + deviated ·
collect 값은 종료 때 코어가 `collect.aggregate` 로 채운 뒤 `on_result_closed` · `stats.measure_series`(개발3) 집계 (개발2).

선언은 이 테스트가 만든 공정(`PRC-T-MEAS`)에 넣는다 — 시드(PRC-EX-01)를 건드리지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mescore.app import collect, measure, nav
from mescore.db import conn

from _dev2_helpers import HTML, client, equipment_id, item_id, uniq

POP02 = nav.path_of("POP-02")
KEYS = ("t_req", "t_range", "t_col")


@pytest.fixture(scope="module")
def declared() -> dict:
    """공정 1 + 선언 3 + 수집 설비 1 (멱등)."""
    proc = conn.q1("select id from bas_process where process_code = 'PRC-T-MEAS'") or conn.q1(
        "insert into bas_process (process_code, process_name, seq, created_by) values ('PRC-T-MEAS', '측정값 시험 공정 (예시)', 90, 'test') returning id")
    eq = conn.q1("select id from bas_equipment where equip_code = 'EQ-T-MEAS'") or conn.q1(
        "insert into bas_equipment (equip_code, equip_name, process_id, collect_yn, created_by) values ('EQ-T-MEAS', '수집 설비 (예시)', %s, 'Y', 'test') returning id", (proc["id"],))
    rows = [("t_req", "필수 항목 (예시)", "Y", None, None, "manual", None, "last", 1),
            ("t_range", "범위 항목 (예시)", "N", 10, 20, "manual", None, "last", 2),
            ("t_col", "수집 항목 (예시)", "N", 0, 5, "collect", "pressure", "avg", 3)]
    for key, label, req, lo, hi, src, tag, agg, seq in rows:
        conn.x("""insert into bas_process_param (process_id, param_key, label, unit, value_type, min_value, max_value, required_yn, source, collect_tag, agg, seq, created_by)
                  values (%s, %s, %s, 'u', 'number', %s, %s, %s, %s, %s, %s, %s, 'test')
                  on conflict (process_id, param_key) do update set min_value = excluded.min_value, max_value = excluded.max_value, required_yn = excluded.required_yn,
                      source = excluded.source, collect_tag = excluded.collect_tag, agg = excluded.agg, use_yn = 'Y'""",
               (proc["id"], key, label, lo, hi, req, src, tag, agg, seq))
    conn.x("delete from eqp_collect where equipment_id = %s", (eq["id"],))                       # 지난 실행의 수집값은 지운다 (구간이 겹친다)
    conn.x("delete from ifc_collect_raw where equip_code = 'EQ-T-MEAS'")
    return {"process_id": proc["id"], "equipment_id": eq["id"]}


def _start(declared) -> dict:
    wo = conn.q1("""insert into job_work_order (work_order_no, item_id, process_id, equipment_id, plan_qty, unit, plan_date, status, created_by)
                    values (%s, %s, %s, %s, 10, 'EA', current_date, '대기', 'test') returning *""",
                 (uniq("T-W"), item_id("PRD-EX-01"), declared["process_id"], declared["equipment_id"]))
    c = client("prod")
    s = c.post(f"{POP02}/start", data={"work_order_id": wo["id"]}).json()
    assert s["ok"]
    return {"c": c, "id": s["id"], "wo": wo}


@pytest.mark.fn("F-POP-03")
def test_declaration_makes_three_fields_in_end_form(declared):
    s = _start(declared)
    params = measure.params_for(declared["process_id"])
    assert [p["param_key"] for p in params] == list(KEYS)
    j = s["c"].get(POP02, params={"id": s["id"]}).json()
    assert [p["field"] for p in j["params"]] == ["m_t_req", "m_t_range", "m_t_col"]
    html = s["c"].get(POP02, params={"id": s["id"]}, headers=HTML).text
    assert 'name="m_t_req"' in html and 'name="m_t_range"' in html and 'name="m_t_col"' not in html      # collect 칸은 읽기 전용
    assert "수집값 자동" in html and "미수집" in html and "필수" in html and "10 ~ 20" in html


@pytest.mark.fn("F-POP-03")
def test_required_missing_is_422_and_deviation_is_saved(declared):
    s = _start(declared)
    r = s["c"].post(f"{POP02}/{s['id']}/end", data={"good_qty": 5, "m_t_range": "15"})
    assert r.status_code == 422 and r.json()["message"] == "필수 측정값이 비었습니다" and r.json()["fields"][0]["name"] == "m_t_req"
    assert conn.q1("select ended_at from pop_work_result where id = %s", (s["id"],))["ended_at"] is None       # 아무것도 저장되지 않았다
    assert s["c"].post(f"{POP02}/{s['id']}/end", data={"good_qty": 5, "m_t_req": "abc"}).status_code == 422   # 숫자 아님
    r = s["c"].post(f"{POP02}/{s['id']}/end", data={"good_qty": 5, "m_t_req": "1", "m_t_range": "25"})           # 범위 이탈 — 422 아님
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["measures"]["t_range"]["deviated"] is True and body["measures"]["t_req"]["deviated"] is False and body["deviated"] == ["t_range"]
    rows = measure.values_of(s["id"])
    assert set(rows) == set(KEYS)
    assert rows["t_range"]["value_num"] == 25 and rows["t_range"]["deviated"] is True and rows["t_range"]["source"] == "manual"
    assert rows["t_col"]["value_num"] is None and rows["t_col"]["source"] == "collect" and rows["t_col"]["deviated"] is False   # 수신 0 → 미수집, 422 아님
    html = s["c"].get(POP02, params={"id": s["id"]}, headers=HTML).text
    assert "이탈" in html and 'class="deviated"' in html


@pytest.mark.fn("F-POP-03")
def test_collect_source_is_filled_from_equipment_series(declared):
    s = _start(declared)
    conn.x("update pop_work_result set started_at = started_at - interval '10 minutes' where id = %s", (s["id"],))   # 구간을 넓혀 수신 시각을 안에 둔다
    started = conn.q1("select started_at from pop_work_result where id = %s", (s["id"],))["started_at"]
    with conn.tx() as cur:
        for i, v in enumerate((2.0, 4.0, 9.0)):          # 구간 안 2 · 4 → avg 3 / 9 는 구간 밖(시작 전)
            ts = started + timedelta(minutes=1 + i) if v != 9.0 else started - timedelta(minutes=5)
            collect.receive(cur, collect.CollectMessage(equip_code="EQ-T-MEAS", ts=ts, tags={"pressure": v, "run_state": 1}))
    r = s["c"].post(f"{POP02}/{s['id']}/end", data={"good_qty": 5, "m_t_req": "1"})
    assert r.status_code == 200, r.text
    row = measure.values_of(s["id"])["t_col"]
    assert row["value_num"] == 3 and row["source"] == "collect" and row["deviated"] is False
    # 범위(0~5) 이탈이면 deviated — 다른 실적에서 값 7
    s2 = _start(declared)
    conn.x("delete from eqp_collect where equipment_id = %s", (declared["equipment_id"],))        # 앞 실적의 수집값과 구간이 겹치지 않게
    conn.x("update pop_work_result set started_at = started_at - interval '10 minutes' where id = %s", (s2["id"],))
    started2 = conn.q1("select started_at from pop_work_result where id = %s", (s2["id"],))["started_at"]
    with conn.tx() as cur:
        collect.receive(cur, collect.CollectMessage(equip_code="EQ-T-MEAS", ts=started2 + timedelta(minutes=1), tags={"pressure": 7}))
    assert s2["c"].post(f"{POP02}/{s2['id']}/end", data={"good_qty": 5, "m_t_req": "1"}).status_code == 200
    row2 = measure.values_of(s2["id"])["t_col"]
    assert row2["value_num"] == 7 and row2["deviated"] is True
    # stats.measure_series (개발3) 집계 — 모듈이 있으면 같은 값
    try:
        from mescore.app import stats
    except ModuleNotFoundError:
        pytest.skip("app/stats.py 없음 (개발3)")
    today = datetime.now().date()
    series = stats.measure_series("t_col", today, today, by="day", agg="avg")
    assert series and any(abs(float(x.get("value") or 0) - 5) < 1e-6 or x.get("n", 0) >= 2 for x in series)


def test_bool_select_text_fields_parse():
    params = [dict(param_key="b", label="b", value_type="bool", required_yn="Y", source="manual", choices=None),
              dict(param_key="s", label="s", value_type="select", required_yn="N", source="manual", choices=["A", "B"]),
              dict(param_key="x", label="x", value_type="text", required_yn="N", source="manual", choices=None)]
    params = [measure._decorate(p, "m_") for p in params]
    v, errs = measure.parse_form(params, {"m_b": "1", "m_s": "B", "m_x": " ok "})
    assert not errs and v["b"]["value_num"] == 1 and v["s"]["value_text"] == "B" and v["x"]["value_text"] == "ok"
    v, errs = measure.parse_form(params, {"m_s": "C"})
    assert [e["name"] for e in errs] == ["m_b", "m_s"]
    assert measure.range_text(0.5, None) == "0.5 이상" and measure.range_text(None, 12) == "12 이하" and measure.range_text(60, 80) == "60 ~ 80"
    assert measure.deviated({"min_value": 10, "max_value": None}, 9) and not measure.deviated({"min_value": 10, "max_value": None}, 10)


@pytest.mark.fn("F-POP-03")
def test_turned_off_declaration_keeps_past_values_visible():
    """DEF-QA2-004 — 선언을 use_yn=N 으로 꺼도 지난 실적 POP-02 화면 · 조회에 기록 값이 보인다. 새 실적에는 입력 칸이 생기지 않는다."""
    proc = conn.q1("select id from bas_process where process_code = 'PRC-T-MEAS2'") or conn.q1(
        "insert into bas_process (process_code, process_name, seq, created_by) values ('PRC-T-MEAS2', '측정값 끔 시험 공정 (예시)', 91, 'test') returning id")
    for key, label, seq in (("d_keep", "남는 항목 (예시)", 1), ("d_off", "끌 항목 (예시)", 2)):
        conn.x("""insert into bas_process_param (process_id, param_key, label, unit, value_type, required_yn, source, seq, created_by)
                  values (%s, %s, %s, 'mm', 'number', 'N', 'manual', %s, 'test')
                  on conflict (process_id, param_key) do update set label = excluded.label, use_yn = 'Y'""", (proc["id"], key, label, seq))
    decl = {"process_id": proc["id"], "equipment_id": None}
    s = _start(decl)
    assert s["c"].post(f"{POP02}/{s['id']}/end", data={"good_qty": 1, "m_d_keep": "1.5", "m_d_off": "7.25"}).status_code == 200
    conn.x("update bas_process_param set use_yn = 'N' where process_id = %s and param_key = 'd_off'", (proc["id"],))
    j = s["c"].get(POP02, params={"id": s["id"]}).json()
    by_key = {p["param_key"]: p for p in j["params"]}
    assert set(by_key) == {"d_keep", "d_off"} and by_key["d_off"]["recorded_only"] is True and float(j["values"]["d_off"]["value_num"]) == 7.25
    html = s["c"].get(POP02, params={"id": s["id"]}, headers=HTML).text
    assert "끌 항목 (예시)" in html and "7.25" in html
    s2 = _start(decl)                                                                          # 새 실적 — 꺼진 칸은 입력 칸 없음
    assert [p["param_key"] for p in s2["c"].get(POP02, params={"id": s2["id"]}).json()["params"]] == ["d_keep"]
    html2 = s2["c"].get(POP02, params={"id": s2["id"]}, headers=HTML).text
    assert 'name="m_d_keep"' in html2 and 'name="m_d_off"' not in html2
    # 선언 행을 지워도 기록 키 그대로 보인다
    conn.x("update pop_measure set param_id = null where work_result_id = %s and param_key = 'd_off'", (s["id"],))
    conn.x("delete from bas_process_param where process_id = %s and param_key = 'd_off'", (proc["id"],))
    p_off = next(p for p in measure.params_with_recorded(proc["id"], measure.values_of(s["id"])) if p["param_key"] == "d_off")
    assert p_off["recorded_only"] and p_off["label"] == "d_off"
