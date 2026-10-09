"""집계 — 생산 · 품질 · 납기 · 설비 · 측정값 · 현황판 · 지표 SQL 의 **유일한 자리** (`interfaces.md` §7 · G-C10).

담당 **개발3**. 집계 화면(KPI-02) · 현황판(KPI-01) · 지표(KPI-03) · 대시보드(CMN-04)가 전부 이 파일의 함수만 부른다.
**어떤 테이블에도 쓰지 않는다** — `snapshot()` 하나만 예외이고 그것은 배치(`make kpi-snapshot` · F-SYS)만 부른다. 집계 결과를 담는 캐시 테이블은 없다.
행이 없으면 빈 리스트 · 값이 없으면 `None` 이다(화면이 `미수집` 을 그린다). 분모가 0 인 비율은 `None`(0 으로 지어내지 않는다).
비율은 전부 **퍼센트(0~100) float** 이고 반올림하지 않는다 — 화면이 표시할 때만 자른다. QA2 가 같은 문장으로 SQL 을 따로 짜서 대조한다(G-C10) —
산식을 바꾸려면 이 문서(docstring)와 `progress-dev3.md` §1 부터 고친다.

산식 (QA2 대조용 — 날짜는 `timestamptz::date`, 기간은 양 끝 포함)
  production(frm, to, by)      계획 = `job_work_order`(status<>취소) 중 `plan_date` 가 기간 안 → Σ plan_qty · 지시 수
                               실적 = `pop_work_result` 중 `ended_at` 이 있고 그 날짜가 기간 안 → 실적 수 · Σ good_qty · Σ defect_qty
                               by: day(plan_date / ended_at::date) · item(지시 품목) · process(지시 공정 / 실적 공정) · equipment(지시 설비 / 실적 설비)
                               good_rate = good / (good + defect) × 100 · achieve_rate = good / plan × 100 (분모 0 → None). 두 쪽을 키로 full outer join
  quality(frm, to, by)         `qua_inspection` 중 `judgement` 가 있고 `judged_at` 날짜가 기간 안. pass = 합격 · fail = 불합격 · cond = 조건부
                               pass_rate = 합격 / 전체 × 100 — **조건부는 합격에 세지 않는다** (D-302). by: day(judged_at::date) · item(lot.item_id)
                               by=defect: 그 검사들의 `qua_defect` 를 불량코드별로 — defect_count(행) · defect_qty(Σ qty) · inspection_count(distinct 검사)
  delivery(frm, to, by, today) `ord_order`(status<>취소) 중 `due_date` 가 기간 안. 그 수주의 **승인된** `shp_shipment` 가운데 가장 이른 `ship_date` 로 판정 —
                               on_time: 그 날짜 ≤ 납기 · late: 그 날짜 > 납기, 또는 승인 출하 없이 납기 < today · pending: 승인 출하 없고 납기 ≥ today
                               shipped = 승인 출하가 있는 수주 수 · on_time_rate = on_time / (on_time + late) × 100. by: day(due_date) · partner
  equipment(frm, to)           `bas_equipment`(use_yn=Y) 마다 `eqp_run_log` 구간을 [frm 00:00, to+1일 00:00) 으로 잘라 상태별 초를 더한다(ended_at NULL = now()).
                               run_rate = 가동 초 / (가동+정지+점검+고장 초) × 100 (기록 0 → None) · stop_count = 기간에 시작한 정지 구간 수
                               fault_count = `eqp_fault.occurred_at` 이 기간 안 · mttr_hours = 그 고장 중 복구된 것의 평균 (fixed_at − occurred_at) 시간 · fixed_count = 복구된 고장 수
                               totals 의 mttr_hours = 모든 설비의 복구 고장을 한데 모은 평균(Σ 복구 시간 / Σ fixed_count — 설비별 MTTR 의 평균이 아니다)
                               current_state = ended_at 이 NULL 인 가장 최근 구간의 state (없으면 None → 화면 `미수집`)
  measure_series(key, …)       `pop_measure`(value_num 이 있는 행) 중 `measured_at` 날짜가 기간 안. by: day · work_order · equipment(실적의 설비)
                               agg: avg · min · max · sum · count · last(measured_at 이 가장 늦은 값). n = 행 수 · deviated_count = deviated 행 수
  board(today)                 위 함수를 **오늘 하루**(frm = to = today) 로 부른 값 + 오늘의 진행 지시 · 측정값 이탈. `kpi_snapshot(today)` 가 있으면
                               지표 값만 그 스냅샷에서 읽고 source 를 `스냅샷 HH:MM` 으로 알린다 (나머지는 실시간)
  indicators(frm, to)          `kpi_indicator` 정의 + 현재값. calc_kind `core:<키>` 는 core_metrics 에서, `pack:<키>` 는 훅 `kpi_extra(frm, to)` 결과에서.
                               status: value 또는 target 이 None → None · value ≥ target → good · value ≥ target × 0.95 → warn · 그 밖 critical (D-602)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..db import conn
from . import packs

#: 코어 집계 키 — `kpi_indicator.calc_kind = core:<키>` 로 쓴다 (KPI-03 · 현황판 지표). 팩 키는 `pack:<kpi_extra 의 key>`
CORE_METRIC_KEYS: tuple[str, ...] = ("production.achieve_rate", "production.good_rate", "quality.pass_rate",
                                     "delivery.on_time_rate", "equipment.run_rate")
PRODUCTION_BY = ("day", "item", "process", "equipment")
QUALITY_BY = ("day", "item", "defect")
DELIVERY_BY = ("day", "partner")
MEASURE_BY = ("day", "work_order", "equipment")
MEASURE_AGG = ("avg", "min", "max", "sum", "count", "last")
WARN_RATIO = 0.95                    # D-602: 목표의 95 % 이상이면 warn
PASS, FAIL, COND = "합격", "불합격", "조건부"
EQUIP_STATES = ("가동", "정지", "점검", "고장")
EQUIP_STATE_KEY = {"가동": "run", "정지": "stop", "점검": "check", "고장": "fault"}


# ── 공용 ───────────────────────────────────────────────────────────────
def rate(numerator, denominator) -> float | None:
    """퍼센트(0~100). 분모가 0 · None 이면 None — 0 으로 지어내지 않는다."""
    if denominator in (None, 0):
        return None
    return float(Decimal(str(numerator or 0)) / Decimal(str(denominator)) * 100)


def _f(v) -> float | None:
    return None if v is None else float(v)


def parse_date(text: str | date | None) -> date | None:
    """`YYYY-MM-DD` → date. 비어 있으면 None. 형식이 틀리면 ValueError(라우터가 422 로)."""
    if text is None or isinstance(text, date):
        return text
    text = str(text).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"날짜는 YYYY-MM-DD 로 입력한다: {text!r}") from None


def period(frm: str | date | None, to: str | date | None, *, today: date | None = None) -> tuple[date, date]:
    """집계 기간. 비워 두면 **이번 달 1일 ~ 오늘**. 시작이 끝보다 늦으면 ValueError."""
    day = today or date.today()
    d1 = parse_date(frm) or day.replace(day=1)
    d2 = parse_date(to) or max(day, d1)
    if d1 > d2:
        raise ValueError(f"기간의 시작이 끝보다 늦다: {d1} ~ {d2}")
    return d1, d2


def _check(value: str, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise ValueError(f"{what} 는 {' · '.join(allowed)} 중 하나다: {value!r}")
    return value


# ── 생산 ───────────────────────────────────────────────────────────────
_PROD_KEY: dict[str, tuple[str, str, str, str]] = {
    # by → (계획 쪽 키 식, 실적 쪽 키 식, 키 열 이름, 이름 join)
    "day": ("w.plan_date", "r.ended_at::date", "day", ""),
    "item": ("w.item_id", "wo.item_id", "item_id", "left join bas_item i on i.id = k.key"),
    "process": ("w.process_id", "r.process_id", "process_id", "left join bas_process pr on pr.id = k.key"),
    "equipment": ("w.equipment_id", "r.equipment_id", "equipment_id", "left join bas_equipment e on e.id = k.key"),
}
_PROD_LABEL: dict[str, str] = {
    "day": "k.key as day, null::text as code, null::text as name",
    "item": "k.key as item_id, i.item_code as code, i.item_name as name",
    "process": "k.key as process_id, pr.process_code as code, pr.process_name as name",
    "equipment": "k.key as equipment_id, e.equip_code as code, e.equip_name as name",
}


def production(frm: date, to: date, *, by: str = "day") -> list[dict]:
    """생산 집계 — 키별 {day|item_id|process_id|equipment_id, code, name, wo_count, plan_qty, result_count, good_qty, defect_qty, good_rate, achieve_rate}."""
    by = _check(by, PRODUCTION_BY, "by")
    pk, rk, _col, name_join = _PROD_KEY[by]
    sql = f"""
        with plan as (
            select {pk} as key, count(*)::int as wo_count, sum(w.plan_qty) as plan_qty
              from job_work_order w
             where w.status <> '취소' and w.plan_date between %(frm)s and %(to)s
             group by 1),
        actual as (
            select {rk} as key, count(*)::int as result_count, sum(r.good_qty) as good_qty, sum(r.defect_qty) as defect_qty
              from pop_work_result r
              join job_work_order wo on wo.id = r.work_order_id
             where r.ended_at is not null and r.ended_at::date between %(frm)s and %(to)s
             group by 1),
        k as (
            select coalesce(p.key, a.key) as key, p.wo_count, p.plan_qty, a.result_count, a.good_qty, a.defect_qty
              from plan p full outer join actual a on a.key = p.key)
        select {_PROD_LABEL[by]}, coalesce(k.wo_count, 0) as wo_count, k.plan_qty,
               coalesce(k.result_count, 0) as result_count, k.good_qty, k.defect_qty
          from k {name_join}
         order by 1 nulls last"""
    rows = conn.q(sql, {"frm": frm, "to": to})
    for r in rows:
        good, defect = r["good_qty"], r["defect_qty"]
        r["good_rate"] = rate(good, (good or 0) + (defect or 0)) if (good is not None or defect is not None) else None
        r["achieve_rate"] = rate(good, r["plan_qty"])
    return rows


# ── 품질 ───────────────────────────────────────────────────────────────
def quality(frm: date, to: date, *, by: str = "day") -> list[dict]:
    """품질 집계 — day/item: {day|item_id, code, name, inspection_count, pass_count, fail_count, cond_count, pass_rate}
    · defect: {defect_code_id, code, name, defect_count, defect_qty, inspection_count}."""
    by = _check(by, QUALITY_BY, "by")
    params = {"frm": frm, "to": to}
    if by == "defect":
        return conn.q("""
            select d.defect_code_id, dc.defect_code as code, dc.defect_name as name,
                   count(*)::int as defect_count, sum(d.qty) as defect_qty, count(distinct n.id)::int as inspection_count
              from qua_defect d
              join qua_inspection n on n.id = d.inspection_id
              join bas_defect_code dc on dc.id = d.defect_code_id
             where n.judgement is not null and n.judged_at::date between %(frm)s and %(to)s
             group by d.defect_code_id, dc.defect_code, dc.defect_name
             order by count(*) desc, dc.defect_code""", params)
    key = "n.judged_at::date" if by == "day" else "l.item_id"
    label = "k.key as day, null::text as code, null::text as name" if by == "day" else "k.key as item_id, i.item_code as code, i.item_name as name"
    name_join = "" if by == "day" else "left join bas_item i on i.id = k.key"
    rows = conn.q(f"""
        with k as (
            select {key} as key, count(*)::int as inspection_count,
                   count(*) filter (where n.judgement = '합격')::int as pass_count,
                   count(*) filter (where n.judgement = '불합격')::int as fail_count,
                   count(*) filter (where n.judgement = '조건부')::int as cond_count
              from qua_inspection n
              join lot l on l.id = n.lot_id
             where n.judgement is not null and n.judged_at::date between %(frm)s and %(to)s
             group by 1)
        select {label}, k.inspection_count, k.pass_count, k.fail_count, k.cond_count
          from k {name_join}
         order by 1 nulls last""", params)
    for r in rows:
        r["pass_rate"] = rate(r["pass_count"], r["inspection_count"])
    return rows


# ── 납기 ───────────────────────────────────────────────────────────────
_DELIVERY_BASE = """
    with first_ship as (
        select s.order_id, min(s.ship_date) as first_ship_date
          from shp_shipment s where s.status = '승인' and s.order_id is not null
         group by s.order_id),
    o as (
        select o.id, o.order_no, o.partner_id, o.due_date, f.first_ship_date,
               (f.first_ship_date is not null) as shipped,
               (f.first_ship_date is not null and f.first_ship_date <= o.due_date) as on_time,
               (f.first_ship_date > o.due_date or (f.first_ship_date is null and o.due_date < %(today)s)) as late,
               (f.first_ship_date is null and o.due_date >= %(today)s) as pending
          from ord_order o
          left join first_ship f on f.order_id = o.id
         where o.status <> '취소' and o.due_date between %(frm)s and %(to)s)
"""


def delivery(frm: date, to: date, *, by: str = "day", today: date | None = None) -> list[dict]:
    """납기 집계 — {day|partner_id, code, name, due_count, shipped_count, on_time, late, pending, on_time_rate}."""
    by = _check(by, DELIVERY_BY, "by")
    params = {"frm": frm, "to": to, "today": today or date.today()}
    if by == "day":
        sql = _DELIVERY_BASE + """
            select o.due_date as day, null::text as code, null::text as name, count(*)::int as due_count,
                   count(*) filter (where o.shipped)::int as shipped_count, count(*) filter (where o.on_time)::int as on_time,
                   count(*) filter (where o.late)::int as late, count(*) filter (where o.pending)::int as pending
              from o group by o.due_date order by o.due_date"""
    else:
        sql = _DELIVERY_BASE + """
            select o.partner_id, p.partner_code as code, p.partner_name as name, count(*)::int as due_count,
                   count(*) filter (where o.shipped)::int as shipped_count, count(*) filter (where o.on_time)::int as on_time,
                   count(*) filter (where o.late)::int as late, count(*) filter (where o.pending)::int as pending
              from o join bas_partner p on p.id = o.partner_id
             group by o.partner_id, p.partner_code, p.partner_name order by p.partner_code"""
    rows = conn.q(sql, params)
    for r in rows:
        r["on_time_rate"] = rate(r["on_time"], r["on_time"] + r["late"])
    return rows


def late_orders(*, today: date | None = None, limit: int = 20) -> list[dict]:
    """납기가 지났는데 승인된 출하가 없는 수주 — {order_no, partner_name, item_name(첫 상세), due_date}. 납기 오름차순."""
    day = today or date.today()
    return conn.q("""
        select o.order_no, p.partner_name, o.due_date,
               (select i.item_name from ord_order_dtl d join bas_item i on i.id = d.item_id
                 where d.order_id = o.id order by d.line_no limit 1) as item_name
          from ord_order o
          join bas_partner p on p.id = o.partner_id
         where o.status <> '취소' and o.due_date < %(today)s
           and not exists (select 1 from shp_shipment s where s.order_id = o.id and s.status = '승인')
         order by o.due_date, o.order_no
         limit %(limit)s""", {"today": day, "limit": limit})



def shipment_due(shipment_ids: list[int]) -> dict[int, dict]:
    """출하 행별 납기 대비 (SHP-03) — {shipment_id: {due_date, due_days, due_state}}. `due_days` = 출하일 − 수주 납기(일 · 양수 = 지남).
    `due_state` 지연 / 당일 / 앞섬 · 수주 없음 또는 납기 없음 → None(화면 「-」). 읽기만."""
    if not shipment_ids:
        return {}
    rows = conn.q("""
        select s.id as shipment_id, o.due_date, (s.ship_date - o.due_date)::int as due_days
          from shp_shipment s left join ord_order o on o.id = s.order_id
         where s.id = any(%(ids)s)""", {"ids": list(shipment_ids)})
    out: dict[int, dict] = {}
    for r in rows:
        d = r["due_days"]
        r["due_state"] = None if d is None else ("지연" if d > 0 else "당일" if d == 0 else "앞섬")
        out[r.pop("shipment_id")] = r
    return out

# ── 설비 ───────────────────────────────────────────────────────────────
def equipment(frm: date, to: date) -> list[dict]:
    """설비 집계 — 설비마다 {equipment_id, code, name, collect_yn, run_seconds, stop_seconds, check_seconds, fault_seconds, logged_seconds,
    run_rate, stop_count, fault_count, fixed_count, mttr_hours, current_state}."""
    params = {"ws": datetime.combine(frm, datetime.min.time()), "we": datetime.combine(to + timedelta(days=1), datetime.min.time()),
              "frm": frm, "to": to}
    rows = conn.q("""
        with seg as (
            select g.equipment_id, g.state,
                   extract(epoch from (least(coalesce(g.ended_at, now()), %(we)s::timestamptz) - greatest(g.started_at, %(ws)s::timestamptz))) as sec,
                   g.started_at
              from eqp_run_log g
             where g.started_at < %(we)s::timestamptz and coalesce(g.ended_at, now()) > %(ws)s::timestamptz),
        agg as (
            select equipment_id,
                   coalesce(sum(sec) filter (where state = '가동'), 0) as run_seconds,
                   coalesce(sum(sec) filter (where state = '정지'), 0) as stop_seconds,
                   coalesce(sum(sec) filter (where state = '점검'), 0) as check_seconds,
                   coalesce(sum(sec) filter (where state = '고장'), 0) as fault_seconds,
                   count(*) filter (where state = '정지' and started_at >= %(ws)s::timestamptz)::int as stop_count
              from seg group by equipment_id),
        fault as (
            select f.equipment_id, count(*)::int as fault_count,
                   count(f.fixed_at)::int as fixed_count,
                   avg(extract(epoch from (f.fixed_at - f.occurred_at)) / 3600.0) as mttr_hours
              from eqp_fault f where f.occurred_at::date between %(frm)s and %(to)s
             group by f.equipment_id),
        cur as (
            select distinct on (g.equipment_id) g.equipment_id, g.state
              from eqp_run_log g where g.ended_at is null order by g.equipment_id, g.started_at desc)
        select e.id as equipment_id, e.equip_code as code, e.equip_name as name, e.collect_yn,
               coalesce(a.run_seconds, 0)::float as run_seconds, coalesce(a.stop_seconds, 0)::float as stop_seconds,
               coalesce(a.check_seconds, 0)::float as check_seconds, coalesce(a.fault_seconds, 0)::float as fault_seconds,
               coalesce(a.stop_count, 0) as stop_count, coalesce(f.fault_count, 0) as fault_count, coalesce(f.fixed_count, 0) as fixed_count, f.mttr_hours, c.state as current_state
          from bas_equipment e
          left join agg a on a.equipment_id = e.id
          left join fault f on f.equipment_id = e.id
          left join cur c on c.equipment_id = e.id
         where e.use_yn = 'Y'
         order by e.equip_code""", params)
    for r in rows:
        r["logged_seconds"] = r["run_seconds"] + r["stop_seconds"] + r["check_seconds"] + r["fault_seconds"]
        r["run_rate"] = rate(r["run_seconds"], r["logged_seconds"])
        r["mttr_hours"] = _f(r["mttr_hours"])
    return rows


# ── 측정값 ─────────────────────────────────────────────────────────────
def measure_series(param_key: str, frm: date, to: date, *, by: str = "day", agg: str = "avg") -> list[dict]:
    """측정값 시계열 — {day|work_order_id|equipment_id, code, value, n, deviated_count, min_value, max_value}."""
    by = _check(by, MEASURE_BY, "by")
    agg = _check(agg, MEASURE_AGG, "agg")
    key, label, name_join = {
        "day": ("m.measured_at::date", "k.key as day, null::text as code", ""),
        "work_order": ("r.work_order_id", "k.key as work_order_id, w.work_order_no as code", "left join job_work_order w on w.id = k.key"),
        "equipment": ("r.equipment_id", "k.key as equipment_id, e.equip_code as code", "left join bas_equipment e on e.id = k.key"),
    }[by]
    value_expr = {"avg": "avg(m.value_num)", "min": "min(m.value_num)", "max": "max(m.value_num)", "sum": "sum(m.value_num)",
                  "count": "count(m.value_num)", "last": "(array_agg(m.value_num order by m.measured_at desc, m.id desc))[1]"}[agg]
    rows = conn.q(f"""
        with k as (
            select {key} as key, {value_expr} as value, count(*)::int as n,
                   count(*) filter (where m.deviated)::int as deviated_count, min(m.value_num) as min_value, max(m.value_num) as max_value
              from pop_measure m
              join pop_work_result r on r.id = m.work_result_id
             where m.param_key = %(key)s and m.value_num is not null and m.measured_at::date between %(frm)s and %(to)s
             group by 1)
        select {label}, k.value, k.n, k.deviated_count, k.min_value, k.max_value
          from k {name_join}
         order by 1 nulls last""", {"key": param_key, "frm": frm, "to": to})
    for r in rows:
        r["value"], r["min_value"], r["max_value"] = _f(r["value"]), _f(r["min_value"]), _f(r["max_value"])
    return rows


def measure_keys() -> list[dict]:
    """측정값 키 목록(선택칸용) — `bas_process_param` 선언 + 기록에만 있는 키."""
    return conn.q("""
        select p.param_key, min(p.label) as label, min(p.unit) as unit from bas_process_param p where p.use_yn = 'Y' group by p.param_key
        union
        select m.param_key, m.param_key as label, min(m.unit) as unit from pop_measure m
         where not exists (select 1 from bas_process_param p where p.param_key = m.param_key) group by m.param_key
        order by 1""")


# ── 합계 · 핵심 지표 ────────────────────────────────────────────────────
def _sum(rows: list[dict], col: str):
    vals = [r[col] for r in rows if r.get(col) is not None]
    return sum((Decimal(str(v)) for v in vals), Decimal(0)) if vals else None


def totals(kind: str, rows: list[dict]) -> dict | None:
    """키별 행을 한 줄로 더한다(합계 줄 · 현황판 대표 숫자). 행이 없으면 None. 비율은 더한 값으로 다시 나눈다(비율의 평균이 아니다)."""
    if not rows:
        return None
    if kind == "production":
        good, defect, plan = _sum(rows, "good_qty"), _sum(rows, "defect_qty"), _sum(rows, "plan_qty")
        return {"wo_count": sum(r["wo_count"] for r in rows), "plan_qty": plan, "result_count": sum(r["result_count"] for r in rows),
                "good_qty": good, "defect_qty": defect,
                "good_rate": rate(good, (good or 0) + (defect or 0)) if (good is not None or defect is not None) else None,
                "achieve_rate": rate(good, plan)}
    if kind == "quality" and rows and "defect_count" in rows[0]:
        return {"defect_count": sum(r["defect_count"] for r in rows), "defect_qty": _sum(rows, "defect_qty"),
                "inspection_count": sum(r["inspection_count"] for r in rows)}
    if kind == "quality":
        n = sum(r["inspection_count"] for r in rows)
        p, f, c = sum(r["pass_count"] for r in rows), sum(r["fail_count"] for r in rows), sum(r["cond_count"] for r in rows)
        return {"inspection_count": n, "pass_count": p, "fail_count": f, "cond_count": c, "pass_rate": rate(p, n)}
    if kind == "delivery":
        on_time, late = sum(r["on_time"] for r in rows), sum(r["late"] for r in rows)
        return {"due_count": sum(r["due_count"] for r in rows), "shipped_count": sum(r["shipped_count"] for r in rows),
                "on_time": on_time, "late": late, "pending": sum(r["pending"] for r in rows), "on_time_rate": rate(on_time, on_time + late)}
    if kind == "equipment":
        run, logged = sum(r["run_seconds"] for r in rows), sum(r["logged_seconds"] for r in rows)
        fixed = [(r["mttr_hours"], r.get("fixed_count") or 0) for r in rows if r["mttr_hours"] is not None]
        n_fixed = sum(n for _, n in fixed)                              # 복구 고장 전체 평균(가중) — 설비별 MTTR 의 평균이 아니다
        return {"equipment_count": len(rows), "run_seconds": run, "logged_seconds": logged, "run_rate": rate(run, logged),
                "stop_count": sum(r["stop_count"] for r in rows), "fault_count": sum(r["fault_count"] for r in rows),
                "fixed_count": n_fixed, "mttr_hours": (sum(h * n for h, n in fixed) / n_fixed) if n_fixed else None}
    raise ValueError(f"집계 종류가 아니다: {kind!r}")


def core_metrics(frm: date, to: date, *, today: date | None = None) -> dict[str, float | None]:
    """코어 지표 5 (`CORE_METRIC_KEYS`) — 기간 합계에서 계산한 퍼센트."""
    p = totals("production", production(frm, to)) or {}
    q = totals("quality", quality(frm, to)) or {}
    d = totals("delivery", delivery(frm, to, today=today)) or {}
    e = totals("equipment", equipment(frm, to)) or {}
    return {"production.achieve_rate": p.get("achieve_rate"), "production.good_rate": p.get("good_rate"),
            "quality.pass_rate": q.get("pass_rate"), "delivery.on_time_rate": d.get("on_time_rate"), "equipment.run_rate": e.get("run_rate")}


# ── 지표 · 팩 kpi_extra · 스냅샷 ───────────────────────────────────────
def kpi_extra(frm: date, to: date, by: str | None = None) -> list[dict]:
    """팩 훅 `kpi_extra(frm, to[, by])` (D-508). 없으면 빈 목록. 항목은 {key, label, value, unit}. 형식이 아니면 ValueError(조용히 버리지 않는다)."""
    fn = packs.hook("kpi_extra")
    if fn is packs.NOOP_HOOK:
        return []
    out = fn(frm, to) if by is None else fn(frm, to, by)
    rows = []
    for m in out or []:
        if not isinstance(m, dict) or "key" not in m:
            raise ValueError(f"kpi_extra 항목은 {{key, label, value, unit}} dict 여야 한다: {m!r}")
        rows.append({"key": str(m["key"]), "label": m.get("label") or m.get("name") or str(m["key"]),
                     "value": _f(m.get("value")), "unit": m.get("unit")})
    return rows


def status_of(value: float | None, target: float | None) -> str | None:
    """D-602 — 값 ≥ 목표 good · ≥ 목표 × 95 % warn · 그 밖 critical. 값 또는 목표가 없으면 None(상태색 없음)."""
    if value is None or target is None:
        return None
    if value >= target:
        return "good"
    if value >= target * WARN_RATIO:
        return "warn"
    return "critical"


def _metric_values(frm: date, to: date, *, today: date | None = None) -> dict[str, float | None]:
    values: dict[str, float | None] = dict(core_metrics(frm, to, today=today))
    for m in kpi_extra(frm, to):
        values[f"pack:{m['key']}"] = m["value"]
    return values


def _snapshot_values(day: date) -> tuple[dict[str, float | None], datetime | None]:
    rows = conn.q("select indicator_key, value, calc_at from kpi_snapshot where snap_date = %s", (day,))
    if not rows:
        return {}, None
    return {r["indicator_key"]: _f(r["value"]) for r in rows}, max(r["calc_at"] for r in rows)


def _metric_key(calc_kind: str) -> str:
    """`core:<키>` → 키 · `pack:<키>` → `pack:<키>` (값 사전의 키)."""
    kind, _, key = (calc_kind or "").partition(":")
    if kind == "core":
        return key
    if kind == "pack":
        return f"pack:{key}"
    return calc_kind or ""


def indicator_rows() -> list[dict]:
    return conn.q("""select id, indicator_key, name, unit, target_value, calc_kind, visible_yn, seq, attrs
                       from kpi_indicator order by seq, indicator_key""")


def indicators(frm: date | None = None, to: date | None = None, *, values: dict[str, float | None] | None = None,
               today: date | None = None) -> list[dict]:
    """지표 정의 + 현재값 + 목표 대비 (F-KPI-08). 기간을 비우면 오늘 하루. `values` 를 주면(스냅샷) 다시 계산하지 않는다."""
    day = today or date.today()
    frm, to = frm or day, to or day
    vals = values if values is not None else _metric_values(frm, to, today=day)
    out = []
    for r in indicator_rows():
        key = _metric_key(r["calc_kind"])
        known = key in vals
        value = vals.get(key)
        target = _f(r["target_value"])
        out.append({"id": r["id"], "indicator_key": r["indicator_key"], "name": r["name"], "unit": r["unit"], "calc_kind": r["calc_kind"],
                    "metric_key": key, "known": known, "value": value, "target_value": target, "status": status_of(value, target),
                    "visible_yn": r["visible_yn"], "seq": r["seq"], "attrs": r["attrs"]})
    return out


def snapshot(cur, day: date) -> int:
    """현황판 일 스냅샷 — 코어 지표 5 + 팩 `kpi_extra` 결과를 `kpi_snapshot(snap_date, indicator_key)` 로 upsert. **배치만 부른다**
    (`make kpi-snapshot` · F-SYS). 돌려주는 값은 쓴 행 수. 화면은 이 함수를 부르지 않는다 (G-C05)."""
    values = _metric_values(day, day, today=day)
    n = 0
    for key, value in values.items():
        cur.execute("""insert into kpi_snapshot (snap_date, indicator_key, value, calc_at, created_by) values (%s, %s, %s, now(), 'kpi-snapshot')
                       on conflict (snap_date, indicator_key) do update
                           set value = excluded.value, calc_at = now(), updated_at = now(), updated_by = 'kpi-snapshot'""",
                    (day, key, value))
        n += 1
    return n


# ── 현황판 ─────────────────────────────────────────────────────────────
def _by_hour(day: date) -> list[dict]:
    rows = conn.q("""select to_char(r.ended_at, 'HH24') as hour, sum(r.good_qty) as qty
                       from pop_work_result r where r.ended_at is not null and r.ended_at::date = %s
                      group by 1 order by 1""", (day,))
    if not rows:
        return []
    first = int(rows[0]["hour"])
    have = {r["hour"]: _f(r["qty"]) or 0.0 for r in rows}
    return [{"hour": f"{h:02d}", "qty": have.get(f"{h:02d}", 0.0)} for h in range(first, 24)]


def _top_defects(day: date, limit: int = 3) -> list[dict]:
    rows = quality(day, day, by="defect")[:limit]
    top = _f(rows[0]["defect_qty"]) if rows and rows[0]["defect_qty"] is not None else None
    out = []
    for r in rows:
        qty = _f(r["defect_qty"]) if r["defect_qty"] is not None else float(r["defect_count"])
        base = top if top else (float(rows[0]["defect_count"]) if rows else None)
        out.append({"defect_code": r["code"], "defect_name": r["name"], "qty": qty, "share": rate(qty, base) if base else None})
    return out


def _equipment_board(rows: list[dict]) -> dict:
    counts = {v: 0 for v in EQUIP_STATE_KEY.values()}
    for r in rows:
        k = EQUIP_STATE_KEY.get(r["current_state"] or "")
        if k:
            counts[k] += 1
    order = {"고장": 0, "정지": 1, "점검": 2, "가동": 3, None: 4}
    items = sorted(rows, key=lambda r: (order.get(r["current_state"], 4), r["code"]))[:5]
    last = {}
    if items:
        ids = [r["equipment_id"] for r in items]
        last = {r["equipment_id"]: r["ts"] for r in conn.q(
            "select equipment_id, max(ts) as ts from eqp_collect where equipment_id = any(%s) group by equipment_id", (ids,))}
    return {**counts, "items": [{"equip_code": r["code"], "equip_name": r["name"], "state": r["current_state"], "collect_yn": r["collect_yn"],
                                 "last_received_at": last[r["equipment_id"]].strftime("%H:%M:%S") if last.get(r["equipment_id"]) else None}
                                for r in items]}


def open_work_orders(limit: int = 7) -> list[dict]:
    """진행 중(대기 · 진행) 작업지시 — 진행 먼저. {work_order_no, item_name, process_name, equipment_name, plan_qty, actual_qty, achieve_rate, status}."""
    rows = conn.q("""
        select w.work_order_no, i.item_name, p.process_name, e.equip_name as equipment_name, w.plan_qty, w.status,
               (select sum(r.good_qty) from pop_work_result r where r.work_order_id = w.id and r.ended_at is not null) as actual_qty
          from job_work_order w
          join bas_item i on i.id = w.item_id
          join bas_process p on p.id = w.process_id
          left join bas_equipment e on e.id = w.equipment_id
         where w.status in ('대기', '진행')
         order by case w.status when '진행' then 0 else 1 end, w.plan_date nulls last, w.work_order_no
         limit %s""", (limit,))
    for r in rows:
        r["plan_qty"], r["actual_qty"] = _f(r["plan_qty"]), _f(r["actual_qty"]) or 0.0
        r["achieve_rate"] = rate(r["actual_qty"], r["plan_qty"])
    return rows


#: 지표 목표값이 없을 때(NULL) 근거 결정 — 현황판 · 지표 화면의 `미확정 (D-602)`
TARGET_DECISION = "D-602"


def board(today: date | None = None) -> dict:
    """현황판 한 화면 분 — 키는 `docs/design/README.md` 디자이너3 절(D-602) 그대로. 전부 **오늘 하루** 기준."""
    day = today or date.today()
    snap, snap_at = _snapshot_values(day)
    values = snap if snap else _metric_values(day, day, today=day)
    prod = totals("production", production(day, day)) or {}
    qual = totals("quality", quality(day, day)) or {}
    deli = totals("delivery", delivery(day, day, today=day)) or {}
    eq_rows = equipment(day, day)
    meas = conn.q1("""select count(*)::int as measured_count, count(*) filter (where deviated)::int as deviated_count
                        from pop_measure where measured_at::date = %s""", (day,)) or {}
    inds = [i for i in indicators(day, day, values=values, today=day) if i["visible_yn"] == "Y"]
    target_of = {i["metric_key"]: i["target_value"] for i in inds}
    wos = open_work_orders()
    unit = conn.q1("""select w.unit from job_work_order w where w.plan_date = %s and w.status <> '취소' and w.unit is not null
                       group by w.unit order by count(*) desc limit 1""", (day,))
    return {
        "today": day.isoformat(),
        "source": f"스냅샷 {snap_at.strftime('%H:%M')}" if snap_at else "실시간",
        "undecided": f"{packs.t('미확정')} ({TARGET_DECISION})",                       # 목표 NULL 칸 문구 — goal G-C11 `미확정 (D-nn)` (DEF-QA2-003)
        "production": {"plan_qty": _f(prod.get("plan_qty")), "actual_qty": _f((prod.get("good_qty") or 0) + (prod.get("defect_qty") or 0)) if prod else None,
                       "good_qty": _f(prod.get("good_qty")), "defect_qty": _f(prod.get("defect_qty")), "unit": unit["unit"] if unit else None,
                       "achieve_rate": values.get("production.achieve_rate") if snap else prod.get("achieve_rate"),
                       "good_rate": values.get("production.good_rate") if snap else prod.get("good_rate"),
                       "good_rate_target": target_of.get("production.good_rate"), "by_hour": _by_hour(day)},
        "quality": {"inspection_count": qual.get("inspection_count"), "pass_count": qual.get("pass_count"), "fail_count": qual.get("fail_count"),
                    "pass_rate": values.get("quality.pass_rate") if snap else qual.get("pass_rate"),
                    "pass_rate_target": target_of.get("quality.pass_rate"), "top_defects": _top_defects(day)},
        "delivery": {"due_count": deli.get("due_count"), "shipped_count": deli.get("shipped_count"), "late_count": deli.get("late"),
                     "pending_count": deli.get("pending"), "on_time_rate": values.get("delivery.on_time_rate") if snap else deli.get("on_time_rate"),
                     "late_orders": [{"order_no": r["order_no"], "partner_name": r["partner_name"], "item_name": r["item_name"],
                                      "due_date": r["due_date"].strftime("%m-%d")} for r in late_orders(today=day, limit=2)]},
        "equipment": _equipment_board(eq_rows),
        "work_orders_count": len(wos),
        "work_orders": wos,
        "measure": {"measured_count": meas.get("measured_count"), "deviated_count": meas.get("deviated_count")},
        "indicators": [{"indicator_key": i["indicator_key"], "name": i["name"], "unit": i["unit"], "value": i["value"],
                        "target_value": i["target_value"], "status": i["status"]} for i in inds][:6],
    }


# ── 대시보드 (CMN-04) ──────────────────────────────────────────────────
def dashboard(today: date | None = None) -> dict:
    """역할별 대시보드의 숫자 — `today`(4개 공통) + `extra`(역할별 강조 후보 전부). 읽기만."""
    day = today or date.today()
    t = conn.q1("""
        select (select count(*)::int from job_work_order w where w.plan_date = %(d)s and w.status <> '취소') as work_orders,
               (select count(*)::int from pop_work_result r where r.started_at::date = %(d)s) as results,
               (select count(*)::int from qua_inspection n where n.judgement is null) as inspections_pending,
               (select count(*)::int from shp_shipment s where s.status = '등록') as shipments_pending""", {"d": day}) or {}
    extra = conn.q1("""
        select (select count(*)::int from pop_measure m where m.deviated and m.measured_at::date = %(d)s) as deviated,
               (select count(*)::int from eqp_fault f where f.fixed_at is null) as faults,
               (select count(*)::int from shp_shipment s where s.status = '등록') as approvals_pending,
               (select count(*)::int from qua_issue q where q.status <> '종결') as issues_open,
               (select count(*)::int from lot l where l.kind_base = 'PRODUCT' and l.made_at::date = %(d)s) as labels_today""", {"d": day}) or {}
    extra["late_orders"] = len(late_orders(today=day, limit=1000))
    return {"today": {"date": day.isoformat(), **t}, "extra": extra, "recent": recent_activity(limit=5)}


def recent_activity(limit: int = 5) -> list[dict]:
    """최근 변경 N건 (CMN-04 `recent[]`) — `sys_access_log` 의 change 행, 최신 순.
    {logged_at, login_id, fn_id, screen_id, target, name(기능 이름 — detail.name)}. 비밀번호 · 세션 값은 로그에 없다(audit)."""
    return conn.q("""
        select l.logged_at, l.login_id, l.fn_id, l.screen_id, l.target, l.detail ->> 'name' as name
          from sys_access_log l
         where l.kind = 'change'
         order by l.logged_at desc, l.id desc
         limit %(limit)s""", {"limit": limit})


#: 메인 카드 "오늘 건수" 출처 — 모듈 코드 → 무엇을 세는가 (home/main.html 디자이너3 가설 · trc 는 오늘 계보 연결)
class _TermsDict(dict):
    """읽을 때 팩 terms 를 건 값을 돌려주는 dict — 출처 문장이 화면(CMN-02 카드 title)에 그대로 나가므로 `t()` 를 여기서 건다(G-P05).
    저장 값은 코어 중립어 원문 그대로."""

    def __getitem__(self, key):
        return packs.t(super().__getitem__(key))

    def get(self, key, default=None):
        return self[key] if key in self else default


TODAY_COUNT_SOURCES: dict[str, str] = _TermsDict({
    "bas": "오늘 기준정보 변경(F-BAS-* change 로그)", "ord": "오늘 납기 수주(취소 제외)", "job": "오늘 계획 작업지시(취소 제외)",
    "mat": "오늘 입고", "pop": "오늘 시작 실적", "qua": "판정 대기 검사", "eqp": "고장 중 설비(미조치 고장)", "shp": "출하 대기(등록)",
    "trc": "오늘 계보 연결", "kpi": "오늘 측정값 이탈", "sys": "오늘 로그인", "ifc": "오늘 수신 거부",
})


def today_counts(today: date | None = None) -> dict[str, int]:
    """메인 카드(CMN-02) 모듈별 "오늘 건수" — {bas ord job mat pop qua eqp shp trc kpi sys ifc: int}. 출처는 `TODAY_COUNT_SOURCES`. 읽기만 · 0 도 숫자."""
    day = today or date.today()
    r = conn.q1("""
        select (select count(*)::int from sys_access_log l where l.kind = 'change' and l.fn_id like 'F-BAS-%%'
                  and l.logged_at >= %(d)s::date and l.logged_at < %(d)s::date + 1) as bas,
               (select count(*)::int from ord_order o where o.due_date = %(d)s and o.status <> '취소') as ord,
               (select count(*)::int from job_work_order w where w.plan_date = %(d)s and w.status <> '취소') as job,
               (select count(*)::int from mat_receipt m where m.receipt_date = %(d)s) as mat,
               (select count(*)::int from pop_work_result p where p.started_at >= %(d)s::date and p.started_at < %(d)s::date + 1) as pop,
               (select count(*)::int from qua_inspection n where n.judgement is null) as qua,
               (select count(distinct f.equipment_id)::int from eqp_fault f where f.fixed_at is null) as eqp,
               (select count(*)::int from shp_shipment s where s.status = '등록') as shp,
               (select count(*)::int from lot_genealogy g where g.linked_at >= %(d)s::date and g.linked_at < %(d)s::date + 1) as trc,
               (select count(*)::int from pop_measure m where m.deviated and m.measured_at >= %(d)s::date and m.measured_at < %(d)s::date + 1) as kpi,
               (select count(*)::int from sys_access_log l where l.kind = 'login_ok'
                  and l.logged_at >= %(d)s::date and l.logged_at < %(d)s::date + 1) as sys,
               (select count(*)::int from ifc_collect_raw c where c.rejected_reason is not null
                  and c.received_at >= %(d)s::date and c.received_at < %(d)s::date + 1) as ifc""", {"d": day}) or {}
    return {k: int(r.get(k) or 0) for k in TODAY_COUNT_SOURCES}


@dataclass(frozen=True)
class Kind:
    """집계 종류 하나 — KPI-02 의 탭."""
    code: str
    name: str
    fn_id: str
    by_options: tuple[str, ...]
    date_label: str


KINDS: dict[str, Kind] = {
    "production": Kind("production", "생산", "F-KPI-02", PRODUCTION_BY, "계획일 · 종료일"),
    "quality": Kind("quality", "품질", "F-KPI-03", QUALITY_BY, "판정일"),
    "delivery": Kind("delivery", "납기", "F-KPI-04", DELIVERY_BY, "납기"),
    "equipment": Kind("equipment", "설비", "F-KPI-05", (), "가동 기록"),
}


def summary(kind: str, frm: date, to: date, *, by: str | None = None, today: date | None = None) -> dict[str, Any]:
    """집계 화면 한 종류 분 — {kind, by, rows, total}. 종류 · by 가 틀리면 ValueError."""
    k = KINDS.get(kind)
    if k is None:
        raise ValueError(f"집계 종류는 {' · '.join(KINDS)} 중 하나다: {kind!r}")
    if kind == "production":
        rows = production(frm, to, by=by or "day")
    elif kind == "quality":
        rows = quality(frm, to, by=by or "day")
    elif kind == "delivery":
        rows = delivery(frm, to, by=by or "day", today=today)
    else:
        rows = equipment(frm, to)
    return {"kind": kind, "by": by or (k.by_options[0] if k.by_options else None), "rows": rows, "total": totals(kind, rows)}


if __name__ == "__main__":                      # make kpi-snapshot — `uv run python -m mescore.app.stats snapshot [YYYY-MM-DD]`
    import sys

    if len(sys.argv) < 2 or sys.argv[1] != "snapshot":
        raise SystemExit("쓰는 법: python -m mescore.app.stats snapshot [YYYY-MM-DD]")
    target_day = parse_date(sys.argv[2]) if len(sys.argv) > 2 else date.today()
    with conn.tx() as cur:
        written = snapshot(cur, target_day)
    print(f"kpi_snapshot {target_day}: {written}행")
