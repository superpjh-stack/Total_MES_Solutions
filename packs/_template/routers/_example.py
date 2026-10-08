"""E4 팩 라우터의 최소 예 — 화면 1 · 기능 2 (contracts/pack-contract.md §6).

`_` 로 시작하는 파일은 로더가 include 하지 않는다. 쓰려면 `example.py` 처럼 이름을 바꾸고 pack.yaml 에 다음을 선언한다:

    menus:
      add: [{ code: exm, name: 예시 모듈, after: pop, owner: 개발N, channels: [관리자 Web] }]
    screens:
      - { id: X-EXM-01, name: 예시 화면, module: exm, path: /exm/example, channels: [관리자 Web], owner: 개발N }
    write_scope: { exm: [] }      # x_<팩>_* 만 쓴다

그리고 packs/<팩>/function-list.md 에 F-X-EXM-01(조회) · F-X-EXM-02(등록) 두 줄, seed/permissions.csv 에 exm 행(역할마다), schema_ext.sql 에 x_<팩>_example.
모양은 코어 라우터와 같다 — 화면 GET = nav.path_of + rbac.require_fn(읽기 기능), 쓰기 POST = 검증 → conn.tx → audit.log_change → http.saved.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request

from mescore.app import audit, nav, packs, rbac, templating
from mescore.app.packs import t
from mescore.app.util import http
from mescore.db import conn

router = APIRouter()
PACK = "_template"      # pack-new 가 바꾸지 않는다 — 직접 고친다
TABLE = f"x_{PACK}_example"


@router.get(nav.path_of("X-EXM-01"))                                                   # F-X-EXM-01 예시 조회 = 화면 GET
def example_list(request: Request, user: rbac.User = rbac.require_fn("F-X-EXM-01")):
    rows = conn.q(f"select id, code, name, attrs, created_at from {TABLE} order by code")
    return templating.render(request, "exm/example.html", {"rows": rows}, screen_id="X-EXM-01")


@router.post(nav.path_of("X-EXM-01"))                                                  # F-X-EXM-02 예시 등록
def example_create(request: Request, code: str = Form(...), name: str = Form(...),
                   user: rbac.User = rbac.require_fn("F-X-EXM-02")):
    if conn.q1(f"select 1 from {TABLE} where code = %s", (code,)):
        raise http.validation_error(t("이미 있는 코드입니다"), fields=[{"name": "code", "label": t("코드"), "reason": code}])
    with conn.tx() as cur:
        row = {"code": code, "name": name, "attrs": {}}
        packs.hook(f"validate_{TABLE}")(cur, row, user)
        cur.execute(f"insert into {TABLE} (code, name, created_by) values (%s, %s, %s)", (code, name, user.login_id))
    audit.log_change(request, user, "F-X-EXM-02", f"{TABLE}:{code}")
    return http.saved(request, t("등록했습니다"))
