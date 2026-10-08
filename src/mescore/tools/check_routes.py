#!/usr/bin/env python
"""G-C03 화면 라우트 검사 (G-C21 · G-C17 의 일부) — `make check-routes`.

  1. 코어 화면 51 + 공통 5(로그인 · 메인 · 오류 · 대시보드 · 팝업)가 전부 HTTP 200 인가 (관리자로 로그인 · JSON 응답으로 판정 — D-18)
  2. `_placeholder` 가 몇 건 남았는가 (0 이어야 G-C03 PASS). 담당별로 센다
  3. 권한 표에서 `없음` 인 칸의 화면은 403 이고 메인에서 숨겨지는가 (기대값은 core.yaml/pack.yaml 병합본 — 역할마다 시드 계정으로)
  4. 미로그인 — 브라우저 GET 은 /login 303, 그 밖은 401
  5. (MES_PACK) 팩 화면 X- 도 200

출력 행: `G-C03  화면  PASS|FAIL  실측` (+ 사람용 요약). 종료코드: 0 = 전부 200 · placeholder 0 · 권한 위반 0, 그 밖은 1.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from mescore.app.settings import get_settings  # noqa: E402

if not get_settings().seed_password:
    sys.exit("MES_SEED_PASSWORD 미설정 — 시드 계정으로 로그인할 수 없어 화면 검사를 할 수 없다 (`make setup` 으로 .env 를 만든다)")

from fastapi.testclient import TestClient  # noqa: E402

from mescore.app import nav, packs  # noqa: E402
from mescore.app.main import app  # noqa: E402
from mescore.db.seed_core import USERS as SEED_USERS  # noqa: E402

HTML = {"accept": "text/html"}


def is_placeholder(resp) -> bool:
    if resp.headers.get("content-type", "").startswith("application/json"):
        return bool(resp.json().get("placeholder"))
    return 'class="tag"' in resp.text and "미구현" in resp.text


def login(client: TestClient, login_id: str) -> bool:
    r = client.post("/login", data={"login_id": login_id, "password": get_settings().seed_password}, follow_redirects=False)
    return r.status_code in (200, 303)


def main() -> int:
    fails: list[str] = []
    if app.state.include_errors:
        fails.extend(f"라우터 임포트 실패 — {e}" for e in app.state.include_errors)

    anon = TestClient(app, raise_server_exceptions=False)
    first = nav.CORE_SCREENS[0]
    r_html = anon.get(first.path, headers=HTML, follow_redirects=False)
    r_api = anon.get(first.path)
    print(f"[미로그인] 브라우저 GET {r_html.status_code} → {r_html.headers.get('location', '-')} · 그 밖 {r_api.status_code}")
    if r_html.status_code != 303 or r_api.status_code != 401:
        fails.append(f"미로그인 기대 303/401, 실제 {r_html.status_code}/{r_api.status_code}")

    client = TestClient(app, raise_server_exceptions=False)
    if not login(client, "admin"):
        print("G-C03  화면  FAIL  관리자(admin) 로그인 실패 — 공통 시드를 먼저 돌린다 (`make db-seed`)")
        return 1
    ok = 0
    placeholders: list[tuple[str, str]] = []
    targets = [s for s in nav.COMMON if s.auth] + nav.SCREENS
    for s in targets:
        resp = client.get(s.probe or s.path)
        if resp.status_code != 200:
            fails.append(f"{s.screen_id} {s.path} → HTTP {resp.status_code}")
            continue
        ok += 1
        if is_placeholder(resp):
            placeholders.append((s.screen_id, s.owner))
    for s in nav.COMMON:
        if not s.auth:
            resp = anon.get(s.path, headers=HTML)
            if resp.status_code == 200:
                ok += 1
            else:
                fails.append(f"{s.screen_id} {s.path} (인증 없이) → HTTP {resp.status_code}")
    total = len(nav.COMMON) + len(nav.SCREENS)
    print(f"[HTTP 200] {ok} / {total}  (코어 {len(nav.CORE_SCREENS)} + 공통 {len(nav.COMMON)} + 팩 {len(nav.PACK_SCREENS)})")
    by_owner: dict[str, int] = {}
    for _sid, owner in placeholders:
        by_owner[owner] = by_owner.get(owner, 0) + 1
    print(f"[placeholder] 잔여 {len(placeholders)} 건" + (" — " + " · ".join(f"{k} {v}" for k, v in sorted(by_owner.items())) if by_owner else ""))

    # 3. 권한 없음 = 403 + 메뉴 숨김 (기대값 = 병합본 permissions)
    p = packs.current()
    login_of = {code: login_id for login_id, _name, code in SEED_USERS}
    checked, bad = 0, []
    clients: dict[str, TestClient] = {}
    n_none = 0
    for m in nav.ALL_MENUS:
        for role in p.roles:
            code = role["code"]
            if code not in login_of:
                continue
            c = clients.get(code)
            if c is None:
                c = TestClient(app, raise_server_exceptions=False)
                if not login(c, login_of[code]):
                    bad.append(f"{role['name']}({login_of[code]}) 로그인 실패")
                clients[code] = c
            level = p.permission(m.code, code)["level"]
            none = level == "없음" or m.hidden
            n_none += none
            want = 403 if none else 200
            for s in m.screens:
                got = c.get(s.path).status_code
                checked += 1
                if got != want:
                    bad.append(f"{role['name']} → {s.screen_id} {s.path} 기대 {want}, 실제 {got}")
            if none:
                home = c.get("/", headers=HTML).text
                shown = [s.path for s in m.screens if f'href="{s.path}"' in home]
                if shown:
                    bad.append(f"{role['name']}: `없음` 인 {m.name} 이 메인에 보인다 {shown[:2]}")
    print(f"[RBAC] 역할 {len(clients)} × 화면 {len(nav.SCREENS)} = {checked} 건 조회 검사 (없음 {n_none}칸 → 403 + 메뉴 숨김) · 위반 {len(bad)}")
    for b in bad:
        print(f"    {b}")
    fails.extend(bad)

    print()
    all200 = ok == total
    status = "PASS" if (all200 and not placeholders and not fails) else "FAIL"
    print(f"G-C03  화면  {status}  200: {ok}/{total} · placeholder {len(placeholders)} (기대 0)"
          + (" — " + " · ".join(f"{k} {v}" for k, v in sorted(by_owner.items())) if by_owner else "")
          + (f" · 위반 {len(fails)}" if fails else ""))
    for f in fails:
        print(f"  - {f}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
