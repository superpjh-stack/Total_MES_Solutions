"""역할별 데이터 접근 — 허브가 보여 주고 내보내는 테이블은 지금 역할이 그 모듈 메뉴를 읽을 수 있는 것뿐이다.

규칙은 AI Agent(D-47 · D-49)와 같다. 모듈은 테이블 접두로 정하고, LOT · 계보 · LOT 뷰 · 품목은 그것을 화면에 보여 주는 업무 모듈과 공유한다.
비밀번호 해시 · 세션 · 내부 카운터는 어느 역할에도 주지 않는다. 팩 테이블(`x_…`)은 관리자만 본다.
"""

from __future__ import annotations

from mescore.app import nav, rbac

NEVER = {"sys_session", "sys_user", "sys_number_seq"}
SHARED = {"lot": ("trc", "mat", "pop", "shp"), "lot_genealogy": ("trc", "mat", "pop", "shp"),
          "v_lot_state": ("trc", "mat", "pop", "shp"), "v_lot_stock": ("trc", "mat", "pop", "shp"),
          "v_work_order_progress": ("job", "pop"),
          "bas_item": ("bas", "job", "pop", "mat", "qua", "shp", "trc", "ord")}
MODULES = ("bas", "ord", "job", "mat", "pop", "qua", "eqp", "shp", "trc", "kpi", "sys", "ifc")


def module_of(rel: str) -> str:
    """대표 모듈 코드 (화면 묶음용). 팩 테이블은 'pack'."""
    if rel.startswith("x_"):
        return "pack"
    if rel.startswith(("lot", "v_lot")):
        return "trc"
    if rel == "v_work_order_progress":
        return "job"
    p = rel.split("_", 1)[0]
    return p if p in MODULES else "etc"


def module_name(code: str) -> str:
    if code == "pack":
        return "업종 팩"
    m = nav._MENU.get(code)
    return m.name if m is not None else code


def can_read(user: rbac.User, rel: str) -> bool:
    if rel in NEVER:
        return False
    if rel.startswith("x_"):
        return user.role_code == "ADMIN"
    mods = SHARED.get(rel) or ((module_of(rel),) if module_of(rel) in MODULES else ())
    return any(rbac.can_read_menu(user.role_code, m) for m in mods)


def is_admin(user: rbac.User) -> bool:
    return user.role_code == "ADMIN"
