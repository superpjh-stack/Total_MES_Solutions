"""cond — X-COND-01 품목별 공정 조건 기준 (F-X-COND-01~04 · 개발3). 쓰는 테이블: x_kimchi_item_std 만.

세척 · 절임 기준은 품목(× 크기구분)별이라 `bas_process_param`(공정별 범위)에 못 들어간다(README C-2 · D-509 차단 → 1차는 이 표). 키는 `bas_process_param.param_key`
또는 `aging_days` 만. 정본 값(9 % · 48 h · 13 % · 24 h · 소독수 10 ppm)은 시드가 아니라 **이 화면에서 입력**한다(임진강 D-08).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request

from mescore.app import nav, rbac, templating
from mescore.app.packs import t
from mescore.app.util import audit, http
from mescore.db import conn

from packs.kimchi import common
from packs.kimchi.common import f

router = APIRouter()
PATH = nav.path_of("X-COND-01")
SCREEN = "X-COND-01"
TABLE = "x_kimchi_item_std"


def _allowed_keys() -> list[str]:
    keys = [r["param_key"] for r in conn.q("select distinct param_key from bas_process_param where use_yn = 'Y' order by param_key")]
    return sorted(set(keys) | {common.AGING_DAYS_KEY})


def _row(std_id: int) -> dict:
    r = conn.q1(f"select * from {TABLE} where id = %s", (std_id,))
    if r is None:
        raise http.not_found(t("없는 공정 조건입니다"))
    return r


def _rows(process_id: int | None, item_id: int | None, param_key: str | None) -> list[dict]:
    return conn.q(f"""select s.*, p.process_code, p.process_name, i.item_code, i.item_name,
                             (select count(*) from x_kimchi_tank k where k.std_id = s.id and k.status <> '완료') as open_tanks
                        from {TABLE} s join bas_process p on p.id = s.process_id join bas_item i on i.id = s.item_id
                       where (%s::bigint is null or s.process_id = %s) and (%s::bigint is null or s.item_id = %s) and (%s::text is null or s.param_key = %s)
                       order by p.seq, i.item_code, s.size_type nulls first, s.param_key, s.valid_from desc, s.id desc limit 500""",
                  (process_id, process_id, item_id, item_id, param_key, param_key))


@router.get(PATH)                                                                      # F-X-COND-04 조회 = 화면 GET
def item_standards(request: Request, process_id: str | None = None, item_id: str | None = None, param_key: str | None = None,
                   user: rbac.User = rbac.require_fn("F-X-COND-04")):
    pid, iid = f.int_id(process_id, "process_id", "공정"), f.int_id(item_id, "item_id", "품목")
    key = f.opt_text(param_key)
    ctx = {"rows": _rows(pid, iid, key), "process_id": pid, "item_id": iid, "param_key": key or "", "today": date.today(),
           "process_options": f.options(conn.q("select id, process_code, process_name from bas_process where use_yn = 'Y' order by seq"), "id", "process_code", "process_name"),
           "item_options": f.options(conn.q("select id, item_code, item_name from bas_item where use_yn = 'Y' order by item_code"), "id", "item_code", "item_name"),
           "key_options": [(k, k) for k in _allowed_keys()],
           "size_options": [(c["code"], c["code_name"]) for c in conn.q("select code, code_name from bas_code where group_code = 'SIZE_TYPE' and use_yn = 'Y' order by seq")],
           "undecided_count": conn.q1(f"select count(*) as n from {TABLE} where std_value is null and use_yn = 'Y'")["n"]}
    return templating.render(request, "cond/item_standards.html", ctx, screen_id=SCREEN)


@router.post(PATH)                                                                     # F-X-COND-01 등록
def create(request: Request, process_id: str = Form(...), item_id: str = Form(...), param_key: str = Form(...), size_type: str | None = Form(None),
           std_value: str | None = Form(None), min_value: str | None = Form(None), max_value: str | None = Form(None), tolerance: str | None = Form(None),
           unit: str | None = Form(None), valid_from: str | None = Form(None), haccp_chk_yn: str | None = Form(None),
           user: rbac.User = rbac.require_fn("F-X-COND-01")):
    pid = f.int_id(process_id, "process_id", "공정", required=True)
    iid = f.int_id(item_id, "item_id", "품목", required=True)
    key = f.req_text(param_key, "param_key", "키")
    if conn.q1("select 1 from bas_process where id = %s", (pid,)) is None:
        raise http.validation_error(t("없는 공정입니다"), fields=[f.field_error("process_id", "공정", str(pid))])
    if conn.q1("select 1 from bas_item where id = %s", (iid,)) is None:
        raise http.validation_error(t("없는 품목입니다"), fields=[f.field_error("item_id", "품목", str(iid))])
    if key not in _allowed_keys():
        raise http.validation_error(t("측정값 정의에 없는 키입니다"), fields=[f.field_error("param_key", "키", key)])
    size = f.opt_text(size_type)
    if size and conn.q1("select 1 from bas_code where group_code = 'SIZE_TYPE' and code = %s and use_yn = 'Y'", (size,)) is None:
        raise http.validation_error(t("크기구분 코드가 아닙니다"), fields=[f.field_error("size_type", "크기구분", size)])
    day = f.a_date(valid_from, "valid_from", "적용 시작일", default=date.today())
    vals = {"std_value": f.num(std_value, "std_value", "기준값"), "min_value": f.num(min_value, "min_value", "하한"), "max_value": f.num(max_value, "max_value", "상한"),
            "tolerance": f.num(tolerance, "tolerance", "허용편차", nonneg=True)}
    if vals["min_value"] is not None and vals["max_value"] is not None and vals["min_value"] > vals["max_value"]:
        raise http.validation_error(t("하한이 상한보다 큽니다"), fields=[f.field_error("min_value", "하한", f"{vals['min_value']} > {vals['max_value']}")])
    if conn.q1(f"select 1 from {TABLE} where process_id = %s and item_id = %s and coalesce(size_type, '') = coalesce(%s, '') and param_key = %s and valid_from = %s",
               (pid, iid, size, key, day)):
        raise http.validation_error(t("같은 공정 · 품목 · 크기구분 · 키 · 적용일의 기준이 이미 있습니다"), fields=[f.field_error("param_key", "키", key)])
    with conn.tx() as cur:
        cur.execute(f"""insert into {TABLE} (process_id, item_id, size_type, param_key, std_value, min_value, max_value, tolerance, unit, haccp_chk_yn, valid_from, created_by)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                    (pid, iid, size, key, vals["std_value"], vals["min_value"], vals["max_value"], vals["tolerance"], f.opt_text(unit),
                     "Y" if (haccp_chk_yn or "").upper() in ("Y", "1", "ON", "TRUE") else "N", day, user.login_id))
        new_id = cur.fetchone()["id"]
    audit.log_change(request, user, "F-X-COND-01", f"{TABLE}:{new_id}", {"param_key": key, "std_value": str(vals["std_value"])})
    msg = t("공정 조건을 등록했습니다") + ("" if vals["std_value"] is not None else f" — {t('기준값')} {t('미확정')}")
    return http.saved(request, msg, data={"id": new_id, "undecided": vals["std_value"] is None})


@router.post(PATH + "/{id}")                                                           # F-X-COND-02 수정 (키 · 품목은 못 바꾼다)
def update(request: Request, id: int, std_value: str | None = Form(None), min_value: str | None = Form(None), max_value: str | None = Form(None),
           tolerance: str | None = Form(None), unit: str | None = Form(None), use_yn: str | None = Form(None), haccp_chk_yn: str | None = Form(None),
           user: rbac.User = rbac.require_fn("F-X-COND-02")):
    r = _row(id)
    new = {"std_value": f.num(std_value, "std_value", "기준값") if std_value not in (None, "") else r["std_value"],
           "min_value": f.num(min_value, "min_value", "하한") if min_value not in (None, "") else r["min_value"],
           "max_value": f.num(max_value, "max_value", "상한") if max_value not in (None, "") else r["max_value"],
           "tolerance": f.num(tolerance, "tolerance", "허용편차", nonneg=True) if tolerance not in (None, "") else r["tolerance"],
           "unit": f.opt_text(unit) if unit is not None else r["unit"],
           "use_yn": f.choice(use_yn, "use_yn", "사용 여부", ("Y", "N"), required=False) or r["use_yn"],
           "haccp_chk_yn": f.choice(haccp_chk_yn, "haccp_chk_yn", "HACCP 확인", ("Y", "N"), required=False) or r["haccp_chk_yn"]}
    with conn.tx() as cur:
        cur.execute(f"""update {TABLE} set std_value = %s, min_value = %s, max_value = %s, tolerance = %s, unit = %s, use_yn = %s, haccp_chk_yn = %s,
                               updated_at = now(), updated_by = %s where id = %s""",
                    (new["std_value"], new["min_value"], new["max_value"], new["tolerance"], new["unit"], new["use_yn"], new["haccp_chk_yn"], user.login_id, id))
    before = {k: str(r[k]) for k in new if str(r[k]) != str(new[k])}
    audit.log_change(request, user, "F-X-COND-02", f"{TABLE}:{id}", {"before": before, "after": {k: str(new[k]) for k in before}})
    return http.saved(request, t("공정 조건을 수정했습니다"), data={"id": id, "changed": sorted(before)})


@router.post(PATH + "/{id}/delete")                                                    # F-X-COND-03 사용중지 (삭제 대신 use_yn=N)
def deactivate(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-COND-03")):
    r = _row(id)
    if conn.q1("select 1 from x_kimchi_tank where std_id = %s and status <> '완료'", (id,)):
        raise http.validation_error(t("진행 중 절임통 배치가 참조하는 기준은 중지할 수 없습니다"), fields=[f.field_error("id", "공정 조건", str(id))])
    with conn.tx() as cur:
        cur.execute(f"update {TABLE} set use_yn = 'N', updated_at = now(), updated_by = %s where id = %s", (user.login_id, id))
    audit.log_change(request, user, "F-X-COND-03", f"{TABLE}:{id}", {"param_key": r["param_key"]})
    return http.saved(request, t("공정 조건을 사용중지했습니다"), data={"id": id, "use_yn": "N"})
