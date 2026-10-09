"""sys 라우터 — 시스템 (기능 16 · 화면 6) · 담당 개발1.

쓰는 테이블: `sys_*` 9 (db-schema.md §2). 권한 표 · 역할은 **DB 데이터** — 바꾸면 `rbac.invalidate()` 로 다음 요청부터 반영(G-C17).
비밀번호는 `auth.hash_password` 해시만 저장하고 화면 · 응답 · 로그 어디에도 값을 내보내지 않는다(G-C19).
사용자 상태는 요청마다 DB 에서 본다(D-19) — 중지 · 비밀번호 재설정은 그 사용자의 세션을 끊어 다음 요청부터 401.

담당 화면과 기능 (contracts/function-list.md)
  SYS-01 사용자 /sys/users — F-SYS-01 등록 · F-SYS-02 수정 · F-SYS-03 중지 · 해제 (/toggle) · F-SYS-04 조회
  SYS-02 역할 /sys/roles — F-SYS-05 등록(모든 메뉴 칸 `없음`) · F-SYS-06 수정(ADMIN 중지 불가) · F-SYS-07 조회(역할별 사용자 수)
  SYS-03 권한 표 /sys/permissions — F-SYS-08 수정(48칸 · ADMIN 의 sys 칸 `입력` 고정 · invalidate) · F-SYS-09 조회(빈 칸 `미확정`)
  SYS-04 접근 로그 /sys/logs — F-SYS-10 (G-C18. 비밀번호 · 세션 ID 는 없다)
  SYS-05 채번 규칙 /sys/numbering — F-SYS-11 수정 + `numbering.peek` 미리보기 · F-SYS-12 조회(오늘 카운터 · 다음 번호 · 규칙 없으면 `미확정 (D-10)`)
  SYS-06 백업 · 이관 /sys/backup — F-SYS-13 백업(tools/backup.py) · F-SYS-14 복구 확인(임시 DB) · F-SYS-15 이관(개발3 mescore.migrate.run — 모듈이 없으면 ImportError 그대로 · 화면에 "개발3 모듈 대기") · F-SYS-16 이력
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from starlette.datastructures import FormData

from ...db import conn
from .. import auth, contracts, nav, numbering, packs, rbac, templating
from ..packs import t
from ..settings import get_settings
from ..util import audit, http, screen
from .bas import bad, contains, form_data, id_of_path, int_of, ref_of, text_of, yn_of

router = APIRouter()

USERS, ROLES, PERMISSIONS, LOGS, NUMBERING, BACKUP = (nav.path_of("SYS-01"), nav.path_of("SYS-02"), nav.path_of("SYS-03"),
                                                      nav.path_of("SYS-04"), nav.path_of("SYS-05"), nav.path_of("SYS-06"))
ST_ACTIVE, ST_STOPPED, ST_LOCKED = auth.STATUS_ACTIVE, auth.STATUS_STOPPED, auth.STATUS_LOCKED
USER_STATUSES = (ST_ACTIVE, ST_STOPPED, ST_LOCKED)
LOGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{1,49}$")
ROLE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
PREFIX_RE = re.compile(r"^[A-Z0-9-]*$")
LOG_KINDS = (audit.LOGIN_OK, audit.LOGIN_FAIL, audit.VIEW, audit.CHANGE, audit.ERROR)
LOG_LIMIT, USER_LIMIT = 500, 1000
GUARDED_ROLE, GUARDED_MENU = "ADMIN", "sys"               # F-SYS-08 — 이 칸은 `입력` 고정
MIGRATE_MODULE = "mescore.migrate"
MIGRATE = BACKUP.rsplit("/", 1)[0] + "/migrate"           # POST /sys/migrate (function-list.md F-SYS-15)
MIGRATE_COMMANDS = ("basics", "orders", "lots", "history")  # function-list.md B-MIG-01~04

# 비밀번호 해시는 어떤 조회에도 넣지 않는다
USER_COLUMNS = """u.id, u.login_id, u.user_name, u.role_id, r.role_code, r.role_name, u.worker_id, w.worker_code, w.worker_name,
                  u.status, u.fail_count, u.last_login_at, u.password_changed_at, u.attrs, u.created_at, u.created_by, u.updated_at, u.updated_by"""
USER_FROM = "from sys_user u join sys_role r on r.id = u.role_id left join bas_worker w on w.id = u.worker_id"


# ── SYS-01 사용자 ───────────────────────────────────────────────────────
def user_of_path(raw_id: str) -> dict:
    row = conn.q1(f"select {USER_COLUMNS} {USER_FROM} where u.id = %s", (id_of_path(raw_id),))
    if row is None:
        raise http.not_found()
    return row


def role_options() -> list[tuple[str, str]]:
    return [(str(r["id"]), f"{r['role_code']} {r['role_name']}") for r in conn.q("select id, role_code, role_name from sys_role where use_yn = 'Y' order by id")]


def password_of(form: FormData, label: str, *, required: bool) -> str | None:
    """비밀번호는 앞뒤 공백도 값이다 — 다듬지 않는다. 복잡도 규칙은 정본에 없다(지어내지 않는다). 값은 어디에도 남기지 않는다."""
    raw = form.get("password")
    value = raw if isinstance(raw, str) else ""
    if "\x00" in value or len(value) > 200:
        raise bad("입력값을 확인해 주세요", "password", "쓸 수 없는 값입니다", label)
    if not value:
        if required:
            raise bad("필수값이 빠졌습니다", "password", "필수값입니다", label)
        return None
    return value


@router.get(USERS, response_class=HTMLResponse)                                                 # F-SYS-04 사용자 조회 = 화면 GET
def users(request: Request, q: str = "", role_id: str = "", status: str = "", edit: str = "", user: rbac.User = rbac.require_fn("F-SYS-04")) -> HTMLResponse:
    where, params = ["true"], []
    if q.strip():
        where.append(f"({contains('u.login_id')} or {contains('u.user_name')})")
        params += [q.strip(), q.strip()]
    if role_id.strip():
        if not role_id.strip().isdigit():
            raise bad("입력값을 확인해 주세요", "role_id", f"없는 값입니다: {role_id}", "역할")
        where.append("u.role_id = %s")
        params.append(int(role_id))
    if status.strip():
        if status not in USER_STATUSES:
            raise bad("입력값을 확인해 주세요", "status", f"{' · '.join(USER_STATUSES)} 중 하나: {status}", "상태")
        where.append("u.status = %s")
        params.append(status)
    rows = conn.q(f"select {USER_COLUMNS} {USER_FROM} where {' and '.join(where)} order by u.login_id limit {USER_LIMIT}", params)
    return templating.render(request, "sys/users.html", {
        "rows": rows, "f": {"q": q, "role_id": role_id, "status": status, "edit": edit}, "editing": user_of_path(edit) if edit else None,
        "options": {"role_id": role_options(), "status": [(s, s) for s in USER_STATUSES],
                    "worker_id": [(str(r["id"]), f"{r['worker_code']} {r['worker_name']}") for r in conn.q(
                        "select id, worker_code, worker_name from bas_worker where use_yn = 'Y' order by worker_code")]},
        "path": USERS, "me": user.id,
        "can": {"create": user.can("F-SYS-01"), "update": user.can("F-SYS-02"), "toggle": user.can("F-SYS-03")},
    }, screen_id="SYS-01")


@router.post(USERS)                                                                              # F-SYS-01 사용자 등록
def create_user(request: Request, user: rbac.User = rbac.require_fn("F-SYS-01"), form: FormData = Depends(form_data)):
    login_id = text_of(form, "login_id", "로그인 ID", required=True, max_len=50)
    if not LOGIN_ID_RE.match(login_id):
        raise bad("입력값을 확인해 주세요", "login_id", "영문 · 숫자 · `_` `.` `-` 로 2~50자 (첫 글자는 영문 · 숫자)", "로그인 ID")
    user_name = text_of(form, "user_name", "이름", required=True, max_len=100)
    role_id = ref_of(form, "role_id", "역할", "sys_role", required=True)
    worker_id = ref_of(form, "worker_id", "작업자", "bas_worker")
    password = password_of(form, "초기 비밀번호", required=True)
    if conn.q1("select 1 as hit from sys_user where login_id = %s", (login_id,)):
        raise bad("이미 있는 로그인 ID 입니다", "login_id", login_id, "로그인 ID")
    row: dict[str, Any] = {"login_id": login_id, "user_name": user_name, "role_id": role_id, "worker_id": worker_id, "status": ST_ACTIVE}
    with conn.tx() as cur:
        packs.hook("validate_sys_user")(cur, row, user)
        cur.execute("""insert into sys_user (login_id, user_name, password_hash, role_id, worker_id, status, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s) returning id""",
                    (login_id, user_name, auth.hash_password(password), role_id, worker_id, ST_ACTIVE, user.login_id))   # 해시만 저장한다
        row["id"] = cur.fetchone()["id"]
        packs.hook("after_save_sys_user")(cur, row, user)
    audit.log_change(request, user, "F-SYS-01", f"sys_user:{login_id}", {"id": row["id"], "role_id": role_id})
    return http.saved(request, t("사용자를 등록했습니다") + f" — {login_id}", back=USERS, data={"id": row["id"], "login_id": login_id, "status": ST_ACTIVE})


@router.post(USERS + "/{id}")                                                                    # F-SYS-02 사용자 수정
def update_user(request: Request, id: str, user: rbac.User = rbac.require_fn("F-SYS-02"), form: FormData = Depends(form_data)):
    target = user_of_path(id)
    sets: dict[str, Any] = {}
    changed: list[str] = []
    if "login_id" in form and (text_of(form, "login_id", "로그인 ID", max_len=50) or target["login_id"]) != target["login_id"]:
        raise bad("로그인 ID 는 바꿀 수 없습니다", "login_id", target["login_id"], "로그인 ID")
    if "user_name" in form:
        sets["user_name"] = text_of(form, "user_name", "이름", required=True, max_len=100)
    if "role_id" in form:
        sets["role_id"] = ref_of(form, "role_id", "역할", "sys_role", required=True)      # 다음 요청부터 반영 (요청마다 DB)
    if "worker_id" in form:
        sets["worker_id"] = ref_of(form, "worker_id", "작업자", "bas_worker")
    if "status" in form:
        raise bad("상태는 중지 · 해제 버튼으로만 바꾼다", "status", str(form.get("status")), "상태")
    sets = {k: v for k, v in sets.items() if v != target[k]}
    changed = list(sets)
    password = password_of(form, "새 비밀번호", required=False)                               # 비밀번호 재설정 — 비워 두면 그대로
    if password is not None:
        sets["password_hash"] = auth.hash_password(password)
        sets["fail_count"] = 0
        changed.append("password_reset")
    if not sets:
        raise http.validation_error(t("바꿀 값이 없습니다"))
    merged = {**target, **{k: v for k, v in sets.items() if k != "password_hash"}}
    with conn.tx() as cur:
        packs.hook("validate_sys_user")(cur, merged, user)
        cur.execute(f"update sys_user set {', '.join(f'{c} = %s' for c in sets)}, updated_at = now(), updated_by = %s where id = %s",
                    [*sets.values(), user.login_id, target["id"]])
        if password is not None:
            auth.revoke_user_sessions(cur, target["id"])                                          # 그 사용자의 세션 전부 — 다음 요청부터 401
        packs.hook("after_save_sys_user")(cur, merged, user)
    audit.log_change(request, user, "F-SYS-02", f"sys_user:{target['login_id']}", {"id": target["id"], "changed": changed})
    return http.saved(request, t("사용자를 수정했습니다") + f" — {target['login_id']}", back=USERS,
                      data={"id": target["id"], "login_id": target["login_id"], "changed": changed, "role_id": sets.get("role_id", target["role_id"])})


@router.post(USERS + "/{id}/toggle")                                                             # F-SYS-03 사용자 중지 · 해제
def toggle_user(request: Request, id: str, user: rbac.User = rbac.require_fn("F-SYS-03")):
    target = user_of_path(id)
    if target["id"] == user.id:
        raise bad("자기 자신의 계정은 중지할 수 없습니다", "id", target["login_id"], "로그인 ID")
    new_status = ST_STOPPED if target["status"] == ST_ACTIVE else ST_ACTIVE                     # 중지 · 잠금 → 사용 (해제)
    with conn.tx() as cur:
        cur.execute("update sys_user set status = %s, fail_count = case when %s = %s then 0 else fail_count end, updated_at = now(), updated_by = %s where id = %s",
                    (new_status, new_status, ST_ACTIVE, user.login_id, target["id"]))
        revoked = auth.revoke_user_sessions(cur, target["id"]) if new_status != ST_ACTIVE else 0   # 세션 전부 무효 → 다음 요청 401
    audit.log_change(request, user, "F-SYS-03", f"sys_user:{target['login_id']}", {"id": target["id"], "from": target["status"], "to": new_status, "sessions_revoked": revoked})
    return http.saved(request, t("사용자 상태를 바꿨습니다") + f" — {target['login_id']}: {target['status']} → {new_status}", back=USERS,
                      data={"id": target["id"], "login_id": target["login_id"], "status": new_status, "sessions_revoked": revoked})


# ── SYS-02 역할 ─────────────────────────────────────────────────────────
def role_of_path(raw_id: str) -> dict:
    row = conn.q1("select id, role_code, role_name, use_yn, created_at, created_by, updated_at, updated_by from sys_role where id = %s", (id_of_path(raw_id),))
    if row is None:
        raise http.not_found()
    return row


@router.get(ROLES, response_class=HTMLResponse)                                                 # F-SYS-07 역할 조회 = 화면 GET
def roles(request: Request, edit: str = "", user: rbac.User = rbac.require_fn("F-SYS-07")) -> HTMLResponse:
    rows = conn.q("""select r.id, r.role_code, r.role_name, r.use_yn, r.created_at, r.updated_at,
                            (select count(*) from sys_user u where u.role_id = r.id) as user_count,
                            (select count(*) from sys_user u where u.role_id = r.id and u.status = '사용') as active_user_count,
                            (select count(*) from sys_permission p where p.role_id = r.id) as cell_count
                       from sys_role r order by r.id""")
    return templating.render(request, "sys/roles.html", {
        "rows": rows, "f": {"edit": edit}, "editing": role_of_path(edit) if edit else None, "path": ROLES, "n_menus": len(nav.ALL_MENUS), "guarded": GUARDED_ROLE,
        "can": {"create": user.can("F-SYS-05"), "update": user.can("F-SYS-06")},
    }, screen_id="SYS-02")


@router.post(ROLES)                                                                              # F-SYS-05 역할 등록
def create_role(request: Request, user: rbac.User = rbac.require_fn("F-SYS-05"), form: FormData = Depends(form_data)):
    role_code = text_of(form, "role_code", "역할 코드", required=True, max_len=20)
    if not ROLE_CODE_RE.match(role_code):
        raise bad("입력값을 확인해 주세요", "role_code", "영문 대문자 · 숫자 · `_` 로 2~20자 (첫 글자는 영문 대문자)", "역할 코드")
    role_name = text_of(form, "role_name", "역할 이름", required=True, max_len=100)
    if conn.q1("select 1 as hit from sys_role where role_code = %s", (role_code,)):
        raise bad("이미 있는 역할 코드입니다", "role_code", role_code, "역할 코드")
    row: dict[str, Any] = {"role_code": role_code, "role_name": role_name, "use_yn": "Y"}
    with conn.tx() as cur:
        packs.hook("validate_sys_role")(cur, row, user)
        cur.execute("insert into sys_role (role_code, role_name, use_yn, created_by) values (%s, %s, 'Y', %s) returning id", (role_code, role_name, user.login_id))
        row["id"] = cur.fetchone()["id"]
        for m in nav.ALL_MENUS:                                                                 # 모든 메뉴 칸을 `없음` 으로 (칸 수 = 메뉴 수)
            cur.execute("insert into sys_permission (role_id, menu_code, level, scopes, created_by) values (%s, %s, %s, '{}', %s)",
                        (row["id"], m.code, rbac.LEVEL_NONE, user.login_id))
        packs.hook("after_save_sys_role")(cur, row, user)
    rbac.invalidate()
    audit.log_change(request, user, "F-SYS-05", f"sys_role:{role_code}", {"id": row["id"], "cells": len(nav.ALL_MENUS)})
    return http.saved(request, t("역할을 등록했습니다") + f" — {role_code} ({t('메뉴')} {len(nav.ALL_MENUS)}칸 {rbac.LEVEL_NONE})", back=ROLES,
                      data={"id": row["id"], "role_code": role_code, "cells": len(nav.ALL_MENUS)})


@router.post(ROLES + "/{id}")                                                                    # F-SYS-06 역할 수정
def update_role(request: Request, id: str, user: rbac.User = rbac.require_fn("F-SYS-06"), form: FormData = Depends(form_data)):
    target = role_of_path(id)
    sets: dict[str, Any] = {}
    if "role_code" in form and (text_of(form, "role_code", "역할 코드", max_len=20) or target["role_code"]) != target["role_code"]:
        raise bad("역할 코드는 바꿀 수 없습니다", "role_code", target["role_code"], "역할 코드")
    if "role_name" in form:
        sets["role_name"] = text_of(form, "role_name", "역할 이름", required=True, max_len=100)
    if "use_yn" in form:
        sets["use_yn"] = yn_of(form, "use_yn", "사용 여부")
        if sets["use_yn"] == "N" and target["role_code"] == GUARDED_ROLE:
            raise bad("ADMIN 역할은 중지할 수 없습니다", "use_yn", "N", "사용 여부")
        if sets["use_yn"] == "N" and target["role_code"] == user.role_code:
            raise bad("자기 자신의 역할은 중지할 수 없습니다", "use_yn", target["role_code"], "사용 여부")
    sets = {k: v for k, v in sets.items() if v != target[k]}
    if not sets:
        raise http.validation_error(t("바꿀 값이 없습니다"))
    merged = {**target, **sets}
    with conn.tx() as cur:
        packs.hook("validate_sys_role")(cur, merged, user)
        cur.execute(f"update sys_role set {', '.join(f'{c} = %s' for c in sets)}, updated_at = now(), updated_by = %s where id = %s",
                    [*sets.values(), user.login_id, target["id"]])
        packs.hook("after_save_sys_role")(cur, merged, user)
    rbac.invalidate()
    audit.log_change(request, user, "F-SYS-06", f"sys_role:{target['role_code']}", {"id": target["id"], "changed": list(sets)})
    return http.saved(request, t("역할을 수정했습니다") + f" — {target['role_code']}", back=ROLES, data={"id": target["id"], "role_code": target["role_code"], "changed": list(sets)})


# ── SYS-03 권한 표 ──────────────────────────────────────────────────────
def known_scopes() -> list[str]:
    """쓰기 기능이 갖는 범위 이름 — 병합본 `scopes`(core.yaml + 팩) 와 계약 표의 합. `일반` 이 먼저."""
    p = packs.current()
    scopes = set(p.scopes) | {f.scope for f in contracts.all_functions() if f.is_write and f.scope}
    return sorted(scopes, key=lambda s: (s != p.scope_general, s))


def menu_scopes() -> dict[str, list[str]]:
    """메뉴 코드 → 그 메뉴의 쓰기 범위들 (권한 표 편집 화면의 선택지)."""
    out: dict[str, list[str]] = {m.code: [] for m in nav.ALL_MENUS}
    for f in contracts.all_functions():
        if f.is_write and f.menu_code in out and f.scope not in out[f.menu_code]:
            out[f.menu_code].append(f.scope)
    return out


def matrix_rows() -> tuple[list[dict], list[dict], int]:
    """역할 × 메뉴 전 칸 — DB 에 행이 없는 칸은 `미확정`(시드 누락 · check_security FAIL). 캐시가 아니라 DB 의 지금 값."""
    rbac.invalidate()
    role_rows = conn.q("select id, role_code, role_name, use_yn from sys_role order by id")
    cells = {(r["role_id"], r["menu_code"]): r for r in conn.q("select role_id, menu_code, level, scopes, updated_at, updated_by from sys_permission")}
    missing = 0
    rows = []
    for m in nav.ALL_MENUS:
        row = {"menu_code": m.code, "menu_name": m.name, "hidden": m.hidden, "is_pack": m.is_pack, "cells": []}
        for r in role_rows:
            c = cells.get((r["id"], m.code))
            if c is None:
                missing += 1
                row["cells"].append({"role_code": r["role_code"], "level": None, "label": screen.undecided("시드 누락"), "scopes": [], "updated_at": None, "updated_by": None})
            else:
                row["cells"].append({"role_code": r["role_code"], "level": c["level"], "label": rbac.Cell(c["level"], frozenset(c["scopes"] or ())).label,
                                     "scopes": list(c["scopes"] or []), "updated_at": c["updated_at"], "updated_by": c["updated_by"]})
        rows.append(row)
    return rows, role_rows, missing


@router.get(PERMISSIONS, response_class=HTMLResponse)                                           # F-SYS-09 권한 표 조회 = 화면 GET
def permissions(request: Request, user: rbac.User = rbac.require_fn("F-SYS-09")) -> HTMLResponse:
    rows, role_rows, missing = matrix_rows()
    return templating.render(request, "sys/permissions.html", {
        "rows": rows, "roles": role_rows, "missing": missing, "counts": rbac.counts(), "levels": list(rbac.LEVELS), "scopes": known_scopes(),
        "menu_scopes": menu_scopes(), "guarded": {"role": GUARDED_ROLE, "menu": GUARDED_MENU}, "path": PERMISSIONS,
        "scope_general": packs.current().scope_general, "can_write": user.can("F-SYS-08"),
    }, screen_id="SYS-03")


def _parse_cells(form: FormData) -> list[dict]:
    """두 모양을 받는다 — 한 칸(`role_code` · `menu_code` · `level` · `scopes`) 또는 표 전체(`level__<ROLE>__<menu>` · `scopes__<ROLE>__<menu>`)."""
    out: list[dict] = []
    if "role_code" in form or "menu_code" in form:
        role_code = text_of(form, "role_code", "역할", required=True, max_len=20)
        menu_code = text_of(form, "menu_code", "메뉴", required=True, max_len=20)
        level = text_of(form, "level", "권한", required=True, max_len=10)
        scopes = [s.strip() for v in form.getlist("scopes") if isinstance(v, str) for s in v.replace("·", ",").split(",") if s.strip()]
        out.append({"role_code": role_code, "menu_code": menu_code, "level": level, "scopes": scopes})
        return out
    for key in form.keys():
        if not key.startswith("level__"):
            continue
        _, role_code, menu_code = key.split("__", 2)
        scopes = [s.strip() for v in form.getlist(f"scopes__{role_code}__{menu_code}") if isinstance(v, str) for s in v.replace("·", ",").split(",") if s.strip()]
        out.append({"role_code": role_code, "menu_code": menu_code, "level": str(form.get(key) or "").strip(), "scopes": scopes})
    if not out:
        raise bad("바꿀 칸이 없습니다", "level", "role_code · menu_code · level 또는 level__<역할>__<메뉴>", "권한")
    return out


@router.post(PERMISSIONS)                                                                        # F-SYS-08 권한 표 수정
def update_permissions(request: Request, user: rbac.User = rbac.require_fn("F-SYS-08"), form: FormData = Depends(form_data)):
    cells = _parse_cells(form)
    roles_by_code = {r["role_code"]: r["id"] for r in conn.q("select id, role_code from sys_role")}
    menus = {m.code for m in nav.ALL_MENUS}
    general = packs.current().scope_general
    valid_scopes = set(known_scopes())
    changes: list[dict] = []
    with conn.tx() as cur:
        for c in cells:
            if c["role_code"] not in roles_by_code:
                raise bad("입력값을 확인해 주세요", "role_code", f"없는 역할입니다: {c['role_code']}", "역할")
            if c["menu_code"] not in menus:
                raise bad("입력값을 확인해 주세요", "menu_code", f"없는 메뉴입니다: {c['menu_code']}", "메뉴")
            if c["level"] not in rbac.LEVELS:
                raise bad("입력값을 확인해 주세요", "level", f"{' · '.join(rbac.LEVELS)} 중 하나여야 합니다: {c['level']!r}", "권한")
            scopes = list(dict.fromkeys(c["scopes"])) if c["level"] == rbac.LEVEL_WRITE else []
            if c["level"] == rbac.LEVEL_WRITE and not scopes:
                scopes = [general]                                                               # 괄호 없는 `입력` = 일반
            unknown = [s for s in scopes if s not in valid_scopes]
            if unknown:
                raise bad("입력값을 확인해 주세요", "scopes", f"없는 범위입니다: {', '.join(unknown)} ({' · '.join(sorted(valid_scopes))})", "범위")
            if c["role_code"] == GUARDED_ROLE and c["menu_code"] == GUARDED_MENU and not (c["level"] == rbac.LEVEL_WRITE and general in scopes):
                raise bad("ADMIN 의 시스템 칸은 `입력` 으로 고정되어 있습니다 (잠그지 못한다)", "level", f"{c['role_code']} × {c['menu_code']} → {c['level']}", "권한")
            cur.execute("select level, scopes from sys_permission where role_id = %s and menu_code = %s", (roles_by_code[c["role_code"]], c["menu_code"]))
            before = cur.fetchone()
            if before and before["level"] == c["level"] and list(before["scopes"] or []) == scopes:
                continue
            cur.execute("""insert into sys_permission (role_id, menu_code, level, scopes, created_by) values (%s, %s, %s, %s, %s)
                           on conflict (role_id, menu_code) do update set level = excluded.level, scopes = excluded.scopes, updated_at = now(), updated_by = excluded.created_by""",
                        (roles_by_code[c["role_code"]], c["menu_code"], c["level"], scopes, user.login_id))
            changes.append({"role_code": c["role_code"], "menu_code": c["menu_code"], "from": (f"{before['level']}{list(before['scopes'] or [])}" if before else None),
                            "to": f"{c['level']}{scopes}"})
    rbac.invalidate()                                                                            # 저장 즉시 — 다음 요청부터 DB 를 다시 읽는다 (G-C17)
    audit.log_change(request, user, "F-SYS-08", f"sys_permission:{len(changes)}", {"changes": changes[:48]})
    return http.saved(request, t("권한 표를 저장했습니다") + f" — {len(changes)}칸", back=PERMISSIONS, data={"changed": len(changes), "changes": changes})


# ── SYS-04 접근 로그 ─────────────────────────────────────────────────────
def _date(value: str, key: str, label: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise bad("입력값을 확인해 주세요", key, f"날짜(YYYY-MM-DD)가 아닙니다: {value}", label) from None


@router.get(LOGS, response_class=HTMLResponse)                                                  # F-SYS-10 접근 로그 조회
def logs(request: Request, date_from: str = "", date_to: str = "", login_id: str = "", kind: str = "", screen_id: str = "", fn_id: str = "",
         target: str = "", user: rbac.User = rbac.require_fn("F-SYS-10")) -> HTMLResponse:
    where, params = ["true"], []
    d_from, d_to = _date(date_from, "date_from", "시작일"), _date(date_to, "date_to", "종료일")
    if d_from:
        where.append("l.logged_at >= %s::date")
        params.append(d_from)
    if d_to:
        where.append("l.logged_at < %s::date + 1")                                               # 종료일을 포함한다
        params.append(d_to)
    if login_id.strip():
        where.append(contains("coalesce(l.login_id, '')"))
        params.append(login_id.strip())
    if kind.strip():
        if kind not in LOG_KINDS:
            raise bad("입력값을 확인해 주세요", "kind", f"{' · '.join(LOG_KINDS)} 중 하나: {kind}", "종류")
        where.append("l.kind = %s")
        params.append(kind)
    for key, val in (("screen_id", screen_id), ("fn_id", fn_id)):
        if val.strip():
            where.append(f"l.{key} = %s")
            params.append(val.strip())
    if target.strip():
        where.append(contains("coalesce(l.target, '')"))
        params.append(target.strip())
    cond = " and ".join(where)
    rows = conn.q(f"""select l.id, l.logged_at, l.kind, l.login_id, l.user_id, l.screen_id, l.fn_id, l.target, l.detail, l.ip, l.device
                        from sys_access_log l where {cond} order by l.logged_at desc, l.id desc limit {LOG_LIMIT}""", params)
    by_kind = {r["kind"]: r["n"] for r in conn.q(f"select l.kind, count(*) as n from sys_access_log l where {cond} group by l.kind", params)}
    return templating.render(request, "sys/logs.html", {
        "rows": rows, "by_kind": by_kind, "total": sum(by_kind.values()), "limit": LOG_LIMIT, "kinds": list(LOG_KINDS), "kind_options": [(k, k) for k in LOG_KINDS], "path": LOGS,
        "f": {"date_from": date_from, "date_to": date_to, "login_id": login_id, "kind": kind, "screen_id": screen_id, "fn_id": fn_id, "target": target},
    }, screen_id="SYS-04")


# ── SYS-05 채번 규칙 ─────────────────────────────────────────────────────
def numbering_rows() -> list[dict]:
    """종류별 규칙 · 오늘 카운터 · 다음 번호(peek). 규칙 행이 없으면 `미확정 (D-10)`."""
    out = []
    declared = packs.current().numbering
    kinds = list(declared) + [r["kind"] for r in conn.q("select kind from sys_number_rule order by kind") if r["kind"] not in declared]
    for kind in kinds:
        r = numbering.rule(kind)
        row = {"kind": kind, "label": declared.get(kind, {}).get("label", kind), "declared": kind in declared, "rule": r, "counter": None, "next_no": None, "error": None}
        if r is not None and r["use_yn"] == "Y":
            row["counter"] = numbering.counter(kind)
            try:
                row["next_no"] = numbering.peek(kind)
            except RuntimeError as exc:                                                          # 규칙이 바코드 글자를 어긴다 — 화면에 사유를 보인다
                row["error"] = str(exc)
        out.append(row)
    return out


@router.get(NUMBERING, response_class=HTMLResponse)                                             # F-SYS-12 채번 규칙 조회
def numbering_rules(request: Request, edit: str = "", user: rbac.User = rbac.require_fn("F-SYS-12")) -> HTMLResponse:
    rows = numbering_rows()
    return templating.render(request, "sys/numbering.html", {
        "rows": rows, "f": {"edit": edit}, "editing": next((r for r in rows if r["kind"] == edit), None), "path": NUMBERING,
        "undecided": screen.undecided("D-10"), "can_write": user.can("F-SYS-11"),
    }, screen_id="SYS-05")


@router.post(NUMBERING)                                                                          # F-SYS-11 채번 규칙 수정
def update_numbering(request: Request, user: rbac.User = rbac.require_fn("F-SYS-11"), form: FormData = Depends(form_data)):
    kind = text_of(form, "kind", "종류", required=True, max_len=30)
    if not re.match(r"^[A-Z][A-Z0-9_]{0,29}$", kind):
        raise bad("입력값을 확인해 주세요", "kind", "영문 대문자 · 숫자 · `_` 로 30자까지", "종류")
    prefix = text_of(form, "prefix", "접두어", max_len=10) or ""
    if not PREFIX_RE.match(prefix):
        raise bad("입력값을 확인해 주세요", "prefix", "영문 대문자 · 숫자 · `-` 만 (바코드)", "접두어")
    date_format = text_of(form, "date_format", "날짜 형식", max_len=20) or ""
    seq_digits = int_of(form, "seq_digits", "자릿수", required=True, positive=True)
    if seq_digits > 10:
        raise bad("입력값을 확인해 주세요", "seq_digits", "자릿수는 10 이하", "자릿수")
    use_yn = yn_of(form, "use_yn", "사용 여부")
    if date_format:
        try:
            sample = conn.q1("select to_char(now(), %s) as v", (date_format,))["v"]
        except Exception as exc:  # noqa: BLE001 — to_char 형식 오류는 사용자 입력 오류다
            raise bad("입력값을 확인해 주세요", "date_format", f"to_char 형식이 아닙니다: {type(exc).__name__}", "날짜 형식") from None
        if not PREFIX_RE.match(sample or ""):
            raise bad("입력값을 확인해 주세요", "date_format", f"날짜 부분이 바코드에 쓸 수 없는 글자를 만듭니다: {sample!r}", "날짜 형식")
    before = numbering.rule(kind)
    row = {"kind": kind, "prefix": prefix, "date_format": date_format, "seq_digits": seq_digits, "use_yn": use_yn}
    with conn.tx() as cur:
        packs.hook("validate_sys_number_rule")(cur, row, user)
        cur.execute("""insert into sys_number_rule (kind, prefix, date_format, seq_digits, use_yn, created_by) values (%s, %s, %s, %s, %s, %s)
                       on conflict (kind) do update set prefix = excluded.prefix, date_format = excluded.date_format, seq_digits = excluded.seq_digits,
                           use_yn = excluded.use_yn, updated_at = now(), updated_by = excluded.created_by returning id""",
                    (kind, prefix, date_format, seq_digits, use_yn, user.login_id))
        row["id"] = cur.fetchone()["id"]
        packs.hook("after_save_sys_number_rule")(cur, row, user)
    preview = numbering.peek(kind) if use_yn == "Y" else None                                    # 바꾼 뒤 미리보기 — 이미 발번된 번호는 바뀌지 않는다
    audit.log_change(request, user, "F-SYS-11", f"sys_number_rule:{kind}",
                     {"from": {k: before[k] for k in ("prefix", "date_format", "seq_digits", "use_yn")} if before else None, "to": {k: row[k] for k in ("prefix", "date_format", "seq_digits", "use_yn")}})
    return http.saved(request, t("채번 규칙을 저장했습니다") + f" — {kind}: {t('다음 번호')} {preview or '-'}", back=NUMBERING,
                      data={"kind": kind, "prefix": prefix, "date_format": date_format, "seq_digits": seq_digits, "use_yn": use_yn, "next_no": preview})


# ── SYS-06 백업 · 이관 ───────────────────────────────────────────────────
def migrate_available() -> bool:
    return importlib.util.find_spec(MIGRATE_MODULE) is not None


def _backup_tool():
    return importlib.import_module("mescore.tools.backup")


def backup_of_path(raw_id: str) -> dict:
    row = conn.q1("select * from sys_backup_hist where id = %s", (id_of_path(raw_id),))
    if row is None:
        raise http.not_found()
    return row


MIGRATE_DIR_UNDECIDED = "미확정 (D-109)"                                                      # 이관 실행 폴더 — 현장 반입 경로 미정 (G-C11 형식)


def migrate_dir_label(migrate_dir: str | None) -> str:
    """SYS-06 이관 폴더 표시 — 값이 있으면 그 경로, 없으면 `미확정 (D-109)` (DEF-QA2-003)."""
    return migrate_dir or MIGRATE_DIR_UNDECIDED


@router.get(BACKUP, response_class=HTMLResponse)                                                # F-SYS-16 백업 · 이관 이력 조회
def backup_history(request: Request, user: rbac.User = rbac.require_fn("F-SYS-16")) -> HTMLResponse:
    s = get_settings()
    backups = conn.q("select * from sys_backup_hist order by started_at desc, id desc limit 200")
    migrations = conn.q("select * from sys_migration_log order by started_at desc, id desc limit 200")
    return templating.render(request, "sys/backup.html", {
        "backups": backups, "migrations": migrations, "path": BACKUP, "migrate_path": MIGRATE, "commands": list(MIGRATE_COMMANDS),
        "migrate_dir": s.migrate_dir, "migrate_dir_label": migrate_dir_label(s.migrate_dir),
        "migrate_available": migrate_available(), "migrate_note": None if migrate_available() else "개발3 모듈 대기 — mescore.migrate 가 아직 없다 (F-SYS-15)",
        "can": {"backup": user.can("F-SYS-13"), "verify": user.can("F-SYS-14"), "migrate": user.can("F-SYS-15")},
    }, screen_id="SYS-06")


@router.post(BACKUP)                                                                             # F-SYS-13 백업 실행
def run_backup(request: Request, user: rbac.User = rbac.require_fn("F-SYS-13")):
    tool = _backup_tool()
    hist_id = conn.q1("insert into sys_backup_hist (started_at, created_by) values (now(), %s) returning id", (user.login_id,))["id"]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = tool.backup()
        dump = tool.latest_dump(tool.conn_params()["dbname"])                                    # 그 DB 의 덤프만 (아키텍트 DEF-QA1-008)
        manifest = json.loads(dump.with_suffix(".json").read_text(encoding="utf-8"))
        counts = manifest.get("tables", {})
        conn.x("update sys_backup_hist set dump_path = %s, row_counts = %s::jsonb, ended_at = now(), ok = %s, message = %s where id = %s",
               (str(dump.relative_to(tool.ROOT)), json.dumps(counts), rc == 0, out.getvalue()[-1000:], hist_id))
    except tool.BackupError as exc:                                                              # 실패는 이력에 남고 500 이 아니라 422 사유
        conn.x("update sys_backup_hist set ended_at = now(), ok = false, message = %s where id = %s", (str(exc)[:1000], hist_id))
        audit.log_change(request, user, "F-SYS-13", f"sys_backup_hist:{hist_id}", {"ok": False, "error": str(exc)[:300]})
        raise http.validation_error(t("백업이 실패했습니다") + f" — {exc}", fields=[{"name": "backup", "label": t("백업"), "reason": str(exc)[:300]}]) from None
    except Exception as exc:                                                                     # 예상 밖 오류도 이력은 끝맺는다(ok NULL 로 남기지 않는다) — 500 은 그대로
        conn.x("update sys_backup_hist set ended_at = now(), ok = false, message = %s where id = %s", (f"{type(exc).__name__}: {exc}"[:1000], hist_id))
        raise
    audit.log_change(request, user, "F-SYS-13", f"sys_backup_hist:{hist_id}", {"ok": True, "dump": dump.name, "tables": len(counts), "rows": sum(counts.values())})
    return http.saved(request, t("백업을 만들었습니다") + f" — {dump.name} ({t('테이블')} {len(counts)} · {t('행')} {sum(counts.values()):,})", back=BACKUP,
                      data={"id": hist_id, "dump": dump.name, "tables": len(counts), "rows": sum(counts.values()), "ok": True})


@router.post(BACKUP + "/{id}/verify")                                                            # F-SYS-14 복구 확인 (임시 DB — 운영 DB 는 건드리지 않는다)
def verify_backup(request: Request, id: str, user: rbac.User = rbac.require_fn("F-SYS-14")):
    hist = backup_of_path(id)
    tool = _backup_tool()
    if not hist.get("dump_path"):
        raise bad("덤프가 없는 이력입니다 — 백업이 실패했거나 아직 끝나지 않았다", "dump_path", str(hist.get("message") or "-"), "덤프")
    dump = tool.ROOT / hist["dump_path"]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = tool.restore_check(str(dump))
    except tool.BackupError as exc:
        conn.x("update sys_backup_hist set verified_at = now(), verify_ok = false, message = %s where id = %s", (str(exc)[:1000], hist["id"]))
        audit.log_change(request, user, "F-SYS-14", f"sys_backup_hist:{hist['id']}", {"verify_ok": False, "error": str(exc)[:300]})
        raise http.validation_error(t("복구 확인이 실패했습니다") + f" — {exc}", fields=[{"name": "verify", "label": t("복구 확인"), "reason": str(exc)[:300]}]) from None
    text = out.getvalue()
    verdict = next((ln for ln in text.splitlines() if ln.startswith("판정:")), "")
    conn.x("update sys_backup_hist set verified_at = now(), verify_ok = %s, message = %s where id = %s", (rc == 0, (verdict or text)[-1000:], hist["id"]))
    audit.log_change(request, user, "F-SYS-14", f"sys_backup_hist:{hist['id']}", {"verify_ok": rc == 0, "verdict": verdict[:300]})
    if rc != 0:
        raise http.validation_error(t("복구 확인 결과가 기준과 다릅니다") + f" — {verdict}", fields=[{"name": "verify", "label": t("복구 확인"), "reason": verdict[:300]}])
    return http.saved(request, t("복구 확인을 마쳤습니다") + f" — {verdict}", back=BACKUP, data={"id": hist["id"], "verify_ok": True, "verdict": verdict})


@router.post(MIGRATE)                                              # F-SYS-15 이관 실행 — POST /sys/migrate
def run_migrate(request: Request, user: rbac.User = rbac.require_fn("F-SYS-15"), form: FormData = Depends(form_data)):
    command = text_of(form, "command", "명령", required=True, max_len=20)
    if command not in MIGRATE_COMMANDS:
        raise bad("입력값을 확인해 주세요", "command", f"{' · '.join(MIGRATE_COMMANDS)} 중 하나: {command}", "명령")
    dry_run = yn_of(form, "dry_run", "시험 실행", default="N") == "Y"
    s = get_settings()
    if not s.migrate_dir:
        raise bad("이관 폴더(MES_MIGRATE_DIR)가 정해지지 않았다", "dir", migrate_dir_label(s.migrate_dir), "폴더")
    migrate = importlib.import_module(MIGRATE_MODULE)                                            # 개발3 모듈 — 없으면 ImportError 를 잡지 않는다 (500 · 화면은 "개발3 모듈 대기")
    report = migrate.run(command, s.migrate_dir, dry_run=dry_run)
    body = templating.jsonable(report)
    audit.log_change(request, user, "F-SYS-15", f"sys_migration_log:{command}", {"dir": s.migrate_dir, "dry_run": dry_run, "report": body if isinstance(body, dict) else str(body)[:500]})
    return http.saved(request, t("이관을 실행했습니다") + f" — {command}" + (f" ({t('시험 실행')})" if dry_run else ""), back=BACKUP,
                      data={"command": command, "dry_run": dry_run, "report": body})
