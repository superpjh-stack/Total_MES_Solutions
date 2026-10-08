"""printfilm `rll` — 후가공 · splice · 슬리팅 · 롤 이력 · 롤 라벨 (F-X-RLL-01~07 · X-RLL-01~03 · 현장 POP · 개발2).

계보에 닿는 기능은 F-X-RLL-01 · 02 · 04 뿐이고 전부 `lineage.merge/split(relation=…, kind="ROLL", process_id=, equipment_id=, attrs=)` 를 거친다(D-503).
`lot_genealogy` 직접 SQL 0(R8). 이 파일의 코어 테이블 쓰기는 `update lot` 둘뿐 — 슬리팅 자식별 폭(attrs) · splice 의 Job 지정 (write_scope.rll = [lot] · D-514).
x_printfilm_lot_ext 는 hooks.upsert_lot_ext 로 같은 tx 에서. 라벨은 응답의 링크로 브라우저 인쇄(D-04).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request

from mescore.app import lineage, measure, nav, printing, rbac, templating
from mescore.app.packs import t
from mescore.app.routers import _dev2 as f
from mescore.app.util import audit, http
from mescore.db import conn

from . import _shared as sh
from .. import hooks as pf_hooks                      # packs.printfilm.hooks — upsert_lot_ext 를 같이 쓴다 (packs.hook 이 올린 같은 모듈)

router = APIRouter()
FINISHING, SLITTING, HISTORY = (nav.path_of(s) for s in ("X-RLL-01", "X-RLL-02", "X-RLL-03"))
POP02 = nav.path_of("POP-02")


def _attrs(length_m: str | None, width_mm: str | None) -> dict:
    out: dict = {}
    lm, wm = f.num(length_m, "length_m", "길이(m)", positive=True), f.num(width_mm, "width_mm", "폭(mm)", positive=True)
    if lm is not None:
        out["length_m"] = float(lm)
    if wm is not None:
        out["width_mm"] = float(wm)
    return out


def _label_link(lot_no: str) -> str:
    return f"{HISTORY}/{lot_no}/label"


def _stack(rolls: str | None) -> tuple[list[lineage.Node], dict | None]:
    """?rolls= 의 번호를 하나씩 검사해 쌓는다 — 어디에도 저장하지 않는다(엘컴화인 D-203). 첫 오류에서 멈추고 (유효한 것, 오류) 를 돌려준다."""
    nodes: list[lineage.Node] = []
    seen: set[str] = set()
    for no in sh.split_nos(rolls):
        if no in seen:
            return nodes, {"message": t("이미 쌓인 롤입니다"), "fields": [f.field_error("rolls", "롤", no)], "no": no}
        try:
            nodes.append(sh.require_roll(no))
        except http.HTTPException as exc:
            d = exc.detail if isinstance(exc.detail, dict) else {}
            return nodes, {"message": d.get("message", t("없는 번호입니다")), "fields": d.get("fields") or [], "no": no}
        seen.add(no)
    return nodes, None


def _job_for_merge(parents: list[lineage.Node], work_order_no: str | None) -> dict | None:
    """부모들의 Job 이 서로 다르면 `work_order_no` 로 받아야 한다 — 부모 롤의 Job 중 하나 · 마감 · 취소면 422 (엘컴화인 D-203 · D-208)."""
    jobs = {p.work_order_id for p in parents}
    if len(jobs) <= 1:
        return None
    no = f.opt_text(work_order_no)
    if not no:
        raise http.validation_error(t("부모 롤의 Job 이 서로 다릅니다 — 후가공 롤의 Job 번호를 고릅니다"),
                                    fields=[f.field_error("work_order_no", "Job", " · ".join(sorted({p.work_order_no or "-" for p in parents})))])
    wo = conn.q1("select id, work_order_no, status from job_work_order where work_order_no = %s", (no,))
    if wo is None or wo["id"] not in jobs:
        raise http.validation_error(t("부모 롤의 Job 중 하나여야 합니다"), fields=[f.field_error("work_order_no", "Job", no)])
    if wo["status"] in ("마감", "취소"):
        raise http.validation_error(t("마감 · 취소된 Job 에는 롤을 붙일 수 없습니다"), fields=[f.field_error("work_order_no", "Job", f"{no} {wo['status']}")])
    return wo


# ── X-RLL-01 후가공 ──────────────────────────────────────────────────────
@router.get(FINISHING)                                                                 # F-X-RLL-03 후가공 조회 (+ ?rolls= 스캔 쌓기 · 오류는 422 재렌더)
def finishing(request: Request, rolls: str | None = None, stacked: str | None = None, user: rbac.User = rbac.require_fn("F-X-RLL-03")):
    stack, err = _stack(",".join(x for x in (stacked or "", rolls or "") if x.strip()))      # 이미 쌓인 것 + 방금 스캔한 것 (저장하지 않는다)
    ctx: dict = {"rows": sh.rolls_of(sh.FINISH), "stack": stack, "stack_nos": ",".join(n.no for n in stack), "scan_no": (err or {}).get("no", ""),
                 "equipment_options": sh.equipment_options(), "label_path": HISTORY}
    if err:
        ctx.update({"scan_error": err["message"], "code": "validation_error", "message": err["message"], "fields": err["fields"]})
        return templating.render(request, "rll/finishing.html", ctx, screen_id="X-RLL-01", status_code=422)
    return templating.render(request, "rll/finishing.html", ctx, screen_id="X-RLL-01")


@router.post(FINISHING)                                                                # F-X-RLL-01 후가공 실적 등록 (부모 1 → 롤 1 · 관계 후가공)
def finishing_create(request: Request, roll_no: str = Form(...), equipment_id: str | None = Form(None), length_m: str | None = Form(None),
                     width_mm: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-RLL-01")):
    nos = sh.split_nos(roll_no)
    if not nos:
        raise http.validation_error(t("롤 번호를 스캔합니다"), fields=[f.field_error("roll_no", "롤", t("필수"))])
    if len(nos) > 1:
        raise http.validation_error(t("롤이 2개 이상이면 splice 로 등록하세요"), fields=[f.field_error("roll_no", "롤", ", ".join(nos))])
    parent = sh.require_roll(nos[0])
    eq = sh.equipment(equipment_id)
    attrs = _attrs(length_m, width_mm)
    with conn.tx() as cur:
        child = lineage.merge(cur, parent_ids=[parent.id], by=user.login_id, relation="후가공", kind=sh.ROLL,
                              process_id=eq["process_id"] if eq else None, equipment_id=eq["id"] if eq else None, attrs=attrs, user=user)
        pf_hooks.upsert_lot_ext(cur, child["id"], sh.FINISH, eq["id"] if eq else None, None, user.login_id)
    audit.log_change(request, user, "F-X-RLL-01", f"lot:{child['lot_no']}", {"parent": parent.no, "relation": "후가공"})
    return http.saved(request, f"{t('후가공 롤')} {child['lot_no']} ← {parent.no}", back=f"{FINISHING}",
                      data={"id": child["id"], "lot_no": child["lot_no"], "parent": parent.no, "relation": "후가공", "label_url": _label_link(child["lot_no"])})


@router.post(FINISHING + "/splice")                                                    # F-X-RLL-02 splice 등록 (부모 N ≥ 2 → 롤 1 · 관계 splice)
def splice_create(request: Request, roll_no: list[str] = Form([]), work_order_no: str | None = Form(None), equipment_id: str | None = Form(None),
                  length_m: str | None = Form(None), width_mm: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-RLL-02")):
    nos: list[str] = []
    for chunk in roll_no:
        nos.extend(sh.split_nos(chunk))
    if len(nos) < 2:
        raise http.validation_error(t("splice 는 롤 2개 이상을 잇습니다"), fields=[f.field_error("roll_no", "롤", ", ".join(nos) or t("필수"))])
    if len(set(nos)) != len(nos):
        raise http.validation_error(t("같은 롤이 두 번 들어 있습니다"), fields=[f.field_error("roll_no", "롤", ", ".join(nos))])
    parents = [sh.require_roll(no) for no in nos]
    wo = _job_for_merge(parents, work_order_no)
    eq = sh.equipment(equipment_id)
    attrs = _attrs(length_m, width_mm)
    with conn.tx() as cur:
        child = lineage.merge(cur, parent_ids=[p.id for p in parents], by=user.login_id, relation="splice", kind=sh.ROLL,
                              process_id=eq["process_id"] if eq else None, equipment_id=eq["id"] if eq else None, attrs=attrs, user=user)
        if wo is not None:                                                                       # 부모 Job 이 여럿 — 고른 Job 으로 (D-514 · write_scope.rll lot)
            cur.execute("update lot set work_order_id = %s, updated_at = now(), updated_by = %s where id = %s", (wo["id"], user.login_id, child["id"]))
        pf_hooks.upsert_lot_ext(cur, child["id"], sh.FINISH, eq["id"] if eq else None, None, user.login_id)
    audit.log_change(request, user, "F-X-RLL-02", f"lot:{child['lot_no']}", {"parents": nos, "relation": "splice"})
    return http.saved(request, f"splice {child['lot_no']} ← {', '.join(nos)}", back=FINISHING,
                      data={"id": child["id"], "lot_no": child["lot_no"], "parents": nos, "relation": "splice", "label_url": _label_link(child["lot_no"])})


# ── X-RLL-02 슬리팅 ─────────────────────────────────────────────────────
def _children_labels(parent_no: str | None) -> tuple[lineage.Node | None, list[dict]]:
    if not f.opt_text(parent_no):
        return None, []
    parent = sh.require_roll(parent_no, must_stock=False)
    kids = [e.child for e in lineage.children_of(parent.id) if e.relation == "슬리팅"]
    return parent, [sh.roll_label(k.id) for k in kids]


@router.get(SLITTING)                                                                  # F-X-RLL-05 슬리팅 조회 (?parent= 그 부모의 자식 N + 라벨 N장)
def slitting(request: Request, parent: str | None = None, user: rbac.User = rbac.require_fn("F-X-RLL-05")):
    ctx: dict = {"rows": sh.rolls_of(sh.SLIT), "parent": None, "labels": [], "scan_no": parent or "", "equipment_options": sh.equipment_options(),
                 "label_path": HISTORY, "barcode_svg": printing.barcode_svg, "size": "100x50"}
    if f.opt_text(parent):
        try:
            p, labels = _children_labels(parent)
        except http.HTTPException as exc:
            d = exc.detail if isinstance(exc.detail, dict) else {}
            ctx.update({"scan_error": d.get("message", t("없는 번호입니다")), "code": "validation_error", "message": d.get("message", ""), "fields": d.get("fields") or []})
            return templating.render(request, "rll/slitting.html", ctx, screen_id="X-RLL-02", status_code=422)
        ctx.update({"parent": p, "labels": labels})
    return templating.render(request, "rll/slitting.html", ctx, screen_id="X-RLL-02")


@router.post(SLITTING)                                                                 # F-X-RLL-04 슬리팅 분할 등록 (부모 1 → 롤 N · 관계 슬리팅 · slit_seq 1..N)
def slitting_create(request: Request, roll_no: str = Form(...), count: str = Form(...), widths_mm: str | None = Form(None), length_m: str | None = Form(None),
                    equipment_id: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-RLL-04")):
    parent = sh.require_roll(f.req_text(roll_no, "roll_no", "롤"))
    n = f.int_id(count, "count", "분할 수", required=True)
    if n < 1:
        raise http.validation_error(t("분할 수는 1 이상입니다"), fields=[f.field_error("count", "분할 수", str(n))])
    if n < 2:
        raise http.validation_error(t("슬리팅은 2 이상으로 나눕니다 — 1개면 후가공으로 등록하세요"), fields=[f.field_error("count", "분할 수", str(n))])
    widths = [f.num(w, "widths_mm", "폭(mm)", positive=True) for w in sh.split_nos(widths_mm)]
    if widths and len(widths) != n:
        raise http.validation_error(t("폭의 개수가 분할 수와 다릅니다"), fields=[f.field_error("widths_mm", "폭(mm)", f"{len(widths)} ≠ {n}")])
    eq = sh.equipment(equipment_id)
    base_attrs = _attrs(length_m, None)
    with conn.tx() as cur:
        children = lineage.split(cur, parent_id=parent.id, count=n, by=user.login_id, relation="슬리팅", kind=sh.ROLL,
                                 process_id=eq["process_id"] if eq else None, equipment_id=eq["id"] if eq else None, attrs=base_attrs, user=user)
        for i, child in enumerate(children, start=1):
            if widths:                                                                              # 자식별 폭 — split 은 attrs 하나만 받는다 (D-514 · write_scope.rll lot)
                cur.execute("update lot set attrs = %s::jsonb, updated_at = now(), updated_by = %s where id = %s",
                            (json.dumps({**base_attrs, "width_mm": float(widths[i - 1])}, ensure_ascii=False), user.login_id, child["id"]))
            pf_hooks.upsert_lot_ext(cur, child["id"], sh.SLIT, eq["id"] if eq else None, i, user.login_id)
    audit.log_change(request, user, "F-X-RLL-04", f"lot:{parent.no}", {"slit": [c["lot_no"] for c in children]})
    return http.saved(request, f"{t('슬리팅')} {parent.no} → {len(children)}", back=f"{SLITTING}?parent={parent.no}",
                      data={"parent": parent.no, "parent_id": parent.id, "relation": "슬리팅",
                            "lots": [{"id": c["id"], "lot_no": c["lot_no"], "slit_seq": i + 1, "label_url": _label_link(c["lot_no"])} for i, c in enumerate(children)]})


# ── X-RLL-03 롤 이력 ────────────────────────────────────────────────────
def _work_results_of(roll_ids: list[int]) -> list[dict]:
    """조상(또는 자기) 인쇄 롤의 작업 실적 — 측정값 · 투입 · 정지 · 폐기 (G-C08 · 엘컴화인 D-210). 읽기만."""
    if not roll_ids:
        return []
    rows = conn.q("""select l.lot_no, r.id, r.started_at, r.ended_at, r.good_qty, r.defect_qty, r.unit, w.work_order_no, e.equip_code, k.worker_name
                       from lot l join pop_work_result r on r.id = l.work_result_id join job_work_order w on w.id = r.work_order_id
                       left join bas_equipment e on e.id = r.equipment_id left join bas_worker k on k.id = r.worker_id
                      where l.id = any(%s) order by r.started_at, r.id""", (roll_ids,))
    for r in rows:
        r["measures"] = [{"key": k, "value": measure.display_value(v)} for k, v in measure.values_of(r["id"]).items()]
        r["inputs"] = conn.q("select x.qty, x.unit, m.lot_no from pop_input x join lot m on m.id = x.material_lot_id where x.work_result_id = %s and x.canceled_yn = 'N' order by x.id", (r["id"],))
        r["stops"] = conn.q("select reason_code, started_at, ended_at from pop_stop where work_result_id = %s order by id", (r["id"],))
        r["scraps"] = conn.q("select s.qty, s.unit, d.defect_code from pop_scrap s left join bas_defect_code d on d.id = s.defect_code_id where s.work_result_id = %s order by s.id", (r["id"],))
    return rows


@router.get(HISTORY)                                                                   # F-X-RLL-06 롤 이력 조회 (?no= 스캔 · 롤 아님 422 재렌더 · 쓰지 않는다)
def history(request: Request, no: str | None = None, user: rbac.User = rbac.require_fn("F-X-RLL-06")):
    ctx: dict = {"roll": None, "parents": [], "children": [], "results": [], "scan_no": no or "", "recent": sh.rolls_of(sh.PRINT, 30), "label_path": HISTORY}
    if no is not None and no.strip() != "":
        try:
            n = sh.require_roll(no, must_stock=False)
        except http.HTTPException as exc:
            d = exc.detail if isinstance(exc.detail, dict) else {}
            ctx.update({"scan_error": d.get("message", t("없는 번호입니다")), "code": "validation_error", "message": d.get("message", ""), "fields": d.get("fields") or []})
            return templating.render(request, "rll/history.html", ctx, screen_id="X-RLL-03", status_code=422)
        roll = sh.roll_row(n.id)
        ctx["roll"] = roll
        ctx["parents"] = lineage.parents_of(n.id)
        ctx["children"] = lineage.children_of(n.id)
        ancestors = [x for x in lineage.trace_backward(n.id).nodes() if x.kind == sh.ROLL]
        ids = [x.id for x in ancestors]
        if n.id not in ids:
            ids.append(n.id)
        ctx["results"] = _work_results_of(ids)
        ctx["label_url"] = _label_link(n.no)
    return templating.render(request, "rll/history.html", ctx, screen_id="X-RLL-03")


@router.get(HISTORY + "/{lot_no}/label")                                               # F-X-RLL-07 롤 라벨 출력 (없는 번호 404 · 경로 키)
def label(request: Request, lot_no: str, size: str = "100x50", user: rbac.User = rbac.require_fn("F-X-RLL-07")):
    n = lineage.resolve(lot_no)
    if n is None:
        raise http.not_found(t("없는 롤 번호입니다"))
    lab = sh.roll_label(n.id, size)
    return printing.render_print(request, "label_lot", {"labels": [lab], "size": size, **lab}, screen_id="X-RLL-03")
