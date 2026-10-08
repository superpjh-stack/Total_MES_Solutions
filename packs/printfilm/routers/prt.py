"""printfilm `prt` — 인쇄 기준 관리: 판사양 · 아니록스 · 잉크조성 (F-X-PRT-01~12 · X-PRT-01~03 · 개발2).

쓰는 테이블: x_printfilm_plate · x_printfilm_anilox · x_printfilm_ink_formula(_component) 만 (write_scope.prt = []). 코어 테이블은 읽기만.
모양은 코어 라우터와 같다 — 화면 GET = nav.path_of + require_fn(조회 기능), 쓰기 = 검증 → conn.tx → audit.log_change → http.saved.
삭제는 Job(x_printfilm_job_work_order_ext) · 조색 기록이 참조하면 422 — 막는 참조는 FK 에서 읽는다(엘컴화인 D-102).
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Form, Request

from mescore.app import nav, rbac, templating
from mescore.app.packs import t
from mescore.app.routers import _dev2 as f
from mescore.app.util import audit, http
from mescore.db import conn

from . import _shared as sh

router = APIRouter()
PLATES, ANILOX, INKS = (nav.path_of(s) for s in ("X-PRT-01", "X-PRT-02", "X-PRT-03"))


def _form(request: Request):
    return anyio.from_thread.run(request.form)


def _like(v: str | None) -> str | None:
    v = (v or "").strip()
    return f"%{v}%" if v else None


def _product_options() -> list[tuple]:
    return f.options(conn.q("select id, item_code, item_name from bas_item where use_yn = 'Y' and item_type = '제품' order by item_code"), "id", "item_code", "item_name")


def _product(item_id: str | None) -> int | None:
    iid = f.int_id(item_id, "item_id", "품목")
    if iid is None:
        return None
    it = conn.q1("select id, item_code, item_type, use_yn from bas_item where id = %s", (iid,))
    if it is None or it["use_yn"] != "Y":
        raise http.validation_error(t("미사용 품목은 고를 수 없습니다") if it else t("없는 품목입니다"), fields=[f.field_error("item_id", "품목", str(iid))])
    if it["item_type"] != "제품":
        raise http.validation_error(t("판사양의 품목은 제품만 고릅니다"), fields=[f.field_error("item_id", "품목", f"{it['item_code']} {it['item_type']}")])
    return iid


def _require(table: str, id: int, label: str) -> dict:
    r = conn.q1(f"select * from {table} where id = %s", (int(id),))
    if r is None:
        raise http.not_found(t(f"없는 {label}입니다"))
    return r


def _in_use(sql: str, params) -> int:
    return int(conn.q1(sql, params)["n"])


# ── X-PRT-01 판사양 ─────────────────────────────────────────────────────
@router.get(PLATES)                                                                    # F-X-PRT-04 판사양 조회 = 화면 GET
def plates(request: Request, code: str | None = None, name: str | None = None, item_id: str | None = None, use_yn: str | None = None,
           edit: str | None = None, user: rbac.User = rbac.require_fn("F-X-PRT-04")):
    iid = f.int_id(item_id, "item_id", "품목")
    rows = conn.q("""select p.*, i.item_code, i.item_name, (select count(*) from x_printfilm_job_work_order_ext x where x.plate_id = p.id) as job_count
                       from x_printfilm_plate p left join bas_item i on i.id = p.item_id
                      where (%s::text is null or p.plate_code ilike %s) and (%s::text is null or p.plate_name ilike %s)
                        and (%s::bigint is null or p.item_id = %s) and (%s::text is null or p.use_yn = %s)
                      order by p.plate_code limit 500""", (_like(code), _like(code), _like(name), _like(name), iid, iid, sh.yn(use_yn, "") or None, sh.yn(use_yn, "") or None))
    eid = f.int_id(edit, "edit", "판사양")
    ctx = {"rows": rows, "editing": _require("x_printfilm_plate", eid, "판사양") if eid else None, "product_options": _product_options(),
           "q": {"code": code or "", "name": name or "", "item_id": item_id or "", "use_yn": use_yn or ""}}
    return templating.render(request, "prt/plates.html", ctx, screen_id="X-PRT-01")


@router.post(PLATES)                                                                   # F-X-PRT-01 판사양 등록
def plate_create(request: Request, plate_code: str = Form(...), plate_name: str = Form(...), item_id: str | None = Form(None),
                 color_count: str | None = Form(None), spec_note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-PRT-01")):
    code, name = f.req_text(plate_code, "plate_code", "판 코드"), f.req_text(plate_name, "plate_name", "판명")
    if conn.q1("select 1 from x_printfilm_plate where plate_code = %s", (code,)):
        raise http.validation_error(t("이미 있는 판 코드입니다"), fields=[f.field_error("plate_code", "판 코드", code)])
    iid = _product(item_id)
    cc = f.int_id(color_count, "color_count", "도수")
    with conn.tx() as cur:
        cur.execute("insert into x_printfilm_plate (plate_code, plate_name, item_id, color_count, spec_note, created_by) values (%s, %s, %s, %s, %s, %s) returning id",
                    (code, name, iid, cc, f.opt_text(spec_note), user.login_id))
        new_id = cur.fetchone()["id"]
    audit.log_change(request, user, "F-X-PRT-01", f"x_printfilm_plate:{code}")
    return http.saved(request, t("판사양을 등록했습니다") + f" — {code}", back=PLATES, data={"id": new_id, "plate_code": code})


@router.post(PLATES + "/{id}")                                                         # F-X-PRT-02 판사양 수정 (코드는 못 바꾼다)
def plate_update(request: Request, id: int, plate_code: str | None = Form(None), plate_name: str | None = Form(None), item_id: str | None = Form(None),
                 color_count: str | None = Form(None), spec_note: str | None = Form(None), use_yn: str | None = Form(None),
                 user: rbac.User = rbac.require_fn("F-X-PRT-02")):
    row = _require("x_printfilm_plate", id, "판사양")
    if f.opt_text(plate_code) and plate_code.strip() != row["plate_code"]:
        raise http.validation_error(t("판 코드는 바꿀 수 없습니다"), fields=[f.field_error("plate_code", "판 코드", plate_code)])
    name = f.opt_text(plate_name) or row["plate_name"]
    iid = _product(item_id) if f.opt_text(item_id) else row["item_id"]
    cc = f.int_id(color_count, "color_count", "도수") if f.opt_text(color_count) else row["color_count"]
    with conn.tx() as cur:
        cur.execute("update x_printfilm_plate set plate_name = %s, item_id = %s, color_count = %s, spec_note = %s, use_yn = %s, updated_at = now(), updated_by = %s where id = %s",
                    (name, iid, cc, f.opt_text(spec_note) if spec_note is not None else row["spec_note"], sh.yn(use_yn, row["use_yn"]), user.login_id, id))
    audit.log_change(request, user, "F-X-PRT-02", f"x_printfilm_plate:{row['plate_code']}")
    return http.saved(request, t("판사양을 수정했습니다") + f" — {row['plate_code']}", back=PLATES, data={"id": id, "plate_code": row["plate_code"]})


@router.post(PLATES + "/{id}/delete")                                                  # F-X-PRT-03 판사양 삭제 (Job 참조 422)
def plate_delete(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-PRT-03")):
    row = _require("x_printfilm_plate", id, "판사양")
    n = _in_use("select count(*) as n from x_printfilm_job_work_order_ext where plate_id = %s", (id,))
    if n:
        raise http.validation_error(t("사용 중이라 삭제할 수 없습니다"), fields=[f.field_error("id", "판사양", f"{row['plate_code']} — Job {n}")])
    with conn.tx() as cur:
        cur.execute("delete from x_printfilm_plate where id = %s", (id,))
    audit.log_change(request, user, "F-X-PRT-03", f"x_printfilm_plate:{row['plate_code']}")
    return http.saved(request, t("판사양을 삭제했습니다") + f" — {row['plate_code']}", back=PLATES, data={"id": id, "plate_code": row["plate_code"]})


# ── X-PRT-02 아니록스 ───────────────────────────────────────────────────
@router.get(ANILOX)                                                                    # F-X-PRT-08 아니록스 조회 = 화면 GET
def anilox(request: Request, code: str | None = None, name: str | None = None, use_yn: str | None = None, edit: str | None = None,
           user: rbac.User = rbac.require_fn("F-X-PRT-08")):
    u = sh.yn(use_yn, "") or None
    rows = conn.q("""select a.*, (select count(*) from x_printfilm_job_work_order_ext x where x.anilox_id = a.id) as job_count
                       from x_printfilm_anilox a
                      where (%s::text is null or a.anilox_code ilike %s) and (%s::text is null or a.anilox_name ilike %s) and (%s::text is null or a.use_yn = %s)
                      order by a.anilox_code limit 500""", (_like(code), _like(code), _like(name), _like(name), u, u))
    eid = f.int_id(edit, "edit", "아니록스")
    ctx = {"rows": rows, "editing": _require("x_printfilm_anilox", eid, "아니록스") if eid else None, "q": {"code": code or "", "name": name or "", "use_yn": use_yn or ""}}
    return templating.render(request, "prt/anilox.html", ctx, screen_id="X-PRT-02")


@router.post(ANILOX)                                                                   # F-X-PRT-05 아니록스 등록
def anilox_create(request: Request, anilox_code: str = Form(...), anilox_name: str = Form(...), line_count: str | None = Form(None),
                  cell_volume: str | None = Form(None), note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-PRT-05")):
    code, name = f.req_text(anilox_code, "anilox_code", "아니록스 코드"), f.req_text(anilox_name, "anilox_name", "명칭")
    if conn.q1("select 1 from x_printfilm_anilox where anilox_code = %s", (code,)):
        raise http.validation_error(t("이미 있는 아니록스 코드입니다"), fields=[f.field_error("anilox_code", "아니록스 코드", code)])
    lc, cv = f.num(line_count, "line_count", "선수", positive=True), f.num(cell_volume, "cell_volume", "셀 용적", positive=True)
    with conn.tx() as cur:
        cur.execute("insert into x_printfilm_anilox (anilox_code, anilox_name, line_count, cell_volume, note, created_by) values (%s, %s, %s, %s, %s, %s) returning id",
                    (code, name, lc, cv, f.opt_text(note), user.login_id))
        new_id = cur.fetchone()["id"]
    audit.log_change(request, user, "F-X-PRT-05", f"x_printfilm_anilox:{code}")
    return http.saved(request, t("아니록스를 등록했습니다") + f" — {code}", back=ANILOX, data={"id": new_id, "anilox_code": code})


@router.post(ANILOX + "/{id}")                                                         # F-X-PRT-06 아니록스 수정
def anilox_update(request: Request, id: int, anilox_code: str | None = Form(None), anilox_name: str | None = Form(None), line_count: str | None = Form(None),
                  cell_volume: str | None = Form(None), note: str | None = Form(None), use_yn: str | None = Form(None),
                  user: rbac.User = rbac.require_fn("F-X-PRT-06")):
    row = _require("x_printfilm_anilox", id, "아니록스")
    if f.opt_text(anilox_code) and anilox_code.strip() != row["anilox_code"]:
        raise http.validation_error(t("아니록스 코드는 바꿀 수 없습니다"), fields=[f.field_error("anilox_code", "아니록스 코드", anilox_code)])
    lc = f.num(line_count, "line_count", "선수", positive=True) if f.opt_text(line_count) else row["line_count"]
    cv = f.num(cell_volume, "cell_volume", "셀 용적", positive=True) if f.opt_text(cell_volume) else row["cell_volume"]
    with conn.tx() as cur:
        cur.execute("update x_printfilm_anilox set anilox_name = %s, line_count = %s, cell_volume = %s, note = %s, use_yn = %s, updated_at = now(), updated_by = %s where id = %s",
                    (f.opt_text(anilox_name) or row["anilox_name"], lc, cv, f.opt_text(note) if note is not None else row["note"], sh.yn(use_yn, row["use_yn"]), user.login_id, id))
    audit.log_change(request, user, "F-X-PRT-06", f"x_printfilm_anilox:{row['anilox_code']}")
    return http.saved(request, t("아니록스를 수정했습니다") + f" — {row['anilox_code']}", back=ANILOX, data={"id": id, "anilox_code": row["anilox_code"]})


@router.post(ANILOX + "/{id}/delete")                                                  # F-X-PRT-07 아니록스 삭제 (Job 참조 422)
def anilox_delete(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-PRT-07")):
    row = _require("x_printfilm_anilox", id, "아니록스")
    n = _in_use("select count(*) as n from x_printfilm_job_work_order_ext where anilox_id = %s", (id,))
    if n:
        raise http.validation_error(t("사용 중이라 삭제할 수 없습니다"), fields=[f.field_error("id", "아니록스", f"{row['anilox_code']} — Job {n}")])
    with conn.tx() as cur:
        cur.execute("delete from x_printfilm_anilox where id = %s", (id,))
    audit.log_change(request, user, "F-X-PRT-07", f"x_printfilm_anilox:{row['anilox_code']}")
    return http.saved(request, t("아니록스를 삭제했습니다") + f" — {row['anilox_code']}", back=ANILOX, data={"id": id, "anilox_code": row["anilox_code"]})


# ── X-PRT-03 잉크조성 ───────────────────────────────────────────────────
def _components(ink_id: int) -> list[dict]:
    return conn.q("select id, seq_no, component_name, ratio_pct from x_printfilm_ink_formula_component where ink_formula_id = %s order by seq_no", (ink_id,))


@router.get(INKS)                                                                      # F-X-PRT-12 잉크조성 조회 = 화면 GET (?id= 한 건 + 조성 행)
def inks(request: Request, code: str | None = None, name: str | None = None, color: str | None = None, use_yn: str | None = None, id: str | None = None,
         user: rbac.User = rbac.require_fn("F-X-PRT-12")):
    u = sh.yn(use_yn, "") or None
    rows = conn.q("""select k.*, (select count(*) from x_printfilm_ink_formula_component c where c.ink_formula_id = k.id) as component_count,
                            (select count(*) from x_printfilm_job_work_order_ext x where x.ink_formula_id = k.id) as job_count,
                            (select count(*) from x_printfilm_color_record r where r.ink_formula_id = k.id) as record_count
                       from x_printfilm_ink_formula k
                      where (%s::text is null or k.ink_code ilike %s) and (%s::text is null or k.ink_name ilike %s)
                        and (%s::text is null or k.color_name ilike %s) and (%s::text is null or k.use_yn = %s)
                      order by k.ink_code limit 500""", (_like(code), _like(code), _like(name), _like(name), _like(color), _like(color), u, u))
    iid = f.int_id(id, "id", "잉크조성")
    opened = _require("x_printfilm_ink_formula", iid, "잉크조성") if iid else None
    ctx = {"rows": rows, "opened": opened, "components": _components(iid) if iid else [],
           "q": {"code": code or "", "name": name or "", "color": color or "", "use_yn": use_yn or ""}}
    return templating.render(request, "prt/inks.html", ctx, screen_id="X-PRT-03")


def _write_components(cur, ink_id: int, lines: list[dict], by: str) -> None:
    cur.execute("delete from x_printfilm_ink_formula_component where ink_formula_id = %s", (ink_id,))
    for ln in lines:
        cur.execute("insert into x_printfilm_ink_formula_component (ink_formula_id, seq_no, component_name, ratio_pct, created_by) values (%s, %s, %s, %s, %s)",
                    (ink_id, ln["seq_no"], ln["component_name"], ln["ratio_pct"], by))


@router.post(INKS)                                                                     # F-X-PRT-09 잉크조성 등록 (+ 조성 행 N줄 · 한 tx)
def ink_create(request: Request, ink_code: str = Form(...), ink_name: str = Form(...), color_name: str | None = Form(None),
               target_l: str | None = Form(None), target_a: str | None = Form(None), target_b: str | None = Form(None), note: str | None = Form(None),
               user: rbac.User = rbac.require_fn("F-X-PRT-09")):
    code, name = f.req_text(ink_code, "ink_code", "잉크 코드"), f.req_text(ink_name, "ink_name", "잉크명")
    if conn.q1("select 1 from x_printfilm_ink_formula where ink_code = %s", (code,)):
        raise http.validation_error(t("이미 있는 잉크 코드입니다"), fields=[f.field_error("ink_code", "잉크 코드", code)])
    lines = sh.component_lines(_form(request), required=False)                         # 기준 조성은 합 100 을 강제하지 않는다 (F-X-CLR-02 만)
    with conn.tx() as cur:
        cur.execute("""insert into x_printfilm_ink_formula (ink_code, ink_name, color_name, target_l, target_a, target_b, note, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                    (code, name, f.opt_text(color_name), sh.lab(target_l, "target_l"), sh.lab(target_a, "target_a"), sh.lab(target_b, "target_b"), f.opt_text(note), user.login_id))
        new_id = cur.fetchone()["id"]
        _write_components(cur, new_id, lines, user.login_id)
    audit.log_change(request, user, "F-X-PRT-09", f"x_printfilm_ink_formula:{code}", {"components": len(lines)})
    return http.saved(request, t("잉크조성을 등록했습니다") + f" — {code}", back=f"{INKS}?id={new_id}", data={"id": new_id, "ink_code": code, "components": len(lines)})


@router.post(INKS + "/{id}")                                                           # F-X-PRT-10 잉크조성 수정 (조성 행은 통째로 바꿔 넣는다)
def ink_update(request: Request, id: int, ink_code: str | None = Form(None), ink_name: str | None = Form(None), color_name: str | None = Form(None),
               target_l: str | None = Form(None), target_a: str | None = Form(None), target_b: str | None = Form(None), note: str | None = Form(None),
               use_yn: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-PRT-10")):
    row = _require("x_printfilm_ink_formula", id, "잉크조성")
    if f.opt_text(ink_code) and ink_code.strip() != row["ink_code"]:
        raise http.validation_error(t("잉크 코드는 바꿀 수 없습니다"), fields=[f.field_error("ink_code", "잉크 코드", ink_code)])
    form = _form(request)
    replace = any(k in form for k in ("component_name", "ratio_pct"))
    lines = sh.component_lines(form, required=False) if replace else []
    with conn.tx() as cur:
        cur.execute("""update x_printfilm_ink_formula set ink_name = %s, color_name = %s, target_l = %s, target_a = %s, target_b = %s, note = %s, use_yn = %s,
                              updated_at = now(), updated_by = %s where id = %s""",
                    (f.opt_text(ink_name) or row["ink_name"], f.opt_text(color_name) if color_name is not None else row["color_name"],
                     sh.lab(target_l, "target_l") if f.opt_text(target_l) else row["target_l"], sh.lab(target_a, "target_a") if f.opt_text(target_a) else row["target_a"],
                     sh.lab(target_b, "target_b") if f.opt_text(target_b) else row["target_b"], f.opt_text(note) if note is not None else row["note"],
                     sh.yn(use_yn, row["use_yn"]), user.login_id, id))
        if replace:
            _write_components(cur, id, lines, user.login_id)
    audit.log_change(request, user, "F-X-PRT-10", f"x_printfilm_ink_formula:{row['ink_code']}", {"components": len(lines) if replace else None})
    return http.saved(request, t("잉크조성을 수정했습니다") + f" — {row['ink_code']}", back=f"{INKS}?id={id}", data={"id": id, "ink_code": row["ink_code"], "components": len(lines) if replace else None})


@router.post(INKS + "/{id}/delete")                                                    # F-X-PRT-11 잉크조성 삭제 (Job · 조색 기록 참조 422 · 조성 행 cascade)
def ink_delete(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-PRT-11")):
    row = _require("x_printfilm_ink_formula", id, "잉크조성")
    n_job = _in_use("select count(*) as n from x_printfilm_job_work_order_ext where ink_formula_id = %s", (id,))
    n_rec = _in_use("select count(*) as n from x_printfilm_color_record where ink_formula_id = %s", (id,))
    if n_job or n_rec:
        raise http.validation_error(t("사용 중이라 삭제할 수 없습니다"), fields=[f.field_error("id", "잉크조성", f"{row['ink_code']} — Job {n_job} · {t('조색 기록')} {n_rec}")])
    with conn.tx() as cur:
        cur.execute("delete from x_printfilm_ink_formula where id = %s", (id,))
    audit.log_change(request, user, "F-X-PRT-11", f"x_printfilm_ink_formula:{row['ink_code']}")
    return http.saved(request, t("잉크조성을 삭제했습니다") + f" — {row['ink_code']}", back=INKS, data={"id": id, "ink_code": row["ink_code"]})
