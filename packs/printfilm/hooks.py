"""printfilm 훅 (E5) — hooks.md 의 훅 6 + 코어가 실제로 부르는 자리 2 (개발2 · 2026-10-09).

서명은 pack-contract.md §5, 호출 지점은 interfaces.md §9. 전부 동기 · 코어 트랜잭션 안 · 거부는 HookError(422 hook_rejected), 그 밖 예외는 500.
코어 테이블 쓰기는 write_scope.hooks = [lot] 안에서만(lineage.retag 경유). 팩 테이블 x_printfilm_* 는 자유.

| 훅 | 코어 시점 | 하는 일 |
|---|---|---|
| on_result_closed | F-POP-03 생산 LOT 생성 후 | 인쇄 공정만 → lineage.retag(ROLL) + x_printfilm_lot_ext(process_type=인쇄, 설비) |
| validate_job_work_order | F-JOB-01 · 02 저장 직전 | 수주 상세 필수(D-506) · 제품만 · 판사양 · 아니록스 · 잉크조성 코드 검증 |
| after_save_job_work_order | F-JOB-01 · 02 저장 직후(같은 tx · row["id"] 있음 · D-504) | x_printfilm_job_work_order_ext upsert (등록 · 수정 모두 — CR-5 의 on_work_order_updated 대신) |
| on_work_order_created | F-JOB-01 저장 후 | 같은 upsert(멱등) — hooks.md §3 의 자리 |
| on_lot_created | LOT 생성 후 | 없음 — 라벨은 응답의 링크로 브라우저 인쇄(D-04) |
| validate_shipment | F-SHP-07 승인 직전 | 롤 아님 · 불합격 롤 · 다른 Job 의 롤 거부 (읽기만) |
| validate_shp_document | F-SHP-09 발행 직전 | 스냅샷 보강 — 롤별 ΔE · 판정 · 불량 · 길이 · 폭 · 공정 구분 · 출하 LOT 번호 (CR-8 의 임시 처리 · 발행 뒤 불변) |
| kpi_extra | stats.indicators 조회 시 | 평균 ΔE(검사) · 불합격 롤 수 · 재고 롤 수 · splice 건수 (읽기만) |
"""

from __future__ import annotations

from datetime import date
from typing import Any

from mescore.app import lineage
from mescore.app.packs import t
from mescore.app.util.http import HookError
from mescore.db import conn

ROLL = "ROLL"
PRINT, FINISH, SLIT = "인쇄", "후가공", "슬리팅"
PACK_BY = "printfilm"

#: Job attrs 키 → (팩 테이블, 코드 컬럼, ext 컬럼, 라벨)
JOB_LOOKUPS: tuple[tuple[str, str, str, str, str], ...] = (
    ("plate_code", "x_printfilm_plate", "plate_code", "plate_id", "판사양"),
    ("anilox_code", "x_printfilm_anilox", "anilox_code", "anilox_id", "아니록스"),
    ("ink_code", "x_printfilm_ink_formula", "ink_code", "ink_formula_id", "잉크조성"),
)


def _one(cur, sql: str, params=None) -> dict | None:
    cur.execute(sql, params)
    r = cur.fetchone()
    return dict(r) if r else None


def _field(name: str, label: str, reason: str) -> dict:
    return {"name": name, "label": t(label), "reason": reason}


# ── 1. 인쇄 롤 만들기 ──────────────────────────────────────────────────
def upsert_lot_ext(cur, lot_id: int, process_type: str, equipment_id: int | None, slit_seq: int | None, by: str | None) -> None:
    """x_printfilm_lot_ext 1행 — 재호출 멱등. rll 라우터도 같은 함수를 쓴다."""
    if process_type not in (PRINT, FINISH, SLIT):
        raise ValueError(f"공정 구분 {process_type!r} 은 인쇄 · 후가공 · 슬리팅 중 하나여야 한다")
    cur.execute("""insert into x_printfilm_lot_ext (id, process_type, equipment_id, slit_seq, created_by) values (%s, %s, %s, %s, %s)
                   on conflict (id) do update set process_type = excluded.process_type, equipment_id = excluded.equipment_id,
                       slit_seq = excluded.slit_seq, updated_at = now(), updated_by = excluded.created_by""",
                (int(lot_id), process_type, equipment_id, slit_seq, by or PACK_BY))


def on_result_closed(cur, result: dict, user) -> None:
    """F-POP-03 — result["product_lot"] 이 이미 있다. 인쇄 공정(bas_process.attrs.process_type = 인쇄)의 실적만 롤을 만든다(엘컴화인 P5 · D-13).
    후가공 · 슬리팅은 POP 이 아니라 X-RLL 화면(lineage.merge/split)에서 만든다."""
    lot = result.get("product_lot") or {}
    if not lot.get("id"):
        raise HookError(t("생산 LOT 이 만들어지지 않았습니다"), fields=[_field("product_lot", "생산 LOT", t("비어 있음"))])
    proc = _one(cur, "select process_code, process_name, attrs from bas_process where id = %s", (result.get("process_id"),))
    ptype = ((proc or {}).get("attrs") or {}).get("process_type")
    if ptype != PRINT:
        reason = f"{(proc or {}).get('process_code') or result.get('process_id')} — {t('공정 구분')} {ptype or t('미설정')}"
        raise HookError(t("인쇄 공정의 작업 실적만 롤을 만듭니다"), fields=[_field("process_id", "공정", reason)])
    by = getattr(user, "login_id", None)
    lineage.retag(cur, lot["id"], ROLL, by=by)
    upsert_lot_ext(cur, lot["id"], PRINT, result.get("equipment_id"), None, by)


# ── 2 · 3. Job 의 인쇄 기준 · 수주 ───────────────────────────────────────
def _resolve_job_refs(cur, attrs: dict | None) -> dict[str, int | None]:
    """attrs 의 코드 3 → ext FK 3. 없는 코드 · 미사용 코드는 HookError. 셋 다 비워도 된다(엘컴화인 F-JOB-01)."""
    out: dict[str, int | None] = {}
    for key, table, code_col, fk, label in JOB_LOOKUPS:
        code = str((attrs or {}).get(key) or "").strip()
        if not code:
            out[fk] = None
            continue
        row = _one(cur, f"select id, use_yn from {table} where {code_col} = %s", (code,))
        if row is None:
            raise HookError(t(f"없는 {label} 코드"), fields=[_field(f"attrs.{key}", label, code)])
        if row["use_yn"] != "Y":
            raise HookError(t(f"미사용 {label}"), fields=[_field(f"attrs.{key}", label, code)])
        out[fk] = int(row["id"])
    return out


def validate_job_work_order(cur, row: dict, user) -> None:
    """F-JOB-01 · 02 저장 직전 (row 는 저장될 값 · attrs 포함 · 수정 때만 id)."""
    if not row.get("order_dtl_id"):
        raise HookError(t("수주 상세를 골라야 합니다 — 고객 · 납기는 수주에서 옵니다"), fields=[_field("order_dtl_id", "수주 상세", t("비어 있음"))])   # D-506
    item = _one(cur, "select item_code, item_type from bas_item where id = %s", (row.get("item_id"),))
    if item is None or item["item_type"] != "제품":
        raise HookError(t("Job 의 품목은 제품만 고를 수 있습니다"), fields=[_field("item_id", "품목", f"{(item or {}).get('item_code') or row.get('item_id')} {(item or {}).get('item_type') or ''}".strip())])
    _resolve_job_refs(cur, row.get("attrs"))


def _upsert_job_ext(cur, row: dict, user) -> None:
    if not row.get("id"):
        return
    refs = _resolve_job_refs(cur, row.get("attrs"))
    by = getattr(user, "login_id", None) or PACK_BY
    if all(v is None for v in refs.values()):
        cur.execute("delete from x_printfilm_job_work_order_ext where id = %s", (int(row["id"]),))      # 셋 다 비면 행을 두지 않는다 (hooks.md §3)
        return
    cur.execute("""insert into x_printfilm_job_work_order_ext (id, plate_id, anilox_id, ink_formula_id, created_by) values (%s, %s, %s, %s, %s)
                   on conflict (id) do update set plate_id = excluded.plate_id, anilox_id = excluded.anilox_id, ink_formula_id = excluded.ink_formula_id,
                       updated_at = now(), updated_by = excluded.created_by""",
                (int(row["id"]), refs["plate_id"], refs["anilox_id"], refs["ink_formula_id"], by))


def after_save_job_work_order(cur, row: dict, user) -> None:
    """F-JOB-01 · 02 저장 직후 — 같은 tx · row["id"] 있음 (D-504). CR-5 `on_work_order_updated` 가 없어 여기서 등록 · 수정 둘 다 upsert."""
    _upsert_job_ext(cur, row, user)


def on_work_order_created(cur, wo: dict, user) -> None:
    """F-JOB-01 저장 후 — after_save 가 이미 넣었다. 같은 upsert(멱등). 소요량 · 생산 LOT 생성 없음(CR-1 · D-503)."""
    _upsert_job_ext(cur, wo, user)


# ── 4. 라벨 자동 출력 없음 ────────────────────────────────────────────────
def on_lot_created(cur, lot: dict, user) -> None:
    """의도적으로 비웠다 — 라벨은 응답의 라벨 링크로 브라우저 인쇄(엘컴화인 D-04 · D-206). 프린터 규격이 정해지면 after_commit_lot_created 로."""
    return


# ── 5. 출하 승인 직전 ─────────────────────────────────────────────────────
def validate_shipment(cur, shipment: dict, lots: list[dict], user) -> None:
    """F-SHP-07. lots = 담긴 LOT 행(lot_no · kind · insp_status · work_order_no …). 하나라도 걸리면 승인 실패 — 메시지에 롤 번호 목록."""
    not_roll = [l["lot_no"] for l in lots if l.get("kind") != ROLL]
    if not_roll:
        raise HookError(t("롤이 아닌 LOT 은 출하할 수 없습니다") + f": {', '.join(not_roll)}", fields=[_field("lots", "출하 LOT", ", ".join(not_roll))])
    failed = [l["lot_no"] for l in lots if l.get("insp_status") == "불합격"]
    if failed:
        raise HookError(t("불합격 롤이 있어 승인할 수 없습니다") + f": {', '.join(failed)}", fields=[_field("lots", "출하 LOT", ", ".join(failed))])
    jobs = sorted({str(l.get("work_order_no") or "") for l in lots})
    if len(jobs) > 1:
        raise HookError(t("출하 LOT 하나에는 한 Job 의 롤만 담습니다") + f": {' · '.join(j or '-' for j in jobs)}", fields=[_field("lots", "출하 LOT", ", ".join(jobs))])


# ── 5b. COA 스냅샷 보강 (CR-8 임시) ──────────────────────────────────────
def _roll_snapshot_extra(cur, lot_no: str) -> dict[str, Any]:
    r = _one(cur, """select l.id, l.attrs, l.insp_status, x.process_type, x.slit_seq, w.work_order_no
                       from lot l left join x_printfilm_lot_ext x on x.id = l.id left join job_work_order w on w.id = l.work_order_id
                      where l.lot_no = %s""", (lot_no,))
    if r is None:
        return {}
    attrs = r.get("attrs") or {}
    insp = _one(cur, "select id, judgement, inspected_at from qua_inspection where lot_id = %s order by inspected_at desc, id desc limit 1", (r["id"],))
    defects: list[dict] = []
    if insp:
        cur.execute("""select d.defect_code, d.defect_name, q.qty, q.position from qua_defect q join bas_defect_code d on d.id = q.defect_code_id
                        where q.inspection_id = %s order by q.id""", (insp["id"],))
        defects = [{"defect_code": x["defect_code"], "defect_name": x["defect_name"], "qty": float(x["qty"]) if x["qty"] is not None else None,
                    "position": x["position"]} for x in cur.fetchall()]
    return {"length_m": attrs.get("length_m"), "width_mm": attrs.get("width_mm"), "process_type": r["process_type"], "slit_seq": r["slit_seq"],
            "work_order_no": r["work_order_no"], "defects": defects}


def validate_shp_document(cur, row: dict, user) -> None:
    """F-SHP-09 발행 직전 — row["snapshot"] 을 **제자리에서** 보강한다(코어가 같은 객체를 json 으로 저장한다). 스냅샷은 발행 뒤 바뀌지 않는다(D-304).
    더하는 것: shipment.shipment_lot_no(바코드 값 · D-305) · lots[].{delta_e, judgement, inspected_at, defects, length_m, width_mm, process_type, slit_seq}."""
    snap = row.get("snapshot")
    if not isinstance(snap, dict):
        return
    x = _one(cur, "select lot_no from lot where shipment_id = %s and kind_base = 'SHIPMENT' order by id limit 1", (row.get("shipment_id"),))
    snap.setdefault("shipment", {})["shipment_lot_no"] = x["lot_no"] if x else None
    for l in snap.get("lots") or []:
        insp = l.get("inspection") or {}
        values = insp.get("values") or {}
        de = values.get("delta_e") or {}
        l.update({"delta_e": de.get("value"), "delta_e_deviated": bool(de.get("deviated")), "judgement": insp.get("judgement"),
                  "inspected_at": insp.get("inspected_at"), **_roll_snapshot_extra(cur, l["lot_no"])})
    snap["pack"] = PACK_BY


# ── 6. 인쇄 지표 ──────────────────────────────────────────────────────────
def kpi_extra(frm: date, to: date, by: str | None = None) -> list[dict]:
    """읽기만. 값이 없으면 None(화면 미수집). 산식은 hooks.md §6 — 기간 경계는 날짜 양 끝 포함."""
    avg = conn.q1("""select avg(qi.value_num) as v from qua_insp_item qi join qua_inspection n on n.id = qi.inspection_id
                      where qi.item_key = 'delta_e' and qi.value_num is not null and n.inspected_at::date between %s and %s""", (frm, to))
    fail = conn.q1("""select count(distinct n.lot_id) as v from qua_inspection n join lot l on l.id = n.lot_id
                       where l.kind = %s and n.judgement = '불합격' and n.judged_at::date between %s and %s""", (ROLL, frm, to))
    stock = conn.q1("select count(*) as v from v_lot_state s join lot l on l.id = s.lot_id where l.kind = %s and s.state = '재고'", (ROLL,))
    splice = conn.q1("select count(distinct child_lot_id) as v from lot_genealogy where relation = 'splice' and linked_at::date between %s and %s", (frm, to))
    return [
        {"key": "avg_delta_e", "label": "평균 ΔE (검사)", "value": None if avg["v"] is None else float(avg["v"]), "unit": None},
        {"key": "fail_roll_count", "label": "불합격 롤 수", "value": int(fail["v"]), "unit": "개"},
        {"key": "stock_roll_count", "label": "재고 롤 수", "value": int(stock["v"]), "unit": "개"},
        {"key": "splice_count", "label": "splice 건수", "value": int(splice["v"]), "unit": "건"},
    ]


__all__ = ["on_result_closed", "validate_job_work_order", "after_save_job_work_order", "on_work_order_created", "on_lot_created",
           "validate_shipment", "validate_shp_document", "kpi_extra", "upsert_lot_ext"]
