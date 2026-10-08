"""E5 훅 — kimchi 팩 (hooks.md 를 코드로 · 개발3 · 2026-10-09).

전부 동기 · 코어 트랜잭션 안 · 거부는 `HookError`(422 hook_rejected) · 그 밖 예외는 500(삼키지 않는다).
코어 테이블 쓰기는 `pack.yaml: write_scope.hooks = [lot, pop_measure, qua_issue]` 안에서만 — `lot` 은 `lineage.retag` 경유 · `pop_measure` 는 파생 측정값 upsert(D-510) ·
`qua_issue` 는 CCP · 손실률 이탈. `lot_genealogy` · `sys_number_seq` 직접 SQL 0. 환경 알람은 팩 테이블(`alarm.raise_env` · D-501 1차 우회).
임계값은 전부 데이터(`bas_process_param` · `x_kimchi_item_std` · `qua_insp_plan`)에서 읽고, 없으면 판정하지 않는다(미확정 · 지어내지 않는다).

정의하지 않는 훅(validate_<table> · on_order_created · on_work_order_* · on_result_started · on_lot_created · after_commit_*)은 no-op 다(hooks.md §6).
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mescore.app import collect, lineage, numbering  # noqa: E402
from mescore.app.packs import t  # noqa: E402
from mescore.app.util.http import HookError  # noqa: E402

from packs.kimchi import alarm, common  # noqa: E402
from packs.kimchi.adapters import collect_tags as tags  # noqa: E402

log = logging.getLogger("packs.kimchi.hooks")
TANK_KIND, AGING_KIND = "TANK", "AGING"
LOSS_KEY, IN_KEY, OUT_KEY = "loss_rate_pct", "input_weight_kg", "output_weight_kg"
WASH_KEYS: tuple[str, ...] = ("wash_time_min", "wash_volume_l", "wash_weight_kg")
WORK_HOURS_PER_DAY = Decimal("8")      # 정본 TD1 재계산식(22.33일 × 8h) — kpi_indicator(throughput_kg_per_h).attrs.work_hours_per_day 가 있으면 그 값


# ── CCP 판정 공용 ─────────────────────────────────────────────────────────
def _ccp_failed(item: dict) -> bool:
    """항목 이탈 — item_judgement=불합격 · deviated · select 값이 기준(standard)과 다름. 기준이 없으면(미확정) 이탈 아님."""
    if item.get("item_judgement") == "불합격" or item.get("deviated"):
        return True
    std = item.get("standard")
    if item.get("value_text") is not None and std:
        return str(item["value_text"]).strip().upper() != str(std).strip().upper()
    return False


def _ccp_items(cur, lot_ids: list[int]) -> list[dict]:
    """LOT 들의 검사 항목(CCP 키만) — 최신 순."""
    if not lot_ids:
        return []
    return common.rows(cur, """select q.id as inspection_id, q.lot_id, q.insp_type, q.inspected_at, q.judgement, i.item_key, i.value_num, i.value_text,
                                      i.item_judgement, i.deviated, p.standard, p.min_value, p.max_value, p.process_id as plan_process_id, p.label
                                 from qua_inspection q join qua_insp_item i on i.inspection_id = q.id left join qua_insp_plan p on p.id = i.plan_id
                                where q.lot_id = any(%s) and i.item_key = any(%s) and q.insp_type in ('공정', '최종')
                                order by q.inspected_at desc, q.id desc, i.id""", ([int(x) for x in lot_ids], list(common.CCP_KEYS)))


def _latest_by_key(items: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for it in items:                       # 최신 순이므로 처음 본 키가 최신
        out.setdefault(it["item_key"], it)
    return out


# ── 1. 출하 승인 직전 — 금속검출 미통과 · CCP 불합격 · 숙성 미완료 (hooks.md §1) ──
def validate_shipment(cur, shipment: dict, lots: list[dict], user) -> None:
    no_metal, ccp_fail, not_aged = [], [], []
    today = date.today()
    for lot in lots:
        lid = int(lot["lot_id"])
        ids = [n.id for n in lineage.trace_backward(lid, cur).nodes()]        # 그 LOT + 역추적 조상 (금속검출은 혼합 배치에서 한다)
        latest = _latest_by_key(_ccp_items(cur, ids))
        metal = latest.get("metal_detect")
        if metal is None or metal["judgement"] != "합격" or _ccp_failed(metal):
            no_metal.append(lot["lot_no"])
        if any(_ccp_failed(it) for it in latest.values()):
            ccp_fail.append(lot["lot_no"])
        if lot.get("kind") == AGING_KIND:
            ext = common.lot_ext(cur, lid)
            if ext and ext["shippable_yn"] != "Y" and ext["aging_due_date"] is not None and ext["aging_due_date"] > today:
                not_aged.append(f"{lot['lot_no']} ({t('예정')} {ext['aging_due_date']})")
    if ccp_fail:
        raise HookError(t("CCP 불합격 배치는 출하할 수 없습니다") + ": " + ", ".join(ccp_fail), fields=[{"name": "lots", "label": t("생산 LOT"), "reason": ", ".join(ccp_fail)}])
    if no_metal:
        raise HookError(t("금속검출 합격 기록이 없는 배치가 있습니다") + ": " + ", ".join(no_metal), fields=[{"name": "lots", "label": t("생산 LOT"), "reason": ", ".join(no_metal)}])
    if not_aged:
        raise HookError(t("숙성 완료 전입니다") + ": " + ", ".join(not_aged), fields=[{"name": "lots", "label": t("생산 LOT"), "reason": ", ".join(not_aged)}])


# ── 2. 검사 판정 후 — CCP 이탈 → qua_issue(source=hook) (hooks.md §2) ──
def _issue_exists(cur, inspection_id: int, item_key: str) -> bool:
    return common.one(cur, "select 1 as x from qua_issue where inspection_id = %s and source = 'hook' and position(%s in content) > 0",
                      (int(inspection_id), f"[{item_key}]")) is not None


def _insert_issue(cur, *, process_id, lot_id, inspection_id, content: str, occurred_at, by: str) -> int:
    no = numbering.next("ISSUE", cur=cur)
    cur.execute("""insert into qua_issue (issue_no, occurred_at, process_id, lot_id, inspection_id, content, status, source, created_by)
                   values (%s, coalesce(%s, now()), %s, %s, %s, %s, '발생', 'hook', %s) returning id""",
                (no, occurred_at, process_id, lot_id, inspection_id, content, by))
    return int(cur.fetchone()["id"])


def on_inspection_judged(cur, insp: dict, user) -> None:
    if insp.get("insp_type") not in ("공정", "최종"):
        return                                                            # 입고 검사는 코어가 lot.insp_status 로 끝낸다
    items = common.rows(cur, """select i.*, p.standard, p.min_value, p.max_value, p.process_id as plan_process_id, p.label, p.unit as plan_unit
                                  from qua_insp_item i left join qua_insp_plan p on p.id = i.plan_id where i.inspection_id = %s order by i.id""", (int(insp["id"]),))
    ng_qty = next((it["value_num"] for it in items if it["item_key"] == "ng_qty" and it["value_num"] is not None and it["value_num"] > 0), None)
    by = getattr(user, "login_id", None) or "hook"
    for it in items:
        if it["item_key"] not in common.CCP_KEYS or not _ccp_failed(it) or _issue_exists(cur, insp["id"], it["item_key"]):
            continue
        value = it["value_text"] if it["value_text"] is not None else (f"{float(it['value_num']):g}" if it["value_num"] is not None else t("미수집"))
        basis = it["standard"] or common.limit_text(it["min_value"], it["max_value"], it.get("plan_unit"))
        content = f"{t('CCP 이탈')} {it.get('label') or it['item_key']}[{it['item_key']}] {value} / {t('기준')} {basis}"
        if it["item_key"] == "metal_detect" and ng_qty is not None:
            content += f" · {t('불합격 수량')} {float(ng_qty):g}"
        _insert_issue(cur, process_id=it["plan_process_id"], lot_id=insp["lot_id"], inspection_id=insp["id"], content=content, occurred_at=insp.get("judged_at"), by=by)


# ── 3. 수집 정제 후 — 범위 이탈 · 염도 · 테이핑 집계 (hooks.md §3) ──
def _judge_range(cur, raw: dict, tag: str, value: Decimal) -> None:
    p = common.param_for(cur, raw["equipment_id"], tag)
    if p is None or (p["min_value"] is None and p["max_value"] is None):
        return                                                            # 선언 없음 · 범위 미확정 → 판정 안 함
    if common.out_of_range(value, p["min_value"], p["max_value"]):
        alarm.raise_env(cur, kind=tags.alarm_kind(tag, p["label"]), equipment_id=raw["equipment_id"], tag=tag, value=value,
                        limit_text=common.limit_text(p["min_value"], p["max_value"], p["unit"]), at=raw["ts"], param_id=p["id"])


def _judge_salinity(cur, raw: dict, value: Decimal) -> None:
    tank = common.open_tank_for_sensor(cur, raw["equipment_id"], raw["equip_code"])
    if tank is None or tank.get("target_salinity_pct") is None:
        return                                                            # 센서 ↔ 절임통 매핑 없음 · 목표 없음 → 판정 안 함 (D-206)
    tol = common.tank_tolerance(cur, tank)
    if tol is None:
        return                                                            # 허용편차 미확정 (임진강 D-08)
    target = Decimal(str(tank["target_salinity_pct"]))
    if abs(value - target) > tol:
        alarm.raise_env(cur, kind=tags.alarm_kind(tags.SALINITY_TAG), equipment_id=raw["equipment_id"], tag=tags.SALINITY_TAG, value=value,
                        limit_text=f"{float(target):g} ± {float(tol):g} %", at=raw["ts"], lot_id=tank.get("product_lot_id"), work_result_id=tank["id"])


def _run_status(v) -> str | None:
    s = str(v).strip().lower() if v is not None else ""
    if s in ("1", "1.0", "true", "run", "running", "on", "가동"):
        return "가동"
    if s in ("0", "0.0", "false", "stop", "stopped", "off", "정지"):
        return "정지"
    return None


def _taping(cur, raw: dict) -> None:
    cnt = common.dec(raw["tags"].get(tags.TAPING_COUNT_TAG))
    run = _run_status(raw["tags"].get(tags.TAPING_RUN_TAG)) if tags.TAPING_RUN_TAG in raw["tags"] else None
    if cnt is None and run is None:
        return
    r = common.one(cur, """select r.id, r.work_order_id from pop_work_result r join bas_process p on p.id = r.process_id
                            where r.equipment_id = %s and r.ended_at is null and p.process_code = %s order by r.started_at desc limit 1""",
                   (raw["equipment_id"], common.PACK_PROCESS))
    if r is None:
        log.warning("테이핑 수집 %s %s — 진행 중 포장 실적이 없다 (work_result_id NULL 로 쌓는다)", raw["equip_code"], raw["ts"])
    prev = common.one(cur, """select cum_count from x_kimchi_taping_log where equipment_id = %s and source = 'collect' and cum_count is not null
                               order by logged_at desc, id desc limit 1""", (raw["equipment_id"],))
    qty = Decimal(0)
    if cnt is not None:
        qty = cnt - prev["cum_count"] if prev and prev["cum_count"] is not None and cnt >= prev["cum_count"] else cnt      # 음수면 카운터 리셋
    cur.execute("""insert into x_kimchi_taping_log (equipment_id, work_result_id, work_order_id, pack_qty, cum_count, run_status, source, raw_id, logged_at, created_by)
                   values (%s, %s, %s, %s, %s, %s, 'collect', %s, %s, 'hook') on conflict (equipment_id, logged_at, source) do nothing""",
                (raw["equipment_id"], r["id"] if r else None, r["work_order_id"] if r else None, qty, cnt, run, raw["id"], raw["ts"]))


def on_collect(cur, raw: dict, user=None) -> None:
    if raw.get("duplicate"):
        return
    for tag, v in (raw.get("tags") or {}).items():
        if tag in (tags.TAPING_COUNT_TAG, tags.TAPING_RUN_TAG):
            continue
        value = common.dec(v)
        if value is None:
            continue                                                      # 글자 값은 범위 판정 대상이 아니다
        if tag == tags.SALINITY_TAG:
            _judge_salinity(cur, raw, value)
        else:
            _judge_range(cur, raw, tag, value)
    if tags.TAPING_COUNT_TAG in raw.get("tags", {}) or tags.TAPING_RUN_TAG in raw.get("tags", {}):
        _taping(cur, raw)


# ── 4. 실적 종료 후 — 절임통 retag · 손실률 · 세척 품목 기준 (hooks.md §4) ──
def _upsert_measure(cur, work_result_id: int, param: dict | None, key: str, value, *, source: str, deviated: bool, by: str) -> None:
    cur.execute("""insert into pop_measure (work_result_id, param_id, param_key, value_num, unit, source, deviated, measured_at, created_by)
                   values (%s, %s, %s, %s, %s, %s, %s, now(), %s)
                   on conflict (work_result_id, param_key) do update set value_num = excluded.value_num, source = excluded.source, deviated = excluded.deviated,
                       measured_at = now(), updated_at = now(), updated_by = excluded.created_by""",
                (int(work_result_id), param["id"] if param else None, key, value, (param or {}).get("unit"), source, deviated, by))


def on_result_closed(cur, result: dict, user) -> None:
    by = getattr(user, "login_id", None) or "hook"
    code = common.process_code_of(cur, result.get("process_id"))
    values = {r["param_key"]: r for r in common.rows(cur, "select * from pop_measure where work_result_id = %s", (int(result["id"]),))}
    item = common.item_of_work_order(cur, result.get("work_order_id"))

    if code == common.SALTING_PROCESS:
        tank = common.tank_row(cur, result["id"])
        if tank is not None and result.get("product_lot_id"):
            lineage.retag(cur, result["product_lot_id"], TANK_KIND, by=by)
            common.ensure_lot_ext(cur, result["product_lot_id"], by, tank_equipment_id=tank["equipment_id"])
            # 절임 완료(F-X-TANK-03)는 여기서 대신하지 않는다 — "완료 전 실적 종료는 422 가 아니다(순서 자유) · 둘 다 끝나야 완료" (function-list F-X-TANK-03).
            # 그래야 종료 뒤에도 진행 중 배치의 염도 이탈 알람이 TANK LOT(lot_id)에 붙는다 (gates S3 · salinity_alarm_lot_kind=TANK).
            if tank.get("sensor_equipment_id") is not None:
                v = collect.aggregate(tank["sensor_equipment_id"], tags.SALINITY_TAG, tank["started_at"], result.get("ended_at") or tank["ended_at"], "last")
                if v is not None:
                    row = values.get(tags.SALINITY_TAG)
                    if row is None or row["value_num"] is None:
                        _upsert_measure(cur, result["id"], common.param_by_code(cur, code, tags.SALINITY_TAG), tags.SALINITY_TAG, Decimal(str(v)), source="collect", deviated=False, by=by)
                    if tank["final_salinity_pct"] is None:
                        cur.execute("update x_kimchi_tank set final_salinity_pct = %s, updated_at = now(), updated_by = %s where id = %s", (Decimal(str(v)), by, tank["id"]))
        for key in WASH_KEYS:                                              # 세척 — 품목별 기준 대비 (코어는 공정 범위만 봤다)
            row = values.get(key)
            if row is None or row["value_num"] is None or item is None:
                continue
            std = common.std_for(cur, item["id"], key)
            if std and common.out_of_range(row["value_num"], std["min_value"], std["max_value"]) and not row["deviated"]:
                cur.execute("update pop_measure set deviated = true, updated_at = now(), updated_by = %s where id = %s", (by, row["id"]))

    elif code == common.PRETREAT_PROCESS:
        vin, vout = values.get(IN_KEY), values.get(OUT_KEY)
        if vin and vout and vin["value_num"] and vout["value_num"] is not None and vin["value_num"] > 0:
            loss = ((vin["value_num"] - vout["value_num"]) / vin["value_num"] * 100).quantize(Decimal("0.01"))
            p = common.param_by_code(cur, code, LOSS_KEY)
            dev = common.out_of_range(loss, p["min_value"] if p else None, p["max_value"] if p else None)
            _upsert_measure(cur, result["id"], p, LOSS_KEY, loss, source="manual", deviated=dev, by=by)          # D-510
            if dev:
                mark = f"[result:{result['id']}:{LOSS_KEY}]"
                content = f"{t('손실률 기준 초과')} {mark} {float(loss):g} % / {t('기준')} {common.limit_text(p['min_value'], p['max_value'], '%') if p else t('미확정')}"
                cur.execute("select 1 as x from qua_issue where source = 'hook' and position(%s in content) > 0", (mark,))
                if cur.fetchone() is None:                                   # 멱등 — 같은 실적은 1건
                    _insert_issue(cur, process_id=result.get("process_id"), lot_id=result.get("product_lot_id"), inspection_id=None, content=content,
                                  occurred_at=result.get("ended_at"), by=by)


# ── 5. 지표 — kpi_extra(frm, to, by=None) (hooks.md §5 · D-508) ──
def _kg(qty, unit: str | None, item_attrs: dict | None) -> Decimal | None:
    """kg 환산 — 단위가 kg 가 아니면 bas_item.attrs.capacity_kg 로, 없으면 None(제외)."""
    if qty is None:
        return None
    q = Decimal(str(qty))
    if (unit or "").strip().lower() == "kg":
        return q
    cap = common.dec((item_attrs or {}).get("capacity_kg"))
    return q * cap if cap is not None else None


def _work_hours() -> Decimal:
    r = common.one(None, "select attrs from kpi_indicator where indicator_key = 'throughput_kg_per_h'")
    v = common.dec((r or {}).get("attrs", {}).get("work_hours_per_day")) if r else None
    return v if v is not None and v > 0 else WORK_HOURS_PER_DAY


def kpi_extra(frm, to, by=None) -> list[dict]:
    good_rows = common.rows(None, """select r.good_qty, r.unit, r.ended_at::date as day, i.attrs from pop_work_result r
                                      join bas_process p on p.id = r.process_id and p.process_code = %s
                                      join job_work_order w on w.id = r.work_order_id left join bas_item i on i.id = w.item_id
                                     where r.ended_at::date between %s and %s and r.good_qty is not null""", (common.PACK_PROCESS, frm, to))
    good, days, excluded = Decimal(0), set(), 0
    for r in good_rows:
        kg = _kg(r["good_qty"], r["unit"], r["attrs"])
        if kg is None:
            excluded += 1
            continue
        good += kg
        days.add(r["day"])
    hours = Decimal(len(days)) * _work_hours()
    throughput = float(good / hours) if hours > 0 else None

    defect = Decimal(0)
    for r in common.rows(None, """select d.qty, l.unit, i.attrs as item_attrs, c.attrs as code_attrs from qua_defect d
                                    join qua_inspection q on q.id = d.inspection_id join lot l on l.id = q.lot_id
                                    join bas_process p on p.id = l.process_id and p.process_code = %s
                                    join bas_defect_code c on c.id = d.defect_code_id left join bas_item i on i.id = l.item_id
                                   where q.judged_at::date between %s and %s""", (common.PACK_PROCESS, frm, to)):
        if not (r["code_attrs"] or {}).get("kpi_target_yn"):
            continue
        kg = _kg(r["qty"], r["unit"], r["item_attrs"])
        if kg is None:
            excluded += 1
        else:
            defect += kg
    for r in common.rows(None, """select s.qty, s.unit, i.attrs from pop_scrap s join pop_work_result r on r.id = s.work_result_id
                                    join bas_process p on p.id = r.process_id and p.process_code = %s
                                    join job_work_order w on w.id = r.work_order_id left join bas_item i on i.id = w.item_id
                                   where s.scrapped_at::date between %s and %s""", (common.PACK_PROCESS, frm, to)):
        kg = _kg(r["qty"], r["unit"], r["attrs"])
        if kg is None:
            excluded += 1
        else:
            defect += kg
    total = good + defect
    defect_rate = float(defect / total * 100) if total > 0 else None

    aging = Decimal(0)
    for r in common.rows(None, "select remain_qty, unit, item_id, (select attrs from bas_item b where b.id = v.item_id) as attrs from x_kimchi_v_aging_stock v"):
        kg = _kg(r["remain_qty"], r["unit"], r["attrs"])
        if kg is None:
            excluded += 1
        else:
            aging += kg
    note = f"kg 환산 불가 제외 {excluded}" if excluded else None
    return [
        {"key": "throughput_kg_per_h", "label": "시간당 생산량", "value": throughput, "unit": "kg/h", "note": note},
        {"key": "fg_defect_rate", "label": "완제품 불량률", "value": defect_rate, "unit": "%", "note": note},
        {"key": "aging_stock_kg", "label": "숙성 재고", "value": float(aging), "unit": "kg", "note": note},
    ]
