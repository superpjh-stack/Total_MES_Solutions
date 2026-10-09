"""shp 라우터 — 출하 등록 · LOT 스캔/승인 · 현황 · 성적서 (기능 10 · F-SHP-01~10) · 담당 개발3.

쓰는 테이블: `shp_shipment` · `shp_document` 와, **`lineage.ship` · `lineage.unship` 를 거친** `lot`(SHIPMENT) · `lot_genealogy`(출하) 뿐 (db-schema.md §2).
이 파일에 `lot` · `lot_genealogy` 에 쓰는 SQL 은 없다 — 담긴 LOT 은 읽기만 한다(계보 한 줄이 곧 "실렸다"). 출하 LOT 목록 테이블도 없다.
번호는 `numbering.next("SHIPMENT" | "DOCUMENT", cur=cur)` (개발1). 저장 순서: 검증 → `validate_<table>` → tx → `after_save_<table>`(D-504) → audit → saved.

흐름: 출하 등록(등록) → LOT 스캔(`lineage.ship` — 출하 LOT 이 없으면 만든다) → 승인(`validate_shipment` 훅 직전 · `after_commit("shipment_approved")`)
→ 성적서 발행(그 LOT 들의 **최신 검사 항목 값을 스냅샷 JSON** 으로) → 출력(스냅샷만 그린다 — 검사가 나중에 바뀌어도 발행본 불변).
승인 뒤에는 수정 · 취소 · 스캔 · 스캔 취소 모두 422. 취소는 스캔된 LOT 전부 `lineage.unship`.

  SHP-01 출하 등록    GET/POST /shp/shipments · POST /shp/shipments/{id} · /cancel · GET /shp/shipments/{id}/label (D-601)
  SHP-02 LOT 스캔 · 승인  GET /shp/scan?no= · POST /shp/scan · POST /shp/scan/cancel · POST /shp/shipments/{id}/approve
  SHP-03 출하 현황    GET /shp/status (모바일 390px)
  SHP-04 성적서       GET/POST /shp/documents · GET /shp/documents/{id}/print
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ...db import conn
from .. import nav, packs, rbac, stats, templating
from ..packs import t
from ..util import audit, http

router = APIRouter()

REGISTERED, APPROVED, CANCELED = "등록", "승인", "취소"
STATUSES: tuple[str, ...] = (REGISTERED, APPROVED, CANCELED)
DOC_TYPES: tuple[str, ...] = ("성적서", "거래명세서")
PASS, FAIL, COND = "합격", "불합격", "조건부"
LIST_LIMIT = 300


def _lineage():
    from .. import lineage  # noqa: PLC0415 — 개발2 모듈. 계보 쓰기는 여기뿐
    return lineage


def _numbering():
    from .. import numbering  # noqa: PLC0415 — 개발1 모듈
    return numbering


def _printing():
    from .. import printing  # noqa: PLC0415 — 개발2 모듈
    return printing


# ── 공통 ───────────────────────────────────────────────────────────────
_SHIPMENT_SQL = """
    select s.id, s.shipment_no, s.ship_date, s.status, s.approved_at, s.approved_by, s.note, s.partner_id, s.order_id, s.attrs, s.created_at, s.created_by,
           p.partner_code, p.partner_name, o.order_no, o.due_date,
           x.lot_no as shipment_lot_no,
           (select count(*)::int from lot_genealogy g where g.child_lot_id = x.id and g.relation_base = '출하') as lot_count,
           (select sum(g.qty) from lot_genealogy g where g.child_lot_id = x.id and g.relation_base = '출하') as total_qty,
           (select count(*)::int from shp_document d where d.shipment_id = s.id) as document_count
      from shp_shipment s
      join bas_partner p on p.id = s.partner_id
      left join ord_order o on o.id = s.order_id
      left join lot x on x.shipment_id = s.id and x.kind_base = 'SHIPMENT'
"""

#: 목록 조회 — 출하 한 건 SQL + 조건에 맞는 전체 건수(`total_count` · 상한 LIST_LIMIT 앞에서 센다)
_SEARCH_SQL = _SHIPMENT_SQL.replace(" as document_count\n", " as document_count,\n           count(*) over ()::int as total_count\n", 1)


def _total(rows: list[dict]) -> int:
    """`_search` 결과의 전체 건수를 꺼내고 행에서는 지운다."""
    total = rows[0]["total_count"] if rows else 0
    for r in rows:
        r.pop("total_count", None)
    return total


def _date(text: str | None, label: str, *, required: bool = False) -> date | None:
    try:
        d = stats.parse_date(text)
    except ValueError:
        raise http.validation_error(t("날짜 형식(YYYY-MM-DD)이 아닙니다"), fields=[{"name": label, "label": t(label), "reason": text}]) from None
    if d is None and required:
        raise http.validation_error(t("필수값을 입력해 주세요"), fields=[{"name": label, "label": t(label), "reason": t("비어 있음")}])
    return d


def _shipment(shipment_id: int) -> dict:
    row = conn.q1(_SHIPMENT_SQL + " where s.id = %s", (shipment_id,))
    if row is None:
        raise http.not_found()
    return row


def _by_no(no: str) -> dict | None:
    return conn.q1(_SHIPMENT_SQL + " where s.shipment_no = %s", (no.strip(),))


def _partner(code: str) -> dict:
    row = conn.q1("select id, partner_code, partner_name from bas_partner where partner_code = %s and use_yn = 'Y'", (code.strip(),))
    if row is None:
        raise http.validation_error(t("없는 거래처입니다"), fields=[{"name": "partner_code", "label": t("거래처"), "reason": code}])
    return row


def _order(order_no: str) -> dict | None:
    if not (order_no or "").strip():
        return None
    row = conn.q1("select id, order_no, partner_id, status from ord_order where order_no = %s", (order_no.strip(),))
    if row is None or row["status"] == "취소":
        raise http.validation_error(t("없는 수주입니다"), fields=[{"name": "order_no", "label": t("수주"), "reason": order_no}])
    return row


def _lots(shipment_id: int) -> list[dict]:
    """그 출하에 담긴 생산 LOT(스캔 순) + 각 LOT 의 최신 검사. **읽기만.**"""
    rows = conn.q("""
        select l.id as lot_id, l.lot_no, l.kind, l.qty as lot_qty, g.qty, l.unit, l.insp_status, i.item_code, i.item_name, w.work_order_no,
               g.linked_at as scanned_at, g.linked_by as scanned_by, g.id as genealogy_id
          from lot_genealogy g
          join lot x on x.id = g.child_lot_id
          join lot l on l.id = g.parent_lot_id
          left join bas_item i on i.id = l.item_id
          left join job_work_order w on w.id = l.work_order_id
         where x.shipment_id = %s and x.kind_base = 'SHIPMENT' and g.relation_base = '출하'
         order by g.id""", (shipment_id,))
    latest = _latest_inspections([r["lot_id"] for r in rows])
    for r in rows:
        r["inspection"] = latest.get(r["lot_id"])
    return rows


def _latest_inspections(lot_ids: list[int]) -> dict[int, dict]:
    """LOT 마다 최신 검사 1건 + 항목 값(F-SHP-09 스냅샷 재료). 읽기만."""
    if not lot_ids:
        return {}
    insps = conn.q("""
        select distinct on (n.lot_id) n.id, n.lot_id, n.insp_type, n.inspected_at, n.inspector, n.judgement, n.judged_at
          from qua_inspection n where n.lot_id = any(%s) order by n.lot_id, n.inspected_at desc, n.id desc""", (lot_ids,))
    out = {r["lot_id"]: {**r, "values": {}} for r in insps}
    if insps:
        for it in conn.q("""select qi.inspection_id, qi.item_key, qi.value_num, qi.value_text, qi.unit, qi.item_judgement, qi.deviated,
                                   p.label, p.standard, p.min_value, p.max_value, p.unit as plan_unit, p.seq
                              from qua_insp_item qi left join qua_insp_plan p on p.id = qi.plan_id
                             where qi.inspection_id = any(%s) order by p.seq nulls last, qi.item_key""", ([r["id"] for r in insps],)):
            for lot_id, insp in out.items():
                if insp["id"] == it["inspection_id"]:
                    insp["values"][it["item_key"]] = {"value": float(it["value_num"]) if it["value_num"] is not None else it["value_text"],
                                                      "deviated": bool(it["deviated"]), "item_judgement": it["item_judgement"],
                                                      "label": it["label"] or it["item_key"], "unit": it["unit"] or it["plan_unit"],
                                                      "standard": it["standard"], "min_value": it["min_value"], "max_value": it["max_value"], "seq": it["seq"]}
    return out


def _summary(lots: list[dict]) -> dict:
    judged = [l["inspection"]["judgement"] if l["inspection"] else None for l in lots]
    sm = {"lot_count": len(lots), "passed": judged.count(PASS), "failed": judged.count(FAIL), "conditional": judged.count(COND),
          "uninspected": sum(1 for j in judged if j is None)}
    if not lots:
        sm["judgement"] = None
    elif sm["failed"]:
        sm["judgement"] = FAIL
    elif sm["uninspected"]:
        sm["judgement"] = "미확정"
    elif sm["conditional"]:
        sm["judgement"] = COND
    else:
        sm["judgement"] = PASS
    return sm


def _search(no: str, partner: str, status: str, d1: date | None, d2: date | None, *, statuses: tuple[str, ...] | None = None) -> list[dict]:
    if status and status not in STATUSES:
        raise http.validation_error(t("상태가 올바르지 않습니다"), fields=[{"name": "status", "label": t("상태"), "reason": status}])
    return conn.q(_SEARCH_SQL + f"""
         where (%(no)s::text is null or s.shipment_no ilike '%%' || %(no)s::text || '%%' or o.order_no ilike '%%' || %(no)s::text || '%%')
           and (%(partner)s::text is null or p.partner_code ilike '%%' || %(partner)s::text || '%%' or p.partner_name ilike '%%' || %(partner)s::text || '%%')
           and (%(status)s::text is null or s.status = %(status)s::text)
           and (%(statuses)s::text[] is null or s.status = any(%(statuses)s::text[]))
           and (%(d1)s::date is null or s.ship_date >= %(d1)s::date) and (%(d2)s::date is null or s.ship_date <= %(d2)s::date)
         order by s.ship_date desc, s.id desc limit {LIST_LIMIT}""",
                  {"no": no.strip() or None, "partner": partner.strip() or None, "status": status or None,
                   "statuses": list(statuses) if statuses else None, "d1": d1, "d2": d2})


def _scan_error(request: Request, exc) -> dict | None:
    """스캔 진입 GET 의 422 — JSON 은 올리고, 브라우저는 그 화면을 422 로 다시 그린다 (api-contract.md §2)."""
    if not http.wants_html(request):
        raise exc
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return {"message": detail.get("message", ""), "fields": detail.get("fields") or []}


# ── SHP-01 출하 등록 ───────────────────────────────────────────────────
@router.get(nav.path_of("SHP-01"), response_class=HTMLResponse)                     # F-SHP-04 출하 조회 = 화면 GET
def shipments(request: Request, no: str = "", partner: str = "", status: str = "", frm: str = "", to: str = "", id: str = "",
              user: rbac.User = rbac.require_fn("F-SHP-04")):
    d1, d2 = _date(frm, "frm"), _date(to, "to")
    rows = _search(no, partner, status, d1, d2)
    total = _total(rows)
    opened, lots = None, []
    if id.strip():
        if not id.strip().isdigit():
            raise http.not_found()
        opened = _shipment(int(id))
        lots = _lots(opened["id"])
    partners = conn.q("select partner_code, partner_name from bas_partner where use_yn = 'Y' order by partner_code")
    orders = conn.q("select order_no, due_date from ord_order where status in ('등록', '진행') order by due_date nulls last, order_no limit 100")
    return templating.render(request, "shp/shipments.html", {
        "rows": rows, "total": total, "limit": LIST_LIMIT, "opened": opened, "lots": lots, "summary": _summary(lots), "partners": partners, "orders": orders,
        "statuses": STATUSES, "today": date.today(), "attr_specs": packs.attrs_of("shp_shipment"),
        "q": {"no": no, "partner": partner, "status": status, "frm": frm, "to": to},
    }, screen_id="SHP-01")


@router.post(nav.path_of("SHP-01"))                                                  # F-SHP-01 출하 등록
def create_shipment(request: Request, partner_code: str = Form(""), ship_date: str = Form(""), order_no: str = Form(""), note: str = Form(""),
                    user: rbac.User = rbac.require_fn("F-SHP-01")):
    if not partner_code.strip():
        raise http.validation_error(t("필수값을 입력해 주세요"), fields=[{"name": "partner_code", "label": t("거래처"), "reason": t("비어 있음")}])
    partner = _partner(partner_code)
    day = _date(ship_date, "ship_date") or date.today()
    order = _order(order_no)
    try:
        attrs = packs.read_attrs(request, "shp_shipment")
    except ValueError as exc:
        raise http.validation_error(str(exc)) from None
    with conn.tx() as cur:
        shipment_no = _numbering().next("SHIPMENT", cur=cur)
        row = {"shipment_no": shipment_no, "partner_id": partner["id"], "ship_date": day, "order_id": order["id"] if order else None,
               "status": REGISTERED, "note": note.strip() or None, "attrs": attrs}
        packs.hook("validate_shp_shipment")(cur, row, user)
        cur.execute("""insert into shp_shipment (shipment_no, partner_id, ship_date, order_id, status, note, attrs, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s) returning id""",
                    (shipment_no, partner["id"], day, row["order_id"], REGISTERED, row["note"], json.dumps(attrs, ensure_ascii=False), user.login_id))
        row["id"] = cur.fetchone()["id"]
        packs.hook("after_save_shp_shipment")(cur, row, user)                            # D-504
    audit.log_change(request, user, "F-SHP-01", f"shp_shipment:{shipment_no}")
    return http.saved(request, t("출하를 등록했습니다") + f" — {shipment_no}. " + t("이어서 LOT 을 스캔합니다"),
                      back=f"{nav.path_of('SHP-02')}?no={shipment_no}", data={"id": row["id"], "shipment_no": shipment_no})


@router.post(nav.path_of("SHP-01") + "/{shipment_id}")                                # F-SHP-02 출하 수정
def update_shipment(request: Request, shipment_id: int, partner_code: str = Form(None), ship_date: str = Form(None), order_no: str = Form(None),
                    clear_order: str = Form(""), note: str = Form(None), user: rbac.User = rbac.require_fn("F-SHP-02")):
    """빈 폼 값은 "바꾸지 않음" 이다(FastAPI 가 빈 문자열을 None 으로 준다). 수주 연결을 지우려면 `clear_order=1`."""
    s = _shipment(shipment_id)
    if s["status"] != REGISTERED:
        raise http.validation_error(t("승인되거나 취소된 출하는 수정할 수 없습니다"), fields=[{"name": "status", "label": t("상태"), "reason": s["status"]}])
    partner_id = _partner(partner_code)["id"] if partner_code is not None and partner_code.strip() else s["partner_id"]
    day = _date(ship_date, "ship_date") if ship_date is not None and ship_date.strip() else s["ship_date"]
    order_id = s["order_id"]
    if clear_order.strip() in ("1", "Y", "y", "true"):
        order_id = None
    elif order_no is not None and order_no.strip():
        order_id = _order(order_no)["id"]
    row = {**s, "partner_id": partner_id, "ship_date": day, "order_id": order_id, "note": note.strip() if note is not None else s["note"]}
    with conn.tx() as cur:
        packs.hook("validate_shp_shipment")(cur, row, user)
        cur.execute("""update shp_shipment set partner_id = %s, ship_date = %s, order_id = %s, note = %s, updated_at = now(), updated_by = %s
                        where id = %s and status = %s""", (partner_id, day, order_id, row["note"], user.login_id, shipment_id, REGISTERED))
        if cur.rowcount != 1:
            raise http.validation_error(t("출하 상태가 바뀌어 수정하지 못했습니다"), fields=[{"name": "status", "label": t("상태"), "reason": t("다시 조회")}])
        packs.hook("after_save_shp_shipment")(cur, row, user)
    audit.log_change(request, user, "F-SHP-02", f"shp_shipment:{s['shipment_no']}")
    return http.saved(request, t("출하를 수정했습니다"), back=f"{nav.path_of('SHP-01')}?id={shipment_id}", data={"id": shipment_id, "shipment_no": s["shipment_no"]})


@router.post(nav.path_of("SHP-01") + "/{shipment_id}/cancel")                         # F-SHP-03 출하 취소
def cancel_shipment(request: Request, shipment_id: int, user: rbac.User = rbac.require_fn("F-SHP-03")):
    s = _shipment(shipment_id)
    if s["status"] != REGISTERED:
        reason = t("승인된 출하는 취소할 수 없습니다") if s["status"] == APPROVED else t("이미 취소된 출하입니다")
        raise http.validation_error(reason, fields=[{"name": "status", "label": t("상태"), "reason": s["status"]}])
    lots = _lots(shipment_id)
    with conn.tx() as cur:                                     # 계보 되돌림(unship)과 상태 변경은 한 트랜잭션
        row = {**s, "status": CANCELED}
        packs.hook("validate_shp_shipment")(cur, row, user)
        for l in lots:
            _lineage().unship(cur, shipment_id=shipment_id, lot_id=l["lot_id"], by=user.login_id, user=user)
        cur.execute("update shp_shipment set status = %s, updated_at = now(), updated_by = %s where id = %s and status = %s",
                    (CANCELED, user.login_id, shipment_id, REGISTERED))
        if cur.rowcount != 1:
            raise http.validation_error(t("출하 상태가 바뀌어 취소하지 못했습니다"), fields=[{"name": "status", "label": t("상태"), "reason": t("다시 조회")}])
        packs.hook("after_save_shp_shipment")(cur, row, user)
    audit.log_change(request, user, "F-SHP-03", f"shp_shipment:{s['shipment_no']}", {"unshipped": len(lots)})
    return http.saved(request, t("출하를 취소했습니다") + f" — {s['shipment_no']}", back=nav.path_of("SHP-01"),
                      data={"id": shipment_id, "shipment_no": s["shipment_no"], "status": CANCELED, "unshipped": len(lots)})


@router.get(nav.path_of("SHP-01") + "/{shipment_id}/label", response_class=HTMLResponse)   # 출하 라벨 (D-601 · 기능 수 밖)
def shipment_label(request: Request, shipment_id: int, user: rbac.User = rbac.require_screen("SHP-02")):
    _shipment(shipment_id)
    printing = _printing()
    return printing.render_print(request, "label_shipment", printing.shipment_label_for(shipment_id), screen_id="SHP-02")


# ── SHP-02 LOT 스캔 · 승인 ────────────────────────────────────────────
@router.get(nav.path_of("SHP-02"), response_class=HTMLResponse)                     # 화면 GET — ?no= 출하 번호(바코드) 로 연다
def scan_screen(request: Request, no: str = "", id: str = "", user: rbac.User = rbac.require_screen("SHP-02")):
    opened, lots, scan_error = None, [], None
    if no.strip():
        opened = _by_no(no)
        if opened is None:
            scan_error = _scan_error(request, http.validation_error(t("없는 출하 번호입니다"), fields=[{"name": "no", "label": t("출하"), "reason": no.strip()}]))
    elif id.strip():
        if not id.strip().isdigit():
            raise http.not_found()
        opened = _shipment(int(id))
    if opened is not None:
        lots = _lots(opened["id"])
    waiting = _search("", "", REGISTERED, None, None)[:50]
    _total(waiting)
    return templating.render(request, "shp/scan.html", {
        "opened": opened, "lots": lots, "summary": _summary(lots), "scan_error": scan_error, "waiting": waiting,
        "can_approve": user.can("F-SHP-07"), "can_scan": user.can("F-SHP-05"),
    }, screen_id="SHP-02", status_code=422 if scan_error else 200)


def _assert_remaining(cur, node) -> None:
    """DEF-QA2-008 (출하 경로) — 종료 전 실적에 투입 스캔돼(열린 투입) 잔량이 0 이하인 생산 LOT 은 출하 스캔 422.
    §3.4 회전 5 는 열린 투입이 상태를 바꾸지 않으므로(상태 `재고`) 상태만으로는 못 막는다. 잔량은 `v_lot_stock`(열린 투입 포함)을
    이 tx 안에서 다시 읽는다. LOT 수량이 없으면(NULL) 판정하지 않는다 — 개발2 `lineage.ship` 이 같은 검사를 갖게 되면 여기는 지운다."""
    r = cur.execute("select k.qty, k.remain_qty from v_lot_stock k where k.lot_id = %s", (int(node.id),)).fetchone()
    if r is None or r["qty"] is None or r["remain_qty"] is None or r["remain_qty"] > 0:
        return
    raise http.validation_error(t("다른 실적에 투입된(잔량 0) LOT 은 출하할 수 없습니다"),
                                fields=[{"name": "barcode", "label": t("생산 LOT"), "reason": f"{node.no} {t('잔량')} {r['remain_qty']}"}])


@router.post(nav.path_of("SHP-02"))                                                  # F-SHP-05 출하 LOT 스캔
def scan_lot(request: Request, shipment_no: str = Form(""), barcode: str = Form(""), user: rbac.User = rbac.require_fn("F-SHP-05")):
    s = _by_no(shipment_no) if shipment_no.strip() else None
    if s is None:
        raise http.validation_error(t("없는 출하 번호입니다"), fields=[{"name": "shipment_no", "label": t("출하"), "reason": shipment_no}])
    if s["status"] != REGISTERED:
        raise http.validation_error(t("승인되거나 취소된 출하에는 LOT 을 담을 수 없습니다"), fields=[{"name": "shipment_no", "label": t("출하"), "reason": f"{s['shipment_no']} {s['status']}"}])
    lineage = _lineage()
    node = lineage.resolve(barcode)
    if node is None:
        raise http.validation_error(t("없는 LOT 번호입니다"), fields=[{"name": "barcode", "label": t("생산 LOT"), "reason": barcode.strip()}])
    with conn.tx() as cur:
        # 재고 아님 · 불합격 · 미검사 · 이미 출하 · 생산 LOT 아님 → lineage 가 422 (스캔칸은 남는다)
        if node.insp_status == "미검사":
            raise http.validation_error(t("검사하지 않은 LOT 은 출하할 수 없습니다"), fields=[{"name": "barcode", "label": t("생산 LOT"), "reason": node.no}])
        _assert_remaining(cur, node)
        genealogy_id = lineage.ship(cur, shipment_id=s["id"], lot_id=node.id, by=user.login_id, user=user)
    audit.log_change(request, user, "F-SHP-05", f"shp_shipment:{s['shipment_no']} lot:{node.no}")
    return http.saved(request, f"{node.no} → {s['shipment_no']}", back=f"{nav.path_of('SHP-02')}?no={s['shipment_no']}",
                      data={"shipment_id": s["id"], "shipment_no": s["shipment_no"], "lot_no": node.no, "genealogy_id": genealogy_id,
                            "lot_count": s["lot_count"] + 1})


@router.post(nav.path_of("SHP-02") + "/cancel")                                       # F-SHP-06 출하 LOT 스캔 취소
def unscan_lot(request: Request, shipment_no: str = Form(""), barcode: str = Form(""), user: rbac.User = rbac.require_fn("F-SHP-06")):
    s = _by_no(shipment_no) if shipment_no.strip() else None
    if s is None:
        raise http.validation_error(t("없는 출하 번호입니다"), fields=[{"name": "shipment_no", "label": t("출하"), "reason": shipment_no}])
    if s["status"] != REGISTERED:
        raise http.validation_error(t("승인되거나 취소된 출하의 LOT 은 뺄 수 없습니다"), fields=[{"name": "shipment_no", "label": t("출하"), "reason": f"{s['shipment_no']} {s['status']}"}])
    lineage = _lineage()
    node = lineage.resolve(barcode)
    if node is None:
        raise http.validation_error(t("없는 LOT 번호입니다"), fields=[{"name": "barcode", "label": t("생산 LOT"), "reason": barcode.strip()}])
    with conn.tx() as cur:
        removed = lineage.unship(cur, shipment_id=s["id"], lot_id=node.id, by=user.login_id, user=user)
    audit.log_change(request, user, "F-SHP-06", f"shp_shipment:{s['shipment_no']} lot:{node.no}")
    return http.saved(request, f"{node.no} ← {s['shipment_no']}", back=f"{nav.path_of('SHP-02')}?no={s['shipment_no']}",
                      data={"shipment_id": s["id"], "shipment_no": s["shipment_no"], "lot_no": node.no, "removed": removed})


@router.post(nav.path_of("SHP-01") + "/{shipment_id}/approve")                        # F-SHP-07 출하 승인 (관리자 · 범위 승인)
def approve_shipment(request: Request, shipment_id: int, user: rbac.User = rbac.require_fn("F-SHP-07")):
    s = _shipment(shipment_id)
    with conn.tx() as cur:
        cur.execute("select status from shp_shipment where id = %s for update", (shipment_id,))
        status = cur.fetchone()["status"]
        if status != REGISTERED:
            reason = t("이미 승인된 출하입니다") if status == APPROVED else t("취소된 출하는 승인할 수 없습니다")
            raise http.validation_error(reason, fields=[{"name": "status", "label": t("상태"), "reason": status}])
        lots = _lots(shipment_id)
        if not lots:
            raise http.validation_error(t("LOT 이 담기지 않은 출하는 승인할 수 없습니다"), fields=[{"name": "lots", "label": t("생산 LOT"), "reason": "0"}])
        row = {**s, "status": APPROVED, "approved_by": user.login_id}
        packs.hook("validate_shipment")(cur, row, lots, user)                            # interfaces.md §9 — 승인 직전 (HookError → 422)
        packs.hook("validate_shp_shipment")(cur, row, user)
        cur.execute("""update shp_shipment set status = %s, approved_at = now(), approved_by = %s, updated_at = now(), updated_by = %s
                        where id = %s""", (APPROVED, user.login_id, user.login_id, shipment_id))
        packs.hook("after_save_shp_shipment")(cur, row, user)
    payload = {"shipment_id": shipment_id, "shipment_no": s["shipment_no"], "partner_code": s["partner_code"], "ship_date": str(s["ship_date"]),
               "order_no": s["order_no"], "approved_by": user.login_id, "lots": [{"lot_no": l["lot_no"], "qty": l["qty"], "unit": l["unit"]} for l in lots]}
    http.after_commit(request, "shipment_approved", payload)                             # → after_commit_shipment_approved (트랜잭션 밖 · D-20)
    audit.log_change(request, user, "F-SHP-07", f"shp_shipment:{s['shipment_no']}", {"lots": len(lots)})
    return http.saved(request, t("출하를 승인했습니다") + f" — {s['shipment_no']}", back=f"{nav.path_of('SHP-02')}?no={s['shipment_no']}",
                      data={"id": shipment_id, "shipment_no": s["shipment_no"], "status": APPROVED, "lot_count": len(lots)})


# ── SHP-03 출하 현황 ───────────────────────────────────────────────────
@router.get(nav.path_of("SHP-03"), response_class=HTMLResponse)                     # F-SHP-08 출하 현황 조회
def shipment_status(request: Request, frm: str = "", to: str = "", user: rbac.User = rbac.require_fn("F-SHP-08")):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    d1 = _date(frm, "frm") or week_start
    d2 = _date(to, "to") or (week_start + timedelta(days=6))
    rows = _search("", "", "", d1, d2)
    total = _total(rows)
    due = stats.shipment_due([r["id"] for r in rows])                                       # 행별 납기 대비 — 집계는 stats 만
    for r in rows:
        r["lots"] = _lots(r["id"]) if r["lot_count"] else []
        d = due.get(r["id"]) or {}
        r["due_days"], r["due_state"] = d.get("due_days"), d.get("due_state")
    today_rows = [r for r in rows if r["ship_date"] == today]
    delivery = stats.delivery(d1, d2, by="day", today=today)                                 # 납기 대비 — 집계는 stats 만
    return templating.render(request, "shp/status.html", {
        "rows": rows, "total": total, "limit": LIST_LIMIT, "today_rows": today_rows, "frm": d1, "to": d2, "today": today,
        "stat": {"today_count": len(today_rows), "today_approved": sum(1 for r in today_rows if r["status"] == APPROVED),
                 "week_count": len(rows), "week_approved": sum(1 for r in rows if r["status"] == APPROVED),
                 "week_lots": sum(r["lot_count"] for r in rows)},
        "delivery": delivery, "delivery_total": stats.totals("delivery", delivery),
    }, screen_id="SHP-03")


# ── SHP-04 성적서 ──────────────────────────────────────────────────────
def _document(document_id: int) -> dict:
    row = conn.q1("""select d.*, s.shipment_no, s.status as shipment_status from shp_document d join shp_shipment s on s.id = d.shipment_id where d.id = %s""",
                  (document_id,))
    if row is None:
        raise http.not_found()
    return row


def _snapshot(s: dict, lots: list[dict]) -> dict:
    """F-SHP-09 — 발행 시점의 LOT · 최신 검사 값. 디자이너3 `print/document.html` 의 필드 그대로."""
    columns: dict[str, dict] = {}
    for l in lots:
        if l["inspection"]:
            for key, v in l["inspection"]["values"].items():
                columns.setdefault(key, {"item_key": key, "label": v["label"], "unit": v["unit"], "standard": v["standard"],
                                         "min_value": v["min_value"], "max_value": v["max_value"], "seq": v["seq"]})
    cols = sorted(columns.values(), key=lambda c: (c["seq"] is None, c["seq"] or 0, c["item_key"]))
    return {
        "shipment": {"shipment_no": s["shipment_no"], "partner_code": s["partner_code"], "partner_name": s["partner_name"], "ship_date": s["ship_date"],
                     "order_no": s["order_no"], "approved_at": s["approved_at"], "approved_by": s["approved_by"]},
        "columns": [{k: v for k, v in c.items() if k != "seq"} for c in cols],
        "lots": [{"lot_no": l["lot_no"], "item_code": l["item_code"], "item_name": l["item_name"], "qty": l["qty"], "unit": l["unit"],
                  "inspection": None if not l["inspection"] else {
                      "insp_type": l["inspection"]["insp_type"], "inspected_at": l["inspection"]["inspected_at"], "inspector": l["inspection"]["inspector"],
                      "judgement": l["inspection"]["judgement"],
                      "values": {k: {"value": v["value"], "deviated": v["deviated"], "item_judgement": v["item_judgement"]} for k, v in l["inspection"]["values"].items()}}}
                 for l in lots],
        "summary": _summary(lots),
    }


@router.get(nav.path_of("SHP-04"), response_class=HTMLResponse)                     # 화면 GET — 발행본 목록 + 발행 대상(승인 출하)
def documents(request: Request, no: str = "", frm: str = "", to: str = "", user: rbac.User = rbac.require_screen("SHP-04")):
    d1, d2 = _date(frm, "frm"), _date(to, "to")
    rows = conn.q(f"""
        select d.id, d.document_no, d.doc_type, d.issued_at, d.issued_by, s.id as shipment_id, s.shipment_no, s.ship_date, p.partner_name,
               (d.snapshot->'summary'->>'lot_count')::int as lot_count, d.snapshot->'summary'->>'judgement' as judgement
          from shp_document d join shp_shipment s on s.id = d.shipment_id join bas_partner p on p.id = s.partner_id
         where (%(no)s::text is null or d.document_no ilike '%%' || %(no)s::text || '%%' or s.shipment_no ilike '%%' || %(no)s::text || '%%')
           and (%(d1)s::date is null or d.issued_at::date >= %(d1)s::date) and (%(d2)s::date is null or d.issued_at::date <= %(d2)s::date)
         order by d.issued_at desc, d.id desc limit {LIST_LIMIT}""", {"no": no.strip() or None, "d1": d1, "d2": d2})
    approved = _search("", "", APPROVED, None, None)[:100]
    _total(approved)
    return templating.render(request, "shp/documents.html", {
        "rows": rows, "limit": LIST_LIMIT, "approved": approved, "doc_types": DOC_TYPES, "can_issue": user.can("F-SHP-09"),
        "q": {"no": no, "frm": frm, "to": to},
    }, screen_id="SHP-04")


@router.post(nav.path_of("SHP-04"))                                                  # F-SHP-09 성적서 발행
def issue_document(request: Request, shipment_id: str = Form(""), doc_type: str = Form("성적서"), user: rbac.User = rbac.require_fn("F-SHP-09")):
    if not shipment_id.strip().isdigit():
        raise http.validation_error(t("출하를 선택해 주세요"), fields=[{"name": "shipment_id", "label": t("출하"), "reason": shipment_id}])
    if doc_type not in DOC_TYPES:
        raise http.validation_error(t("문서 종류가 올바르지 않습니다"), fields=[{"name": "doc_type", "label": t("종류"), "reason": doc_type}])
    s = _shipment(int(shipment_id))
    if s["status"] != APPROVED:
        raise http.validation_error(t("승인된 출하만 성적서를 발행할 수 있습니다"), fields=[{"name": "status", "label": t("상태"), "reason": s["status"]}])
    lots = _lots(s["id"])
    snapshot = _snapshot(s, lots)
    with conn.tx() as cur:
        document_no = _numbering().next("DOCUMENT", cur=cur)
        row = {"document_no": document_no, "doc_type": doc_type, "shipment_id": s["id"], "issued_by": user.login_id, "snapshot": snapshot}
        packs.hook("validate_shp_document")(cur, row, user)
        cur.execute("""insert into shp_document (document_no, doc_type, shipment_id, issued_by, snapshot, created_by) values (%s, %s, %s, %s, %s::jsonb, %s) returning id""",
                    (document_no, doc_type, s["id"], user.login_id, json.dumps(snapshot, ensure_ascii=False, default=str), user.login_id))
        row["id"] = cur.fetchone()["id"]
        packs.hook("after_save_shp_document")(cur, row, user)
    audit.log_change(request, user, "F-SHP-09", f"shp_document:{document_no}", {"shipment_no": s["shipment_no"], "lots": len(lots)})
    return http.saved(request, t("성적서를 발행했습니다") + f" — {document_no}", back=f"{nav.path_of('SHP-04')}?no={document_no}",
                      data={"id": row["id"], "document_no": document_no, "shipment_no": s["shipment_no"], "lot_count": len(lots),
                            "judgement": snapshot["summary"]["judgement"]})


@router.get(nav.path_of("SHP-04") + "/{document_id}/print", response_class=HTMLResponse)   # F-SHP-10 성적서 출력 — 스냅샷만 그린다
def print_document(request: Request, document_id: int, user: rbac.User = rbac.require_fn("F-SHP-10")):
    d = _document(document_id)
    data = {"doc": {"document_no": d["document_no"], "doc_type": d["doc_type"], "issued_at": d["issued_at"], "issued_by": d["issued_by"]},
            "snapshot": d["snapshot"], "shipment_no": d["shipment_no"]}
    return _printing().render_print(request, "document", data, screen_id="SHP-04")
