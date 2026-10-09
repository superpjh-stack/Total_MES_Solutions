"""dashboard 라우터 — CMN-04 `/dashboard` 역할별 요약 (공통 화면 · 담당 개발3). **읽기만** — 쓰기 0, 집계는 `stats.dashboard()` 만 부른다.

`core.yaml: common` 의 CMN-04. `packs.CORE_ROUTER_MODULES`(15) 에 들어 `main.py` 가 include 한다(D-29). 디자이너3 `docs/design/home/dashboard.html`: 공통 숫자 4(`today.work_orders results inspections_pending
shipments_pending`) + 역할별 강조 1 + 바로가기(권한 칸 조회 이상만) + 최근 변경 5건 `recent[{at kind text href}]`(접근 로그 change). 역할이 팩에 늘어나면 기본 판 = 생산 판.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from .. import nav, rbac, stats, templating
from ..packs import t

router = APIRouter()

#: 역할 코드 → (판 이름, 강조 지표 키, 강조 라벨, 바로가기 화면 ID)
BOARDS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "ADMIN": ("관리자", "approvals_pending", "승인 대기 출하", ("SHP-02", "ORD-01", "KPI-01", "SYS-03", "IFC-02")),
    "PROD": ("생산", "late_orders", "지연 수주", ("ORD-04", "JOB-01", "POP-01", "SHP-01", "KPI-02")),
    "QA": ("품질", "issues_open", "미종결 이상", ("QUA-02", "MAT-02", "QUA-04", "TRC-02", "KPI-02")),
    "FIELD": ("현장", "labels_today", "오늘 생산 LOT", ("POP-01", "POP-02", "MAT-01", "SHP-02", "EQP-01")),
}
DEFAULT_BOARD = "PROD"


@router.get(nav.path_of("CMN-04"), include_in_schema=False)
def dashboard(request: Request, user: rbac.User = Depends(rbac.require_login)):
    name, extra_key, extra_label, shortcuts = BOARDS.get(user.role_code, BOARDS[DEFAULT_BOARD])
    data = stats.dashboard()
    links = []
    for sid in shortcuts:
        sc = nav.by_id(sid)
        if user.can_open(sid) and nav.channel_allowed(sid, user.device):
            links.append({"screen_id": sid, "name": sc.name, "path": sc.path})
    return templating.render(request, "dashboard/index.html", {
        "board": name, "today": data["today"], "extra": {"key": extra_key, "label": extra_label, "value": data["extra"].get(extra_key)},
        "extra_all": data["extra"], "shortcuts": links, "recent": [_recent_row(r, user) for r in data["recent"]],
    }, screen_id="CMN-04")


def _recent_row(r: dict, user: rbac.User) -> dict:
    """`stats.recent_activity` 한 줄 → 원형 키 {at kind text href}. 링크는 그 화면을 열 수 있을 때만(권한 없으면 글자만)."""
    sid = r.get("screen_id") or ""
    try:
        sc = nav.by_id(sid)
    except KeyError:
        sc = None
    menu = nav.menu_of_screen(sid) if sc else None
    href = sc.path if sc and user.can_open(sid) and nav.channel_allowed(sid, user.device) and "{" not in sc.path else None
    text = " · ".join(x for x in (t(r["name"]) if r.get("name") else r.get("fn_id"), r.get("target")) if x)
    return {"at": r["logged_at"].strftime("%H:%M") if r.get("logged_at") else None, "kind": menu.name if menu else (sc.name if sc else sid),
            "text": text, "href": href, "login_id": r.get("login_id"), "fn_id": r.get("fn_id")}
