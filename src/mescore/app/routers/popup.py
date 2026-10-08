"""popup 라우터 — CMN-05 `/popup/{kind}` 공용 찾기 팝업 (아키텍트 · `screen-map.md` §2). **읽기만** — 어떤 테이블에도 쓰지 않는다.

`kind` = `core.yaml: common[CMN-05].kinds` (item · partner · equipment · lot · worker). 그 밖은 404.
검색어 `q` 는 코드 · 이름 부분 일치(LOT 은 `lineage.search` — 번호 · 품목 · 지시 번호). `q` 가 비면 최근 `limit` 건.
`Accept` 에 `text/html` 이 없으면 ctx(`kind · q · columns · rows · count`)를 JSON 으로 준다(D-18) — 화면의 찾기 버튼은 JSON 으로, 새 창은 HTML 로 같은 경로를 연다.
행 선택을 부모 화면에 돌려주는 동작은 `static/app.js`(디자이너2) 의 몫 — 템플릿은 행마다 `data-pick`(코드 · 번호) · `data-pick-id` 만 둔다.
공통 화면이라 권한 표 밖(`rbac.require_login`). 조회 로그는 `templating.render` 가 남긴다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from .. import packs, rbac, templating
from ...db import conn
from ..packs import t
from ..util import http

router = APIRouter()
SCREEN = "CMN-05"
LIMIT_MAX = 200

#: kind → (표시 이름, 표 · 코드 컬럼 · 이름 컬럼, 보이는 컬럼 [(컬럼, 표시)])
MASTER: dict[str, tuple[str, str, str, str, list[tuple[str, str]]]] = {
    "item": ("품목", "bas_item", "item_code", "item_name",
             [("item_code", "품목 코드"), ("item_name", "품목명"), ("item_type", "구분"), ("spec", "규격"), ("unit", "단위")]),
    "partner": ("거래처", "bas_partner", "partner_code", "partner_name",
                [("partner_code", "거래처 코드"), ("partner_name", "거래처명"), ("partner_type", "구분"), ("contact", "연락처")]),
    "equipment": ("설비", "bas_equipment", "equip_code", "equip_name",
                  [("equip_code", "설비 코드"), ("equip_name", "설비명"), ("process_name", "공정"), ("collect_yn", "수집")]),
    "worker": ("작업자", "bas_worker", "worker_code", "worker_name",
               [("worker_code", "작업자 코드"), ("worker_name", "작업자명"), ("process_name", "공정")]),
}
LOT_COLUMNS: list[tuple[str, str]] = [("no", "LOT 번호"), ("kind_label", "종류"), ("item", "품목"), ("state", "상태"), ("qty", "수량"), ("unit", "단위"), ("work_order_no", "작업지시")]


def kinds() -> list[str]:
    return [str(k) for c in packs.current().common if c["id"] == SCREEN for k in (c.get("kinds") or [])]


def _master_rows(kind: str, q: str, limit: int) -> list[dict]:
    _name, table, code_col, name_col, cols = MASTER[kind]
    select = ", ".join(f"m.{c}" for c, _ in cols if c != "process_name")
    join = ""
    if any(c == "process_name" for c, _ in cols):
        select += ", p.process_name"
        join = " left join bas_process p on p.id = m.process_id"
    where = "m.use_yn = 'Y'"
    params: dict = {"n": limit}
    if q:
        where += f" and (m.{code_col} ilike %(p)s or m.{name_col} ilike %(p)s)"
        params["p"] = f"%{q}%"
    return conn.q(f"select m.id, {select} from {table} m{join} where {where} order by m.{code_col} limit %(n)s", params)


def _lot_rows(q: str, limit: int) -> list[dict]:
    from .. import lineage  # noqa — 개발2 모듈. 번호 · 품목 · 지시 번호 부분 일치

    if q:
        return [templating.jsonable(n) for n in lineage.search(q, limit=limit)]
    rows = conn.q("select l.id, l.lot_no as no, l.kind, coalesce(i.item_name, '') as item, s.state, l.qty, l.unit, w.work_order_no"
                  "  from lot l left join bas_item i on i.id = l.item_id left join v_lot_state s on s.lot_id = l.id"
                  "  left join job_work_order w on w.id = l.work_order_id order by l.made_at desc, l.id desc limit %s", (limit,))
    for r in rows:
        r["kind_label"] = lineage.kind_label(r["kind"])
    return rows


@router.get("/popup/{kind}", include_in_schema=False)
def popup(request: Request, kind: str, q: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=LIMIT_MAX),
          user: rbac.User = Depends(rbac.require_login)):
    allowed = kinds()
    if kind not in allowed:
        raise http.not_found(t("팝업 종류가 없습니다") + f": {kind!r} — {allowed}")
    q = q.strip()
    if kind == "lot":
        title, cols, rows, pick = "LOT", LOT_COLUMNS, _lot_rows(q, limit), "no"
    else:
        title, _tbl, pick, _name_col, cols = MASTER[kind]
        rows = _master_rows(kind, q, limit)
    return templating.render(request, "home/_popup.html", {
        "kind": kind, "kinds": allowed, "title": title, "q": q, "limit": limit, "pick": pick,
        "columns": [{"key": k, "label": label} for k, label in cols], "rows": rows, "count": len(rows),
    }, screen_id=SCREEN)
