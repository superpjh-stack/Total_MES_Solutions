"""age — X-AGE-01 숙성 재고 · X-AGE-02 냉장고 입출고 (F-X-AGE-01~07 · 개발3).

쓰는 테이블: x_kimchi_lot_ext · x_kimchi_cold_move + `lot` · `lot_genealogy` 는 **`lineage.split(relation=숙성, kind=AGING)` · `lineage.retag` 경유만**(write_scope.age). 직접 SQL 0.

숙성 투입(F-X-AGE-01)의 계보: 코어 `lineage.split` 은 N ≥ 2 만 받는다(D-503 은 merge 쪽만 N ≥ 1). 그래서 1차는
  · 부분 수량 → `split(count=2, qtys=[숙성 수량, 잔량], relation=숙성, kind=AGING)` 뒤 잔량 LOT 을 `retag(PRODUCT)`(잔량은 새 번호의 포장 LOT 재고)
  · 전량      → 새 LOT 없이 그 LOT 을 `retag(AGING)` (계보 행 0)
코어가 분할 계열 팩 relation 에 N ≥ 1 을 허용하면 둘 다 `split(count=1)` 한 줄로 바뀐다 — progress-dev3.md §3 코어 변경 요청.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Form, Request

from mescore.app import lineage, nav, printing, rbac, templating
from mescore.app.packs import t
from mescore.app.util import audit, http
from mescore.db import conn

from packs.kimchi import common
from packs.kimchi.adapters import collect_tags as tags
from packs.kimchi.common import f

router = APIRouter()
STOCK, MOVES = nav.path_of("X-AGE-01"), nav.path_of("X-AGE-02")
AGING_KIND, AGING_REL = "AGING", "숙성"
EXT, MOVE = "x_kimchi_lot_ext", "x_kimchi_cold_move"


def _fridges() -> list[dict]:
    return common.equipment_of_type(None, tags.FRIDGE)


def _require_fridge(equipment_id: str | None) -> dict:
    eid = f.int_id(equipment_id, "equipment_id", "냉장고", required=True)
    e = next((x for x in _fridges() if x["id"] == eid), None)
    if e is None:
        raise http.validation_error(t("냉장고가 아닙니다"), fields=[f.field_error("equipment_id", "냉장고", str(eid))])
    return e


def _balance(cur, lot_id: int, equipment_id: int) -> Decimal:
    r = common.one(cur, f"""select coalesce(sum(case when trx_type = '입고' then qty else -qty end), 0) as bal from {MOVE}
                            where lot_id = %s and equipment_id = %s and canceled_yn = 'N'""", (int(lot_id), int(equipment_id)))
    return Decimal(str(r["bal"])) if r else Decimal(0)


def _move(cur, *, lot, equipment_id: int, trx_type: str, qty, device: str, by: str) -> int:
    cur.execute(f"""insert into {MOVE} (lot_id, equipment_id, trx_type, qty, unit, device, moved_at, created_by) values (%s, %s, %s, %s, %s, %s, now(), %s) returning id""",
                (lot.id, equipment_id, trx_type, qty, lot.unit, device, by))
    return int(cur.fetchone()["id"])


# ── X-AGE-01 숙성 재고 ─────────────────────────────────────────────────
@router.get(STOCK)                                                                     # F-X-AGE-03 조회 — FIFO(투입일 오름차순)
def stock(request: Request, item_id: str | None = None, equipment_id: str | None = None, no: str | None = None, user: rbac.User = rbac.require_fn("F-X-AGE-03")):
    iid, eid = f.int_id(item_id, "item_id", "품목"), f.int_id(equipment_id, "equipment_id", "냉장고")
    rows = conn.q("""select * from x_kimchi_v_aging_stock where (%s::bigint is null or item_id = %s) and (%s::bigint is null or location_equipment_id = %s)
                      order by aging_start_date asc nulls last, lot_id limit 500""", (iid, iid, eid, eid))
    today = date.today()
    for r in rows:
        r["due_passed"] = bool(r["aging_due_date"] and r["aging_due_date"] <= today)
    ctx = {"rows": rows, "item_id": iid, "equipment_id": eid, "scan_no": no or "", "lot": None, "today": today,
           "item_options": f.options(conn.q("select id, item_code, item_name from bas_item where use_yn = 'Y' and item_type = '제품' order by item_code"), "id", "item_code", "item_name"),
           "fridge_options": f.options(_fridges(), "id", "equip_code", "equip_name"), "default_days": common.DEFAULT_AGING_DAYS,
           "total_qty": sum(float(r["remain_qty"] or 0) for r in rows), "label_base": STOCK}
    if no is not None and no.strip() != "":
        n = lineage.resolve(no)
        if n is None or n.kind_base != lineage.PRODUCT:
            return f.scan_miss(request, "age/stock.html", ctx, screen_id="X-AGE-01", no=no, what="생산 LOT")
        days, src = common.aging_days(None, n.item_id)
        ctx.update({"lot": n, "aging_days": days, "aging_days_source": src})
    return templating.render(request, "age/stock.html", ctx, screen_id="X-AGE-01")


@router.post(STOCK)                                                                    # F-X-AGE-01 숙성 투입 — lineage.split(relation=숙성, kind=AGING)
def aging_in(request: Request, equipment_id: str = Form(...), qty: str | None = Form(None), lot_no: str | None = Form(None), lot_id: str | None = Form(None),
             barcode: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-AGE-01")):
    n = common.resolve_lot(lot_no or barcode, lot_id)
    if n.kind_base != lineage.PRODUCT or n.state != lineage.IN_STOCK:
        raise http.validation_error(t("재고 상태의 생산 LOT 만 숙성에 넣을 수 있습니다"), fields=[f.field_error("lot_no", "생산 LOT", f"{n.no} {n.state}")])
    if n.insp_status not in lineage.USABLE_INSP:
        raise http.validation_error(t("검사에 통과하지 않은 LOT 입니다"), fields=[f.field_error("lot_no", "생산 LOT", f"{n.no} {n.insp_status}")])
    if n.kind == AGING_KIND:
        raise http.validation_error(t("이미 숙성 배치입니다"), fields=[f.field_error("lot_no", "생산 LOT", n.no)])
    fridge = _require_fridge(equipment_id)
    remain = Decimal(str(n.remain_qty)) if n.remain_qty is not None else None
    q = f.num(qty, "qty", "숙성 수량", positive=True) or remain
    if q is None:
        raise http.validation_error(t("숙성 수량이 필요합니다"), fields=[f.field_error("qty", "숙성 수량", t("필수"))])
    if remain is not None and q > remain + Decimal("0.0005"):
        raise http.validation_error(t("숙성 수량이 잔량을 넘습니다"), fields=[f.field_error("qty", "숙성 수량", f"{q} > {remain}")])
    days, src = common.aging_days(None, n.item_id)
    today = date.today()
    device = (request.query_params.get("device") or "web") if hasattr(request, "query_params") else "web"
    with conn.tx() as cur:
        if remain is not None and q < remain:
            children = lineage.split(cur, parent_id=n.id, count=2, by=user.login_id, qtys=[q, remain - q], relation=AGING_REL, kind=AGING_KIND, user=user)
            aging, rest = children[0], children[1]
            lineage.retag(cur, rest["id"], lineage.PRODUCT, by=user.login_id)                  # 잔량 LOT 은 포장 LOT 재고로 남는다
            cur.execute("update lot set insp_status = %s, updated_at = now(), updated_by = %s where id = any(%s)", (n.insp_status, user.login_id, [aging["id"], rest["id"]]))
            mode = "split"
        else:
            aging = lineage.retag(cur, n.id, AGING_KIND, by=user.login_id)                      # 전량 — LOT 자체가 숙성 배치 (계보 0행)
            rest, mode = None, "retag"
        common.ensure_lot_ext(cur, aging["id"], user.login_id, aging_start_date=today, aging_due_date=today + timedelta(days=days), shippable_yn="N",
                              location_equipment_id=fridge["id"])
        node = lineage.node(aging["id"], cur)
        _move(cur, lot=node, equipment_id=fridge["id"], trx_type="입고", qty=q, device=device, by=user.login_id)
    audit.log_change(request, user, "F-X-AGE-01", f"lot:{aging['lot_no']}", {"from": n.no, "qty": str(q), "days": days, "mode": mode, "fridge": fridge["equip_code"]})
    return http.saved(request, f"{t('숙성 투입')} {aging['lot_no']} · {t('예정')} {today + timedelta(days=days)}", back=STOCK,
                      data={"id": aging["id"], "lot_no": aging["lot_no"], "kind": AGING_KIND, "qty": float(q), "aging_days": days, "aging_days_source": src,
                            "aging_due_date": (today + timedelta(days=days)).isoformat(), "mode": mode, "parent_id": n.id,
                            "rest": {"id": rest["id"], "lot_no": rest["lot_no"], "qty": float(remain - q)} if rest else None})


@router.post(STOCK + "/{lot_id}/complete")                                             # F-X-AGE-02 숙성 완료(출하 가능) — 예정일 전은 사유 필수
def aging_complete(request: Request, lot_id: int, reason: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-AGE-02")):
    n = lineage.node(lot_id)
    if n is None or n.kind != AGING_KIND:
        raise http.validation_error(t("숙성 배치가 아닙니다"), fields=[f.field_error("lot_id", "생산 LOT", str(lot_id))])
    ext = common.lot_ext(None, lot_id) or {}
    if ext.get("shippable_yn") == "Y":
        raise http.validation_error(t("이미 완료한 숙성 배치입니다"), fields=[f.field_error("lot_id", "생산 LOT", n.no)])
    today = date.today()
    early = bool(ext.get("aging_due_date") and ext["aging_due_date"] > today)
    why = f.opt_text(reason)
    if early and not why:
        raise http.validation_error(t("예정일 전 완료는 사유가 필요합니다"), fields=[f.field_error("reason", "사유", t("필수"))])
    with conn.tx() as cur:
        common.ensure_lot_ext(cur, lot_id, user.login_id, shippable_yn="Y", aging_end_date=today)
    audit.log_change(request, user, "F-X-AGE-02", f"lot:{n.no}", {"early": early, "reason": why})
    return http.saved(request, f"{n.no} {t('숙성 완료 — 출하 가능')}", back=STOCK, data={"id": lot_id, "shippable_yn": "Y", "early": early})


@router.get(STOCK + "/{lot_id}/label")                                                 # F-X-AGE-04 라벨 — 코어 print/label_lot 재사용
def aging_label(request: Request, lot_id: int, size: str = "100x50", user: rbac.User = rbac.require_fn("F-X-AGE-04")):
    label = printing.label_for(lot_id, size=size)
    return printing.render_print(request, "label_lot", {"labels": [label], "size": size, **label}, screen_id="X-AGE-01")


# ── X-AGE-02 냉장고 입출고 ─────────────────────────────────────────────
@router.get(MOVES)                                                                     # F-X-AGE-07 조회 + 냉장고별 잔량
def cold_moves(request: Request, equipment_id: str | None = None, item_id: str | None = None, no: str | None = None, frm: str | None = None, to: str | None = None,
               trx_type: str | None = None, user: rbac.User = rbac.require_fn("F-X-AGE-07")):
    eid, iid = f.int_id(equipment_id, "equipment_id", "냉장고"), f.int_id(item_id, "item_id", "품목")
    d1, d2 = f.period(frm, to)
    tt = f.choice(trx_type, "trx_type", "구분", ("입고", "출고"), required=False)
    rows = conn.q(f"""select m.*, e.equip_code, e.equip_name, l.lot_no, l.kind, i.item_code, i.item_name from {MOVE} m join bas_equipment e on e.id = m.equipment_id
                      join lot l on l.id = m.lot_id left join bas_item i on i.id = l.item_id
                     where m.moved_at::date between %s and %s and m.canceled_yn = 'N' and (%s::bigint is null or m.equipment_id = %s) and (%s::bigint is null or l.item_id = %s)
                       and (%s::text is null or l.lot_no ilike %s) and (%s::text is null or m.trx_type = %s) order by m.moved_at desc, m.id desc limit 500""",
                  (d1, d2, eid, eid, iid, iid, f.opt_text(no), f"%{(no or '').strip()}%", tt, tt))
    summary = conn.q(f"""select e.id as equipment_id, e.equip_code, e.equip_name, coalesce(sum(case when m.trx_type = '입고' then m.qty else -m.qty end), 0) as balance,
                                count(distinct m.lot_id) filter (where m.id is not null) as lots
                           from bas_equipment e left join {MOVE} m on m.equipment_id = e.id and m.canceled_yn = 'N' where e.id = any(%s) group by e.id, e.equip_code, e.equip_name order by e.equip_code""",
                     ([x["id"] for x in _fridges()],))
    ctx = {"rows": rows, "summary": summary, "equipment_id": eid, "item_id": iid, "scan_no": no or "", "frm": d1, "to": d2, "trx_type": tt or "",
           "fridge_options": f.options(_fridges(), "id", "equip_code", "equip_name"),
           "item_options": f.options(conn.q("select id, item_code, item_name from bas_item where use_yn = 'Y' and item_type = '제품' order by item_code"), "id", "item_code", "item_name")}
    return templating.render(request, "age/cold_moves.html", ctx, screen_id="X-AGE-02")


def _resolve_product(barcode: str | None, lot_no: str | None, lot_id: str | None):
    n = common.resolve_lot(barcode or lot_no, lot_id)
    if n.kind_base != lineage.PRODUCT:
        raise http.validation_error(t("생산 LOT 만 냉장고에 넣고 뺍니다"), fields=[f.field_error("barcode", "생산 LOT", f"{n.no} {n.kind}")])
    if n.state == lineage.SHIPPED:
        raise http.validation_error(t("출하된 LOT 입니다"), fields=[f.field_error("barcode", "생산 LOT", n.no)])
    return n


@router.post(MOVES + "/in")                                                            # F-X-AGE-05 냉장고 입고
def cold_in(request: Request, equipment_id: str = Form(...), qty: str | None = Form(None), barcode: str | None = Form(None), lot_no: str | None = Form(None),
            lot_id: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-AGE-05")):
    n = _resolve_product(barcode, lot_no, lot_id)
    fridge = _require_fridge(equipment_id)
    q = f.num(qty, "qty", "수량", positive=True) or (Decimal(str(n.remain_qty)) if n.remain_qty is not None else None)
    if q is None:
        raise http.validation_error(t("수량이 필요합니다"), fields=[f.field_error("qty", "수량", t("필수"))])
    device = request.query_params.get("device") or "web"
    with conn.tx() as cur:
        mid = _move(cur, lot=n, equipment_id=fridge["id"], trx_type="입고", qty=q, device=device, by=user.login_id)
        common.ensure_lot_ext(cur, n.id, user.login_id, location_equipment_id=fridge["id"])
    audit.log_change(request, user, "F-X-AGE-05", f"{MOVE}:{mid}", {"lot_no": n.no, "qty": str(q), "fridge": fridge["equip_code"]})
    return http.saved(request, f"{n.no} → {fridge['equip_code']} {t('입고')}", back=MOVES, data={"id": mid, "lot_no": n.no, "qty": float(q), "location_equipment_id": fridge["id"]})


@router.post(MOVES + "/out")                                                           # F-X-AGE-06 냉장고 출고 (출하는 SHP-02)
def cold_out(request: Request, equipment_id: str = Form(...), qty: str | None = Form(None), barcode: str | None = Form(None), lot_no: str | None = Form(None),
             lot_id: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-AGE-06")):
    n = _resolve_product(barcode, lot_no, lot_id)
    fridge = _require_fridge(equipment_id)
    device = request.query_params.get("device") or "web"
    with conn.tx() as cur:
        bal = _balance(cur, n.id, fridge["id"])
        q = f.num(qty, "qty", "수량", positive=True) or bal
        if q <= 0 or q > bal + Decimal("0.0005"):
            raise http.validation_error(t("출고 수량이 냉장고 잔량을 넘습니다"), fields=[f.field_error("qty", "수량", f"{q} > {bal}")])
        mid = _move(cur, lot=n, equipment_id=fridge["id"], trx_type="출고", qty=q, device=device, by=user.login_id)
        left = bal - q
        if left <= 0:
            common.ensure_lot_ext(cur, n.id, user.login_id, location_equipment_id=None)
    audit.log_change(request, user, "F-X-AGE-06", f"{MOVE}:{mid}", {"lot_no": n.no, "qty": str(q), "fridge": fridge["equip_code"]})
    return http.saved(request, f"{n.no} ← {fridge['equip_code']} {t('출고')}", back=MOVES, data={"id": mid, "lot_no": n.no, "qty": float(q), "balance": float(left)})
