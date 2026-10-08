"""메뉴 · 경로의 원본 — `core.yaml` + 팩 `menus` / `screens` 병합본 (`contracts/interfaces.md` §2).

    nav.MENUS        -> list[Menu]     팩 hide 제외 · order 적용 (코어 12 + 팩 add)
    nav.ALL_MENUS    -> list[Menu]     숨긴 것 포함
    nav.SCREENS      -> list[Screen]   코어 51 + 팩 X- 화면
    nav.CORE_SCREENS -> list[Screen]   51
    nav.COMMON       -> list[Screen]   5
    nav.path_of("BAS-01") -> "/bas/items"     경로를 문자열로 다시 적지 않는다
    nav.by_id · by_path · menu(code) · menu_of_screen · channel_allowed(screen_id, device)

**경로는 이 모듈이 유일한 출처다.** `contracts/screen-map.md` §1 · §4 는 렌더본(`make contracts`).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import packs

WEB, POP, MOBILE, BOARD = "관리자 Web", "현장 POP", "모바일", "현황판"
CHANNELS: tuple[str, ...] = (WEB, POP, MOBILE, BOARD)
DEVICE_CHANNEL: dict[str, str] = {"web": WEB, "pop": POP, "mobile": MOBILE, "board": BOARD}
CHANNEL_DEVICE: dict[str, str] = {v: k for k, v in DEVICE_CHANNEL.items()}


@dataclass(frozen=True)
class Screen:
    screen_id: str
    name: str
    menu_code: str            # 모듈 코드 = 권한 표의 menu_code ('' = 공통)
    module: str
    path: str
    owner: str
    channels: tuple[str, ...]
    is_pack: bool = False
    common: bool = False
    auth: bool = True         # 공통 화면 중 로그인 없이 열리는 것(로그인 · 오류)은 False
    probe: str = ""           # 경로에 변수가 있을 때 검사 도구가 여는 구체 경로

    @property
    def device_codes(self) -> tuple[str, ...]:
        return tuple(CHANNEL_DEVICE[c] for c in self.channels if c in CHANNEL_DEVICE)


@dataclass(frozen=True)
class Menu:
    code: str
    name: str
    module: str
    owner: str
    channels: tuple[str, ...]
    screens: tuple[Screen, ...]
    hidden: bool = False
    is_pack: bool = False
    seq: int = 0


SYSTEM_NAME = "MES 표준플랫폼"
MENUS: list[Menu] = []
ALL_MENUS: list[Menu] = []
SCREENS: list[Screen] = []
CORE_SCREENS: list[Screen] = []
PACK_SCREENS: list[Screen] = []
COMMON: list[Screen] = []
ALL: list[Screen] = []
MODULE_OWNER: dict[str, str] = {}
_BY_ID: dict[str, Screen] = {}
_BY_PATH: dict[str, Screen] = {}
_MENU: dict[str, Menu] = {}


def rebuild() -> None:
    """병합본(`packs.current()`)에서 다시 만든다 — 기동 때 한 번, 테스트가 팩을 바꾸면 다시."""
    global SYSTEM_NAME, MENUS, ALL_MENUS, SCREENS, CORE_SCREENS, PACK_SCREENS, COMMON, ALL, MODULE_OWNER
    p = packs.current()
    SYSTEM_NAME = p.display_name if not p.is_core_only else p.system_name
    screens_by_mod: dict[str, list[Screen]] = {}
    for s in p.screens:
        sc = Screen(screen_id=s["id"], name=s["name"], menu_code=s["module"], module=s["module"], path=s["path"],
                    owner=s["owner"], channels=tuple(s["channels"]), is_pack=bool(s.get("is_pack")))
        screens_by_mod.setdefault(s["module"], []).append(sc)
    order = {code: i for i, code in enumerate(p.order)}
    menus: list[Menu] = []
    for m in sorted(p.modules, key=lambda m: order.get(m["code"], len(order))):
        menus.append(Menu(code=m["code"], name=m["name"], module=m["code"], owner=m["owner"], channels=tuple(m["channels"]),
                          screens=tuple(screens_by_mod.get(m["code"], [])), hidden=m["code"] in p.hidden,
                          is_pack=bool(m.get("is_pack")), seq=order.get(m["code"], len(order))))
    ALL_MENUS = menus
    MENUS = [m for m in menus if not m.hidden]
    SCREENS = [s for m in menus for s in m.screens]
    CORE_SCREENS = [s for s in SCREENS if not s.is_pack]
    PACK_SCREENS = [s for s in SCREENS if s.is_pack]
    COMMON = [Screen(screen_id=c["id"], name=c["name"], menu_code="", module="home", path=c["path"], owner=c["owner"],
                     channels=tuple(c["channels"]), common=True, auth=bool(c.get("auth", True)), probe=str(c.get("probe") or c["path"]))
              for c in p.common]
    ALL = COMMON + SCREENS
    MODULE_OWNER = {"home": "개발1", **{m.module: m.owner for m in menus}}
    _BY_ID.clear(); _BY_ID.update({s.screen_id: s for s in ALL})
    _BY_PATH.clear(); _BY_PATH.update({s.path: s for s in ALL})
    _MENU.clear(); _MENU.update({m.code: m for m in menus})
    _selfcheck(p)


def _selfcheck(p) -> None:
    core_menus = [m for m in ALL_MENUS if not m.is_pack]
    if len(core_menus) != 12 or len(CORE_SCREENS) != 51 or len(COMMON) != 5:
        raise AssertionError(f"코어 모듈 12 · 화면 51 · 공통 5 이어야 한다 — 실제 {len(core_menus)} · {len(CORE_SCREENS)} · {len(COMMON)}")
    paths = [s.path for s in ALL]
    dup = sorted({x for x in paths if paths.count(x) > 1})
    if dup:
        raise AssertionError(f"경로 중복: {dup}")
    for s in SCREENS:
        if not set(s.channels) <= set(CHANNELS):
            raise AssertionError(f"{s.screen_id} 의 채널이 4채널 밖이다: {s.channels}")
    if sorted(m.code for m in ALL_MENUS) != sorted({m["code"] for m in p.modules}):
        raise AssertionError("order 가 모듈 전부를 담지 못했다")


def by_id(screen_id: str) -> Screen:
    if screen_id not in _BY_ID:
        raise KeyError(f"nav 에 없는 화면 ID: {screen_id}")
    return _BY_ID[screen_id]


def by_path(path: str) -> Screen | None:
    return _BY_PATH.get(path)


def path_of(screen_id: str) -> str:
    return by_id(screen_id).path


def menu(code: str) -> Menu:
    if code not in _MENU:
        raise KeyError(f"nav 에 없는 메뉴 코드: {code}")
    return _MENU[code]


def menu_of_screen(screen_id: str) -> Menu | None:
    sc = by_id(screen_id)
    return _MENU.get(sc.menu_code) if sc.menu_code else None


def screens_of(module: str) -> list[Screen]:
    return [s for s in SCREENS if s.module == module]


def channel_allowed(screen_id: str, device: str) -> bool:
    """`core.yaml`/`pack.yaml: channels` — web 은 전 화면, 공통 화면은 전 채널. 선언에 없는 화면을 그 채널로 열면 403."""
    if device in ("web", "", None):
        return True
    sc = by_id(screen_id)
    if sc.common:
        return True
    return screen_id in packs.current().channels.get(device, [])


def sidebar_items() -> list[dict]:
    """좌측 메뉴 · 메인 카드 — 일하는 순서(`order`). 권한에 따른 숨김은 `rbac.visible_sidebar` 가 한다."""
    return [{"kind": "menu", "menu": m} for m in MENUS]


rebuild()
