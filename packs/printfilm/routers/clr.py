"""printfilm `clr` — 조색 기록 · 배합비 (F-X-CLR-01~05 · X-CLR-01 · 현장 POP · 개발2).

쓰는 테이블: x_printfilm_color_record · x_printfilm_color_record_mix 만 (write_scope.clr = []). Job(job_work_order) 은 읽기만 — 참조 필수.
배합비(F-X-CLR-02): 비율은 소수 셋째 자리로 반올림해 저장하고 **저장되는 값의 합이 100 이 아니면 422** — 사유에 「입력 → 저장되는 값」 이 보인다(엘컴화인 D-209).
"""

from __future__ import annotations

from decimal import Decimal

import anyio
from fastapi import APIRouter, Form, Request

from mescore.app import nav, rbac, templating
from mescore.app.packs import t
from mescore.app.routers import _dev2 as f
from mescore.app.util import audit, http
from mescore.db import conn

from . import _shared as sh

router = APIRouter()
RECORDS = nav.path_of("X-CLR-01")
HUNDRED = Decimal("100")


def _form(request: Request):
    return anyio.from_thread.run(request.form)


def _job_by_no(no: str | None) -> dict | None:
    if not f.opt_text(no):
        return None
    return conn.q1("select id, work_order_no, status, item_id from job_work_order where work_order_no = %s", (no.strip(),))


def _require_job(no: str | None, job_id: str | None) -> dict:
    wo = _job_by_no(no) if f.opt_text(no) else (conn.q1("select id, work_order_no, status, item_id from job_work_order where id = %s",
                                                        (f.int_id(job_id, "work_order_id", "Job", required=True),)))
    if wo is None:
        raise http.validation_error(t("없는 Job 번호입니다"), fields=[f.field_error("work_order_no", "Job", no or job_id or "")])
    if wo["status"] == "취소":
        raise http.validation_error(t("취소된 Job 에는 조색 기록을 남길 수 없습니다"), fields=[f.field_error("work_order_no", "Job", f"{wo['work_order_no']} {wo['status']}")])
    return wo


def _ink(code: str | None) -> int | None:
    c = f.opt_text(code)
    if not c:
        return None
    r = conn.q1("select id, use_yn from x_printfilm_ink_formula where ink_code = %s", (c,))
    if r is None:
        raise http.validation_error(t("없는 잉크 코드입니다"), fields=[f.field_error("ink_code", "잉크조성", c)])
    return r["id"]


def _require_record(id: int) -> dict:
    r = conn.q1("""select r.*, w.work_order_no, k.ink_code from x_printfilm_color_record r join job_work_order w on w.id = r.work_order_id
                    left join x_printfilm_ink_formula k on k.id = r.ink_formula_id where r.id = %s""", (int(id),))
    if r is None:
        raise http.not_found(t("없는 조색 기록입니다"))
    return r


def _records(work_order_id: int | None, frm, to, limit: int = 300) -> list[dict]:
    rows = conn.q("""select r.*, w.work_order_no, k.ink_code, k.ink_name,
                            (select string_agg(m.component_name || ' ' || m.ratio_pct::text || '%%', ' · ' order by m.seq_no) from x_printfilm_color_record_mix m where m.color_record_id = r.id) as mix,
                            (select coalesce(sum(m.ratio_pct), 0) from x_printfilm_color_record_mix m where m.color_record_id = r.id) as mix_sum
                       from x_printfilm_color_record r join job_work_order w on w.id = r.work_order_id
                       left join x_printfilm_ink_formula k on k.id = r.ink_formula_id
                      where (%s::bigint is null or r.work_order_id = %s) and r.recorded_at::date between %s and %s
                      order by r.work_order_id desc, r.color_name, r.seq_no limit %s""", (work_order_id, work_order_id, frm, to, limit))
    return rows


# ── X-CLR-01 ─────────────────────────────────────────────────────────────
@router.get(RECORDS)                                                                   # F-X-CLR-05 조색 기록 조회 (스캔 ?no= → 없는 Job 422 재렌더)
def records(request: Request, no: str | None = None, frm: str | None = None, to: str | None = None, user: rbac.User = rbac.require_fn("F-X-CLR-05")):
    d1, d2 = f.period(frm, to)
    ctx: dict = {"job": None, "rows": [], "frm": d1, "to": d2, "scan_no": no or "",
                 "ink_options": [(r["ink_code"], f"{r['ink_code']} {r['ink_name']}") for r in conn.q("select ink_code, ink_name from x_printfilm_ink_formula where use_yn = 'Y' order by ink_code")]}
    if no is not None and no.strip() != "":
        wo = _job_by_no(no)
        if wo is None:
            ctx["rows"] = _records(None, d1, d2)
            return f.scan_miss(request, "clr/records.html", ctx, screen_id="X-CLR-01", no=no, what="Job")
        ctx["job"] = wo
        ctx["rows"] = _records(wo["id"], d1, d2)
    else:
        ctx["rows"] = _records(None, d1, d2)
    for r in ctx["rows"]:
        r["mix_rows"] = conn.q("select seq_no, component_name, ratio_pct from x_printfilm_color_record_mix where color_record_id = %s order by seq_no", (r["id"],))
    return templating.render(request, "clr/records.html", ctx, screen_id="X-CLR-01")


@router.post(RECORDS)                                                                  # F-X-CLR-01 조색 기록 등록 (Job 참조 필수 · 차수 비우면 마지막 + 1)
def record_create(request: Request, work_order_no: str | None = Form(None), work_order_id: str | None = Form(None), color_name: str = Form(...),
                  seq_no: str | None = Form(None), color_l: str | None = Form(None), color_a: str | None = Form(None), color_b: str | None = Form(None),
                  ink_code: str | None = Form(None), note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-CLR-01")):
    wo = _require_job(work_order_no, work_order_id)
    cname = f.req_text(color_name, "color_name", "색 이름")
    ink_id = _ink(ink_code)
    seq = f.int_id(seq_no, "seq_no", "차수")
    with conn.tx() as cur:
        if seq is None:
            cur.execute("select coalesce(max(seq_no), 0) + 1 as n from x_printfilm_color_record where work_order_id = %s and color_name = %s", (wo["id"], cname))
            seq = int(cur.fetchone()["n"])
        elif seq < 1:
            raise http.validation_error(t("차수는 1 이상입니다"), fields=[f.field_error("seq_no", "차수", str(seq))])
        cur.execute("select 1 from x_printfilm_color_record where work_order_id = %s and color_name = %s and seq_no = %s", (wo["id"], cname, seq))
        if cur.fetchone():
            raise http.validation_error(t("같은 Job · 색 이름에 이미 있는 차수입니다"), fields=[f.field_error("seq_no", "차수", f"{wo['work_order_no']} {cname} #{seq}")])
        cur.execute("""insert into x_printfilm_color_record (work_order_id, ink_formula_id, color_name, seq_no, color_l, color_a, color_b, note, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                    (wo["id"], ink_id, cname, seq, sh.lab(color_l, "color_l"), sh.lab(color_a, "color_a"), sh.lab(color_b, "color_b"), f.opt_text(note), user.login_id))
        new_id = cur.fetchone()["id"]
    audit.log_change(request, user, "F-X-CLR-01", f"x_printfilm_color_record:{new_id}", {"job": wo["work_order_no"], "color": cname, "seq": seq})
    return http.saved(request, f"{t('조색 기록을 등록했습니다')} — {wo['work_order_no']} {cname} #{seq}", back=f"{RECORDS}?no={wo['work_order_no']}",
                      data={"id": new_id, "work_order_no": wo["work_order_no"], "color_name": cname, "seq_no": seq})


@router.post(RECORDS + "/{id}/mix")                                                    # F-X-CLR-02 배합비 등록 (통째로 바꿔 넣는다 · 합 100 아니면 422)
def mix_replace(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-CLR-02")):
    rec = _require_record(id)
    lines = sh.component_lines(_form(request), required=True)
    total = sum((ln["ratio_pct"] for ln in lines), Decimal("0"))
    if total != HUNDRED:
        shown = " + ".join(f"{ln['component_name']} {ln['input']} → {ln['ratio_pct']}" for ln in lines)
        raise http.validation_error(f"{t('비율 합이 100 이 아닙니다')} — {t('소수 셋째 자리로 반올림한 저장값으로 셉니다')}: {shown} = {total}",
                                    fields=[f.field_error("ratio_pct", "비율", f"{total} ≠ 100")])
    with conn.tx() as cur:
        cur.execute("delete from x_printfilm_color_record_mix where color_record_id = %s", (id,))
        for ln in lines:
            cur.execute("insert into x_printfilm_color_record_mix (color_record_id, seq_no, component_name, ratio_pct, created_by) values (%s, %s, %s, %s, %s)",
                        (id, ln["seq_no"], ln["component_name"], ln["ratio_pct"], user.login_id))
    audit.log_change(request, user, "F-X-CLR-02", f"x_printfilm_color_record:{id}", {"mix": len(lines)})
    return http.saved(request, f"{t('배합비를 등록했습니다')} — {len(lines)}", back=f"{RECORDS}?no={rec['work_order_no']}",
                      data={"id": id, "rows": [{"seq_no": ln["seq_no"], "component_name": ln["component_name"], "ratio_pct": float(ln["ratio_pct"])} for ln in lines], "total": float(total)})


@router.post(RECORDS + "/{id}")                                                        # F-X-CLR-03 조색 기록 수정 (Job 은 못 바꾼다)
def record_update(request: Request, id: int, work_order_no: str | None = Form(None), color_name: str | None = Form(None), color_l: str | None = Form(None),
                  color_a: str | None = Form(None), color_b: str | None = Form(None), ink_code: str | None = Form(None), note: str | None = Form(None),
                  user: rbac.User = rbac.require_fn("F-X-CLR-03")):
    rec = _require_record(id)
    if f.opt_text(work_order_no) and work_order_no.strip() != rec["work_order_no"]:
        raise http.validation_error(t("조색 기록의 Job 은 바꿀 수 없습니다"), fields=[f.field_error("work_order_no", "Job", work_order_no)])
    cname = f.opt_text(color_name) or rec["color_name"]
    ink_id = _ink(ink_code) if ink_code is not None and ink_code.strip() else (rec["ink_formula_id"] if ink_code is None else None)
    with conn.tx() as cur:
        if cname != rec["color_name"]:
            cur.execute("select 1 from x_printfilm_color_record where work_order_id = %s and color_name = %s and seq_no = %s and id <> %s", (rec["work_order_id"], cname, rec["seq_no"], id))
            if cur.fetchone():
                raise http.validation_error(t("같은 Job · 색 이름에 이미 있는 차수입니다"), fields=[f.field_error("color_name", "색 이름", f"{cname} #{rec['seq_no']}")])
        cur.execute("""update x_printfilm_color_record set color_name = %s, color_l = %s, color_a = %s, color_b = %s, ink_formula_id = %s, note = %s,
                              updated_at = now(), updated_by = %s where id = %s""",
                    (cname, sh.lab(color_l, "color_l") if f.opt_text(color_l) else rec["color_l"], sh.lab(color_a, "color_a") if f.opt_text(color_a) else rec["color_a"],
                     sh.lab(color_b, "color_b") if f.opt_text(color_b) else rec["color_b"], ink_id, f.opt_text(note) if note is not None else rec["note"], user.login_id, id))
    audit.log_change(request, user, "F-X-CLR-03", f"x_printfilm_color_record:{id}")
    return http.saved(request, t("조색 기록을 수정했습니다"), back=f"{RECORDS}?no={rec['work_order_no']}", data={"id": id, "color_name": cname})


@router.post(RECORDS + "/{id}/delete")                                                 # F-X-CLR-04 조색 기록 삭제 (배합비 행 cascade)
def record_delete(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-CLR-04")):
    rec = _require_record(id)
    with conn.tx() as cur:
        cur.execute("delete from x_printfilm_color_record where id = %s", (id,))
    audit.log_change(request, user, "F-X-CLR-04", f"x_printfilm_color_record:{id}", {"job": rec["work_order_no"]})
    return http.saved(request, t("조색 기록을 삭제했습니다"), back=f"{RECORDS}?no={rec['work_order_no']}", data={"id": id})
