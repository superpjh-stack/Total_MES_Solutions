"""bas 라우터 — 기준정보 (기능 36 · 화면 9) · 담당 개발1.

쓰는 테이블: `bas_*` 10 (db-schema.md §2). 이 밖에는 쓰지 않는다.
화면 9 중 8 은 **마스터 4기능**(등록 · 수정 · 삭제 · 조회)이라 한 벌의 처리(`Master` + `register`)를 설정만 바꿔 건다.
BOM(BAS-02)은 헤더 + 구성품 N줄이라 따로 쓴다. 규약은 여기 한 곳에 있다 — `job.py` · `sys.py` 가 폼 도우미를 가져다 쓴다.

  · 조회  `GET <화면>` — `?q=`(코드 · 이름) · 화면별 필터 · `?use_yn=` · `?edit=<id>`(수정 폼). 0건이면 `미수집`(G-C11).
  · 등록  `POST <화면>` — 필수 누락 · 코드 중복 422. 팩 속성은 `packs.read_attrs`(E2).
  · 수정  `POST <화면>/{id}` — 코드는 못 바꾼다(다른 코드를 보내면 422). 폼에 있는 항목만 바꾼다. 없는 ID 404.
  · 삭제  `POST <화면>/{id}/delete` — 다른 테이블이 참조하면 삭제 대신 `use_yn=N` 안내 422. 없는 ID 404.
  · 쓰기 흐름 — 검증 → `packs.hook("validate_<table>")` → `tx` → 저장 → `packs.hook("after_save_<table>")`(D-504) → `audit.log_change` → `http.saved`.
  · 권한은 `rbac.require_fn` — 조회 역할의 쓰기는 403. 메서드 · 경로는 function-list.md 의 API 열 글자 그대로.

담당 화면과 기능 (contracts/function-list.md)
  BAS-01 품목 /bas/items F-BAS-01~04 · BAS-02 BOM /bas/bom F-BAS-05~08 · BAS-03 공정 /bas/processes F-BAS-09~12
  BAS-04 공정 측정값 정의 /bas/process-params F-BAS-13~16 (G-C24 의 출발점 — 개발2 ui.measure_fields 가 이 행을 읽는다)
  BAS-05 설비 /bas/equipment F-BAS-17~20 · BAS-06 거래처 /bas/partners F-BAS-21~24 · BAS-07 작업자 /bas/workers F-BAS-25~28
  BAS-08 불량코드 /bas/defect-codes F-BAS-29~32 · BAS-09 공통코드 /bas/codes F-BAS-33~36
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from starlette.datastructures import FormData

from ...db import conn
from .. import contracts, nav, packs, rbac, templating
from ..packs import t
from ..util import audit, http

router = APIRouter()

LIST_LIMIT = 1000           # 서버는 상한만 건다 — 화면이 한 쪽씩 보인다(app.js)
INT_MAX = 2_147_483_647
YN = ("Y", "N")
YN_OPTIONS = (("Y", "사용"), ("N", "미사용"))
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,49}$")       # 경로 · 바코드 · CSV 에 그대로 들어가는 글자만
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,49}$")              # 측정값 키 — pop_measure.param_key · collect 태그와 잇는다
NO_USE_YN = ("ord_plan", "ord_order_dtl", "job_work_order", "lot", "sys_user")   # use_yn 이 없는 참조 대상
IN_USE = "다른 데이터가 참조하고 있어 삭제할 수 없습니다 — 사용 여부를 N 으로 바꿔 둔다"


# ── 폼 값 읽기 (계약: 필수 누락 · 형식 오류는 422) ─────────────────────────
async def form_data(request: Request) -> FormData:
    """HTML 폼 본문. 항목이 화면마다 달라 한꺼번에 받는다 — 검증은 `*_of` 가 한다. 동기 라우터가 Depends 로 받는다."""
    return await request.form()


def bad(message: str, name: str, reason: str, label: str | None = None) -> Exception:
    return http.validation_error(t(message), fields=[{"name": name, "label": t(label or name), "reason": reason}])


def text_of(form: FormData, key: str, label: str, *, required: bool = False, max_len: int = 500) -> str | None:
    """글자 항목. 앞뒤 공백을 떼고, 비면 None(필수면 422)."""
    raw = form.get(key)
    value = raw.strip() if isinstance(raw, str) else ""
    if "\x00" in value:
        raise bad("입력값을 확인해 주세요", key, "쓸 수 없는 글자가 들어 있습니다", label)
    if len(value) > max_len:
        raise bad("입력값을 확인해 주세요", key, f"{max_len}자를 넘습니다", label)
    if not value:
        if required:
            raise bad("필수값이 빠졌습니다", key, "필수값입니다", label)
        return None
    return value


def code_of(form: FormData, key: str, label: str, *, required: bool = True, pattern: re.Pattern = CODE_RE) -> str | None:
    value = text_of(form, key, label, required=required, max_len=50)
    if value is not None and not pattern.match(value):
        raise bad("입력값을 확인해 주세요", key, "영문 · 숫자 · `_` `.` `-` 로 50자까지 (첫 글자는 영문 · 숫자)", label)
    return value


def int_of(form: FormData, key: str, label: str, *, required: bool = False, positive: bool = False, non_negative: bool = False) -> int | None:
    value = text_of(form, key, label, required=required, max_len=20)
    if value is None:
        return None
    try:
        number = int(value)
    except ValueError:
        raise bad("입력값을 확인해 주세요", key, f"정수가 아닙니다: {value}", label) from None
    if abs(number) > INT_MAX:
        raise bad("입력값을 확인해 주세요", key, "값이 너무 큽니다", label)
    if positive and number <= 0:
        raise bad("입력값을 확인해 주세요", key, "0 보다 커야 합니다", label)
    if non_negative and number < 0:
        raise bad("입력값을 확인해 주세요", key, "0 이상이어야 합니다", label)
    return number


def decimal_of(form: FormData, key: str, label: str, *, required: bool = False, positive: bool = False,
               non_negative: bool = False, int_digits: int = 15, scale: int = 3) -> Decimal | None:
    """숫자 항목. `int_digits` = 정수부 자릿수 상한(numeric(p,s) 의 p−s) · `scale` = 소수 자릿수."""
    value = text_of(form, key, label, required=required, max_len=40)
    if value is None:
        return None
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation:
        raise bad("입력값을 확인해 주세요", key, f"숫자가 아닙니다: {value}", label) from None
    if not number.is_finite():
        raise bad("입력값을 확인해 주세요", key, f"숫자가 아닙니다: {value}", label)
    number = round(number, scale)
    if abs(number) >= Decimal(10) ** int_digits:
        raise bad("입력값을 확인해 주세요", key, "값이 너무 큽니다", label)
    if positive and number <= 0:
        raise bad("입력값을 확인해 주세요", key, "0 보다 커야 합니다", label)
    if non_negative and number < 0:
        raise bad("입력값을 확인해 주세요", key, "0 이상이어야 합니다", label)
    return number


def yn_of(form: FormData, key: str, label: str, *, default: str | None = "Y") -> str | None:
    value = text_of(form, key, label, max_len=5)
    if value is None:
        return default
    value = value.upper()
    if value in ("1", "TRUE", "ON", "YES"):
        value = "Y"
    if value in ("0", "FALSE", "OFF", "NO"):
        value = "N"
    if value not in YN:
        raise bad("입력값을 확인해 주세요", key, f"Y 또는 N 이어야 합니다: {value}", label)
    return value


def choice_of(form: FormData, key: str, label: str, choices: tuple[str, ...] | list[str], *, required: bool = False) -> str | None:
    value = text_of(form, key, label, required=required, max_len=100)
    if value is not None and value not in choices:
        raise bad("입력값을 확인해 주세요", key, f"{' · '.join(choices)} 중 하나여야 합니다: {value}", label)
    return value


def ref_of(form: FormData, key: str, label: str, table: str, *, required: bool = False, active_only: bool = True) -> int | None:
    """다른 기준정보를 가리키는 ID 항목 — 없는 ID 는 사용자가 고른 값이므로 404 가 아니라 422."""
    value = text_of(form, key, label, required=required, max_len=20)
    if value is None:
        return None
    if not value.isdigit() or len(value) > 18:
        raise bad("입력값을 확인해 주세요", key, f"없는 {t(label)} 입니다: {value}", label)
    cond = ""
    if active_only:
        cond = " and status = '사용'" if table == "sys_user" else ("" if table in NO_USE_YN else " and use_yn = 'Y'")
    if conn.q1(f"select 1 as hit from {table} where id = %s{cond}", (int(value),)) is None:
        raise bad("입력값을 확인해 주세요", key, f"없는(또는 사용 중지된) {t(label)} 입니다: {value}", label)
    return int(value)


def list_of(form: FormData, key: str, label: str) -> list[str] | None:
    """쉼표로 나눈 목록 (select 형식의 선택지)."""
    value = text_of(form, key, label, max_len=1000)
    if value is None:
        return None
    items = [s.strip() for s in value.split(",") if s.strip()]
    if not items:
        raise bad("입력값을 확인해 주세요", key, "쉼표로 나눈 선택지가 하나 이상 있어야 합니다", label)
    return items


def id_of_path(raw: str) -> int:
    """경로의 `{id}`. 숫자가 아니거나 범위를 벗어나면 그런 대상은 없다 → 404 (api-contract.md §1)."""
    if not raw.isascii() or not raw.isdigit() or len(raw) > 18:
        raise http.not_found()
    return int(raw)


def contains(column: str) -> str:
    """부분 일치 조건(대소문자 무시). `%` · `_` 를 와일드카드로 보지 않는다."""
    return f"position(lower(%s) in lower({column})) > 0"


def codes_of(group: str) -> list[tuple[str, str]]:
    """공통코드 그룹의 (코드, 이름) — 선택칸 · 검증에 쓴다."""
    return [(r["code"], r["code_name"]) for r in conn.q(
        "select code, code_name from bas_code where group_code = %s and use_yn = 'Y' order by seq, code", (group,))]


def table_label(table: str) -> str:
    tb = contracts.db_tables().get(table)
    return t(tb.desc.split("(")[0].split("—")[0].strip()) if tb else table


# ── 참조 검사 (삭제 422) ────────────────────────────────────────────────
def references_to(table: str, row_id: int, pk: str = "id") -> list[str]:
    """`table.pk = row_id` 를 가리키는 다른 테이블들. FK 는 DB 카탈로그에서 읽는다 — 스키마에 참조가 늘어도 여기를 고치지 않는다."""
    fks = conn.q(
        """select c.conrelid::regclass::text as ref_table, a.attname as ref_column
             from pg_constraint c
             join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
             join pg_attribute pa on pa.attrelid = c.confrelid and pa.attnum = c.confkey[1]
            where c.contype = 'f' and c.confrelid = %s::regclass and c.confdeltype <> 'c'
              and array_length(c.conkey, 1) = 1 and pa.attname = %s
            order by 1, 2""", (table, pk))
    used: list[str] = []
    for fk in fks:
        if conn.q1(f'select 1 as hit from "{fk["ref_table"]}" where "{fk["ref_column"]}" = %s limit 1', (row_id,)):
            used.append(f"{table_label(fk['ref_table'])} ({fk['ref_table']}.{fk['ref_column']})")
    return used


def refuse_if_referenced(table: str, row_id: int, name: str) -> None:
    used = references_to(table, row_id)
    if used:
        raise http.validation_error(t(IN_USE), fields=[{"name": name, "label": t("참조"), "reason": " · ".join(used)}])


# ── 마스터 한 벌 ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"            # text | code | key | int | decimal | yn | choice | codes | ref | list
    required: bool = False
    max_len: int = 200
    choices: tuple[str, ...] = ()  # choice
    group: str = ""                # codes — 공통코드 그룹
    ref: str = ""                  # ref — 테이블
    positive: bool = False
    non_negative: bool = False
    scale: int = 3
    default: Any = None            # 등록 때 폼에 없으면 이 값

    def parse(self, form: FormData) -> Any:
        k = self.kind
        if k == "text":
            return text_of(form, self.name, self.label, required=self.required, max_len=self.max_len)
        if k == "code":
            return code_of(form, self.name, self.label, required=self.required)
        if k == "key":
            return code_of(form, self.name, self.label, required=self.required, pattern=KEY_RE)
        if k == "int":
            return int_of(form, self.name, self.label, required=self.required, positive=self.positive, non_negative=self.non_negative)
        if k == "decimal":
            return decimal_of(form, self.name, self.label, required=self.required, positive=self.positive,
                              non_negative=self.non_negative, scale=self.scale)
        if k == "yn":
            return yn_of(form, self.name, self.label, default=self.default if self.default is not None else "Y")
        if k == "choice":
            return choice_of(form, self.name, self.label, self.choices, required=self.required)
        if k == "codes":
            return choice_of(form, self.name, self.label, [c for c, _ in codes_of(self.group)], required=self.required)
        if k == "ref":
            return ref_of(form, self.name, self.label, self.ref, required=self.required)
        if k == "list":
            return list_of(form, self.name, self.label)
        raise ValueError(f"모르는 field kind {k!r}")

    @property
    def sql_cast(self) -> str:
        return "%s::jsonb" if self.kind == "list" else "%s"

    def to_sql(self, value: Any) -> Any:
        if self.kind == "list" and value is not None:
            return json.dumps(value, ensure_ascii=False)
        return value

    def options(self) -> list[tuple[str, str]]:
        """선택칸 목록 — choice · codes · yn (ref 는 Master.options 가 준다)."""
        if self.kind == "choice":
            return [(c, c) for c in self.choices]
        if self.kind == "codes":
            return codes_of(self.group)
        if self.kind == "yn":
            return list(YN_OPTIONS)
        return []


@dataclass(frozen=True)
class Master:
    screen_id: str
    table: str
    label: str                                  # 화면에서 부르는 이름 (t() 로 치환)
    template: str
    fns: tuple[str, str, str, str]              # (등록, 수정, 삭제, 조회)
    code: Field                                 # 코드 — 등록 뒤 못 바꾼다
    name_col: str                               # 이름 컬럼 (검색 · 표시)
    fields: tuple[Field, ...]                   # 코드 제외
    uniq: tuple[str, ...]                       # 중복 판정 컬럼 (코드 포함)
    order_by: str
    filters: tuple[str, ...] = ()               # ?<컬럼>= 정확히 거르는 컬럼
    extra_select: str = ""                      # 목록 SELECT 에 더하는 컬럼 (집계 · 참조 이름)
    joins: str = ""
    check: Callable[[dict, dict | None], None] | None = None    # 추가 검증 (row, 기존 행) — 422 는 bad() 로
    group_by: str = ""                          # 목록 그룹 표시 컬럼

    @property
    def columns(self) -> list[str]:
        return [self.code.name] + [f.name for f in self.fields]

    def all_fields(self) -> list[Field]:
        return [self.code, *self.fields]

    def options(self) -> dict[str, list[tuple[str, str]]]:
        out: dict[str, list[tuple[str, str]]] = {}
        for f in self.all_fields():
            if f.kind == "ref":
                out[f.name] = ref_options(f.ref)
            else:
                opts = f.options()
                if opts:
                    out[f.name] = opts
        return out


def ref_options(table: str) -> list[tuple[str, str]]:
    if table == "sys_user":
        return [(str(r["id"]), f"{r['login_id']} {r['user_name']}") for r in conn.q(
            "select id, login_id, user_name from sys_user where status = '사용' order by login_id")]
    code_col, name_col = REF_COLS[table]
    return [(str(r["id"]), f"{r[code_col]} {r[name_col]}") for r in conn.q(
        f"select id, {code_col}, {name_col} from {table} where use_yn = 'Y' order by {code_col} limit {LIST_LIMIT}")]


REF_COLS: dict[str, tuple[str, str]] = {
    "bas_item": ("item_code", "item_name"), "bas_process": ("process_code", "process_name"),
    "bas_equipment": ("equip_code", "equip_name"), "bas_partner": ("partner_code", "partner_name"),
    "bas_worker": ("worker_code", "worker_name"), "bas_defect_code": ("defect_code", "defect_name"),
}


def _dup_where(m: Master, row: dict, exclude_id: int | None) -> tuple[str, list]:
    cond = " and ".join(f"{c} = %s" for c in m.uniq)
    params: list = [row[c] for c in m.uniq]
    if exclude_id is not None:
        cond += " and id <> %s"
        params.append(exclude_id)
    return cond, params


def _row_of_path(m: Master, raw_id: str) -> dict:
    row = conn.q1(f"select * from {m.table} where id = %s", (id_of_path(raw_id),))
    if row is None:
        raise http.not_found()
    return row


def _list_rows(m: Master, request: Request) -> tuple[list[dict], dict[str, str]]:
    qp = request.query_params
    where, params = ["true"], []
    f: dict[str, str] = {"q": (qp.get("q") or "").strip(), "use_yn": (qp.get("use_yn") or "").strip(), "edit": (qp.get("edit") or "").strip()}
    if f["q"]:
        where.append(f"({contains('x.' + m.code.name)} or {contains('x.' + m.name_col)})")
        params += [f["q"], f["q"]]
    if f["use_yn"] in YN:
        where.append("x.use_yn = %s")
        params.append(f["use_yn"])
    for col in m.filters:
        v = (qp.get(col) or "").strip()
        f[col] = v
        if v:
            if col.endswith("_id"):
                if not v.isdigit():
                    raise bad("입력값을 확인해 주세요", col, f"없는 값입니다: {v}")
                where.append(f"x.{col} = %s")
                params.append(int(v))
            else:
                where.append(f"x.{col} = %s")
                params.append(v)
    rows = conn.q(f"select x.*{', ' + m.extra_select if m.extra_select else ''} from {m.table} x {m.joins} "
                  f"where {' and '.join(where)} order by {m.order_by} limit {LIST_LIMIT}", params)
    return rows, f


def register(m: Master) -> None:
    """마스터 4기능을 라우터에 건다 — 화면 GET 하나 + 쓰기 POST 셋. 함수 이름은 화면마다 다르게 둔다(OpenAPI · 로그)."""
    path = nav.path_of(m.screen_id)
    fn_create, fn_update, fn_delete, fn_list = m.fns
    attrs_table = m.table

    def view(request: Request, user: rbac.User = rbac.require_fn(fn_list)) -> HTMLResponse:
        rows, f = _list_rows(m, request)
        editing = _row_of_path(m, f["edit"]) if f["edit"] else None
        groups: list[str] = []
        if m.group_by:
            groups = list(dict.fromkeys(str(r.get(m.group_by) or "") for r in rows))
        return templating.render(request, m.template, {
            "master": {"screen_id": m.screen_id, "table": m.table, "label": m.label, "code": m.code.name, "name_col": m.name_col,
                       "fields": [{"name": x.name, "label": x.label, "kind": x.kind, "required": x.required} for x in m.all_fields()],
                       "filters": list(m.filters), "group_by": m.group_by},
            "rows": rows, "f": f, "editing": editing, "options": m.options(), "groups": groups,
            "attrs_specs": packs.attrs_of(attrs_table), "path": path,
            "can": {"create": user.can(fn_create), "update": user.can(fn_update), "delete": user.can(fn_delete)},
        }, screen_id=m.screen_id)

    def create(request: Request, user: rbac.User = rbac.require_fn(fn_create), form: FormData = Depends(form_data)):
        row: dict[str, Any] = {m.code.name: m.code.parse(form)}
        for x in m.fields:
            v = x.parse(form)
            row[x.name] = x.default if (v is None and x.default is not None and x.name not in form) else v
        if any(row.get(c) is None for c in m.uniq):
            missing = [c for c in m.uniq if row.get(c) is None]
            raise bad("필수값이 빠졌습니다", missing[0], "필수값입니다")
        cond, params = _dup_where(m, row, None)
        if conn.q1(f"select 1 as hit from {m.table} where {cond}", params):
            raise bad(f"이미 있는 {m.label} 코드입니다", m.code.name, " / ".join(str(row[c]) for c in m.uniq), m.code.label)
        try:
            row["attrs"] = packs.read_attrs(form, attrs_table)
        except ValueError as exc:
            raise http.validation_error(str(exc), fields=[{"name": "attrs", "label": t("업종 속성"), "reason": str(exc)}]) from None
        if m.check:
            m.check(row, None)
        cols = [m.code, *m.fields]
        with conn.tx() as cur:
            packs.hook(f"validate_{m.table}")(cur, row, user)
            cur.execute(f"insert into {m.table} ({', '.join(x.name for x in cols)}, attrs, created_by) "
                        f"values ({', '.join(x.sql_cast for x in cols)}, %s::jsonb, %s) returning id",
                        [*(x.to_sql(row[x.name]) for x in cols), json.dumps(row["attrs"], ensure_ascii=False), user.login_id])
            row["id"] = cur.fetchone()["id"]
            packs.hook(f"after_save_{m.table}")(cur, row, user)
        audit.log_change(request, user, fn_create, f"{m.table}:{row[m.code.name]}", {"id": row["id"]})
        return http.saved(request, t("등록했습니다") + f" — {t(m.label)} {row[m.code.name]}", back=path, data={"id": row["id"], m.code.name: row[m.code.name]})

    def update(request: Request, id: str, user: rbac.User = rbac.require_fn(fn_update), form: FormData = Depends(form_data)):
        existing = _row_of_path(m, id)
        if m.code.name in form:
            new_code = m.code.parse(form)
            if new_code != existing[m.code.name]:
                raise bad(f"{m.label} 코드는 바꿀 수 없습니다", m.code.name, f"{existing[m.code.name]} → {new_code}", m.code.label)
        row: dict[str, Any] = {}
        for x in m.fields:
            if x.name in form:
                row[x.name] = x.parse(form)
                if row[x.name] is None and x.required:
                    raise bad("필수값이 빠졌습니다", x.name, "필수값입니다", x.label)
        if any(k.startswith("attr_") for k in form.keys()):
            try:
                row["attrs"] = {**(existing.get("attrs") or {}), **packs.read_attrs(form, attrs_table)}
            except ValueError as exc:
                raise http.validation_error(str(exc), fields=[{"name": "attrs", "label": t("업종 속성"), "reason": str(exc)}]) from None
        if not row:
            raise http.validation_error(t("바꿀 값이 없습니다"))
        merged = {**existing, **row}
        if any(c in row for c in m.uniq):
            cond, params = _dup_where(m, merged, existing["id"])
            if conn.q1(f"select 1 as hit from {m.table} where {cond}", params):
                raise bad(f"이미 있는 {m.label} 코드입니다", m.code.name, " / ".join(str(merged[c]) for c in m.uniq), m.code.label)
        if m.check:
            m.check(merged, existing)
        by_name = {x.name: x for x in m.fields}
        sets = [f"{k} = {by_name[k].sql_cast if k in by_name else ('%s::jsonb' if k == 'attrs' else '%s')}" for k in row]
        vals = [by_name[k].to_sql(v) if k in by_name else (json.dumps(v, ensure_ascii=False) if k == "attrs" else v) for k, v in row.items()]
        with conn.tx() as cur:
            packs.hook(f"validate_{m.table}")(cur, merged, user)
            cur.execute(f"update {m.table} set {', '.join(sets)}, updated_at = now(), updated_by = %s where id = %s",
                        [*vals, user.login_id, existing["id"]])
            packs.hook(f"after_save_{m.table}")(cur, merged, user)
        audit.log_change(request, user, fn_update, f"{m.table}:{existing[m.code.name]}", {"id": existing["id"], "changed": list(row)})
        return http.saved(request, t("수정했습니다") + f" — {t(m.label)} {existing[m.code.name]}", back=path, data={"id": existing["id"], "changed": list(row)})

    def delete(request: Request, id: str, user: rbac.User = rbac.require_fn(fn_delete)):
        existing = _row_of_path(m, id)
        if m.table == "bas_code" and existing.get("is_core") == "Y":
            raise bad("코어 예약 코드는 삭제할 수 없습니다", "code", f"{existing['group_code']}/{existing['code']}", "공통코드")
        refuse_if_referenced(m.table, existing["id"], m.code.name)
        with conn.tx() as cur:
            cur.execute(f"delete from {m.table} where id = %s", (existing["id"],))
        audit.log_change(request, user, fn_delete, f"{m.table}:{existing[m.code.name]}", {"id": existing["id"]})
        return http.saved(request, t("삭제했습니다") + f" — {t(m.label)} {existing[m.code.name]}", back=path, data={"id": existing["id"]})

    stem = m.screen_id.replace("-", "_").lower()
    view.__name__, create.__name__, update.__name__, delete.__name__ = f"list_{stem}", f"create_{stem}", f"update_{stem}", f"delete_{stem}"
    router.add_api_route(path, view, methods=["GET"], response_class=HTMLResponse)               # 조회 = 화면 GET
    router.add_api_route(path, create, methods=["POST"])                                         # 등록
    router.add_api_route(path + "/{id}", update, methods=["POST"])                               # 수정
    router.add_api_route(path + "/{id}/delete", delete, methods=["POST"])                        # 삭제


# ── 화면별 설정 ──────────────────────────────────────────────────────────
def _check_process_param(row: dict, _existing: dict | None) -> None:
    lo, hi = row.get("min_value"), row.get("max_value")
    if lo is not None and hi is not None and lo > hi:
        raise bad("입력값을 확인해 주세요", "max_value", f"상한({hi})이 하한({lo})보다 작습니다", "상한")
    if row.get("value_type") == "select" and not row.get("choices"):
        raise bad("입력값을 확인해 주세요", "choices", "select 형식은 선택지가 필요합니다", "선택지")
    if row.get("source") == "collect" and not row.get("collect_tag"):
        row["collect_tag"] = row.get("param_key")          # 기본 태그 = 키 (db-schema.md)


ITEMS = Master("BAS-01", "bas_item", "품목", "bas/items.html", ("F-BAS-01", "F-BAS-02", "F-BAS-03", "F-BAS-04"),
               Field("item_code", "품목 코드", "code", required=True), "item_name",
               (Field("item_name", "품목명", required=True), Field("item_type", "구분", "codes", required=True, group="ITEM_TYPE"),
                Field("spec", "규격"), Field("unit", "단위", max_len=20), Field("use_yn", "사용 여부", "yn")),
               ("item_code",), "x.item_code", filters=("item_type",))

PROCESSES = Master("BAS-03", "bas_process", "공정", "bas/processes.html", ("F-BAS-09", "F-BAS-10", "F-BAS-11", "F-BAS-12"),
                   Field("process_code", "공정 코드", "code", required=True), "process_name",
                   (Field("process_name", "공정 이름", required=True), Field("seq", "순서", "int", non_negative=True, default=0),
                    Field("use_yn", "사용 여부", "yn")),
                   ("process_code",), "x.seq, x.process_code",
                   extra_select="(select count(*) from bas_process_param p where p.process_id = x.id and p.use_yn = 'Y') as param_count, "
                                "(select count(*) from bas_equipment e where e.process_id = x.id and e.use_yn = 'Y') as equipment_count")

PROCESS_PARAMS = Master("BAS-04", "bas_process_param", "공정 측정값", "bas/process_params.html", ("F-BAS-13", "F-BAS-14", "F-BAS-15", "F-BAS-16"),
                        Field("param_key", "키", "key", required=True), "label",
                        (Field("process_id", "공정", "ref", required=True, ref="bas_process"), Field("label", "라벨", required=True),
                         Field("unit", "단위", max_len=20), Field("value_type", "형식", "choice", choices=("number", "text", "bool", "select"), default="number"),
                         Field("choices", "선택지", "list"), Field("min_value", "하한", "decimal", scale=4), Field("max_value", "상한", "decimal", scale=4),
                         Field("required_yn", "필수", "yn", default="N"), Field("source", "수집원", "choice", choices=("manual", "collect"), default="manual"),
                         Field("collect_tag", "수집 태그", max_len=100), Field("agg", "대표값", "choice", choices=("last", "avg", "max", "min"), default="last"),
                         Field("seq", "순서", "int", non_negative=True, default=0), Field("use_yn", "사용 여부", "yn")),
                        ("process_id", "param_key"), "p.seq, p.process_code, x.seq, x.param_key", filters=("process_id", "source"),
                        extra_select="p.process_code, p.process_name", joins="join bas_process p on p.id = x.process_id",
                        check=_check_process_param, group_by="process_name")

EQUIPMENT = Master("BAS-05", "bas_equipment", "설비", "bas/equipment.html", ("F-BAS-17", "F-BAS-18", "F-BAS-19", "F-BAS-20"),
                   Field("equip_code", "설비 코드", "code", required=True), "equip_name",
                   (Field("equip_name", "설비 이름", required=True), Field("process_id", "공정", "ref", ref="bas_process"),
                    Field("collect_yn", "수집 여부", "yn", default="N"), Field("use_yn", "사용 여부", "yn")),
                   ("equip_code",), "p.seq nulls last, x.equip_code", filters=("process_id",),
                   extra_select="p.process_code, p.process_name, (select max(c.ts) from eqp_collect c where c.equipment_id = x.id) as last_collect_at",
                   joins="left join bas_process p on p.id = x.process_id", group_by="process_name")

PARTNERS = Master("BAS-06", "bas_partner", "거래처", "bas/partners.html", ("F-BAS-21", "F-BAS-22", "F-BAS-23", "F-BAS-24"),
                  Field("partner_code", "거래처 코드", "code", required=True), "partner_name",
                  (Field("partner_name", "거래처명", required=True), Field("partner_type", "구분", "codes", required=True, group="PARTNER_TYPE"),
                   Field("contact", "연락처"), Field("use_yn", "사용 여부", "yn")),
                  ("partner_code",), "x.partner_code", filters=("partner_type",))

WORKERS = Master("BAS-07", "bas_worker", "작업자", "bas/workers.html", ("F-BAS-25", "F-BAS-26", "F-BAS-27", "F-BAS-28"),
                 Field("worker_code", "작업자 코드", "code", required=True), "worker_name",
                 (Field("worker_name", "이름", required=True), Field("process_id", "담당 공정", "ref", ref="bas_process"),
                  Field("user_id", "사용자 계정", "ref", ref="sys_user"), Field("use_yn", "사용 여부", "yn")),
                 ("worker_code",), "p.seq nulls last, x.worker_code", filters=("process_id",),
                 extra_select="p.process_code, p.process_name, u.login_id", joins="left join bas_process p on p.id = x.process_id left join sys_user u on u.id = x.user_id",
                 group_by="process_name")

DEFECT_CODES = Master("BAS-08", "bas_defect_code", "불량코드", "bas/defect_codes.html", ("F-BAS-29", "F-BAS-30", "F-BAS-31", "F-BAS-32"),
                      Field("defect_code", "불량 코드", "code", required=True), "defect_name",
                      (Field("defect_name", "불량 이름", required=True), Field("process_id", "공정", "ref", ref="bas_process"),
                       Field("use_yn", "사용 여부", "yn")),
                      ("defect_code",), "x.defect_code", filters=("process_id",),
                      extra_select="p.process_code, p.process_name", joins="left join bas_process p on p.id = x.process_id")

CODES = Master("BAS-09", "bas_code", "공통코드", "bas/codes.html", ("F-BAS-33", "F-BAS-34", "F-BAS-35", "F-BAS-36"),
               Field("code", "코드", "code", required=True), "code_name",
               (Field("group_code", "그룹", "code", required=True), Field("code_name", "이름", required=True),
                Field("seq", "순서", "int", non_negative=True, default=0), Field("use_yn", "사용 여부", "yn")),
               ("group_code", "code"), "x.group_code, x.seq, x.code", filters=("group_code",), group_by="group_code")

for _m in (ITEMS, PROCESSES, PROCESS_PARAMS, EQUIPMENT, PARTNERS, WORKERS, DEFECT_CODES, CODES):
    register(_m)


# ── BAS-02 BOM — 헤더 + 구성품 N줄 (F-BAS-05~08) ─────────────────────────
BOM = nav.path_of("BAS-02")
_BOM_SQL = """
select b.id, b.item_id, b.version, b.use_yn, b.attrs, b.created_at, b.created_by, b.updated_at, b.updated_by,
       i.item_code, i.item_name, i.item_type, i.unit as item_unit,
       (select count(*) from bas_bom_dtl d where d.bom_id = b.id) as line_count,
       (select count(*) from job_work_order w where w.bom_id = b.id) as work_order_count
  from bas_bom b join bas_item i on i.id = b.item_id
"""
_BOM_DTL_SQL = """
select d.id, d.bom_id, d.component_item_id, d.qty, d.unit, d.loss_rate, d.seq, d.attrs, c.item_code, c.item_name, c.item_type
  from bas_bom_dtl d join bas_item c on c.id = d.component_item_id
 where d.bom_id = any(%s) order by d.bom_id, d.seq, d.id
"""


def bom_of_path(raw_id: str) -> dict:
    row = conn.q1(_BOM_SQL + " where b.id = %s", (id_of_path(raw_id),))
    if row is None:
        raise http.not_found()
    return row


def parse_bom_lines(form: FormData, item_id: int) -> list[dict]:
    """구성품 줄 — `component_item_id` · `qty` · `unit` · `loss_rate` 가 같은 순서로 반복된다. 자기 자신 구성품 · 중복 구성품 422."""
    ids = [v for v in form.getlist("component_item_id")]
    qtys = form.getlist("qty")
    units = form.getlist("unit")
    losses = form.getlist("loss_rate")
    lines: list[dict] = []
    for i, raw in enumerate(ids):
        raw = (raw or "").strip() if isinstance(raw, str) else ""
        if not raw:
            continue
        single = FormData([("component_item_id", raw), ("qty", qtys[i] if i < len(qtys) else ""),
                           ("unit", units[i] if i < len(units) else ""), ("loss_rate", losses[i] if i < len(losses) else "")])
        cid = ref_of(single, "component_item_id", "구성품", "bas_item", required=True)
        if cid == item_id:
            raise bad("자기 자신을 구성품으로 넣을 수 없습니다", "component_item_id", str(cid), "구성품")
        if any(x["component_item_id"] == cid for x in lines):
            raise bad("같은 구성품이 두 번 있습니다", "component_item_id", str(cid), "구성품")
        lines.append({"component_item_id": cid, "qty": decimal_of(single, "qty", "소요량", required=True, positive=True),
                      "unit": text_of(single, "unit", "단위", max_len=20),
                      "loss_rate": decimal_of(single, "loss_rate", "손실률", non_negative=True) or Decimal(0), "seq": len(lines) + 1})
    if not lines:
        raise bad("구성품이 한 줄 이상 있어야 합니다", "component_item_id", "비어 있습니다", "구성품")
    return lines


def _save_bom_lines(cur, bom_id: int, lines: list[dict], user: rbac.User) -> None:
    cur.execute("delete from bas_bom_dtl where bom_id = %s", (bom_id,))
    for ln in lines:
        row = {**ln, "bom_id": bom_id}
        packs.hook("validate_bas_bom_dtl")(cur, row, user)
        cur.execute("""insert into bas_bom_dtl (bom_id, component_item_id, qty, unit, loss_rate, seq, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s) returning id""",
                    (bom_id, ln["component_item_id"], ln["qty"], ln["unit"], ln["loss_rate"], ln["seq"], user.login_id))
        row["id"] = cur.fetchone()["id"]
        packs.hook("after_save_bas_bom_dtl")(cur, row, user)


@router.get(BOM, response_class=HTMLResponse)                                                   # F-BAS-08 BOM 조회 = 화면 GET
def bom_list(request: Request, item_id: str = "", q: str = "", edit: str = "", user: rbac.User = rbac.require_fn("F-BAS-08")) -> HTMLResponse:
    where, params = ["true"], []
    if item_id.strip():
        if not item_id.strip().isdigit():
            raise bad("입력값을 확인해 주세요", "item_id", f"없는 값입니다: {item_id}", "상위 품목")
        where.append("b.item_id = %s")
        params.append(int(item_id))
    if q.strip():
        where.append(f"({contains('i.item_code')} or {contains('i.item_name')})")
        params += [q.strip(), q.strip()]
    boms = conn.q(_BOM_SQL + f" where {' and '.join(where)} order by i.item_code, b.version limit {LIST_LIMIT}", params)
    dtls = conn.q(_BOM_DTL_SQL, ([b["id"] for b in boms],)) if boms else []
    for b in boms:
        b["lines"] = [d for d in dtls if d["bom_id"] == b["id"]]
    editing = next((b for b in boms if edit and str(b["id"]) == edit), None)
    if edit and editing is None:
        editing = bom_of_path(edit)
        editing["lines"] = conn.q(_BOM_DTL_SQL, ([editing["id"]],))
    trees = [{"item_code": k, "item_name": v[0]["item_name"], "boms": v} for k, v in
             {b["item_code"]: [x for x in boms if x["item_code"] == b["item_code"]] for b in boms}.items()]
    return templating.render(request, "bas/bom.html", {
        "rows": boms, "trees": trees, "f": {"item_id": item_id, "q": q, "edit": edit}, "editing": editing,
        "options": {"item_id": ref_options("bas_item")}, "attrs_specs": packs.attrs_of("bas_bom"), "path": BOM,
        "can": {"create": user.can("F-BAS-05"), "update": user.can("F-BAS-06"), "delete": user.can("F-BAS-07")},
    }, screen_id="BAS-02")


@router.post(BOM)                                                                                # F-BAS-05 BOM 등록
def bom_create(request: Request, user: rbac.User = rbac.require_fn("F-BAS-05"), form: FormData = Depends(form_data)):
    item_id = ref_of(form, "item_id", "상위 품목", "bas_item", required=True)
    version = text_of(form, "version", "버전", max_len=20) or "1"
    if conn.q1("select 1 as hit from bas_bom where item_id = %s and version = %s", (item_id, version)):
        raise bad("이미 있는 BOM 버전입니다", "version", f"{item_id} / {version}", "버전")
    lines = parse_bom_lines(form, item_id)
    try:
        attrs = packs.read_attrs(form, "bas_bom")
    except ValueError as exc:
        raise http.validation_error(str(exc), fields=[{"name": "attrs", "label": t("업종 속성"), "reason": str(exc)}]) from None
    row = {"item_id": item_id, "version": version, "use_yn": yn_of(form, "use_yn", "사용 여부"), "attrs": attrs, "lines": lines}
    with conn.tx() as cur:                                                                       # 헤더 + 구성품 N줄 = tx 하나
        packs.hook("validate_bas_bom")(cur, row, user)
        cur.execute("insert into bas_bom (item_id, version, use_yn, attrs, created_by) values (%s, %s, %s, %s::jsonb, %s) returning id",
                    (item_id, version, row["use_yn"], json.dumps(attrs, ensure_ascii=False), user.login_id))
        row["id"] = cur.fetchone()["id"]
        _save_bom_lines(cur, row["id"], lines, user)
        packs.hook("after_save_bas_bom")(cur, row, user)
    audit.log_change(request, user, "F-BAS-05", f"bas_bom:{row['id']}", {"item_id": item_id, "version": version, "lines": len(lines)})
    return http.saved(request, t("BOM을 등록했습니다"), back=BOM, data={"id": row["id"], "version": version, "lines": len(lines)})


@router.post(BOM + "/{id}")                                                                      # F-BAS-06 BOM 수정
def bom_update(request: Request, id: str, user: rbac.User = rbac.require_fn("F-BAS-06"), form: FormData = Depends(form_data)):
    existing = bom_of_path(id)
    if existing["work_order_count"] and "component_item_id" in form:
        raise bad("작업지시가 참조하는 BOM 버전입니다 — 새 버전으로 등록한다", "version", existing["version"], "버전")
    row: dict[str, Any] = {}
    if "item_id" in form:
        new_item = ref_of(form, "item_id", "상위 품목", "bas_item", required=True)
        if new_item != existing["item_id"]:
            raise bad("BOM 의 상위 품목은 바꿀 수 없습니다", "item_id", f"{existing['item_id']} → {new_item}", "상위 품목")
    if "version" in form:
        row["version"] = text_of(form, "version", "버전", required=True, max_len=20)
        if row["version"] != existing["version"] and conn.q1("select 1 as hit from bas_bom where item_id = %s and version = %s and id <> %s",
                                                            (existing["item_id"], row["version"], existing["id"])):
            raise bad("이미 있는 BOM 버전입니다", "version", row["version"], "버전")
    if "use_yn" in form:
        row["use_yn"] = yn_of(form, "use_yn", "사용 여부")
    lines = parse_bom_lines(form, existing["item_id"]) if "component_item_id" in form else None
    if any(k.startswith("attr_") for k in form.keys()):
        try:
            row["attrs"] = {**(existing.get("attrs") or {}), **packs.read_attrs(form, "bas_bom")}
        except ValueError as exc:
            raise http.validation_error(str(exc), fields=[{"name": "attrs", "label": t("업종 속성"), "reason": str(exc)}]) from None
    if not row and lines is None:
        raise http.validation_error(t("바꿀 값이 없습니다"))
    merged = {**existing, **row, "lines": lines}
    with conn.tx() as cur:
        packs.hook("validate_bas_bom")(cur, merged, user)
        if row:
            sets = ", ".join(f"{k} = %s::jsonb" if k == "attrs" else f"{k} = %s" for k in row)
            vals = [json.dumps(v, ensure_ascii=False) if k == "attrs" else v for k, v in row.items()]
            cur.execute(f"update bas_bom set {sets}, updated_at = now(), updated_by = %s where id = %s", [*vals, user.login_id, existing["id"]])
        if lines is not None:
            _save_bom_lines(cur, existing["id"], lines, user)
        packs.hook("after_save_bas_bom")(cur, merged, user)
    audit.log_change(request, user, "F-BAS-06", f"bas_bom:{existing['id']}", {"changed": list(row), "lines": len(lines) if lines else None})
    return http.saved(request, t("BOM을 수정했습니다"), back=BOM, data={"id": existing["id"], "changed": list(row), "lines": len(lines) if lines else None})


@router.post(BOM + "/{id}/delete")                                                               # F-BAS-07 BOM 삭제
def bom_delete(request: Request, id: str, user: rbac.User = rbac.require_fn("F-BAS-07")):
    existing = bom_of_path(id)
    if existing["work_order_count"]:
        raise bad("작업지시가 참조하는 BOM 은 삭제할 수 없습니다", "id", f"{t('작업지시')} {existing['work_order_count']}건", "BOM")
    with conn.tx() as cur:
        cur.execute("delete from bas_bom_dtl where bom_id = %s", (existing["id"],))
        cur.execute("delete from bas_bom where id = %s", (existing["id"],))
    audit.log_change(request, user, "F-BAS-07", f"bas_bom:{existing['id']}", {"item_id": existing["item_id"], "version": existing["version"]})
    return http.saved(request, t("BOM을 삭제했습니다"), back=BOM, data={"id": existing["id"]})
