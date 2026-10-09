"""foodservice 팩 훅 (E5) — `hooks.md` 사양 12개 + ext 복사(`after_save_<table>` · D-504) · 개발1 · 2026-10-09.

규칙 (contracts/pack-contract.md §5 · interfaces.md §9 · D-06)
- 동기 · 코어와 같은 트랜잭션(`cur`) · 거부는 `HookError`(422 hook_rejected) 뿐. 그 밖 예외는 500 — 조용히 삼키지 않는다.
- 코어 테이블 쓰기는 `pack.yaml: write_scope.hooks` = mat_requirement · qua_issue · job_lot · lot(= `lineage.retag` 경유만) 뿐.
  `x_foodservice_*` 는 자유. `lot_genealogy` · `sys_number_seq` 직접 SQL 0 (R8).
- 문구는 전부 `t()`. 값이 없으면 지어내지 않고 `(미확정)` 을 둔다 — 범위 NULL 이면 판정하지 않는다.
- ext 행은 코어가 `attrs` 로 받은 폼 값을 `after_save_<table>` 에서 같은 트랜잭션에 복사한다(hooks.md §10 "폼 → attrs → 훅이 ext 복사").
  시드처럼 훅을 거치지 않은 행은 `sync_ext(cur)` 가 같은 규칙으로 따라잡는다(이관 · 수동 적재 뒤 — 시드는 seeds[] 의 ext CSV).
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from mescore.app import lineage, numbering
from mescore.app.packs import t
from mescore.app.util.http import HookError
from mescore.db import conn

PACK_DIR = Path(__file__).resolve().parent
BATCH = "BATCH"                                   # pack.yaml: lineage.lot_kinds (base PRODUCT · D-501)
COOK_PROCESS_CODES = ("PRC-030", "PRC-040", "PRC-050", "PRC-060")   # 조리공정구분 — schema_ext.md item_ext CHECK
COLLECT_PROCESS_CODES = ("PRC-040", "PRC-060")                      # 교반기 자동 수집 공정 (D-206)
SERVING_UNIT = "인분"
QTY3 = Decimal("0.001")
SAMPLE_FREQ_RE = re.compile(r"(\d+)\s*솥당\s*(\d+)\s*솥")           # "10솥당 1솥" (니즈푸드 D-204)
UNDECIDED = "(미확정)"


# ── 0. 공통 — 보조 조회 (hooks.md §0) ───────────────────────────────────
def _q(cur, sql: str, params=None) -> list[dict]:
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def _q1(cur, sql: str, params=None) -> dict | None:
    cur.execute(sql, params)
    r = cur.fetchone()
    return dict(r) if r else None


def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "y", "yes", "on")


def _dec(v) -> Decimal | None:
    if v is None or str(v).strip() == "":
        return None
    return Decimal(str(v))


def _date(v) -> date | None:
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v).strip()[:10])


def _by(user) -> str | None:
    return getattr(user, "login_id", None) if user is not None else "hook"


def _field(name: str, label: str, reason: str) -> dict:
    return {"name": name, "label": t(label), "reason": reason}


def _item_ext(cur, item_id: int) -> dict | None:
    return _q1(cur, "select * from x_foodservice_item_ext where id = %s", (int(item_id),))


PACK_ATTR_KEYS = ("menu_type", "serve_qty_g", "material_type", "storage_cond", "expiry_mng_yn", "cook_process_code", "storage_temp")


def _pack_item(cur, item_id) -> dict | None:
    """급식 규칙의 적용 대상인가 — `x_foodservice_item_ext` 행이 있거나 `bas_item.attrs` 에 팩 속성 키가 하나라도 있는 품목.
    코어 예시 데이터(`-EX-` · attrs {}) 는 대상이 아니라 코어 테스트가 팩을 올린 채로도 그대로 통과한다 (pack-contract R9 · README 구현 메모)."""
    if item_id is None:
        return None
    item = _q1(cur, "select i.*, e.cook_process_id, e.storage_temp as ext_storage_temp from bas_item i left join x_foodservice_item_ext e on e.id = i.id where i.id = %s", (int(item_id),))
    if item is None:
        return None
    attrs = item.get("attrs") or {}
    if item["cook_process_id"] is not None or item["ext_storage_temp"] is not None or any(k in attrs for k in PACK_ATTR_KEYS):
        return item
    return None


def _cook_process_id(cur, item_id: int) -> int | None:
    ext = _item_ext(cur, item_id)
    return ext["cook_process_id"] if ext else None


def _active_bom(cur, item_id: int) -> dict | None:
    """`bas_bom.use_yn='Y'` 레시피 1건 + 구성품 + `batch_serve_qty`. 0건 None · 2건 이상 RuntimeError(validate 가 막았어야 한다)."""
    heads = _q(cur, "select b.*, e.batch_serve_qty from bas_bom b left join x_foodservice_bom_ext e on e.id = b.id where b.item_id = %s and b.use_yn = 'Y' order by b.id",
               (int(item_id),))
    if not heads:
        return None
    if len(heads) > 1:
        raise RuntimeError(f"메뉴 {item_id} 의 활성 레시피가 {len(heads)}건 — validate_bas_bom 이 막았어야 한다")
    bom = heads[0]
    bom["lines"] = _bom_lines(cur, bom["id"])
    return bom


def _bom_lines(cur, bom_id: int) -> list[dict]:
    return _q(cur, """select d.id, d.component_item_id, d.qty, d.unit, d.loss_rate, d.seq, i.item_code, i.item_name, i.unit as item_unit
                        from bas_bom_dtl d join bas_item i on i.id = d.component_item_id where d.bom_id = %s order by d.seq, d.id""", (int(bom_id),))


def _per_serving(qty, batch_serve_qty) -> Decimal:
    """1인량 = 배합량(1솥 기준) ÷ 배치 기준인분 (D-502)."""
    bsq = _dec(batch_serve_qty)
    if bsq is None or bsq <= 0:
        raise HookError(t("배치 기준인분이 0 입니다"), fields=[_field("attrs.batch_serve_qty", "배치(솥) 기준인분", str(batch_serve_qty))])
    return Decimal(str(qty)) / bsq


def _fifo_lot(cur, item_id: int) -> dict | None:
    """FIFO 추천 — 합격·조건부 · 잔량 > 0 · 유통기한 오름차순(NULL 뒤) · made_at 순 첫 LOT (TD4-017 기능 3)."""
    return _q1(cur, """select l.id, l.lot_no, e.expiry_date, s.remain_qty
                          from lot l join v_lot_stock s on s.lot_id = l.id left join x_foodservice_lot_ext e on e.id = l.id
                         where l.kind_base = 'MATERIAL' and l.item_id = %s and l.insp_status in ('합격', '조건부') and s.remain_qty > 0
                         order by e.expiry_date asc nulls last, l.made_at asc, l.id asc limit 1""", (int(item_id),))


def _upsert_ext(cur, table: str, id_: int, cols: dict, by: str | None) -> None:
    """`x_foodservice_<코어>_ext` 1:1 행 upsert — 코어 id 가 PK."""
    names = list(cols)
    sets = ", ".join(f"{c} = excluded.{c}" for c in names)
    cur.execute(f"""insert into {table} (id, {', '.join(names)}, created_by) values (%s, {', '.join(['%s'] * len(names))}, %s)
                    on conflict (id) do update set {sets}, updated_at = now(), updated_by = excluded.created_by""",
                [int(id_), *[cols[c] for c in names], by])


# ── 1. validate_bas_bom — F-BAS-05 · 06 (hooks.md §1) ─────────────────────
def validate_bas_bom(cur, row: dict, user) -> None:
    item = _pack_item(cur, row.get("item_id"))
    if item is None:
        return                                                        # 팩 품목이 아니다 — 코어 중립 흐름
    if item["item_type"] != "제품":
        raise HookError(t("레시피는 메뉴에만 등록합니다"), fields=[_field("item_id", "품목", item["item_code"] if item else str(row.get("item_id")))])
    attrs = row.get("attrs") or {}
    bsq = _dec(attrs.get("batch_serve_qty"))
    if bsq is None and row.get("id"):
        ext = _q1(cur, "select batch_serve_qty from x_foodservice_bom_ext where id = %s", (int(row["id"]),))
        bsq = ext["batch_serve_qty"] if ext else None
    if bsq is None or bsq <= 0:
        raise HookError(t("배치(솥) 기준인분이 필요합니다"), fields=[_field("attr_batch_serve_qty", "배치(솥) 기준인분", str(attrs.get("batch_serve_qty") or t("비어 있음")))])
    if (row.get("use_yn") or "Y") == "Y":
        other = _q1(cur, "select id, version from bas_bom where item_id = %s and use_yn = 'Y' and id <> coalesce(%s, 0)", (int(row["item_id"]), row.get("id")))
        if other:
            raise HookError(t("메뉴당 활성 레시피는 1건입니다 — 기존 버전을 비활성으로 바꾸세요"), fields=[_field("use_yn", "사용 여부", f"V{other['version']} {t('활성')}")])


def after_save_bas_bom(cur, row: dict, user) -> None:
    bsq = _dec((row.get("attrs") or {}).get("batch_serve_qty"))
    if bsq is not None and row.get("id"):
        _upsert_ext(cur, "x_foodservice_bom_ext", row["id"], {"batch_serve_qty": bsq}, _by(user))


# ── 2. validate_job_work_order — F-JOB-01 · 02 (hooks.md §2) ──────────────
def validate_job_work_order(cur, row: dict, user) -> None:
    item = _pack_item(cur, row.get("item_id"))
    if item is None:
        return                                                        # 팩 품목이 아니다 — 코어 중립 흐름
    if item["item_type"] != "제품":
        raise HookError(t("원재료에는 조리 지시를 낼 수 없습니다 — 메뉴를 고르세요"), fields=[_field("item_id", "품목", item["item_code"] if item else str(row.get("item_id")))])
    bom = _active_bom(cur, item["id"])
    if bom is None:
        raise HookError(t("활성 레시피가 없는 메뉴입니다 — 레시피를 먼저 등록하세요"), fields=[_field("item_id", "품목", item["item_code"])])
    if row.get("bom_id") is None:
        row["bom_id"] = bom["id"]
    elif _q1(cur, "select 1 as hit from bas_bom where id = %s and item_id = %s", (int(row["bom_id"]), item["id"])) is None:
        raise HookError(t("그 메뉴의 레시피가 아닙니다"), fields=[_field("bom_id", "BOM", str(row["bom_id"]))])
    if not row.get("unit"):
        row["unit"] = SERVING_UNIT
    elif str(row["unit"]).strip() != SERVING_UNIT:
        raise HookError(t("조리 지시 수량 단위는 인분입니다"), fields=[_field("unit", "단위", str(row["unit"]))])
    if row.get("process_id") is None:
        row["process_id"] = _cook_process_id(cur, item["id"])
        if row["process_id"] is None:
            raise HookError(t("조리 공정을 지정하세요"), fields=[_field("process_id", "공정", t("비어 있음"))])
    attrs = dict(row.get("attrs") or {})
    bom_attrs = bom.get("attrs") or {}
    if not attrs.get("caution_note") and bom_attrs.get("caution_note"):
        attrs["caution_note"] = bom_attrs["caution_note"]
    if "recipe" not in attrs:                                          # 지시 시점 레시피 스냅샷 — 조리 지시서(print/work_order.html) 가 찍는다
        bsq = bom.get("batch_serve_qty")
        attrs["recipe"] = {
            "version": bom["version"], "batch_serve_qty": float(bsq) if bsq is not None else None,
            "cook_step_desc": bom_attrs.get("cook_step_desc"), "caution_note": bom_attrs.get("caution_note"),
            "lines": [{"seq": ln["seq"], "item_code": ln["item_code"], "item_name": ln["item_name"], "qty": float(ln["qty"]), "unit": ln["unit"] or ln["item_unit"],
                       "per_serving": float(_per_serving(ln["qty"], bsq)) if bsq else None, "loss_rate": float(ln["loss_rate"] or 0)} for ln in bom["lines"]],
        }
    row["attrs"] = attrs


# ── 3. on_work_order_created — F-JOB-01 저장 후 · G-P04 핵심 (hooks.md §3) ──
def on_work_order_created(cur, wo: dict, user) -> None:
    if _pack_item(cur, wo.get("item_id")) is None:
        return                                                        # 팩 품목이 아니다 — 코어가 만든 job_lot 줄을 그대로 둔다
    bom = _q1(cur, "select b.*, e.batch_serve_qty from bas_bom b left join x_foodservice_bom_ext e on e.id = b.id where b.id = %s", (int(wo["bom_id"]),)) if wo.get("bom_id") else None
    if bom is None:
        bom = _active_bom(cur, wo["item_id"])
    if bom is None:
        raise HookError(t("활성 레시피가 없는 메뉴입니다 — 레시피를 먼저 등록하세요"), fields=[_field("item_id", "품목", str(wo.get("item_id")))])
    lines = _bom_lines(cur, bom["id"])
    plan_qty = Decimal(str(wo["plan_qty"]))
    period = _date(wo.get("plan_date")) or date.today()
    stocks = {r["item_id"]: r["qty"] for r in _q(cur, "select item_id, qty from mat_stock")}
    existing_lots = {r["item_id"]: r for r in _q(cur, "select id, item_id from job_lot where work_order_id = %s", (int(wo["id"]),))}
    for ln in lines:
        per = _per_serving(ln["qty"], bom.get("batch_serve_qty"))
        req = (plan_qty * per * (Decimal(1) + Decimal(str(ln["loss_rate"] or 0)) / Decimal(100))).quantize(QTY3, rounding=ROUND_HALF_UP)
        unit = ln["unit"] or ln["item_unit"]
        stock = Decimal(str(stocks.get(ln["component_item_id"], 0)))
        cur.execute("""insert into mat_requirement (period_from, period_to, item_id, required_qty, stock_qty, shortage_qty, unit, source, calc_at, created_by)
                       values (%(f)s, %(f)s, %(item)s, %(req)s, %(stock)s, greatest(%(req)s - %(stock)s, 0), %(unit)s, 'hook', now(), %(by)s)
                       on conflict (period_from, period_to, item_id, source) do update
                           set required_qty = mat_requirement.required_qty + excluded.required_qty, stock_qty = excluded.stock_qty,
                               shortage_qty = greatest(mat_requirement.required_qty + excluded.required_qty - excluded.stock_qty, 0),
                               unit = excluded.unit, calc_at = now(), updated_at = now(), updated_by = excluded.created_by""",
                    {"f": period, "item": ln["component_item_id"], "req": req, "stock": stock, "unit": unit, "by": _by(user)})
        fifo = _fifo_lot(cur, ln["component_item_id"])
        lot_id = fifo["id"] if fifo else None
        found = existing_lots.get(ln["component_item_id"])
        if found:                                                     # 코어 F-JOB-01 이 BOM 으로 만든 줄 — required_qty · lot_id 만 갱신 (중복 생성 금지)
            cur.execute("update job_lot set required_qty = %s, unit = %s, lot_id = %s, updated_at = now(), updated_by = %s where id = %s",
                        (req, unit, lot_id, _by(user), found["id"]))
        else:
            cur.execute("insert into job_lot (work_order_id, item_id, required_qty, unit, lot_id, created_by) values (%s, %s, %s, %s, %s, %s)",
                        (int(wo["id"]), ln["component_item_id"], req, unit, lot_id, _by(user)))


def on_work_order_canceled(cur, wo: dict, user) -> None:
    """F-JOB-04 취소 뒤 (D-505 · pack-contract §5) — on_work_order_created 가 더한 소요량을 같은 키 행에서 뺀다. 0 이하가 되면 행을 지운다."""
    if _pack_item(cur, wo.get("item_id")) is None or not wo.get("bom_id"):
        return
    bom = _q1(cur, "select b.id, e.batch_serve_qty from bas_bom b left join x_foodservice_bom_ext e on e.id = b.id where b.id = %s", (int(wo["bom_id"]),))
    if bom is None or bom["batch_serve_qty"] is None:
        return
    plan_qty = Decimal(str(wo["plan_qty"]))
    period = _date(wo.get("plan_date")) or _date(wo.get("created_at")) or date.today()
    for ln in _bom_lines(cur, bom["id"]):
        req = (plan_qty * _per_serving(ln["qty"], bom["batch_serve_qty"]) * (Decimal(1) + Decimal(str(ln["loss_rate"] or 0)) / Decimal(100))).quantize(QTY3, rounding=ROUND_HALF_UP)
        cur.execute("""update mat_requirement set required_qty = required_qty - %s, shortage_qty = greatest(required_qty - %s - stock_qty, 0), calc_at = now(),
                              updated_at = now(), updated_by = %s
                        where period_from = %s and period_to = %s and item_id = %s and source = 'hook'""", (req, req, _by(user), period, period, ln["component_item_id"]))
        cur.execute("delete from mat_requirement where period_from = %s and period_to = %s and item_id = %s and source = 'hook' and required_qty <= 0",
                    (period, period, ln["component_item_id"]))


# ── 4. on_result_closed — F-POP-03 종료 후 (hooks.md §4) ───────────────────
def on_result_closed(cur, result: dict, user) -> None:
    lot = result.get("product_lot")
    if not lot:
        raise RuntimeError("on_result_closed: result['product_lot'] 이 없다 — 코어 계약(interfaces.md §9) 위반")
    if _pack_item(cur, lot.get("item_id")) is None:
        return                                                        # 팩 품목이 아니다 — 코어 PRODUCT 그대로
    good, defect = _dec(result.get("good_qty")) or Decimal(0), _dec(result.get("defect_qty")) or Decimal(0)
    if defect > good:
        raise HookError(t("불량 인분이 생산 인분보다 많습니다"), fields=[_field("defect_qty", "불량", f"{defect} > {good}")])
    lineage.retag(cur, lot["id"], BATCH, by=_by(user))
    seq = _q1(cur, "select count(*) as n from pop_work_result where work_order_id = %s and ended_at is not null and id <= %s",
              (int(result["work_order_id"]), int(result["id"])))["n"]
    has_collect = any(m.get("source") == "collect" and m.get("value_num") is not None for m in (result.get("measures") or []))
    device = getattr(user, "device", None) if user is not None else None
    input_type = "자동(PLC)" if has_collect else ("POP수동" if device == "pop" else ("스마트패드" if device == "mobile" else None))
    _upsert_ext(cur, "x_foodservice_lot_ext", lot["id"],
                {"batch_seq": int(seq), "batch_no": f"B-{int(seq):02d}", "work_order_id": int(result["work_order_id"]), "work_result_id": int(result["id"]),
                 "input_type": input_type}, _by(user))


# ── 5. on_inspection_judged — F-QUA-05 · F-MAT-04 판정 후 (hooks.md §5) ───
def on_inspection_judged(cur, insp: dict, user) -> None:
    if insp.get("judgement") != "불합격" or insp.get("insp_type") not in ("공정", "최종"):
        return
    lot = _q1(cur, "select id, lot_no, process_id, kind from lot where id = %s", (int(insp["lot_id"]),))
    if lot is None or lot["kind"] != BATCH:
        return                                                        # 검식 = 배치(솥) LOT 만. 코어 PRODUCT 는 중립 흐름
    if _q1(cur, "select 1 as hit from qua_issue where inspection_id = %s", (int(insp["id"]),)):
        return                                                        # 멱등
    items = _q(cur, "select item_key, value_num, value_text, deviated from qua_insp_item where inspection_id = %s order by id", (int(insp["id"]),))
    foreign = any(x["item_key"] == "foreign_yn" and x["value_num"] is not None and x["value_num"] > 0 for x in items)
    detail = [f"{x['item_key']}={x['value_text'] if x['value_num'] is None else x['value_num']}" for x in items if x["deviated"] or (x["item_key"] == "foreign_yn" and foreign)]
    content = f"{t('검식 불합격')} — {lot['lot_no'] if lot else insp['lot_id']}" + (f" · {' · '.join(detail)}" if detail else "")
    no = numbering.next("ISSUE", cur=cur)
    cur.execute("""insert into qua_issue (issue_no, occurred_at, process_id, lot_id, inspection_id, content, status, source, attrs, created_by)
                   values (%s, %s, %s, %s, %s, %s, '발생', 'hook', %s::jsonb, %s)""",
                (no, insp.get("inspected_at") or datetime.now(), lot["process_id"] if lot else None, int(insp["lot_id"]), int(insp["id"]), content,
                 '{"issue_type": "%s"}' % ("이물" if foreign else "품질이상"), _by(user)))


# ── 6. validate_shipment — F-SHP-07 승인 직전 (hooks.md §6) ───────────────
def validate_shipment(cur, shipment: dict, lots: list[dict], user) -> None:
    ids = [int(l["lot_id"]) for l in lots]
    rows = _q(cur, "select id, lot_no, kind, kind_base, item_id, work_order_id from lot where id = any(%s)", (ids,)) if ids else []
    for r in rows:
        if r["kind_base"] == "MATERIAL" and _pack_item(cur, r["item_id"]) is not None:
            raise HookError(t("원료 LOT 은 출고 대상이 아닙니다"), fields=[_field("lot_no", "LOT", r["lot_no"])])
    allowed_items: set[int] | None = None
    if shipment.get("order_id"):
        allowed_items = {x["item_id"] for x in _q(cur, "select item_id from ord_order_dtl where order_id = %s", (int(shipment["order_id"]),))}
    for r in rows:
        if r["kind"] != BATCH:
            continue                                                  # 배치(솥) LOT 만 검식 규칙 — 코어 PRODUCT 는 중립 흐름
        if allowed_items is not None and r["item_id"] not in allowed_items:
            raise HookError(t("수주에 없는 메뉴입니다"), fields=[_field("lot_no", "LOT", r["lot_no"])])
        scope_ids = [x["id"] for x in _q(cur, "select id from lot where work_order_id = %s and kind_base = 'PRODUCT'", (r["work_order_id"],))] if r["work_order_id"] else [r["id"]]
        js = _q(cur, "select judgement from qua_inspection where lot_id = any(%s) and insp_type = '최종' and judgement is not null", (scope_ids,))
        if any(j["judgement"] == "불합격" for j in js):
            raise HookError(t("검식 합격 전 배치는 출고할 수 없습니다"), fields=[_field("lot_no", "LOT", f"{r['lot_no']} — {t('검식 불합격')}")])
        if not any(j["judgement"] == "합격" for j in js):              # R1' 같은 지시 안 하나라도 최종 합격이면 통과 (샘플링 — 가설)
            raise HookError(t("검식 합격 전 배치는 출고할 수 없습니다"), fields=[_field("lot_no", "LOT", f"{r['lot_no']} — {t('최종 검식 없음')}")])


# ── 7. on_collect — collect.receive 정제 후 (hooks.md §7) ─────────────────
def on_collect(cur, raw: dict, user=None) -> None:
    ext = _q1(cur, "select storage_kind, temp_limit, humi_limit from x_foodservice_equipment_ext where id = %s", (int(raw["equipment_id"]),))
    if not ext:
        return
    for tag, value in (raw.get("tags") or {}).items():
        try:
            v = Decimal(str(value).strip())
        except Exception:  # noqa: BLE001 — 글자 값 · 빈 값은 판정 대상이 아니다 (숫자만 임계와 비교한다)
            continue
        if tag == "PV_TEMP":
            limit = ext["temp_limit"] if ext["storage_kind"] in ("냉장", "냉동") else None
        elif tag == "TEMP":
            limit = ext["temp_limit"] if ext["storage_kind"] is None else None   # 온습도센서만 — 교반기 TEMP 는 실적 측정값(G-C24)이 본다
        elif tag == "HUMI":
            limit = ext["humi_limit"]
        else:
            limit = None
        if limit is None or v <= Decimal(str(limit)):
            continue
        c = _q1(cur, "select id from eqp_collect where equipment_id = %s and tag = %s and ts = %s", (int(raw["equipment_id"]), tag, raw["ts"]))
        cur.execute("""insert into x_foodservice_env_alarm (equipment_id, collect_id, tag, ts, value_num, limit_value, kind, created_by)
                       values (%s, %s, %s, %s, %s, %s, '상한 초과', 'hook') on conflict (equipment_id, tag, ts) do nothing""",
                    (int(raw["equipment_id"]), c["id"] if c else None, tag, raw["ts"], v, Decimal(str(limit))))


# ── 8. kpi_extra — stats.indicators · 현황판 (hooks.md §8) ─────────────────
def _kpi_meta() -> dict[str, dict]:
    """지표 정의 — DB `kpi_indicator`(목표 = target_value · 기준값 · 산식 = attrs.base_value · formula). 시드는 seeds[] 의 kpi_indicators.csv,
    화면(KPI-03)에서 목표를 고치면 그 값이 나온다."""
    out = {}
    for r in conn.q("select indicator_key, target_value, attrs from kpi_indicator"):
        a = r["attrs"] or {}
        out[r["indicator_key"]] = {"target_value": r["target_value"], "base_value": a.get("base_value"), "formula": a.get("formula")}
    return out


def _f(v) -> float | None:
    return None if v is None else float(v)


def kpi_extra(frm, to, by=None) -> list[dict]:
    meta = _kpi_meta()

    def row(key, label, value, unit, note=None):
        m = meta.get(key) or {}
        out = {"key": key, "label": t(label), "value": value, "unit": unit}
        if m.get("target_value") not in (None, ""):
            out["target"] = float(m["target_value"])
        if m.get("base_value") not in (None, ""):
            out["base"] = float(m["base_value"])
        if note or m.get("formula"):
            out["note"] = note or m.get("formula")
        return out

    p = conn.q1("""select sum(good_qty) as good, sum(extract(epoch from (ended_at - started_at))) / 3600 as hours
                     from pop_work_result where ended_at is not null and ended_at::date between %s and %s and ended_at - started_at >= interval '1 minute'""", (frm, to))
    hourly = None if not p or p["hours"] is None or float(p["hours"]) <= 0 else round(float(p["good"] or 0) / float(p["hours"]), 1)
    d = conn.q1("select sum(good_qty) as good, sum(defect_qty) as defect from pop_work_result where ended_at is not null and ended_at::date between %s and %s", (frm, to))
    tot = (_f(d["good"]) or 0) + (_f(d["defect"]) or 0) if d else 0
    defect_rate = None if tot <= 0 else round((_f(d["defect"]) or 0) / tot * 100, 3)
    r = conn.q1("""select (select count(distinct b.item_id) from bas_bom b join bas_item i on i.id = b.item_id where b.use_yn = 'Y' and i.item_type = '제품' and i.use_yn = 'Y') as with_recipe,
                          (select count(*) from bas_item where item_type = '제품' and use_yn = 'Y') as menus""")
    recipe_rate = None if not r or not r["menus"] else round(r["with_recipe"] / r["menus"] * 100, 1)
    q = conn.q1("""select count(*) filter (where judgement = '합격') as pass, count(*) as n from qua_inspection
                    where insp_type in ('공정', '최종') and judgement is not null and coalesce(judged_at, inspected_at)::date between %s and %s""", (frm, to))
    insp_rate = None if not q or not q["n"] else round(q["pass"] / q["n"] * 100, 1)
    s = conn.q1("""select coalesce(sum(l.qty), 0) as shipped from lot_genealogy g join lot l on l.id = g.parent_lot_id join lot x on x.id = g.child_lot_id
                    join shp_shipment sh on sh.id = x.shipment_id
                   where g.relation_base = '출하' and sh.status = '승인' and sh.ship_date between %s and %s""", (frm, to))
    o = conn.q1("select coalesce(sum(d.qty), 0) as ordered, count(*) as n from ord_order_dtl d join ord_order oo on oo.id = d.order_id where oo.status <> '취소' and oo.due_date between %s and %s", (frm, to))
    gap = None if not o or not o["n"] else round(float(s["shipped"]) - float(o["ordered"]), 3)
    a = conn.q1("select count(*) as n from x_foodservice_env_alarm where ts::date between %s and %s", (frm, to))
    plans = conn.q("""select p.id, p.plan_qty, p.item_id, pe.batch_std_qty, be.batch_serve_qty
                        from ord_plan p
                        left join x_foodservice_item_ext ie on ie.id = p.item_id
                        left join x_foodservice_process_ext pe on pe.id = ie.cook_process_id
                        left join bas_bom b on b.item_id = p.item_id and b.use_yn = 'Y'
                        left join x_foodservice_bom_ext be on be.id = b.id
                       where p.status <> '취소' and p.plan_date between %s and %s""", (frm, to))
    batches, skipped = 0, 0
    for pl in plans:
        base = pl["batch_std_qty"] or pl["batch_serve_qty"]
        if base is None or float(base) <= 0:
            skipped += 1
            continue
        batches += math.ceil(float(pl["plan_qty"]) / float(base))
    return [
        row("hourly_output", "시간당 생산량", hourly, "인분/시간"),
        row("defect_rate", "완제품 불량률", defect_rate, "%"),
        row("recipe_std_rate", "레시피 표준화율", recipe_rate, "%", note=f"{t('분모')}: {t('전체 레시피 모집단')} {UNDECIDED[:-1]} D-10)"),
        row("insp_pass_rate", "검식 적합률", insp_rate, "%"),
        row("order_ship_gap", "수주 대비 출고 차이", gap, "인분"),
        row("env_alarm_count", "보관온도 이탈 건수", int(a["n"]) if a else 0, "건"),
        row("plan_batch_count", "계획 배치(솥)수", None if not plans else batches, "솥", note=(f"{t('기준인분 없는 계획')} {skipped}" if skipped else None)),
    ]


# ── 9. validate_pop_input — F-POP-06 투입 스캔 직전 (hooks.md §9) ─────────
def validate_pop_input(cur, row: dict, user) -> None:
    ext = _q1(cur, "select expiry_date from x_foodservice_lot_ext where id = %s", (int(row["material_lot_id"]),))
    if ext and ext["expiry_date"] is not None and ext["expiry_date"] < date.today():
        lot = _q1(cur, "select lot_no from lot where id = %s", (int(row["material_lot_id"]),))
        raise HookError(t("유통기한이 지난 원료 LOT 입니다"), fields=[_field("barcode", "원재료 LOT", f"{lot['lot_no'] if lot else row['material_lot_id']} ({ext['expiry_date']})")])
    rec = _q1(cur, """select jl.lot_id, l.lot_no, s.remain_qty from pop_work_result r join job_lot jl on jl.work_order_id = r.work_order_id
                        join lot m on m.id = %s and m.item_id = jl.item_id
                        left join lot l on l.id = jl.lot_id left join v_lot_stock s on s.lot_id = jl.lot_id
                       where r.id = %s limit 1""", (int(row["material_lot_id"]), int(row["work_result_id"])))
    if rec and rec["lot_id"] and rec["lot_id"] != int(row["material_lot_id"]) and rec["remain_qty"] is not None and rec["remain_qty"] > 0:
        row.setdefault("attrs", {})["fifo_warning"] = t("추천 LOT") + f" {rec['lot_no']} " + t("보다 유통기한이 늦습니다")   # 경고만 — 거부하지 않는다


# ── 10. validate_mat_receipt · on_lot_created — F-MAT-01 (hooks.md §10) ───
def validate_mat_receipt(cur, row: dict, user) -> None:
    item = _q1(cur, "select item_code, attrs from bas_item where id = %s", (int(row["item_id"]),))
    attrs = row.get("attrs") or {}
    expiry = _date(attrs.get("expiry_date"))
    if item and _truthy((item.get("attrs") or {}).get("expiry_mng_yn")) and expiry is None:
        raise HookError(t("유통기한관리 대상 자재는 유통기한이 필요합니다"), fields=[_field("attr_expiry_date", "유통기한", item["item_code"])])
    rdate = _date(row.get("receipt_date"))
    if expiry is not None and rdate is not None and expiry < rdate:
        raise HookError(t("유통기한이 입고일보다 빠릅니다"), fields=[_field("attr_expiry_date", "유통기한", f"{expiry} < {rdate}")])


def on_lot_created(cur, lot: dict, user) -> None:
    if lot.get("kind_base") != "MATERIAL":
        return
    expiry = _date((lot.get("attrs") or {}).get("expiry_date"))
    if expiry is not None:
        _upsert_ext(cur, "x_foodservice_lot_ext", lot["id"], {"expiry_date": expiry}, _by(user))


# ── 11. validate_qua_issue — F-QUA-08 (hooks.md §11) ──────────────────────
def validate_qua_issue(cur, row: dict, user) -> None:
    attrs = row.get("attrs") or {}
    if attrs.get("issue_type") == "클레임" and not str(attrs.get("partner_code") or "").strip():
        raise HookError(t("클레임은 고객사가 필요합니다"), fields=[_field("attr_partner_code", "고객사", t("비어 있음"))])


# ── ext 복사 — after_save_<table> (D-504 자리 · 코어가 attrs 로 받은 값을 같은 트랜잭션에 ext 로) ──
def after_save_bas_item(cur, row: dict, user) -> None:
    attrs = row.get("attrs") or {}
    code, temp = attrs.get("cook_process_code"), _dec(attrs.get("storage_temp"))
    if code is None and temp is None:
        return
    pid = None
    if code:
        if code not in COOK_PROCESS_CODES:
            raise HookError(t("조리공정구분은 무침 · 취사 · 조리 · 볶음 공정 중 하나입니다"), fields=[_field("attr_cook_process_code", "조리공정구분", str(code))])
        if (row.get("item_type") or "") != "제품":
            raise HookError(t("조리공정구분은 메뉴에만 둡니다"), fields=[_field("attr_cook_process_code", "조리공정구분", str(row.get("item_code")))])
        proc = _q1(cur, "select id from bas_process where process_code = %s", (code,))
        if proc is None:
            raise HookError(t("없는 공정입니다"), fields=[_field("attr_cook_process_code", "조리공정구분", str(code))])
        pid = proc["id"]
    _upsert_ext(cur, "x_foodservice_item_ext", row["id"], {"cook_process_id": pid, "storage_temp": temp}, _by(user))


def after_save_bas_process(cur, row: dict, user) -> None:
    attrs = row.get("attrs") or {}
    cols = {"collect_type": attrs.get("collect_type") or None, "std_lead_min": int(float(attrs["std_lead_min"])) if attrs.get("std_lead_min") not in (None, "") else None,
            "batch_std_qty": _dec(attrs.get("batch_std_qty"))}
    if any(v is not None for v in cols.values()):
        _upsert_ext(cur, "x_foodservice_process_ext", row["id"], cols, _by(user))


def after_save_bas_equipment(cur, row: dict, user) -> None:
    attrs = row.get("attrs") or {}
    cols = {"storage_kind": attrs.get("storage_kind") or None, "temp_limit": _dec(attrs.get("temp_limit")), "humi_limit": _dec(attrs.get("humi_limit")),
            "collect_path": attrs.get("collect_path") or None}
    if cols["storage_kind"] not in (None, "냉장", "냉동"):
        raise HookError(t("냉장/냉동 구분 값이 아닙니다"), fields=[_field("attr_storage_kind", "냉장/냉동 구분", str(cols["storage_kind"]))])
    if any(v is not None for v in cols.values()):
        _upsert_ext(cur, "x_foodservice_equipment_ext", row["id"], cols, _by(user))


def after_save_ord_order(cur, row: dict, user) -> None:
    attrs = row.get("attrs") or {}
    due, svc = attrs.get("due_time"), attrs.get("service_type") or None
    due_t = None
    if due not in (None, ""):
        try:
            due_t = time.fromisoformat(str(due).strip())
        except ValueError:
            raise HookError(t("납기시간은 HH:MM 형식입니다"), fields=[_field("attr_due_time", "납기시간(HH:MM)", str(due))]) from None
    if svc not in (None, "이동급식", "위탁급식"):
        raise HookError(t("급식유형 값이 아닙니다"), fields=[_field("attr_service_type", "급식유형", str(svc))])
    if due_t is not None or svc is not None:
        _upsert_ext(cur, "x_foodservice_order_ext", row["id"], {"due_time": due_t, "service_type": svc}, _by(user))


def after_save_qua_insp_plan(cur, row: dict, user) -> None:
    attrs = row.get("attrs") or {}
    freq = attrs.get("sample_freq")
    if not freq and not attrs.get("sample_qty") and not attrs.get("apply_from"):
        return
    m = SAMPLE_FREQ_RE.search(str(freq or ""))
    _upsert_ext(cur, "x_foodservice_insp_plan_ext", row["id"],
                {"sample_freq": freq or None, "sample_n": int(m.group(1)) if m else None, "sample_k": int(m.group(2)) if m else None,
                 "sample_qty": _dec(attrs.get("sample_qty")), "apply_from": _date(attrs.get("apply_from"))}, _by(user))


def sync_ext(cur, by: str = "seed:foodservice") -> dict[str, int]:
    """시드처럼 훅을 거치지 않고 들어온 코어 행의 `attrs` 를 같은 규칙으로 ext 에 따라잡는다 (이관 · 수동 적재 뒤). 돌려주는 값은 테이블별 처리 행 수."""
    class _U:  # noqa: D401 — login_id 만 있는 사용자 대역
        login_id = by
    n: dict[str, int] = {}
    for table, fn in (("bas_item", after_save_bas_item), ("bas_bom", after_save_bas_bom), ("bas_process", after_save_bas_process),
                      ("bas_equipment", after_save_bas_equipment), ("ord_order", after_save_ord_order), ("qua_insp_plan", after_save_qua_insp_plan)):
        rows = _q(cur, f"select * from {table} where attrs <> '{{}}'::jsonb")
        for r in rows:
            fn(cur, r, _U())
        n[table] = len(rows)
    return n
