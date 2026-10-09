"""도메인별 MES 프로세스 카탈로그 로더 — 저장소 루트 `domains/*.yaml` 을 읽는다 (D-46).

업종 문장은 코어 코드에 두지 않는다(G-C23). 이 모듈은 파일을 읽어 구조만 맞추고, 단계의 화면 ID 를 코어 화면 · 팩 화면 · 제안 화면으로 가른다.
- 코어 화면 ID → nav 경로 · 지금 역할의 열람 가능 여부
- 팩 화면 ID(`X-…`) → 그 도메인 팩의 pack.yaml `screens` 에서 이름 · 경로. 지금 올라간 팩이 그 도메인이면 링크
- 어디에도 없는 `X-…` → 제안 화면(아직 없음)
파일을 하나 더 두면 도메인이 하나 늘어난다. 어떤 테이블에도 쓰지 않는다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from . import nav, packs, rbac
from .settings import ROOT

DOMAINS_DIR = ROOT / "domains"
ROLE_CODES = ("ADMIN", "PROD", "QA", "FIELD")


@lru_cache(maxsize=1)
def _load_all() -> tuple[dict, ...]:
    out = []
    for p in sorted(DOMAINS_DIR.glob("*.yaml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        d.setdefault("code", p.stem)
        d["_file"] = str(p.relative_to(ROOT))
        out.append(d)
    return tuple(sorted(out, key=lambda d: (d.get("seq", 99), d["code"])))


def reload() -> None:
    _load_all.cache_clear()
    _pack_screens.cache_clear()


def all_domains() -> tuple[dict, ...]:
    return _load_all()


def by_code(code: str) -> dict | None:
    return next((d for d in _load_all() if d["code"] == code), None)


@lru_cache(maxsize=16)
def _pack_screens(pack_name: str) -> dict[str, dict]:
    f = packs.PACKS_DIR / pack_name / "pack.yaml"
    if not f.exists():
        return {}
    d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {s["id"]: {"name": s.get("name", s["id"]), "path": s.get("path")} for s in d.get("screens") or [] if s.get("id")}


def pack_terms(pack_name: str | None) -> dict[str, str]:
    if not pack_name:
        return {}
    f = packs.PACKS_DIR / pack_name / "pack.yaml"
    if not f.exists():
        return {}
    return dict((yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("terms") or {})


def resolve_screen(screen_id: str, domain: dict, user: rbac.User) -> dict:
    """단계의 화면 → {screen_id name path open kind(core|pack|proposed) menu}."""
    pack_name = domain.get("pack")
    current_pack = packs.current().name
    try:
        s = nav.by_id(screen_id)
        m = nav.menu_of_screen(screen_id)
        visible = m is not None and any(x.code == m.code for x in nav.MENUS)
        return {"screen_id": screen_id, "name": s.name, "path": s.path, "menu": m.name if m else None,
                "kind": "pack" if screen_id.startswith("X-") else "core",
                "open": bool(visible and rbac.can_read_menu(user.role_code, m.code))}
    except KeyError:
        pass
    ps = _pack_screens(pack_name) if pack_name else {}
    if screen_id in ps:
        return {"screen_id": screen_id, "name": ps[screen_id]["name"], "path": None, "menu": None, "kind": "pack",
                "open": False, "other_pack": pack_name != current_pack}
    return {"screen_id": screen_id, "name": screen_id, "path": None, "menu": None, "kind": "proposed", "open": False}


def view(domain: dict, user: rbac.User, process_code: str = "") -> dict:
    """화면용 — 단계마다 화면을 풀고, 프로세스별 화면 종류 수를 센다."""
    roles = {r.code: r.name for r in rbac.roles()}
    procs = []
    for p in domain.get("processes") or []:
        steps = []
        for i, st in enumerate(p.get("steps") or [], 1):
            scr = resolve_screen(str(st.get("screen", "")), domain, user)
            role = str(st.get("role", ""))
            steps.append({"no": i, **scr, "role": role, "role_name": roles.get(role, role), "mine": role == user.role_code,
                          "action": st.get("action", ""), "output": st.get("output", "")})
        procs.append({"code": p.get("code"), "name": p.get("name"), "when": p.get("when", ""), "goal": p.get("goal", ""),
                      "checks": list(p.get("checks") or []), "steps": steps,
                      "n_core": sum(1 for s in steps if s["kind"] == "core"), "n_pack": sum(1 for s in steps if s["kind"] == "pack"),
                      "n_proposed": sum(1 for s in steps if s["kind"] == "proposed")})
    current = next((p for p in procs if p["code"] == process_code), procs[0] if procs else None)
    return {**{k: v for k, v in domain.items() if not k.startswith("_") and k != "processes"},
            "file": domain.get("_file"), "processes": procs, "current": current,
            "terms": pack_terms(domain.get("pack")), "active": bool(domain.get("pack")) and domain.get("pack") == packs.current().name}


def problems() -> list[str]:
    """데이터 점검 — 역할 코드 · 화면 ID 형식 · 팩 화면 존재. 테스트가 부른다."""
    bad = []
    core_ids = {s.screen_id for s in nav.CORE_SCREENS}
    for d in _load_all():
        ps = _pack_screens(d["pack"]) if d.get("pack") else {}
        for p in d.get("processes") or []:
            for st in p.get("steps") or []:
                sid, role = str(st.get("screen", "")), str(st.get("role", ""))
                if role not in ROLE_CODES:
                    bad.append(f"{d['code']}/{p.get('code')}: 역할 {role}")
                if sid.startswith("X-"):
                    if d.get("pack") and sid not in ps:
                        bad.append(f"{d['code']}/{p.get('code')}: 팩에 없는 화면 {sid}")
                elif sid not in core_ids:
                    bad.append(f"{d['code']}/{p.get('code')}: 코어에 없는 화면 {sid}")
    return bad
