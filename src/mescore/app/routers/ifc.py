"""ifc 라우터 — 수집 수신 · ERP 연계 로그 (기능 4 · F-IFC-01~04) · 담당 개발3.

쓰는 테이블: `ifc_collect_raw` · `eqp_collect` 는 **개발2 `collect.receive` 가**, `ifc_outbox` · `ifc_erp_link` 는 **`erp` 모듈이** 쓴다 — 이 파일에 쓰기 SQL 은 없다.
F-IFC-01 `POST /ifc/collect` 는 사용자 세션이 아니라 **`X-Collect-Token`**(`auth.require_collect_token`) 으로 인증한다(api-contract.md §4). 제어 명령 엔드포인트는 없다.
F-IFC-04 재전송은 `erp.retry` 한 건 — 어댑터가 501 이면 **501 그대로**(조용한 폴백 0 · G-C16 · D-02).

  IFC-01 수집 수신 현황  POST /ifc/collect (토큰) · GET /ifc/collect
  IFC-02 ERP 연계 로그   GET /ifc/erp · POST /ifc/erp/{id}/retry
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ...db import conn
from .. import auth, erp, nav, rbac, templating
from ..packs import t
from ..util import audit, http

router = APIRouter()

LIST_LIMIT = 200


def _collect():
    from .. import collect  # noqa: PLC0415 — 개발2 모듈 (수집 수신은 collect 뿐)
    return collect


# ── IFC-01 수집 수신 ───────────────────────────────────────────────────
@router.post(nav.path_of("IFC-01"))                                                  # F-IFC-01 수집 메시지 수신 (토큰 인증 · 사용자 세션 아님)
async def receive_collect(request: Request):
    auth.require_collect_token(request)                                               # 토큰 불일치 401
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — JSON 이 아니면 422 (조용히 비우지 않는다)
        raise http.validation_error(t("본문이 JSON 이 아닙니다"), fields=[{"name": "body", "reason": "invalid json"}]) from None
    collect = _collect()
    msg = collect.CollectMessage.from_payload(payload)
    with conn.tx() as cur:
        result = collect.receive(cur, msg)                                            # 모르는 설비 → 거부 기록 + 422 (collect 가 한다)
    return JSONResponse({"ok": True, "raw_id": result.raw_id, "duplicate": result.duplicate, "unknown_tags": list(result.unknown_tags), "saved": result.saved})


@router.get(nav.path_of("IFC-01"), response_class=HTMLResponse)                     # F-IFC-02 수집 수신 현황 조회
def collect_status(request: Request, frm: str = "", to: str = "", user: rbac.User = rbac.require_fn("F-IFC-02")):
    try:
        d1 = date.fromisoformat(frm) if frm.strip() else None
        d2 = date.fromisoformat(to) if to.strip() else None
    except ValueError:
        raise http.validation_error(t("날짜 형식(YYYY-MM-DD)이 아닙니다"), fields=[{"name": "frm", "label": t("기간"), "reason": f"{frm} ~ {to}"}]) from None
    f_at = datetime.combine(d1, datetime.min.time()) if d1 else None
    t_at = datetime.combine(d2 + timedelta(days=1), datetime.min.time()) if d2 else None
    collect = _collect()
    known = collect.known_tags()
    rows = conn.q("""
        select e.id as equipment_id, e.equip_code, e.equip_name, e.collect_yn,
               (select max(r.received_at) from ifc_collect_raw r where r.equip_code = e.equip_code and r.rejected_reason is null) as last_received_at,
               (select count(*)::int from ifc_collect_raw r where r.equip_code = e.equip_code and r.rejected_reason is null
                   and (%(f)s::timestamptz is null or r.received_at >= %(f)s) and (%(t)s::timestamptz is null or r.received_at < %(t)s)) as received,
               (select count(*)::int from ifc_collect_raw r where r.equip_code = e.equip_code and r.rejected_reason is not null
                   and (%(f)s::timestamptz is null or r.received_at >= %(f)s) and (%(t)s::timestamptz is null or r.received_at < %(t)s)) as rejected,
               (select array_agg(distinct c.tag order by c.tag) from eqp_collect c where c.equipment_id = e.id) as tags
          from bas_equipment e where e.use_yn = 'Y' order by e.equip_code""", {"f": f_at, "t": t_at})
    for r in rows:
        r["unknown_tags"] = [x for x in (r["tags"] or []) if x not in known]
    rejected = conn.q("""select r.id, r.equip_code, r.ts, r.source, r.received_at, r.rejected_reason, r.resend
                           from ifc_collect_raw r where r.rejected_reason is not null
                            and (%(f)s::timestamptz is null or r.received_at >= %(f)s) and (%(t)s::timestamptz is null or r.received_at < %(t)s)
                          order by r.received_at desc limit %(n)s""", {"f": f_at, "t": t_at, "n": LIST_LIMIT})
    counts = conn.q1("""select count(*)::int as total, count(*) filter (where rejected_reason is not null)::int as rejected,
                               count(*) filter (where resend)::int as resent, max(received_at) as last_at
                          from ifc_collect_raw where (%(f)s::timestamptz is null or received_at >= %(f)s) and (%(t)s::timestamptz is null or received_at < %(t)s)""",
                     {"f": f_at, "t": t_at})
    unknown_equipment = conn.q("""select r.equip_code, count(*)::int as n, max(r.received_at) as last_received_at from ifc_collect_raw r
                                   where r.rejected_reason is not null and not exists (select 1 from bas_equipment e where e.equip_code = r.equip_code)
                                   group by r.equip_code order by max(r.received_at) desc limit 50""")
    return templating.render(request, "ifc/collect.html", {
        "rows": rows, "rejected": rejected, "unknown_equipment": unknown_equipment, "counts": counts, "known_tags": sorted(known),
        "q": {"frm": frm, "to": to}, "endpoint": nav.path_of("IFC-01"),
    }, screen_id="IFC-01")


# ── IFC-02 ERP 연계 로그 ───────────────────────────────────────────────
@router.get(nav.path_of("IFC-02"), response_class=HTMLResponse)                     # F-IFC-03 ERP 연계 로그 조회
def erp_log(request: Request, status: str = "", user: rbac.User = rbac.require_fn("F-IFC-03")):
    if status and status not in (erp.WAITING, erp.SENT, erp.FAILED, erp.UNDECIDED):
        raise http.validation_error(t("상태가 올바르지 않습니다"), fields=[{"name": "status", "label": t("상태"), "reason": status}])
    undecided = erp.is_undecided()
    rows = erp.outbox(LIST_LIMIT, status=status or None)
    for r in rows:
        r["display_status"] = f"{r['status']} — 미확정 ({erp.DECISION})" if undecided and r["status"] != erp.SENT else r["status"]
    counts = {r["status"]: r["n"] for r in conn.q("select status, count(*)::int as n from ifc_outbox group by status")}
    return templating.render(request, "ifc/erp.html", {
        "rows": rows, "links": erp.links(LIST_LIMIT), "counts": counts, "adapter_undecided": undecided, "decision": erp.DECISION,
        "adapter_name": type(erp.adapter()).__name__, "statuses": (erp.WAITING, erp.SENT, erp.FAILED, erp.UNDECIDED), "q": {"status": status},
        "can_retry": user.can("F-IFC-04"),
    }, screen_id="IFC-02")


@router.post(nav.path_of("IFC-02") + "/{outbox_id}/retry")                            # F-IFC-04 ERP 재전송 (관리자 · 범위 재전송)
def erp_retry(request: Request, outbox_id: int, user: rbac.User = rbac.require_fn("F-IFC-04")):
    result = erp.retry(outbox_id)                                                     # 어댑터 501 → 행은 `미확정` 으로 적힌 뒤 501 그대로
    audit.log_change(request, user, "F-IFC-04", f"ifc_outbox:{outbox_id}", {"status": result["status"]})
    return http.saved(request, t("재전송했습니다") + f" — {result['status']}", back=nav.path_of("IFC-02"), data=result)
