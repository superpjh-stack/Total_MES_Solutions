#!/usr/bin/env python
"""QA1 — 기능 · 계약 · 용어 검사기 (`goal.md` §3.3 · §2.5 · `contracts/api-contract.md`). `make gate` 가 부른다(G-C02 · G-C03 · G-C17).

기대값은 **계약에서만** 끌어온다 — `contracts/function-list.md`(136줄) · `contracts/api-contract.md` · `src/mescore/core.yaml`(권한 48칸 · 채널 ·
금지어 · terms_keys) · 팩 `pack.yaml` / `gates.yaml`. 개발 코드가 스스로 적은 숫자는 믿지 않는다.

  ① 기능 136 — 각 기능을 계약 그대로 TestClient(JSON) 로 부른다: 정상 코드 + 오류 계약(필수 누락 422 · 중복 422 · 경로 키 404(숫자 아님 포함)
     · 스캔 번호 422 · 미로그인 401 · 권한 403 · ERP 501) + 계약 문장의 422 조건. 이관 배치 4 는 CLI(dry-run · 실적재 2회 멱등).
  ② G-C17 — 역할 4 × 기능 전부: 권한 없음/조회 칸의 쓰기 403 · 입력 칸은 통과(401 · 403 아님) · 범위(scopes) 4종 · DB 48칸 = core.yaml.
  ③ G-C23 — 화면 HTML 전부(시드 · DB 값 포함)에 금지어 0 · 용어 표지 치환으로 찾은 날것 중립어(t() 누락).
  ④ 응답 모양 — 브라우저 303 / 422 재렌더 · JSON 오류 모양 · `/health` 키 · 인증 없이 열리는 경로 · 503.
  ⑤ 채널 — `core.yaml: channels` 밖 화면을 그 채널로 열면 403.

DB — **쓰기 검사는 QA 전용 DB 에서만 한다.** 코어 단독(MES_PACK 비움)은 `MES_QA_DSN`(없으면 `postgresql:///mes_qa_db`)에 붙는다 —
`mes_core_db` 는 다른 사람이 쓴다. 팩(MES_PACK=<팩>)은 `mes_<팩>_db` 에 **읽기 · 호출만**(정상 쓰기 호출은 하지 않는다 · 401/403/404/422 만).

    uv run python src/mescore/tools/check_screens.py                     # 코어 단독 (mes_qa_db)
    uv run python src/mescore/tools/check_screens.py --reset-db          # mes_qa_db 스키마 · 시드를 다시 만든 뒤 (qa 이름 DB 만)
    MES_PACK=kimchi uv run python src/mescore/tools/check_screens.py      # 팩 — 읽기 · 호출만
    … --json <파일>                                                       # 기능별 판정을 JSON 으로 (리포트용)

출력: `G-nn  항목  PASS|FAIL|WARN|미검증  실측` (interfaces.md §10). 종료코드 0 = FAIL 없음.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")
warnings.filterwarnings("ignore", category=DeprecationWarning)

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "mescore"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── DB 고르기 (앱 import 전에) ─────────────────────────────────────────────
PACK = (os.environ.get("MES_PACK") or "").strip()
ARGS = sys.argv[1:]


def _arg(name: str) -> str | None:
    if name in ARGS:
        i = ARGS.index(name)
        return ARGS[i + 1] if i + 1 < len(ARGS) else None
    return None


if PACK and not PACK.startswith("_"):
    WRITE_MODE = False
    DSN = os.environ.get("MES_PG_DSN") or f"postgresql:///mes_{PACK}_db"
else:
    WRITE_MODE = True
    DSN = _arg("--dsn") or os.environ.get("MES_QA_DSN") or "postgresql:///mes_qa_db"
os.environ["MES_PG_DSN"] = DSN
EXAMPLES = SRC / "migrate" / "examples"
if WRITE_MODE and not (os.environ.get("MES_MIGRATE_DIR") or "").strip():
    os.environ["MES_MIGRATE_DIR"] = str(EXAMPLES)          # F-SYS-15 정상 호출용 (examples · dry-run 으로만 부른다)
DB_NAME = DSN.rsplit("/", 1)[-1].split("?")[0]

import yaml  # noqa: E402

CORE_YAML = yaml.safe_load((SRC / "core.yaml").read_text(encoding="utf-8"))
HTML = {"accept": "text/html"}
NOPE_ID = "999999999"
U = datetime.now().strftime("%m%d%H%M%S") + uuid.uuid4().hex[:3].upper()
TODAY = date.today()


def reset_db() -> str:
    if "qa" not in DB_NAME:
        return f"--reset-db 는 qa 이름 DB 만 — {DB_NAME} 거부"
    env = {**os.environ, "MES_PACK": "", "MES_PG_DSN": DSN}
    psql = ["psql", "-q", "-h", "/tmp", "-d", DB_NAME, "-v", "ON_ERROR_STOP=1"]
    for cmd in (psql + ["-c", "set client_min_messages = warning; drop schema public cascade; create schema public;"],
                psql + ["-f", str(SRC / "db" / "schema.sql")], psql + ["-f", str(SRC / "db" / "views.sql")],
                ["uv", "run", "python", "-m", "mescore.db.seed_core"]):
        p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
        if p.returncode != 0:
            return f"실패 {' '.join(cmd[:4])} — {(p.stderr or p.stdout)[-300:]}"
    return "OK"


if "--reset-db" in ARGS and WRITE_MODE:
    print(f"[reset] {DB_NAME}: {reset_db()}")

from mescore.app.settings import get_settings, reset_cache  # noqa: E402

reset_cache()


def _db_exists() -> bool:
    import psycopg
    try:
        with psycopg.connect(DSN, autocommit=True) as c:
            return c.execute("select count(*) from information_schema.tables where table_schema='public' and table_name='sys_user'").fetchone()[0] == 1
    except psycopg.Error:
        return False


if not get_settings().seed_password or not _db_exists():
    why = "MES_SEED_PASSWORD 미설정" if not get_settings().seed_password else f"DB {DB_NAME} 없음 또는 스키마 없음 (`--reset-db`)"
    for g, item in (("G-C02", "기능 136 계약 호출"), ("G-C03", "응답 모양 · 인증 경로"), ("G-C17", "역할 × 기능 RBAC")):
        print(f"{g}  {item}  미검증  {why}")
    raise SystemExit(0)

from fastapi.testclient import TestClient  # noqa: E402

from mescore.app import contracts, nav, packs, rbac  # noqa: E402
from mescore.app.main import app  # noqa: E402
from mescore.db import conn  # noqa: E402
from mescore.db.seed_core import USERS as SEED_USERS  # noqa: E402

PW = get_settings().seed_password or ""
P = packs.current()


# ── 기록 ───────────────────────────────────────────────────────────────
class Rec:
    def __init__(self) -> None:
        self.fn: dict[str, list[tuple[str, bool, str]]] = {}
        self.rows: list[tuple[str, str, str, str]] = []
        self.notes: list[str] = []

    def chk(self, fid: str, name: str, ok: bool, measured: str = "") -> bool:
        self.fn.setdefault(fid, []).append((name, bool(ok), measured))
        return bool(ok)

    def verdict(self, fid: str) -> str:
        items = self.fn.get(fid) or []
        if not items:
            return "미검증"
        return "PASS" if all(ok for _, ok, _ in items) else "FAIL"

    def row(self, gid: str, item: str, status: str, measured: str) -> None:
        self.rows.append((gid, item, status, measured))


R = Rec()


def code_of(r) -> int:
    return r.status_code


def js(r) -> dict:
    try:
        v = r.json()
        return v if isinstance(v, dict) else {"_": v}
    except Exception:  # noqa: BLE001
        return {}


def short(r) -> str:
    b = js(r)
    msg = b.get("message") or b.get("code") or ""
    f = b.get("fields") or []
    fx = f"[{f[0].get('name')}]" if f and isinstance(f[0], dict) else ""
    return f"{r.status_code}{(' ' + str(msg)[:40]) if msg else ''}{fx}"


_CLIENTS: dict[str, TestClient] = {}


def login(login_id: str, password: str | None = None, device: str | None = None, fresh: bool = False) -> TestClient:
    key = f"{login_id}|{device}"
    if not fresh and key in _CLIENTS:
        return _CLIENTS[key]
    c = TestClient(app, raise_server_exceptions=False)
    data = {"login_id": login_id, "password": PW if password is None else password}
    if device:
        data["device"] = device
    r = c.post("/login", data=data)
    if r.status_code != 200:
        raise RuntimeError(f"{login_id} 로그인 실패 {r.status_code}")
    if not fresh:
        _CLIENTS[key] = c
    return c


ANON = TestClient(app, raise_server_exceptions=False)
LOGIN_OF: dict[str, str] = {}
NO_LOGIN: list[str] = []


def _resolve_logins() -> None:
    """역할 → 로그인할 계정. 코어는 시드 계정 4(seed_core.USERS). 팩은 그 팩 역할마다 DB 의 사용 중 계정 중 시드 비밀번호로 열리는 것."""
    if WRITE_MODE:
        LOGIN_OF.update({code: lid for lid, _n, code in SEED_USERS})
        return
    for role in P.roles:
        code = role["code"]
        cands = conn.q("""select u.login_id from sys_user u join sys_role r on r.id = u.role_id where r.role_code = %s and u.status = '사용'
                          order by (u.created_by like 'seed%%') desc, u.id limit 3""", (code,))
        for c in cands:
            t = TestClient(app, raise_server_exceptions=False)
            if t.post("/login", data={"login_id": c["login_id"], "password": PW}).status_code == 200:
                LOGIN_OF[code] = c["login_id"]
                _CLIENTS[f"{c['login_id']}|None"] = t
                break
        else:
            NO_LOGIN.append(code)


_resolve_logins()


def q1(sql: str, params=None) -> dict | None:
    return conn.q1(sql, params)


def expect(fid: str, name: str, r, want, extra_ok: bool = True) -> bool:
    """want: int | tuple[int,...]."""
    ws = want if isinstance(want, tuple) else (want,)
    return R.chk(fid, name, r.status_code in ws and extra_ok, f"{short(r)} (기대 {'/'.join(map(str, ws))})")


def ok200(fid: str, name: str, r, *keys: str) -> dict:
    b = js(r)
    good = r.status_code == 200 and (b.get("ok") is True or not keys or all(k in b for k in keys))
    if keys:
        good = good and all(k in b for k in keys)
    R.chk(fid, name, good, f"{short(r)}" + (f" · 키 {[k for k in keys if k not in b]} 없음" if keys and not all(k in b for k in keys) else ""))
    return b


def read_ok(fid: str, c: TestClient, url: str, name: str = "조회 200 JSON") -> dict:
    r = c.get(url)
    b = js(r)
    good = r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json") and not b.get("placeholder")
    R.chk(fid, name, good, f"{r.status_code}{' placeholder' if b.get('placeholder') else ''} {url}")
    return b


def path_404(fid: str, c: TestClient, method: str, tpl: str, data: dict | None = None) -> None:
    """경로 키가 없음(큰 숫자) · 숫자 아님 → 404 (api-contract.md §1)."""
    for raw, label in ((NOPE_ID, "없는 경로 키 404"), ("abc", "숫자 아닌 경로 키 404")):
        url = re.sub(r"\{[^}]+\}", raw, tpl, count=1)
        r = c.request(method, url, data=data or {})
        R.chk(fid, label, r.status_code == 404, f"{short(r)} {method} {url}")


def unauth(fid: str, method: str, url: str) -> None:
    r = ANON.request(method, url, data={})
    R.chk(fid, "미로그인 401", r.status_code == 401 and js(r).get("code") == "unauthorized", short(r))


def forbid(fid: str, role: str, method: str, url: str, data: dict | None = None) -> None:
    r = login(LOGIN_OF[role]).request(method, url, data=data or {})
    R.chk(fid, f"권한 없는 {role} 403", r.status_code == 403 and js(r).get("code") == "forbidden", short(r))


def scan422(fid: str, c: TestClient, url: str) -> None:
    r = c.get(url)
    R.chk(fid, "없는 스캔 번호 422 (JSON)", r.status_code == 422 and js(r).get("code") == "validation_error", f"{short(r)} {url}")
    h = c.get(url, headers=HTML)
    rerender = h.status_code == 422 and "data-scan" in h.text
    R.chk(fid, "없는 스캔 번호 422 재렌더 (HTML · data-scan 유지)", rerender, f"HTML {h.status_code} data-scan {'있음' if 'data-scan' in h.text else '없음'}")


FN = {f.id: f for f in contracts.functions()}


def api(fid: str) -> tuple[str, str]:
    f = FN[fid]
    return f.method, f.path_base


# ════════════════════════════════════════════════════════════════════════
# ① 기능 136 — 코어 단독 · 쓰기 모드
# ════════════════════════════════════════════════════════════════════════
def master(fid_c: str, fid_u: str, fid_d: str, fid_l: str, path: str, code_key: str, payload: dict, upd: dict, *,
           ref_delete: tuple[str, dict] | None = None) -> int | None:
    a = login("admin")
    # 등록
    r = a.post(path, data=payload)
    b = ok200(fid_c, "등록 200", r, "id")
    rid = b.get("id")
    expect(fid_c, "같은 코드 다시 등록 → 중복 422", a.post(path, data=payload), 422)
    expect(fid_c, "빈 폼 → 필수 누락 422", a.post(path, data={}), 422)
    unauth(fid_c, "POST", path)
    forbid(fid_c, "PROD", "POST", path, payload)
    # 수정
    if rid:
        ok200(fid_u, "수정 200", a.post(f"{path}/{rid}", data=upd))
        changed = {code_key: str(payload[code_key]) + "X"}
        expect(fid_u, "코드 변경 → 422", a.post(f"{path}/{rid}", data=changed), 422)
    path_404(fid_u, a, "POST", path + "/{id}", upd)
    unauth(fid_u, "POST", f"{path}/1")
    forbid(fid_u, "QA", "POST", f"{path}/{rid or 1}", upd)
    # 삭제 — 새 행을 만들어 지운다
    p2 = {**payload, code_key: str(payload[code_key]) + "_D"}
    r2 = a.post(path, data=p2)
    did = js(r2).get("id")
    if did:
        ok200(fid_d, "삭제 200", a.post(f"{path}/{did}/delete"))
        expect(fid_d, "지운 행 다시 삭제 → 404", a.post(f"{path}/{did}/delete"), 404)
    else:
        R.chk(fid_d, "삭제용 행 등록", False, short(r2))
    if ref_delete:
        expect(fid_d, f"참조 중 삭제 → 422 ({ref_delete[0]})", a.post(f"{path}/{ref_delete[1]['id']}/delete"), 422)
    path_404(fid_d, a, "POST", path + "/{id}/delete")
    unauth(fid_d, "POST", f"{path}/1/delete")
    forbid(fid_d, "FIELD", "POST", f"{path}/{rid or 1}/delete")
    # 조회
    b = read_ok(fid_l, a, f"{path}?q={payload[code_key]}")
    rows = b.get("rows") or []
    R.chk(fid_l, "검색 결과에 등록한 코드", any(str(x.get(code_key)) == str(payload[code_key]) for x in rows), f"rows {len(rows)}")
    read_ok(fid_l, login("prod"), path, "조회 역할(PROD) 200")
    forbid(fid_l, "FIELD", "GET", path)
    unauth(fid_l, "GET", path)
    return rid


def core_functions() -> dict:
    a, p, qa, fd = login("admin"), login("prod"), login("qa"), login("field")
    ctx: dict = {}
    T = TODAY.isoformat()

    # ── BAS ───────────────────────────────────────────────────────────
    it = master("F-BAS-01", "F-BAS-02", "F-BAS-03", "F-BAS-04", "/bas/items", "item_code",
                {"item_code": f"QA-IT-{U}", "item_name": "QA 제품", "item_type": "제품", "unit": "EA"}, {"item_name": "QA 제품 2"})
    raw = js(a.post("/bas/items", data={"item_code": f"QA-RAW-{U}", "item_name": "QA 원재료", "item_type": "원재료", "unit": "kg"})).get("id")
    raw2 = js(a.post("/bas/items", data={"item_code": f"QA-RAW2-{U}", "item_name": "QA 원재료 2", "item_type": "원재료", "unit": "kg"})).get("id")
    prc = master("F-BAS-09", "F-BAS-10", "F-BAS-11", "F-BAS-12", "/bas/processes", "process_code",
                 {"process_code": f"QA-PRC-{U}", "process_name": "QA 공정", "seq": "90"}, {"process_name": "QA 공정 2"})
    ctx.update(item=it, raw=raw, raw2=raw2, prc=prc)
    pp = master("F-BAS-13", "F-BAS-14", "F-BAS-15", "F-BAS-16", "/bas/process-params", "param_key",
                {"param_key": "qa_req", "process_id": prc, "label": "QA 필수값", "unit": "u", "value_type": "number", "required_yn": "Y"},
                {"label": "QA 필수값 2"})
    a.post("/bas/process-params", data={"param_key": "qa_rng", "process_id": prc, "label": "QA 범위값", "value_type": "number", "min_value": "1", "max_value": "5"})
    expect("F-BAS-13", "하한 > 상한 → 422", a.post("/bas/process-params", data={"param_key": "qa_bad", "process_id": prc, "label": "x", "min_value": "9", "max_value": "1"}), 422)
    expect("F-BAS-11", "측정값 정의가 참조하는 공정 삭제 → 422", a.post(f"/bas/processes/{prc}/delete"), 422)
    expect("F-BAS-14", "키 변경 → 422", a.post(f"/bas/process-params/{pp}", data={"param_key": "qa_req2"}), 422)
    eq = master("F-BAS-17", "F-BAS-18", "F-BAS-19", "F-BAS-20", "/bas/equipment", "equip_code",
                {"equip_code": f"QA-EQ-{U}", "equip_name": "QA 설비", "process_id": prc, "collect_yn": "Y"}, {"equip_name": "QA 설비 2"})
    cust = master("F-BAS-21", "F-BAS-22", "F-BAS-23", "F-BAS-24", "/bas/partners", "partner_code",
                  {"partner_code": f"QA-CU-{U}", "partner_name": "QA 고객", "partner_type": "고객"}, {"partner_name": "QA 고객 2"})
    sup = js(a.post("/bas/partners", data={"partner_code": f"QA-SU-{U}", "partner_name": "QA 공급", "partner_type": "공급"})).get("id")
    wk = master("F-BAS-25", "F-BAS-26", "F-BAS-27", "F-BAS-28", "/bas/workers", "worker_code",
                {"worker_code": f"QA-WK-{U}", "worker_name": "QA 작업자", "process_id": prc}, {"worker_name": "QA 작업자 2"})
    df = master("F-BAS-29", "F-BAS-30", "F-BAS-31", "F-BAS-32", "/bas/defect-codes", "defect_code",
                {"defect_code": f"QA-DF-{U}", "defect_name": "QA 불량"}, {"defect_name": "QA 불량 2"})
    master("F-BAS-33", "F-BAS-34", "F-BAS-35", "F-BAS-36", "/bas/codes", "code",
           {"group_code": "QA_GRP", "code": f"C{U}", "code_name": "QA 코드"}, {"code_name": "QA 코드 2"})
    core_code = q1("select id from bas_code where is_core = 'Y' order by id limit 1")
    if core_code:
        expect("F-BAS-35", "코어 예약 코드 삭제 → 422", a.post(f"/bas/codes/{core_code['id']}/delete"), 422)
    expect("F-BAS-33", "코어 예약 그룹에 코드 추가 → 200", a.post("/bas/codes", data={"group_code": "STOP_REASON", "code": f"Q{U}", "code_name": "QA 정지"}), 200)
    ctx.update(eq=eq, cust=cust, sup=sup, wk=wk, df=df)
    cust_code, eq_code = f"QA-CU-{U}", f"QA-EQ-{U}"

    # BOM
    bom_body = {"item_id": it, "version": "1", "component_item_id": raw, "qty": "2", "unit": "kg", "loss_rate": "0"}
    bom = ok200("F-BAS-05", "BOM 등록 200 (헤더 + 구성품 tx)", a.post("/bas/bom", data=bom_body), "id").get("id")
    expect("F-BAS-05", "같은 버전 → 중복 422", a.post("/bas/bom", data=bom_body), 422)
    expect("F-BAS-05", "자기 자신 구성품 → 422", a.post("/bas/bom", data={**bom_body, "version": "9", "component_item_id": it}), 422)
    expect("F-BAS-05", "빈 폼 → 422", a.post("/bas/bom", data={}), 422)
    unauth("F-BAS-05", "POST", "/bas/bom")
    forbid("F-BAS-05", "PROD", "POST", "/bas/bom", bom_body)
    ok200("F-BAS-06", "BOM 수정 200 (구성품 수량)", a.post(f"/bas/bom/{bom}", data={"component_item_id": raw, "qty": "3", "unit": "kg"}))
    path_404("F-BAS-06", a, "POST", "/bas/bom/{id}", {"use_yn": "Y"})
    forbid("F-BAS-06", "QA", "POST", f"/bas/bom/{bom}", {"use_yn": "Y"})
    unauth("F-BAS-06", "POST", f"/bas/bom/{bom}")
    b2 = js(a.post("/bas/bom", data={**bom_body, "version": "2"})).get("id")
    ok200("F-BAS-07", "BOM 삭제 200", a.post(f"/bas/bom/{b2}/delete"))
    path_404("F-BAS-07", a, "POST", "/bas/bom/{id}/delete")
    forbid("F-BAS-07", "PROD", "POST", f"/bas/bom/{bom}/delete")
    unauth("F-BAS-07", "POST", f"/bas/bom/{bom}/delete")
    bb = read_ok("F-BAS-08", a, f"/bas/bom?item_id={it}")
    R.chk("F-BAS-08", "구성품 트리", bool(bb.get("trees")) and bool((bb.get("rows") or [{}])[0].get("lines")), f"trees {len(bb.get('trees') or [])}")
    forbid("F-BAS-08", "FIELD", "GET", "/bas/bom")
    unauth("F-BAS-08", "GET", "/bas/bom")
    expect("F-BAS-03", "BOM 이 참조하는 품목 삭제 → 422", a.post(f"/bas/items/{raw}/delete"), 422)

    # ── ORD ───────────────────────────────────────────────────────────
    ob = {"partner_code": cust_code, "order_date": T, "due_date": (TODAY + timedelta(days=7)).isoformat(), "item_code": f"QA-IT-{U}", "qty": "10"}
    o = ok200("F-ORD-01", "수주 등록 200 (번호 ORDER)", p.post("/ord/orders", data=ob), "id", "order_no")
    oid = o.get("id")
    R.chk("F-ORD-01", "번호 형식 = sys_number_rule ORDER", bool(re.match(r"^O\d{6}-\d{3}$", str(o.get("order_no", "")))), str(o.get("order_no")))
    R.chk("F-ORD-01", "이력 1행", (q1("select count(*) n from ord_order_hist where order_id = %s", (oid,)) or {}).get("n", 0) >= 1 if oid else False, "ord_order_hist")
    expect("F-ORD-01", "거래처 누락 → 422", p.post("/ord/orders", data={**ob, "partner_code": ""}), 422)
    expect("F-ORD-01", "상세 0줄 → 422", p.post("/ord/orders", data={"partner_code": cust_code}), 422)
    expect("F-ORD-01", "없는 품목 코드 → 422", p.post("/ord/orders", data={**ob, "item_code": "NOPE-ITEM"}), 422)
    unauth("F-ORD-01", "POST", "/ord/orders")
    forbid("F-ORD-01", "QA", "POST", "/ord/orders", ob)
    ok200("F-ORD-02", "수주 수정 200 (납기)", p.post(f"/ord/orders/{oid}", data={"due_date": (TODAY + timedelta(days=8)).isoformat()}))
    R.chk("F-ORD-02", "납기 변경 전후값 이력", bool(q1("select 1 from ord_order_hist where order_id = %s and field = 'due_date'", (oid,))), "ord_order_hist.field=due_date")
    path_404("F-ORD-02", p, "POST", "/ord/orders/{id}", {"note": "x"})
    forbid("F-ORD-02", "FIELD", "POST", f"/ord/orders/{oid}", {"note": "x"})
    unauth("F-ORD-02", "POST", f"/ord/orders/{oid}")
    o2 = js(p.post("/ord/orders", data=ob)).get("id")
    ok200("F-ORD-03", "수주 취소 200 (지시 없음)", p.post(f"/ord/orders/{o2}/cancel"))
    R.chk("F-ORD-03", "status=취소", (q1("select status from ord_order where id = %s", (o2,)) or {}).get("status") == "취소", "")
    path_404("F-ORD-03", p, "POST", "/ord/orders/{id}/cancel")
    forbid("F-ORD-03", "QA", "POST", f"/ord/orders/{oid}/cancel")
    unauth("F-ORD-03", "POST", f"/ord/orders/{oid}/cancel")
    read_ok("F-ORD-04", fd, "/ord/orders", "조회 200 (현장 조회 칸)")
    unauth("F-ORD-04", "GET", "/ord/orders")
    order_no = o.get("order_no", "")
    hb = read_ok("F-ORD-05", qa, f"/ord/order-history?order_no={order_no}")
    R.chk("F-ORD-05", "전후값 행", len(hb.get("rows") or hb.get("history") or []) >= 1, f"keys {sorted(k for k in hb if isinstance(hb[k], list))[:5]}")
    unauth("F-ORD-05", "GET", "/ord/order-history")
    read_ok("F-ORD-06", fd, "/ord/delivery-calendar")
    unauth("F-ORD-06", "GET", "/ord/delivery-calendar")
    dtl = q1("select id from ord_order_dtl where order_id = %s order by line_no limit 1", (oid,)) or {}
    plb = {"item_code": f"QA-IT-{U}", "plan_date": T, "plan_qty": "10", "order_no": order_no, "line_no": "1"}
    pl = ok200("F-ORD-07", "생산계획 등록 200 (번호 PLAN)", p.post("/ord/plans", data=plb), "id", "plan_no").get("id")
    expect("F-ORD-07", "계획일 누락 → 422", p.post("/ord/plans", data={**plb, "plan_date": ""}), 422)
    unauth("F-ORD-07", "POST", "/ord/plans")
    forbid("F-ORD-07", "QA", "POST", "/ord/plans", plb)
    ok200("F-ORD-08", "생산계획 수정 200", p.post(f"/ord/plans/{pl}", data={"plan_qty": "12"}))
    path_404("F-ORD-08", p, "POST", "/ord/plans/{id}", {"plan_qty": "1"})
    forbid("F-ORD-08", "FIELD", "POST", f"/ord/plans/{pl}", {"plan_qty": "1"})
    unauth("F-ORD-08", "POST", f"/ord/plans/{pl}")
    ok200("F-ORD-09", "확정 200", p.post(f"/ord/plans/{pl}/confirm"))
    expect("F-ORD-09", "이미 확정 → 422", p.post(f"/ord/plans/{pl}/confirm"), 422)
    expect("F-ORD-08", "확정 후 계획일 변경 → 422", p.post(f"/ord/plans/{pl}", data={"plan_date": (TODAY + timedelta(days=3)).isoformat()}), 422)
    ok200("F-ORD-08", "확정 후 수량 변경 200", p.post(f"/ord/plans/{pl}", data={"plan_qty": "13"}))
    path_404("F-ORD-09", p, "POST", "/ord/plans/{id}/confirm")
    forbid("F-ORD-09", "QA", "POST", f"/ord/plans/{pl}/confirm")
    unauth("F-ORD-09", "POST", f"/ord/plans/{pl}/confirm")
    read_ok("F-ORD-10", qa, "/ord/plans")
    unauth("F-ORD-10", "GET", "/ord/plans")
    pl_unconf = js(p.post("/ord/plans", data={"item_code": f"QA-IT-{U}", "plan_date": T, "plan_qty": "5"})).get("id")

    # ── JOB ───────────────────────────────────────────────────────────
    wb = {"item_id": it, "process_id": prc, "equipment_id": eq, "plan_qty": "10", "plan_date": T, "plan_id": pl, "order_dtl_id": dtl.get("id", "")}
    w = ok200("F-JOB-01", "작업지시 등록 200 (번호 WORK_ORDER · 대기)", p.post("/job/work-orders", data=wb), "id")
    wo = w.get("id")
    wrow = q1("select * from job_work_order where id = %s", (wo,)) or {}
    R.chk("F-JOB-01", "status=대기 · 번호 W 형식", wrow.get("status") == "대기" and bool(re.match(r"^W\d{6}-\d{3}$", str(wrow.get("work_order_no")))), f"{wrow.get('status')} {wrow.get('work_order_no')}")
    R.chk("F-JOB-01", "BOM 이 있으면 job_lot 소요 줄", (q1("select count(*) n from job_lot where work_order_id = %s", (wo,)) or {}).get("n", 0) >= 1, "job_lot")
    expect("F-JOB-01", "빈 폼 → 422", p.post("/job/work-orders", data={}), 422)
    expect("F-JOB-01", "확정 안 된 계획 → 422", p.post("/job/work-orders", data={**wb, "plan_id": pl_unconf, "order_dtl_id": ""}), 422)
    unauth("F-JOB-01", "POST", "/job/work-orders")
    forbid("F-JOB-01", "QA", "POST", "/job/work-orders", wb)
    ok200("F-JOB-02", "수정 200 (수량)", p.post(f"/job/work-orders/{wo}", data={"plan_qty": "11"}))
    path_404("F-JOB-02", p, "POST", "/job/work-orders/{id}", {"plan_qty": "1"})
    forbid("F-JOB-02", "FIELD", "POST", f"/job/work-orders/{wo}", {"plan_qty": "1"})
    unauth("F-JOB-02", "POST", f"/job/work-orders/{wo}")
    wo2 = js(p.post("/job/work-orders", data={**wb, "plan_id": "", "order_dtl_id": ""})).get("id")
    ok200("F-JOB-04", "실적 없는 지시 취소 200", p.post(f"/job/work-orders/{wo2}/cancel"))
    expect("F-JOB-02", "취소된 지시 수정 → 422", p.post(f"/job/work-orders/{wo2}", data={"plan_qty": "3"}), 422)
    path_404("F-JOB-04", p, "POST", "/job/work-orders/{id}/cancel")
    forbid("F-JOB-04", "QA", "POST", f"/job/work-orders/{wo}/cancel")
    unauth("F-JOB-04", "POST", f"/job/work-orders/{wo}/cancel")
    jb = read_ok("F-JOB-05", fd, "/job/work-orders")
    R.chk("F-JOB-05", "방금 지시가 목록에", any(x.get("id") == wo for x in (jb.get("rows") or [])), f"rows {len(jb.get('rows') or [])}")
    unauth("F-JOB-05", "GET", "/job/work-orders")
    read_ok("F-JOB-06", qa, "/job/status")
    unauth("F-JOB-06", "GET", "/job/status")
    expect("F-BAS-07", "지시가 참조하는 BOM 삭제 → 422", a.post(f"/bas/bom/{bom}/delete"), 422)
    expect("F-BAS-06", "지시가 참조하는 BOM 구성품 변경 → 422", a.post(f"/bas/bom/{bom}", data={"component_item_id": raw, "qty": "4"}), 422)
    ctx.update(wo=wo)

    # ── MAT ───────────────────────────────────────────────────────────
    rb = {"item_id": raw, "qty": "100", "partner_id": sup, "unit": "kg", "receipt_date": T}
    m1 = ok200("F-MAT-01", "입고 등록 200 (원재료 LOT · 미검사 · 거래 1행)", p.post("/mat/receipts", data=rb))
    lot1 = q1("select l.* from lot l join mat_receipt r on r.lot_id = l.id where r.item_id = %s order by l.id desc limit 1", (raw,)) or \
        q1("select * from lot where item_id = %s and kind_base = 'MATERIAL' order by id desc limit 1", (raw,)) or {}
    R.chk("F-MAT-01", "LOT kind=MATERIAL · insp_status=미검사 · 번호 M", lot1.get("insp_status") == "미검사" and str(lot1.get("lot_no", "")).startswith("M"),
          f"{lot1.get('lot_no')} {lot1.get('insp_status')}")
    rec1 = q1("select id from mat_receipt where lot_id = %s", (lot1.get("id"),)) or {}
    R.chk("F-MAT-01", "재고 거래 1행 (mat_stock_trx 입고)", (q1("select count(*) n from mat_stock_trx where lot_id = %s and trx_type = '입고'", (lot1.get("id"),)) or {}).get("n") == 1, "mat_stock_trx")
    expect("F-MAT-01", "빈 폼 → 422", fd.post("/mat/receipts", data={}), 422)
    expect("F-MAT-01", "없는 품목 → 422", fd.post("/mat/receipts", data={**rb, "item_id": NOPE_ID}), 422)
    unauth("F-MAT-01", "POST", "/mat/receipts")
    forbid("F-MAT-01", "QA", "POST", "/mat/receipts", rb)
    forbid("F-MAT-01", "ADMIN", "POST", "/mat/receipts", rb)
    ok200("F-MAT-02", "입고 수정 200 (수량)", fd.post(f"/mat/receipts/{rec1.get('id')}", data={"qty": "120"}))
    path_404("F-MAT-02", fd, "POST", "/mat/receipts/{id}", {"qty": "1"})
    forbid("F-MAT-02", "QA", "POST", f"/mat/receipts/{rec1.get('id')}", {"qty": "1"})
    unauth("F-MAT-02", "POST", f"/mat/receipts/{rec1.get('id')}")
    read_ok("F-MAT-03", qa, "/mat/receipts")
    unauth("F-MAT-03", "GET", "/mat/receipts")
    m2 = js(p.post("/mat/receipts", data={**rb, "item_id": raw2}))
    lot2 = q1("select * from lot where item_id = %s and kind_base = 'MATERIAL' order by id desc limit 1", (raw2,)) or {}
    m3 = js(p.post("/mat/receipts", data=rb))
    lot3 = q1("select * from lot where item_id = %s and kind_base = 'MATERIAL' order by id desc limit 1", (raw,)) or {}   # 미검사로 둔다
    read_ok("F-MAT-05", fd, f"/mat/inspections?no={lot1.get('lot_no')}", "스캔 진입 ?no= 200")
    scan422("F-MAT-05", fd, "/mat/inspections?no=NOPE-LOT-QA1")
    unauth("F-MAT-05", "GET", "/mat/inspections")
    ok200("F-MAT-04", "입고검사 합격 200", qa.post("/mat/inspections", data={"lot_no": lot1.get("lot_no"), "judgement": "합격"}))
    R.chk("F-MAT-04", "lot.insp_status=합격 · qua_inspection(입고)", (q1("select insp_status from lot where id = %s", (lot1.get("id"),)) or {}).get("insp_status") == "합격"
          and bool(q1("select 1 from qua_inspection where lot_id = %s and insp_type = '입고'", (lot1.get("id"),))), "")
    qa.post("/mat/inspections", data={"lot_no": lot2.get("lot_no"), "judgement": "불합격"})
    expect("F-MAT-04", "판정 누락 → 422", qa.post("/mat/inspections", data={"lot_no": lot1.get("lot_no")}), 422)
    expect("F-MAT-04", "없는 LOT 스캔 → 422", qa.post("/mat/inspections", data={"lot_no": "NOPE-LOT-QA1", "judgement": "합격"}), 422)
    unauth("F-MAT-04", "POST", "/mat/inspections")
    forbid("F-MAT-04", "ADMIN", "POST", "/mat/inspections", {"lot_no": lot1.get("lot_no"), "judgement": "합격"})
    mb = read_ok("F-MAT-06", qa, "/mat/lots")
    R.chk("F-MAT-06", "원재료 LOT 만 · 잔량", all(str(x.get("lot_no", "M")).startswith(("M", "T")) or x.get("kind") for x in (mb.get("rows") or [])) and bool(mb.get("rows")), f"rows {len(mb.get('rows') or [])}")
    unauth("F-MAT-06", "GET", "/mat/lots")
    lab = fd.get(f"/mat/lots/{lot1.get('id')}/label", headers=HTML)
    R.chk("F-MAT-07", "라벨 200 · 인라인 SVG · 바코드 = lot_no", lab.status_code == 200 and "<svg" in lab.text and str(lot1.get("lot_no")) in lab.text, f"{lab.status_code}")
    read_ok("F-MAT-07", fd, f"/mat/lots/{lot1.get('id')}/label", "라벨 JSON 200")
    path_404("F-MAT-07", fd, "GET", "/mat/lots/{id}/label")
    unauth("F-MAT-07", "GET", f"/mat/lots/{lot1.get('id')}/label")
    read_ok("F-MAT-08", qa, "/mat/stock")
    unauth("F-MAT-08", "GET", "/mat/stock")
    ok200("F-MAT-09", "재고 조정 200", fd.post("/mat/stock/adjust", data={"item_id": raw, "qty": "5", "reason": "QA 조정"}))
    expect("F-MAT-09", "사유 누락 → 422", fd.post("/mat/stock/adjust", data={"item_id": raw, "qty": "5"}), 422)
    unauth("F-MAT-09", "POST", "/mat/stock/adjust")
    forbid("F-MAT-09", "QA", "POST", "/mat/stock/adjust", {"item_id": raw, "qty": "5", "reason": "x"})
    c1 = js(p.post("/mat/requirements/calc", data={"frm": T, "to": T}))
    n1 = (q1("select count(*) n from mat_requirement") or {}).get("n")
    c2 = p.post("/mat/requirements/calc", data={"frm": T, "to": T})
    n2 = (q1("select count(*) n from mat_requirement") or {}).get("n")
    ok200("F-MAT-10", "소요량 계산 200", c2)
    R.chk("F-MAT-10", "재실행 멱등 (행 수 같음)", n1 == n2, f"{n1} → {n2} · {str(c1)[:60]}")
    unauth("F-MAT-10", "POST", "/mat/requirements/calc")
    forbid("F-MAT-10", "QA", "POST", "/mat/requirements/calc")
    read_ok("F-MAT-11", qa, "/mat/requirements")
    unauth("F-MAT-11", "GET", "/mat/requirements")

    # ── POP ───────────────────────────────────────────────────────────
    wno = wrow.get("work_order_no", "")
    r = fd.get(f"/pop/work?no={wno}")
    R.chk("F-POP-01", "지시 번호 스캔 → POP-02 로 (200/303)", r.status_code in (200, 303) or (r.history and r.history[0].status_code in (302, 303)), f"{r.status_code} {r.url}")
    read_ok("F-POP-01", fd, "/pop/work")
    scan422("F-POP-01", fd, "/pop/work?no=NOPE-WO-QA1")
    unauth("F-POP-01", "GET", "/pop/work")
    sb = {"work_order_id": wo, "equipment_id": eq, "worker_id": wk}
    res = ok200("F-POP-02", "작업 시작 200 (실적 행)", fd.post("/pop/result/start", data=sb), "id").get("id")
    expect("F-POP-02", "같은 지시 미종료 실적 → 422", fd.post("/pop/result/start", data=sb), 422)
    expect("F-POP-02", "없는 지시 → 422", fd.post("/pop/result/start", data={"work_order_no": "NOPE-WO"}), 422)
    expect("F-POP-02", "취소된 지시 → 422", fd.post("/pop/result/start", data={"work_order_id": wo2}), 422)
    unauth("F-POP-02", "POST", "/pop/result/start")
    forbid("F-POP-02", "QA", "POST", "/pop/result/start", sb)
    expect("F-JOB-04", "실적 있는 지시 취소 → 422", p.post(f"/job/work-orders/{wo}/cancel"), 422)
    expect("F-JOB-03", "종료 안 된 실적 → 마감 422", p.post(f"/job/work-orders/{wo}/close"), 422)
    expect("F-ORD-03", "진행 중 지시가 있는 수주 취소 → 422", p.post(f"/ord/orders/{oid}/cancel"), 422)
    ib = {"work_result_id": res, "barcode": lot1.get("lot_no"), "qty": "10"}
    i1 = ok200("F-POP-06", "투입 스캔 200 (투입 계보 대상)", fd.post("/pop/inputs", data=ib)).get("id")
    expect("F-POP-06", "없는 LOT 바코드 → 422", fd.post("/pop/inputs", data={**ib, "barcode": "NOPE-LOT-QA1"}), 422)
    expect("F-POP-06", "불합격 LOT → 422", fd.post("/pop/inputs", data={**ib, "barcode": lot2.get("lot_no")}), 422)
    expect("F-POP-06", "미검사 LOT → 422", fd.post("/pop/inputs", data={**ib, "barcode": lot3.get("lot_no")}), 422)
    unauth("F-POP-06", "POST", "/pop/inputs")
    forbid("F-POP-06", "QA", "POST", "/pop/inputs", ib)
    expect("F-MAT-02", "투입된 LOT 의 입고 수정 → 422", fd.post(f"/mat/receipts/{rec1.get('id')}", data={"qty": "130"}), 422)
    expect("F-MAT-04", "투입된 LOT 재판정 → 422", qa.post("/mat/inspections", data={"lot_no": lot1.get("lot_no"), "judgement": "불합격"}), 422)
    i2 = js(fd.post("/pop/inputs", data={**ib, "qty": "1"})).get("id")
    ok200("F-POP-07", "투입 취소 200 (종료 전)", fd.post(f"/pop/inputs/{i2}/cancel"))
    path_404("F-POP-07", fd, "POST", "/pop/inputs/{id}/cancel")
    forbid("F-POP-07", "QA", "POST", f"/pop/inputs/{i1}/cancel")
    unauth("F-POP-07", "POST", f"/pop/inputs/{i1}/cancel")
    ok200("F-POP-04", "정지 기록 200 (열기)", fd.post(f"/pop/result/{res}/stop", data={"reason_code": "ETC"}))
    ok200("F-POP-04", "종료 안 된 정지가 있으면 그것을 닫는다 200", fd.post(f"/pop/result/{res}/stop", data={"reason_code": "ETC"}))
    R.chk("F-POP-04", "열린 정지 0 (닫힘)", not q1("select 1 from pop_stop where work_result_id = %s and ended_at is null", (res,)), "pop_stop")
    expect("F-POP-04", "없는 정지 사유 (열린 정지 없음) → 422", fd.post(f"/pop/result/{res}/stop", data={"reason_code": "NOPE"}), 422)
    path_404("F-POP-04", fd, "POST", "/pop/result/{id}/stop", {"reason_code": "ETC"})
    forbid("F-POP-04", "QA", "POST", f"/pop/result/{res}/stop", {"reason_code": "ETC"})
    unauth("F-POP-04", "POST", f"/pop/result/{res}/stop")
    expect("F-POP-03", "측정값 필수 누락 → 422", fd.post(f"/pop/result/{res}/end", data={"good_qty": "10"}), 422)
    expect("F-POP-03", "양품 수량 누락 → 422", fd.post(f"/pop/result/{res}/end", data={"m_qa_req": "3"}), 422)
    e = ok200("F-POP-03", "작업 종료 200 (측정값 · 생산 LOT)", fd.post(f"/pop/result/{res}/end", data={"good_qty": "10", "defect_qty": "0", "m_qa_req": "3", "m_qa_rng": "9"}), "lot_no")
    R.chk("F-POP-03", "범위 이탈 저장 + deviated (오류 아님)", "qa_rng" in (e.get("deviated") or []), f"deviated {e.get('deviated')}")
    R.chk("F-POP-03", "pop_measure 기록 2 · 생산 LOT P 번호", (q1("select count(*) n from pop_measure where work_result_id = %s", (res,)) or {}).get("n") == 2
          and str(e.get("lot_no", "")).startswith("P"), f"{e.get('lot_no')}")
    R.chk("F-POP-03", "투입 계보 (pop_input → 투입)", bool(q1("select 1 from lot_genealogy where child_lot_id = %s and relation_base = '투입'", (e.get("lot_id"),))), "lot_genealogy")
    expect("F-POP-03", "이미 종료 → 422", fd.post(f"/pop/result/{res}/end", data={"good_qty": "1", "m_qa_req": "3"}), 422)
    path_404("F-POP-03", fd, "POST", "/pop/result/{id}/end", {"good_qty": "1"})
    forbid("F-POP-03", "QA", "POST", f"/pop/result/{res}/end", {"good_qty": "1"})
    unauth("F-POP-03", "POST", f"/pop/result/{res}/end")
    expect("F-POP-07", "종료 후 투입 취소 → 422", fd.post(f"/pop/inputs/{i1}/cancel"), 422)
    ok200("F-POP-05", "폐기 기록 200 (종료 후)", fd.post(f"/pop/result/{res}/scrap", data={"qty": "1", "defect_code_id": df}))
    expect("F-POP-05", "수량 누락 → 422", fd.post(f"/pop/result/{res}/scrap", data={"defect_code_id": df}), 422)
    path_404("F-POP-05", fd, "POST", "/pop/result/{id}/scrap", {"qty": "1"})
    forbid("F-POP-05", "QA", "POST", f"/pop/result/{res}/scrap", {"qty": "1"})
    unauth("F-POP-05", "POST", f"/pop/result/{res}/scrap")
    plot_id, plot_no = e.get("lot_id"), e.get("lot_no")
    lb = fd.get(f"/pop/labels?lot={plot_id}", headers=HTML)
    R.chk("F-POP-08", "LOT 라벨 200 · SVG · 바코드 = lot_no", lb.status_code == 200 and "<svg" in lb.text and str(plot_no) in lb.text, f"{lb.status_code}")
    read_ok("F-POP-08", fd, f"/pop/labels?lot={plot_id}")
    r = fd.get(f"/pop/labels?lot={NOPE_ID}")
    R.chk("F-POP-08", "없는 LOT ID → 404/422", r.status_code in (404, 422), short(r))
    unauth("F-POP-08", "GET", "/pop/labels")
    ok200("F-JOB-03", "마감 200 (실적 종료 뒤)", p.post(f"/job/work-orders/{wo}/close"))
    expect("F-JOB-03", "이미 마감 → 422", p.post(f"/job/work-orders/{wo}/close"), 422)
    expect("F-JOB-02", "마감된 지시 수정 → 422", p.post(f"/job/work-orders/{wo}", data={"plan_qty": "3"}), 422)
    path_404("F-JOB-03", p, "POST", "/job/work-orders/{id}/close")
    forbid("F-JOB-03", "QA", "POST", f"/job/work-orders/{wo}/close")
    unauth("F-JOB-03", "POST", f"/job/work-orders/{wo}/close")
    pr = qa.get(f"/job/print?id={wo}", headers=HTML)
    R.chk("F-JOB-07", "작업지시서 200 · SVG · 지시 번호 바코드", pr.status_code == 200 and "<svg" in pr.text and str(wno) in pr.text, f"{pr.status_code}")
    read_ok("F-JOB-07", qa, f"/job/print?id={wo}")
    for raw_id, lbl in ((NOPE_ID, "없는 ID 404"), ("abc", "숫자 아닌 ID 404")):
        r = qa.get(f"/job/print?id={raw_id}")
        R.chk("F-JOB-07", lbl, r.status_code == 404, short(r))
    unauth("F-JOB-07", "GET", "/job/print")
    # 두 번째 생산 LOT (출하 취소 · 미검사 출하 거부용)
    wo3 = js(p.post("/job/work-orders", data={**wb, "plan_id": "", "order_dtl_id": ""})).get("id")
    res3 = js(fd.post("/pop/result/start", data={"work_order_id": wo3})).get("id")
    e3 = js(fd.post(f"/pop/result/{res3}/end", data={"good_qty": "5", "m_qa_req": "2"}))
    ctx.update(plot_id=plot_id, plot_no=plot_no, plot3=e3.get("lot_no"), plot3_id=e3.get("lot_id"), lot1=lot1)

    # ── QUA ───────────────────────────────────────────────────────────
    qp = {"insp_type": "최종", "item_id": it, "item_key": "qa_k", "label": "QA 항목", "min_value": "0", "max_value": "10"}
    qpl = ok200("F-QUA-01", "검사 계획 등록 200", qa.post("/qua/plans", data=qp), "ids").get("ids") or [None]
    expect("F-QUA-01", "같은 항목 키 → 중복 422", qa.post("/qua/plans", data=qp), 422)
    expect("F-QUA-01", "항목 0줄 → 422", qa.post("/qua/plans", data={"insp_type": "최종", "item_id": it}), 422)
    expect("F-QUA-01", "품목 · 공정 둘 다 없음 → 422", qa.post("/qua/plans", data={"insp_type": "최종", "item_key": "z"}), 422)
    unauth("F-QUA-01", "POST", "/qua/plans")
    forbid("F-QUA-01", "PROD", "POST", "/qua/plans", qp)
    ok200("F-QUA-02", "검사 계획 수정 200", qa.post(f"/qua/plans/{qpl[0]}", data={"label": "QA 항목 2"}))
    path_404("F-QUA-02", qa, "POST", "/qua/plans/{id}", {"label": "x"})
    forbid("F-QUA-02", "PROD", "POST", f"/qua/plans/{qpl[0]}", {"label": "x"})
    unauth("F-QUA-02", "POST", f"/qua/plans/{qpl[0]}")
    read_ok("F-QUA-03", p, "/qua/plans")
    unauth("F-QUA-03", "GET", "/qua/plans")
    ins = ok200("F-QUA-04", "검사 결과 등록 200 (판정 전)", qa.post("/qua/inspections", data={"insp_type": "최종", "lot_no": plot_no, "i_qa_k": "5"}), "id").get("id")
    R.chk("F-QUA-04", "항목 값 기록 (qua_insp_item)", bool(q1("select 1 from qua_insp_item where inspection_id = %s and item_key = 'qa_k'", (ins,))), "i_qa_k=5")
    expect("F-QUA-02", "기록된 항목 키 지우기(use_yn=N) → 422", qa.post(f"/qua/plans/{qpl[0]}", data={"use_yn": "N"}), 422)
    R.chk("F-QUA-04", "judgement=NULL",(q1("select judgement from qua_inspection where id = %s", (ins,)) or {"judgement": "?"}).get("judgement") is None, "")
    expect("F-QUA-04", "없는 LOT 스캔 → 422", qa.post("/qua/inspections", data={"insp_type": "최종", "lot_no": "NOPE-LOT-QA1"}), 422)
    expect("F-QUA-04", "검사 유형 누락 → 422", qa.post("/qua/inspections", data={"lot_no": plot_no}), 422)
    unauth("F-QUA-04", "POST", "/qua/inspections")
    forbid("F-QUA-04", "PROD", "POST", "/qua/inspections", {"insp_type": "최종", "lot_no": plot_no})
    ok200("F-QUA-05", "판정 200 → lot.insp_status", qa.post(f"/qua/inspections/{ins}/judge", data={"judgement": "합격"}))
    R.chk("F-QUA-05", "lot.insp_status=합격", (q1("select insp_status from lot where id = %s", (plot_id,)) or {}).get("insp_status") == "합격", "")
    expect("F-QUA-05", "이미 판정 → 422", qa.post(f"/qua/inspections/{ins}/judge", data={"judgement": "합격"}), 422)
    path_404("F-QUA-05", qa, "POST", "/qua/inspections/{id}/judge", {"judgement": "합격"})
    forbid("F-QUA-05", "FIELD", "POST", f"/qua/inspections/{ins}/judge", {"judgement": "합격"})
    unauth("F-QUA-05", "POST", f"/qua/inspections/{ins}/judge")
    ins_bad = js(qa.post("/qua/inspections", data={"insp_type": "최종", "lot_no": e3.get("lot_no")})).get("id")
    ok200("F-QUA-05", "불합격 + 불량 N줄 200", qa.post(f"/qua/inspections/{ins_bad}/judge", data={"judgement": "불합격", "defect_code_id": df, "defect_qty": "1"}))
    R.chk("F-QUA-05", "qua_defect 행", bool(q1("select 1 from qua_defect where inspection_id = %s", (ins_bad,))), "qua_defect")
    read_ok("F-QUA-06", p, f"/qua/inspections?no={plot_no}", "스캔 진입 ?no= 200")
    scan422("F-QUA-06", qa, "/qua/inspections?no=NOPE-LOT-QA1")
    unauth("F-QUA-06", "GET", "/qua/inspections")
    read_ok("F-QUA-07", p, "/qua/defect-stats")
    unauth("F-QUA-07", "GET", "/qua/defect-stats")
    iss = ok200("F-QUA-08", "이상 등록 200 (발생)", qa.post("/qua/issues", data={"content": "QA 이상", "process_id": prc, "lot_no": plot_no}), "id").get("id")
    expect("F-QUA-08", "내용 누락 → 422", qa.post("/qua/issues", data={}), 422)
    unauth("F-QUA-08", "POST", "/qua/issues")
    forbid("F-QUA-08", "PROD", "POST", "/qua/issues", {"content": "x"})
    expect("F-QUA-10", "조치 없이 종결 → 422", qa.post(f"/qua/issues/{iss}/close"), 422)
    ok200("F-QUA-09", "조치 200 (status=조치)", qa.post(f"/qua/issues/{iss}/action", data={"action": "QA 조치"}))
    expect("F-QUA-09", "조치 내용 누락 → 422", qa.post(f"/qua/issues/{iss}/action", data={}), 422)
    path_404("F-QUA-09", qa, "POST", "/qua/issues/{id}/action", {"action": "x"})
    forbid("F-QUA-09", "PROD", "POST", f"/qua/issues/{iss}/action", {"action": "x"})
    unauth("F-QUA-09", "POST", f"/qua/issues/{iss}/action")
    ok200("F-QUA-10", "종결 200", qa.post(f"/qua/issues/{iss}/close"))
    R.chk("F-QUA-10", "status=종결", (q1("select status from qua_issue where id = %s", (iss,)) or {}).get("status") == "종결", "")
    path_404("F-QUA-10", qa, "POST", "/qua/issues/{id}/close")
    forbid("F-QUA-10", "FIELD", "POST", f"/qua/issues/{iss}/close")
    unauth("F-QUA-10", "POST", f"/qua/issues/{iss}/close")
    read_ok("F-QUA-11", fd, "/qua/issues")
    unauth("F-QUA-11", "GET", "/qua/issues")

    # ── EQP ───────────────────────────────────────────────────────────
    read_ok("F-EQP-01", a, "/eqp/status")
    unauth("F-EQP-01", "GET", "/eqp/status")
    ok200("F-EQP-02", "가동 상태 기록 200", fd.post("/eqp/status", data={"equipment_id": eq, "state": "가동"}))
    expect("F-EQP-02", "없는 상태 → 422", fd.post("/eqp/status", data={"equipment_id": eq, "state": "NOPE"}), 422)
    expect("F-EQP-02", "없는 설비 → 422", fd.post("/eqp/status", data={"equipment_id": NOPE_ID, "state": "가동"}), 422)
    unauth("F-EQP-02", "POST", "/eqp/status")
    forbid("F-EQP-02", "QA", "POST", "/eqp/status", {"equipment_id": eq, "state": "가동"})
    ok200("F-EQP-03", "점검 등록 200", fd.post("/eqp/checks", data={"equipment_id": eq, "item": "QA 점검", "result": "양호"}))
    expect("F-EQP-03", "항목 누락 → 422", fd.post("/eqp/checks", data={"equipment_id": eq}), 422)
    unauth("F-EQP-03", "POST", "/eqp/checks")
    forbid("F-EQP-03", "ADMIN", "POST", "/eqp/checks", {"equipment_id": eq, "item": "x"})
    read_ok("F-EQP-04", qa, "/eqp/checks")
    unauth("F-EQP-04", "GET", "/eqp/checks")
    flt = ok200("F-EQP-05", "고장 등록 200 (고장 구간 시작)", p.post("/eqp/faults", data={"equipment_id": eq, "symptom": "QA 증상"}), "id").get("id")
    expect("F-EQP-05", "증상 누락 → 422", p.post("/eqp/faults", data={"equipment_id": eq}), 422)
    unauth("F-EQP-05", "POST", "/eqp/faults")
    forbid("F-EQP-05", "QA", "POST", "/eqp/faults", {"equipment_id": eq, "symptom": "x"})
    R.chk("F-EQP-05", "가동 로그 `고장` 구간 열림", bool(q1("select 1 from eqp_run_log where equipment_id = %s and state = '고장' and ended_at is null", (eq,))), "eqp_run_log")
    ok200("F-EQP-06", "고장 조치 200", p.post(f"/eqp/faults/{flt}/fix", data={"fix_action": "QA 조치"}))
    R.chk("F-EQP-06", "고장 구간 닫힘", not q1("select 1 from eqp_run_log where equipment_id = %s and state = '고장' and ended_at is null", (eq,)), "eqp_run_log")
    expect("F-EQP-06", "조치 내용 누락 → 422", p.post(f"/eqp/faults/{flt}/fix", data={}), 422)
    path_404("F-EQP-06", p, "POST", "/eqp/faults/{id}/fix", {"fix_action": "x"})
    forbid("F-EQP-06", "QA", "POST", f"/eqp/faults/{flt}/fix", {"fix_action": "x"})
    unauth("F-EQP-06", "POST", f"/eqp/faults/{flt}/fix")
    read_ok("F-EQP-07", qa, "/eqp/faults")
    unauth("F-EQP-07", "GET", "/eqp/faults")
    read_ok("F-EQP-08", a, f"/eqp/collect?equipment_id={eq}")
    unauth("F-EQP-08", "GET", "/eqp/collect")

    # ── SHP ───────────────────────────────────────────────────────────
    shb = {"partner_code": cust_code, "ship_date": T}
    s1 = ok200("F-SHP-01", "출하 등록 200 (번호 SHIPMENT · 등록)", p.post("/shp/shipments", data=shb), "id", "shipment_no")
    sid, sno = s1.get("id"), s1.get("shipment_no")
    R.chk("F-SHP-01", "번호 S 형식", bool(re.match(r"^S\d{6}-\d{3}$", str(sno))), str(sno))
    expect("F-SHP-01", "거래처 누락 → 422", p.post("/shp/shipments", data={}), 422)
    expect("F-SHP-01", "없는 거래처 → 422", p.post("/shp/shipments", data={"partner_code": "NOPE-CU"}), 422)
    unauth("F-SHP-01", "POST", "/shp/shipments")
    forbid("F-SHP-01", "ADMIN", "POST", "/shp/shipments", shb)
    ok200("F-SHP-02", "출하 수정 200 (승인 전)", p.post(f"/shp/shipments/{sid}", data={"note": "QA"}))
    path_404("F-SHP-02", p, "POST", "/shp/shipments/{id}", {"note": "x"})
    forbid("F-SHP-02", "QA", "POST", f"/shp/shipments/{sid}", {"note": "x"})
    unauth("F-SHP-02", "POST", f"/shp/shipments/{sid}")
    expect("F-SHP-07", "LOT 0건 승인 → 422", a.post(f"/shp/shipments/{sid}/approve"), 422)
    sc = {"shipment_no": sno, "barcode": plot_no}
    ok200("F-SHP-05", "LOT 스캔 200 (출하 계보 1줄)", fd.post("/shp/scan", data=sc))
    R.chk("F-SHP-05", "출하 계보 · 출하 LOT", bool(q1("select 1 from lot_genealogy where parent_lot_id = %s and relation_base = '출하'", (plot_id,))), "")
    expect("F-SHP-05", "같은 LOT 다시 → 이미 출하 422", fd.post("/shp/scan", data=sc), 422)
    expect("F-SHP-05", "없는 LOT 바코드 → 422", fd.post("/shp/scan", data={**sc, "barcode": "NOPE-LOT-QA1"}), 422)
    expect("F-SHP-05", "불합격 LOT → 422", fd.post("/shp/scan", data={**sc, "barcode": e3.get("lot_no")}), 422)
    expect("F-SHP-05", "생산 LOT 아님(원재료) → 422", fd.post("/shp/scan", data={**sc, "barcode": lot1.get("lot_no")}), 422)
    expect("F-SHP-05", "없는 출하 번호 → 422", fd.post("/shp/scan", data={"shipment_no": "NOPE-S", "barcode": plot_no}), 422)
    unauth("F-SHP-05", "POST", "/shp/scan")
    forbid("F-SHP-05", "QA", "POST", "/shp/scan", sc)
    expect("F-QUA-04", "출하된 LOT 검사 등록 → 422", qa.post("/qua/inspections", data={"insp_type": "최종", "lot_no": plot_no}), 422)
    ok200("F-SHP-06", "스캔 취소 200 (unship)", fd.post("/shp/scan/cancel", data=sc))
    expect("F-SHP-06", "없는 출하 번호 → 422", fd.post("/shp/scan/cancel", data={"shipment_no": "NOPE-S", "barcode": plot_no}), 422)
    unauth("F-SHP-06", "POST", "/shp/scan/cancel")
    forbid("F-SHP-06", "QA", "POST", "/shp/scan/cancel", sc)
    fd.post("/shp/scan", data=sc)
    s2 = js(p.post("/shp/shipments", data=shb))
    ok200("F-SHP-03", "출하 취소 200 (승인 전)", p.post(f"/shp/shipments/{s2.get('id')}/cancel"))
    path_404("F-SHP-03", p, "POST", "/shp/shipments/{id}/cancel")
    forbid("F-SHP-03", "QA", "POST", f"/shp/shipments/{sid}/cancel")
    unauth("F-SHP-03", "POST", f"/shp/shipments/{sid}/cancel")
    forbid("F-SHP-07", "PROD", "POST", f"/shp/shipments/{sid}/approve")
    n_ob0 = (q1("select count(*) n from ifc_outbox") or {}).get("n", 0)
    ok200("F-SHP-07", "승인 200 (관리자 · 범위 승인)", a.post(f"/shp/shipments/{sid}/approve"))
    n_ob1 = (q1("select count(*) n from ifc_outbox") or {}).get("n", 0)
    srow = q1("select status, approved_at, approved_by from shp_shipment where id = %s", (sid,)) or {}
    R.chk("F-SHP-07", "status=승인 · approved_at/by", srow.get("status") == "승인" and srow.get("approved_at") is not None and srow.get("approved_by") == "admin", str(srow.get("status")))
    if n_ob1 == n_ob0:
        R.notes.append("F-SHP-07 승인 뒤 ifc_outbox 행 0 — 코어 단독은 after_commit_shipment_approved 훅이 없어 ERP 큐가 생기지 않는다(계약 문장 「after_commit 으로 ERP 큐」와 차이 · DEF 경미)")
    expect("F-SHP-07", "이미 승인 → 422", a.post(f"/shp/shipments/{sid}/approve"), 422)
    path_404("F-SHP-07", a, "POST", "/shp/shipments/{id}/approve")
    unauth("F-SHP-07", "POST", f"/shp/shipments/{sid}/approve")
    expect("F-POP-03", "출하된 LOT 분할 (D-12 split) → 422", fd.post(f"/pop/result/{res}/split", data={"count": "2", "lot_id": plot_id}), 422)
    expect("F-POP-03", "출하된 LOT 합병 (D-12 merge) → 422", fd.post(f"/pop/result/{res}/merge", data={"lot_ids": f"{plot_id},{e3.get('lot_id')}"}), 422)
    expect("F-SHP-02", "승인 후 수정 → 422",p.post(f"/shp/shipments/{sid}", data={"note": "y"}), 422)
    expect("F-SHP-03", "승인 후 취소 → 422", p.post(f"/shp/shipments/{sid}/cancel"), 422)
    expect("F-SHP-06", "승인 후 스캔 취소 → 422", fd.post("/shp/scan/cancel", data=sc), 422)
    expect("F-SHP-05", "승인된 출하에 스캔 → 422", fd.post("/shp/scan", data={**sc, "barcode": ctx.get("plot3") or plot_no}), 422)
    read_ok("F-SHP-04", qa, "/shp/shipments")
    unauth("F-SHP-04", "GET", "/shp/shipments")
    s3 = js(p.post("/shp/shipments", data=shb))
    doc = ok200("F-SHP-09", "성적서 발행 200 (번호 DOCUMENT · 스냅샷)", p.post("/shp/documents", data={"shipment_id": sid}), "id").get("id")
    expect("F-SHP-09", "미승인 출하 → 422", p.post("/shp/documents", data={"shipment_id": s3.get("id")}), 422)
    expect("F-SHP-09", "출하 누락 → 422", p.post("/shp/documents", data={}), 422)
    unauth("F-SHP-09", "POST", "/shp/documents")
    forbid("F-SHP-09", "QA", "POST", "/shp/documents", {"shipment_id": sid})
    d2 = js(p.post("/shp/documents", data={"shipment_id": sid})).get("id")
    R.chk("F-SHP-09", "같은 출하 재발행 = 새 번호", bool(d2) and d2 != doc, f"{doc} → {d2}")
    dp = qa.get(f"/shp/documents/{doc}/print", headers=HTML)
    R.chk("F-SHP-10", "성적서 출력 200 · SVG", dp.status_code == 200 and "<svg" in dp.text, f"{dp.status_code}")
    read_ok("F-SHP-10", qa, f"/shp/documents/{doc}/print")
    path_404("F-SHP-10", qa, "GET", "/shp/documents/{id}/print")
    unauth("F-SHP-10", "GET", f"/shp/documents/{doc}/print")
    read_ok("F-SHP-08", qa, "/shp/status")
    unauth("F-SHP-08", "GET", "/shp/status")
    xlot = q1("""select l.lot_no from lot l join lot_genealogy g on g.child_lot_id = l.id where g.parent_lot_id = %s and g.relation_base = '출하'""", (plot_id,)) or {}

    # ── TRC (쓰기 0) ──────────────────────────────────────────────────
    before = conn.table_counts()
    fb = read_ok("F-TRC-01", a, f"/trc/forward?no={lot1.get('lot_no')}")
    R.chk("F-TRC-01", "원재료 → 생산 → 출하 LOT 도달", str(xlot.get("lot_no") or "∅") in json.dumps(fb, ensure_ascii=False, default=str), f"출하 LOT {xlot.get('lot_no')}")
    scan422("F-TRC-01", a, "/trc/forward?no=NOPE-LOT-QA1")
    unauth("F-TRC-01", "GET", "/trc/forward")
    forbid("F-TRC-01", "FIELD", "GET", "/trc/forward")
    bk = read_ok("F-TRC-02", qa, f"/trc/backward?no={xlot.get('lot_no')}")
    R.chk("F-TRC-02", "출하 LOT → 원재료 LOT 도달", str(lot1.get("lot_no")) in json.dumps(bk, ensure_ascii=False, default=str), f"원재료 {lot1.get('lot_no')}")
    scan422("F-TRC-02", qa, "/trc/backward?no=NOPE-LOT-QA1")
    unauth("F-TRC-02", "GET", "/trc/backward")
    sr = read_ok("F-TRC-03", p, f"/trc/search?q={str(plot_no)[:7]}")
    R.chk("F-TRC-03", "번호 일부 검색 결과", bool(sr.get("results")), f"results {len(sr.get('results') or [])}")
    unauth("F-TRC-03", "GET", "/trc/search")
    after = conn.table_counts()
    diff = {k for k in set(before) | set(after) if before.get(k) != after.get(k) and k != "sys_access_log"}
    for fid in ("F-TRC-01", "F-TRC-02", "F-TRC-03"):
        R.chk(fid, "쓰기 0 (접근 로그 밖 행 수 diff)", not diff, str(sorted(diff)) if diff else "0")

    # ── KPI ───────────────────────────────────────────────────────────
    kb = fd.get("/kpi/board?device=board")
    R.chk("F-KPI-01", "현황판 ?device=board 200 JSON", kb.status_code == 200, short(kb))
    hb2 = fd.get("/kpi/board?device=board", headers=HTML)
    R.chk("F-KPI-01", "자동 새로고침 + 갱신 시각", "data-refresh-seconds" in hb2.text, f"{hb2.status_code}")
    unauth("F-KPI-01", "GET", "/kpi/board")
    for fid, kind in (("F-KPI-02", "production"), ("F-KPI-03", "quality"), ("F-KPI-04", "delivery"), ("F-KPI-05", "equipment")):
        read_ok(fid, p, f"/kpi/summary?kind={kind}")
        unauth(fid, "GET", f"/kpi/summary?kind={kind}")
    kib = {"indicator_key": f"qa_{U.lower()}", "name": "QA 지표", "calc_kind": "core:production.good_rate", "target_value": "95"}
    kid = ok200("F-KPI-06", "지표 등록 200 (관리자 · 범위 지표)", a.post("/kpi/indicators", data=kib), "id").get("id")
    expect("F-KPI-06", "같은 키 → 중복 422", a.post("/kpi/indicators", data=kib), 422)
    expect("F-KPI-06", "필수 누락 → 422", a.post("/kpi/indicators", data={}), 422)
    expect("F-KPI-06", "모르는 산식 → 422", a.post("/kpi/indicators", data={**kib, "indicator_key": f"qb_{U.lower()}", "calc_kind": "nope"}), 422)
    unauth("F-KPI-06", "POST", "/kpi/indicators")
    forbid("F-KPI-06", "PROD", "POST", "/kpi/indicators", kib)
    ok200("F-KPI-07", "지표 수정 200 (목표값)", a.post(f"/kpi/indicators/{kid}", data={"target_value": "90"}))
    path_404("F-KPI-07", a, "POST", "/kpi/indicators/{id}", {"target_value": "1"})
    forbid("F-KPI-07", "PROD", "POST", f"/kpi/indicators/{kid}", {"target_value": "1"})
    unauth("F-KPI-07", "POST", f"/kpi/indicators/{kid}")
    read_ok("F-KPI-08", fd, "/kpi/indicators")
    unauth("F-KPI-08", "GET", "/kpi/indicators")

    # ── SYS ───────────────────────────────────────────────────────────
    rc = f"QA{U}"
    role = ok200("F-SYS-05", "역할 등록 200", a.post("/sys/roles", data={"role_code": rc, "role_name": "QA 역할"}), "id").get("id")
    n_cells = (q1("select count(*) n, count(*) filter (where level = '없음') z from sys_permission where role_id = %s", (role,)) or {})
    R.chk("F-SYS-05", f"칸 수 = 메뉴 수 {len(nav.ALL_MENUS)} · 전부 없음", n_cells.get("n") == len(nav.ALL_MENUS) and n_cells.get("z") == len(nav.ALL_MENUS), str(n_cells))
    expect("F-SYS-05", "같은 코드 → 중복 422", a.post("/sys/roles", data={"role_code": rc, "role_name": "x"}), 422)
    expect("F-SYS-05", "필수 누락 → 422", a.post("/sys/roles", data={}), 422)
    unauth("F-SYS-05", "POST", "/sys/roles")
    forbid("F-SYS-05", "PROD", "POST", "/sys/roles", {"role_code": "X", "role_name": "x"})
    ok200("F-SYS-06", "역할 수정 200", a.post(f"/sys/roles/{role}", data={"role_name": "QA 역할 2"}))
    admin_role = (q1("select id from sys_role where role_code = 'ADMIN'") or {}).get("id")
    expect("F-SYS-06", "ADMIN 중지 → 422", a.post(f"/sys/roles/{admin_role}", data={"use_yn": "N"}), 422)
    path_404("F-SYS-06", a, "POST", "/sys/roles/{id}", {"role_name": "x"})
    forbid("F-SYS-06", "QA", "POST", f"/sys/roles/{role}", {"role_name": "x"})
    unauth("F-SYS-06", "POST", f"/sys/roles/{role}")
    read_ok("F-SYS-07", a, "/sys/roles")
    forbid("F-SYS-07", "PROD", "GET", "/sys/roles")
    unauth("F-SYS-07", "GET", "/sys/roles")
    lid = f"qa1u{U.lower()}"
    upw = uuid.uuid4().hex
    ub = {"login_id": lid, "user_name": "QA 사용자", "role_id": role, "password": upw}
    uid = ok200("F-SYS-01", "사용자 등록 200", a.post("/sys/users", data=ub), "id").get("id")
    expect("F-SYS-01", "같은 ID → 중복 422", a.post("/sys/users", data=ub), 422)
    expect("F-SYS-01", "필수 누락 → 422", a.post("/sys/users", data={}), 422)
    unauth("F-SYS-01", "POST", "/sys/users")
    forbid("F-SYS-01", "PROD", "POST", "/sys/users", ub)
    u = login(lid, upw, fresh=True)
    r0 = u.get("/bas/items")
    ok200("F-SYS-08", "권한 칸 수정 200 (새 역할 × bas = 조회)", a.post("/sys/permissions", data={"role_code": rc, "menu_code": "bas", "level": "조회"}))
    r1 = u.get("/bas/items")
    R.chk("F-SYS-08", "저장 즉시 다음 요청부터 반영 (403 → 200 · 코드 변경 0)", r0.status_code == 403 and r1.status_code == 200, f"{r0.status_code} → {r1.status_code}")
    expect("F-SYS-08", "ADMIN × sys 를 없음으로 → 422 (고정)", a.post("/sys/permissions", data={"role_code": "ADMIN", "menu_code": "sys", "level": "없음"}), 422)
    expect("F-SYS-08", "없는 등급 → 422", a.post("/sys/permissions", data={"role_code": rc, "menu_code": "bas", "level": "최고"}), 422)
    expect("F-SYS-08", "없는 범위 → 422", a.post("/sys/permissions", data={"role_code": rc, "menu_code": "bas", "level": "입력", "scopes": "없는범위"}), 422)
    expect("F-SYS-08", "빈 폼 → 422", a.post("/sys/permissions", data={}), 422)
    unauth("F-SYS-08", "POST", "/sys/permissions")
    forbid("F-SYS-08", "PROD", "POST", "/sys/permissions", {"role_code": rc, "menu_code": "bas", "level": "조회"})
    ok200("F-SYS-02", "사용자 수정 200", a.post(f"/sys/users/{uid}", data={"user_name": "QA 사용자 2"}))
    upw2 = uuid.uuid4().hex
    rp0 = u.get("/bas/items")
    ok200("F-SYS-02", "비밀번호 재설정 200", a.post(f"/sys/users/{uid}", data={"password": upw2}))
    rp1 = u.get("/bas/items")
    R.chk("F-SYS-02", "비밀번호 변경 전 세션 → 다음 요청 401", rp0.status_code == 200 and rp1.status_code == 401, f"{rp0.status_code} → {rp1.status_code}")
    u = login(lid, upw2, fresh=True)
    path_404("F-SYS-02", a, "POST", "/sys/users/{id}", {"user_name": "x"})
    forbid("F-SYS-02", "QA", "POST", f"/sys/users/{uid}", {"user_name": "x"})
    unauth("F-SYS-02", "POST", f"/sys/users/{uid}")
    prod_role = (q1("select id from sys_role where role_code = 'PROD'") or {}).get("id")
    a.post(f"/sys/users/{uid}", data={"role_id": prod_role})
    r2 = u.get("/ord/orders")
    R.chk("F-SYS-02", "역할 변경이 다음 요청부터 (PROD → ORD 200)", r2.status_code == 200, f"{r2.status_code}")
    ok200("F-SYS-03", "사용자 중지 200", a.post(f"/sys/users/{uid}/toggle"))
    r3 = u.get("/ord/orders")
    R.chk("F-SYS-03", "중지 뒤 그 세션 다음 요청 401", r3.status_code == 401, f"{r3.status_code}")
    admin_id = (q1("select id from sys_user where login_id = 'admin'") or {}).get("id")
    expect("F-SYS-03", "자기 자신 중지 → 422", a.post(f"/sys/users/{admin_id}/toggle"), 422)
    ok200("F-SYS-03", "해제 200", a.post(f"/sys/users/{uid}/toggle"))
    path_404("F-SYS-03", a, "POST", "/sys/users/{id}/toggle")
    forbid("F-SYS-03", "PROD", "POST", f"/sys/users/{uid}/toggle")
    unauth("F-SYS-03", "POST", f"/sys/users/{uid}/toggle")
    ub2 = read_ok("F-SYS-04", a, "/sys/users")
    R.chk("F-SYS-04", "응답에 비밀번호 해시 없음", "password_hash" not in json.dumps(ub2, default=str) and upw not in json.dumps(ub2, default=str), "")
    forbid("F-SYS-04", "QA", "GET", "/sys/users")
    unauth("F-SYS-04", "GET", "/sys/users")
    pb = read_ok("F-SYS-09", a, "/sys/permissions")
    forbid("F-SYS-09", "FIELD", "GET", "/sys/permissions")
    unauth("F-SYS-09", "GET", "/sys/permissions")
    lg = read_ok("F-SYS-10", a, "/sys/logs")
    dump = json.dumps(lg, ensure_ascii=False, default=str)
    R.chk("F-SYS-10", "비밀번호 · 세션 ID 없음", PW not in dump and upw not in dump and '"sid"' not in dump, "")
    forbid("F-SYS-10", "PROD", "GET", "/sys/logs")
    unauth("F-SYS-10", "GET", "/sys/logs")
    rule = q1("select * from sys_number_rule where kind = 'ISSUE'") or {}
    ok200("F-SYS-11", "채번 규칙 수정 200 (같은 값 다시)", a.post("/sys/numbering", data={"kind": "ISSUE", "prefix": rule.get("prefix", "Q"), "date_format": rule.get("date_format", "YYMMDD-"),
                                                                                      "seq_digits": str(rule.get("seq_digits", 3)), "use_yn": "Y"}))
    expect("F-SYS-11", "종류 누락 → 422", a.post("/sys/numbering", data={"seq_digits": "3"}), 422)
    unauth("F-SYS-11", "POST", "/sys/numbering")
    forbid("F-SYS-11", "PROD", "POST", "/sys/numbering", {"kind": "ISSUE", "seq_digits": "3"})
    nb = read_ok("F-SYS-12", a, "/sys/numbering")
    R.chk("F-SYS-12", "다음 번호(peek) 표시", "peek" in json.dumps(nb, default=str) or "next" in json.dumps(nb, default=str), "")
    unauth("F-SYS-12", "GET", "/sys/numbering")
    t0 = time.time()
    bk1 = a.post("/sys/backup")
    bkid = ok200("F-SYS-13", "백업 200", bk1, "id").get("id")
    unauth("F-SYS-13", "POST", "/sys/backup")
    forbid("F-SYS-13", "PROD", "POST", "/sys/backup")
    if bkid:
        ok200("F-SYS-14", "복구 확인 200 (임시 DB)", a.post(f"/sys/backup/{bkid}/verify"))
    path_404("F-SYS-14", a, "POST", "/sys/backup/{id}/verify")
    unauth("F-SYS-14", "POST", "/sys/backup/1/verify")
    forbid("F-SYS-14", "PROD", "POST", "/sys/backup/1/verify")
    R.notes.append(f"F-SYS-13/14 백업 · 복구 확인 {time.time() - t0:.1f}s")
    ok200("F-SYS-15", "이관 실행 200 (examples · dry-run)", a.post("/sys/migrate", data={"command": "basics", "dry_run": "Y"}))
    expect("F-SYS-15", "모르는 명령 → 422", a.post("/sys/migrate", data={"command": "nope"}), 422)
    unauth("F-SYS-15", "POST", "/sys/migrate")
    forbid("F-SYS-15", "PROD", "POST", "/sys/migrate", {"command": "basics", "dry_run": "Y"})
    read_ok("F-SYS-16", a, "/sys/backup")
    unauth("F-SYS-16", "GET", "/sys/backup")

    # ── IFC ───────────────────────────────────────────────────────────
    tok = get_settings().collect_token or ""
    msg = {"equip_code": eq_code, "ts": datetime.now().astimezone().isoformat(timespec="seconds"), "source": "qa1", "tags": {"run_state": 1, "count": 3}, "resend": False}
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/ifc/collect", json=msg, headers={"X-Collect-Token": tok})
    ok200("F-IFC-01", "수신 200 (raw_id)", r, "raw_id")
    r = c.post("/ifc/collect", json=msg, headers={"X-Collect-Token": tok})
    R.chk("F-IFC-01", "같은 메시지 재전송 → 200 duplicate", r.status_code == 200 and js(r).get("duplicate") is True, short(r))
    r = c.post("/ifc/collect", json={**msg, "equip_code": "NOPE-EQ"}, headers={"X-Collect-Token": tok})
    R.chk("F-IFC-01", "모르는 설비 → 422 + 거부 기록", r.status_code == 422 and bool(q1("select 1 from ifc_collect_raw where equip_code = 'NOPE-EQ' and rejected_reason is not null")), short(r))
    r = c.post("/ifc/collect", json={**msg, "ts": (datetime.now().astimezone() + timedelta(seconds=1)).isoformat(timespec="seconds"), "tags": {"qa1_unknown_tag": 1}},
               headers={"X-Collect-Token": tok})
    R.chk("F-IFC-01", "모르는 태그 → 저장 + unknown_tags", r.status_code == 200 and "qa1_unknown_tag" in (js(r).get("unknown_tags") or []), short(r))
    r = c.post("/ifc/collect", json=msg, headers={"X-Collect-Token": "wrong"})
    R.chk("F-IFC-01", "토큰 불일치 → 401", r.status_code == 401, short(r))
    r = c.post("/ifc/collect", content=b"not json", headers={"X-Collect-Token": tok, "content-type": "application/json"})
    R.chk("F-IFC-01", "본문 형식 오류 → 422", r.status_code == 422, short(r))
    read_ok("F-IFC-02", p, "/ifc/collect")
    forbid("F-IFC-02", "QA", "GET", "/ifc/collect")
    unauth("F-IFC-02", "GET", "/ifc/collect")
    read_ok("F-IFC-03", a, "/ifc/erp")
    forbid("F-IFC-03", "FIELD", "GET", "/ifc/erp")
    unauth("F-IFC-03", "GET", "/ifc/erp")
    ob_row = q1("select id from ifc_outbox order by id desc limit 1") or {}
    r = a.post(f"/ifc/erp/{ob_row.get('id')}/retry")
    R.chk("F-IFC-04", "재전송 → 501 미확정 (D-02) · 조용한 폴백 0", r.status_code == 501 and js(r).get("decision") == "D-02" and js(r).get("code") == "undecided", short(r) + f" decision={js(r).get('decision')}")
    path_404("F-IFC-04", a, "POST", "/ifc/erp/{id}/retry")
    forbid("F-IFC-04", "PROD", "POST", f"/ifc/erp/{ob_row.get('id')}/retry")
    unauth("F-IFC-04", "POST", f"/ifc/erp/{ob_row.get('id')}/retry")
    return ctx


def batch_functions() -> None:
    env = {**os.environ, "MES_PACK": "", "MES_PG_DSN": DSN}
    for f in contracts.batch_functions():
        cmd = f.path.split()[-1] if f.path else f.api.split()[-1]
        base = ["uv", "run", "python", "-m", "mescore.migrate", cmd, "--dir", str(EXAMPLES)]
        p1 = subprocess.run(base + ["--dry-run"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        head = "파일" in p1.stdout and "읽음" in p1.stdout and "오류" in p1.stdout
        R.chk(f.id, "dry-run 종료 0 · 리포트 열 (파일 읽음 적재 갱신 건너뜀 오류)", p1.returncode == 0 and head, f"rc={p1.returncode} {(p1.stdout.strip().splitlines() or [''])[-1][:80]}")
        outs = []
        for _ in range(2):
            pr = subprocess.run(base, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
            m = re.search(r"적재\s+(\d+)", (pr.stdout.strip().splitlines() or [""])[-1])
            outs.append((pr.returncode, int(m.group(1)) if m else -1))
        R.chk(f.id, "실적재 2회 — 둘째 적재 0 (멱등)", outs[0][0] == 0 and outs[1][0] == 0 and outs[1][1] == 0, f"{outs}")
        bad = subprocess.run(["uv", "run", "python", "-m", "mescore.migrate", cmd, "--dir", "/nonexistent-qa1"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        R.chk(f.id, "없는 폴더 → 종료 코드 ≠ 0", bad.returncode != 0, f"rc={bad.returncode}")


# ════════════════════════════════════════════════════════════════════════
# 팩 모드 — 읽기 · 호출만 (정상 쓰기 호출 없음)
# ════════════════════════════════════════════════════════════════════════
MSGS: list[tuple[str, str, list[str]]] = []       # 팩 모드 — 오류 응답의 message · fields[].label (치환됐는지 본다)


def unreplaced(text: str) -> list[str]:
    terms = {k: v for k, v in P.terms.items() if k != v}
    vis = text
    for v in sorted(set(terms.values()), key=len, reverse=True):
        vis = vis.replace(v, " ")
    return [k for k in sorted(terms, key=len, reverse=True) if k in vis]


def readonly_functions(fns) -> None:
    """읽기 기능: 조회 200 JSON · 미로그인 401. 쓰기 기능: 미로그인 401 · 빈 폼/없는 키 → 422/404 (쓰지 않는다)."""
    a = login("admin")
    for f in fns:
        if f.is_batch:
            continue
        if f.is_token:
            r = ANON.post(f.path_base, json={}, headers={"X-Collect-Token": "wrong"})
            R.chk(f.id, "토큰 불일치 401", r.status_code == 401, short(r))
            continue
        has_key = "{" in f.path_base
        url = re.sub(r"\{[^}]+\}", NOPE_ID, f.path_base)
        if f.module in {m.code for m in nav.ALL_MENUS if m.hidden}:
            r = a.request(f.method, url, data={})
            R.chk(f.id, "팩이 숨긴 메뉴 → 403", r.status_code == 403, short(r))
            unauth(f.id, f.method, url)
            continue
        if not f.is_write:
            if has_key:
                r = a.get(url)
                R.chk(f.id, "없는 경로 키 404", r.status_code == 404, short(r))
                r = a.get(re.sub(r"\{[^}]+\}", "abc", f.path_base))
                R.chk(f.id, "숫자 아닌 경로 키 404", r.status_code in (404,) or "lot_no" in f.path_base, short(r))
            else:
                read_ok(f.id, a, f.path)
            unauth(f.id, "GET", url)
            continue
        unauth(f.id, f.method, url)
        writer = next((code for code in LOGIN_OF if rbac.can_do(code, f.id)), None)
        if writer is None:
            R.notes.append(f"{f.id}: 이 팩의 역할 {sorted(LOGIN_OF)} 중 쓸 수 있는 역할 없음 (권한 표 · 범위) — 기능이 막혀 있다")
            R.chk(f.id, "입력 역할 없음 → 전 역할 403", all(login(LOGIN_OF[cd]).request(f.method, url, data={}).status_code == 403 for cd in LOGIN_OF), "")
            continue
        c = login(LOGIN_OF[writer])
        if f.id in ("F-MAT-10", "F-SYS-13", "F-SYS-15"):
            R.chk(f.id, "호출 생략 — 빈 폼으로도 쓰기가 일어나는 기능 (읽기 전용 DB)", True, "401 만")
            continue
        r = c.request(f.method, url, data={})
        b = js(r)
        MSGS.append((f.id, str(b.get("message") or ""), [str(x.get("label") or "") for x in (b.get("fields") or []) if isinstance(x, dict)]))
        want = (404, 422) if has_key else (422,)          # 필수 폼 누락 422 가 경로 조회보다 먼저일 수 있다 — 둘 다 쓰지 않는다
        R.chk(f.id, f"{writer} 빈 폼/없는 키 → {'/'.join(map(str, want))} (쓰기 0)", r.status_code in want, short(r))


# ════════════════════════════════════════════════════════════════════════
# ② G-C17 — 역할 4 × 기능 전부 · 48칸
# ════════════════════════════════════════════════════════════════════════
def expected_cell(menu: str, role: str) -> tuple[str, set[str]]:
    if WRITE_MODE:
        v = (CORE_YAML.get("permissions") or {}).get(menu, {}).get(role, "없음")
    else:
        c = P.permission(menu, role)
        return c["level"], set(c["scopes"])
    if isinstance(v, dict):
        return v.get("level", "없음"), set(v.get("scopes") or [CORE_YAML.get("scope_general", "일반")])
    return str(v), ({CORE_YAML.get("scope_general", "일반")} if v == "입력" else set())


def rbac_matrix() -> dict:
    fns = [f for f in (list(contracts.functions()) + list(contracts.pack_functions())) if not f.is_batch and not f.is_token]
    menus = [m for m in nav.ALL_MENUS]
    hidden = {m.code for m in menus if m.hidden}
    cells: dict[tuple[str, str], dict] = {}
    db = {(r["role_code"], r["menu_code"]): (r["level"], set(r["scopes"] or [])) for r in conn.q(
        "select r.role_code, p.menu_code, p.level, p.scopes from sys_permission p join sys_role r on r.id = p.role_id")}
    bad: list[str] = []
    tried = allowed_n = denied_n = 0
    skip_allowed = {"F-SYS-13", "F-SYS-14"} | (set() if WRITE_MODE else {"F-MAT-10", "F-SYS-15"})
    all_roles = list(LOGIN_OF) if WRITE_MODE else [r["code"] for r in P.roles]
    for m in menus:
        for role in all_roles:
            lvl, scopes = expected_cell(m.code, role)
            got = db.get((role, m.code))
            data_ok = got is not None and got[0] == lvl and (lvl != "입력" or got[1] == scopes)
            cells[(m.code, role)] = {"level": lvl, "scopes": sorted(scopes), "db": f"{got[0]}{sorted(got[1]) if got and got[0] == '입력' else ''}" if got else "없음(행 없음)",
                                     "data_ok": data_ok, "screens": [], "writes": [], "fails": []}
            if not data_ok:
                cells[(m.code, role)]["fails"].append(f"DB {got} ≠ 기대 {lvl}{sorted(scopes)}")
    for role, lid in LOGIN_OF.items():
        c = login(lid)
        for m in menus:
            lvl, scopes = expected_cell(m.code, role)
            cell = cells[(m.code, role)]
            for s in m.screens:
                r = c.get(s.probe or s.path)
                want_none = lvl == "없음" or m.code in hidden
                ok = (r.status_code == 403) if want_none else (r.status_code == 200)
                cell["screens"].append(ok)
                if not ok:
                    cell["fails"].append(f"화면 {s.screen_id} {r.status_code} (기대 {'403' if want_none else '200'})")
        for f in fns:
            m = f.module
            lvl, scopes = expected_cell(m, role)
            allowed = lvl == "입력" and f.scope in scopes and m not in hidden
            if not f.is_write:
                allowed = lvl in ("입력", "조회") and m not in hidden
            if f.is_write and allowed and f.id in skip_allowed:
                cells.setdefault((m, role), {"writes": [], "fails": [], "screens": []})["writes"].append(True)
                continue
            url = re.sub(r"\{[^}]+\}", NOPE_ID, f.path)
            r = c.request(f.method, url, data={})
            tried += 1
            if allowed:
                allowed_n += 1
                ok = r.status_code not in (401, 403, 500)
            else:
                denied_n += 1
                ok = r.status_code == 403
            cell = cells.setdefault((m, role), {"writes": [], "fails": [], "screens": []})
            cell["writes"].append(ok)
            if not ok:
                msg = f"{role}×{f.id} {f.method} {url} → {r.status_code} (기대 {'통과' if allowed else '403'})"
                cell["fails"].append(msg)
                bad.append(msg)
    return {"cells": cells, "bad": bad, "tried": tried, "allowed": allowed_n, "denied": denied_n, "hidden": sorted(hidden)}


# ════════════════════════════════════════════════════════════════════════
# ③ G-C23 · G-P05 — 화면 HTML 전부
# ════════════════════════════════════════════════════════════════════════
DATA_RE = [re.compile(p, re.S | re.I) for p in (r"<script.*?</script>", r"<style.*?</style>", r"<tbody.*?</tbody>", r"<option.*?</option>",
                                                   r"<textarea.*?</textarea>", r"<code.*?</code>", r"<pre.*?</pre>", r"<!--.*?-->")]


def visible_text(html: str) -> str:
    for rx in DATA_RE:
        html = rx.sub(" ", html)
    html = re.sub(r"<[^>]*>", " ", html)
    return re.sub(r"\s+", " ", html)


def all_screen_urls() -> list[tuple[str, str]]:
    out = [(s.screen_id, s.probe or s.path) for s in nav.COMMON if s.auth] + [(s.screen_id, s.probe or s.path) for s in nav.SCREENS]
    return out + [("CMN-01", "/login"), ("CMN-03", "/error")]


def screen_html(c: TestClient, extra: list[tuple[str, str]] | None = None) -> dict[str, str]:
    out = {}
    for sid, url in all_screen_urls() + (extra or []):
        r = (ANON if sid in ("CMN-01", "CMN-03") else c).get(url, headers=HTML)
        if r.status_code in (200, 422):
            out[f"{sid} {url}"] = r.text
    return out


def forbidden_runtime(pages: dict[str, str]) -> list[str]:
    from check_terms import find_hits  # noqa — 같은 판정 규칙 (한국어 부분 문자열 · 영문 낱말 경계)
    terms = {k: list(v) for k, v in (CORE_YAML.get("forbidden_terms") or {}).items()}
    hits = []
    for key, html in pages.items():
        text = re.sub(r"<[^>]*>", " ", html)
        for _line, w, src in find_hits(text, terms):
            hits.append(f"{key} `{w}`({src})")
    return sorted(set(hits))


def raw_neutral_runtime(c: TestClient, detail_urls: list[tuple[str, str]]) -> tuple[list[str], int]:
    """용어 표지 치환 — terms_keys 를 전부 표지(§n§)로 바꾼 뒤에도 화면 글(표 본문 · 선택지 · 스크립트 밖)에 날것으로 남은 중립어 = t() 누락."""
    keys = list(CORE_YAML.get("terms_keys") or [])
    pk = packs.current()
    saved_terms, saved_sorted = dict(pk.terms), list(pk._terms_sorted)
    marks = {k: f"§{i}§" for i, k in enumerate(keys)}
    try:
        pk.terms.clear()
        pk.terms.update(marks)
        pk._terms_sorted = sorted(marks.items(), key=lambda kv: -len(kv[0]))
        pages = screen_html(c, detail_urls)
    finally:
        pk.terms.clear()
        pk.terms.update(saved_terms)
        pk._terms_sorted = saved_sorted
    found: dict[str, set[str]] = {}
    for key, html in pages.items():
        for node in text_nodes(html):
            if re.search(r"\d|\(예시\)|^QA ", node):      # DB 값(시드 · 이 검사기가 만든 행) — 화면 문구가 아니다
                continue
            for k in sorted(keys, key=len, reverse=True):
                if k in node:
                    found.setdefault(key, set()).add(f"`{k}` «{node[:40]}»")
                    node = node.replace(k, " ")
    return [f"{k}: {sorted(v)[:3]}" for k, v in sorted(found.items())], len(pages)


def text_nodes(html: str) -> list[str]:
    """표 본문 · 선택지 · 스크립트 밖의 글 조각(태그 사이 글 · title/placeholder/aria-label 속성)."""
    for rx in DATA_RE:
        html = rx.sub(" ", html)
    nodes = [re.sub(r"\s+", " ", x).strip() for x in re.findall(r">([^<>]+)<", html)]
    nodes += [x.strip() for x in re.findall(r'\b(?:title|placeholder|aria-label)="([^"]+)"', html)]
    return [x for x in nodes if x and not x.startswith("{")]


def pack_terms_runtime(c: TestClient) -> tuple[list[str], int, int]:
    """G-P05 — 팩 terms 로 바뀌어야 할 키가 화면 글(표 본문 · 선택지 · DB 값 밖)에 그대로 보이는 곳."""
    terms = dict(P.terms)
    keys = [k for k, v in terms.items() if k != v]
    pages = screen_html(c)
    bad = []
    for key, html in pages.items():
        for node in text_nodes(html):
            if re.search(r"\d|\(예시\)", node):
                continue
            vis = node
            # menus.rename 값은 팩이 쓴 최종 이름 — 노출로 세지 않는다 (D-38 · check_terms --pack 과 같은 규칙 · 아키텍트 회전 5 수정 — QA1 검토)
            for v in sorted(set(getattr(P, "verbatim", set()) or set()) | set(terms.values()), key=len, reverse=True):
                vis = vis.replace(v, " ")
            for k in sorted(keys, key=len, reverse=True):
                if k in vis:
                    bad.append(f"{key} `{k}`→`{terms[k]}` «{node[:40]}»")
                    vis = vis.replace(k, " ")
    return bad, len(pages), len(keys)


# ════════════════════════════════════════════════════════════════════════
# ④ 응답 모양 · 인증 없는 경로 · ⑤ 채널
# ════════════════════════════════════════════════════════════════════════
HEALTH_KEYS = {"status", "system", "pack", "core_version", "db", "menus", "screens", "functions", "placeholders", "pack_screens", "router_include_errors"}
OPEN_PATHS = {("GET", "/health"), ("GET", "/login"), ("POST", "/login"), ("GET", "/error"), ("POST", "/ifc/collect"), ("GET", "/logout"), ("POST", "/logout")}


def route_list(routes=None, prefix: str = "") -> list[tuple[str, str]]:
    out = []
    for rt in (app.routes if routes is None else routes):
        inner = getattr(rt, "original_router", None)
        if inner is not None:
            ctx = getattr(rt, "include_context", None)
            out += route_list(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
            continue
        for m in (getattr(rt, "methods", None) or ()):
            if m in ("HEAD", "OPTIONS"):
                continue
            out.append((m, prefix + getattr(rt, "path", "")))
    return sorted(set(out))


def shapes(ctx: dict) -> list[tuple[str, bool, str]]:
    res: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, m: str = "") -> None:
        res.append((name, bool(ok), m))

    h = ANON.get("/health")
    hb = js(h)
    leak = [w for w in ("postgresql", "/tmp", DB_NAME, "mes_core_db", "host=") if w in h.text]
    add("/health 인증 없이 200 · 계약 키 11", h.status_code == 200 and set(hb) == HEALTH_KEYS, f"{h.status_code} 빠짐 {sorted(HEALTH_KEYS - set(hb))} 더함 {sorted(set(hb) - HEALTH_KEYS)}")
    add("/health 에 접속 문자열 · 호스트 · DB 이름 없음", not leak, str(leak))
    add("/health 수 = 계약 (메뉴 · 화면 · 기능 · placeholder 0)", hb.get("menus") == len(nav.MENUS) and hb.get("screens") == 51 and hb.get("functions") == 132 and hb.get("placeholders") == 0
        and hb.get("router_include_errors") == [], f"menus {hb.get('menus')} screens {hb.get('screens')} functions {hb.get('functions')} placeholders {hb.get('placeholders')} errors {hb.get('router_include_errors')}")
    for u in ("/docs", "/redoc"):
        r = ANON.get(u)
        add(f"{u} 404", r.status_code == 404, str(r.status_code))
    r0, r1, r2 = ANON.get("/openapi.json"), login("prod").get("/openapi.json"), login("admin").get("/openapi.json")
    add("/openapi.json 미로그인 401 · 시스템 조회 없음 403 · 관리자 200", (r0.status_code, r1.status_code, r2.status_code) == (401, 403, 200), f"{r0.status_code}/{r1.status_code}/{r2.status_code}")
    add("/static/app.js 인증 없이 200", ANON.get("/static/app.js").status_code == 200, "")
    add("/login · /error 인증 없이 200", ANON.get("/login", headers=HTML).status_code == 200 and ANON.get("/error", headers=HTML).status_code == 200, "")
    # 인증 없이 열리는 경로 전수
    leaks, n = [], 0
    for m, p in route_list():
        if (m, p) in OPEN_PATHS or p.startswith("/static") or p in ("/docs", "/redoc", "/docs/oauth2-redirect", "/openapi.json"):
            continue
        url = re.sub(r"\{kind\}", "item", re.sub(r"\{[^}]+\}", "1", p))
        r = ANON.request(m, url, data={})
        n += 1
        if r.status_code != 401:
            leaks.append(f"{m} {url} → {r.status_code}")
    add(f"인증 없이 열리는 경로 = 계약 5종뿐 (라우트 {n} 전수 401)", not leaks, f"{leaks[:6]}")
    c_as = TestClient(app, raise_server_exceptions=False)
    r = c_as.post("/login/as", data={"role": "ADMIN"})
    after = c_as.get("/sys/users").status_code
    add("비밀번호 없는 로그인 경로 0 (POST /login/as role=ADMIN)", not (r.status_code == 200 and after == 200),
        f"/login/as {r.status_code} → 그 세션 /sys/users {after} · MES_ENV={get_settings().env}")
    r = ANON.get("/bas/items", headers=HTML, follow_redirects=False)
    add("미로그인 브라우저 GET → 303 /login?next=", r.status_code == 303 and r.headers.get("location", "").startswith("/login?next="), f"{r.status_code} {r.headers.get('location')}")
    r = ANON.post("/bas/items", headers=HTML, data={}, follow_redirects=False)
    add("미로그인 브라우저 POST → 401 오류 화면", r.status_code == 401 and "text/html" in r.headers.get("content-type", ""), f"{r.status_code}")
    r = ANON.get("/bas/items")
    add("미로그인 JSON → 401 {code: unauthorized, message: 로그인이 필요합니다}", r.status_code == 401 and js(r) == {"code": "unauthorized", "message": "로그인이 필요합니다"}, str(js(r))[:80])
    # 로그인
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/login", data={"login_id": "admin", "password": "wrong-" + uuid.uuid4().hex}, headers=HTML, follow_redirects=False)
    add("로그인 실패 (브라우저) → 401 로그인 화면 재렌더", r.status_code == 401 and "login_id" in r.text, f"{r.status_code}")
    r = c.post("/login", data={"login_id": "admin", "password": "wrong-" + uuid.uuid4().hex})
    add("로그인 실패 (JSON) → 401", r.status_code == 401, f"{r.status_code}")
    r = c.post("/login", data={"login_id": "admin", "password": PW}, headers=HTML, follow_redirects=False)
    add("로그인 성공 (브라우저) → 303", r.status_code == 303, f"{r.status_code} {r.headers.get('location')}")
    # 쓰기 성공 / 422 (브라우저 · JSON)
    a = login("admin")
    fd = login("field")
    if WRITE_MODE and ctx.get("eq"):
        r = fd.post("/eqp/status", data={"equipment_id": ctx["eq"], "state": "정지"}, headers={**HTML, "referer": "http://testserver/eqp/status"}, follow_redirects=False)
        add("쓰기 성공 (브라우저) → 303 원래 화면", r.status_code == 303 and "/eqp/status" in r.headers.get("location", ""), f"{r.status_code} {r.headers.get('location')}")
        r2 = fd.get("/eqp/status", headers=HTML)
        add("303 뒤 알림 한 번 (flash)", "알림" in r2.text or "flash" in r2.text or "toast" in r2.text, "")
        r = fd.post("/eqp/status", data={"equipment_id": ctx["eq"], "state": "정지"})
        add("쓰기 성공 (JSON) → 200 {ok: true, message}", r.status_code == 200 and js(r).get("ok") is True and bool(js(r).get("message")), short(r))
    r = a.post("/bas/items", data={}, headers={**HTML, "referer": "http://testserver/bas/items"}, follow_redirects=False)
    add("422 폼 POST (브라우저) → 303 Referer + 알림", r.status_code == 303 and r.headers.get("location", "").endswith("/bas/items"), f"{r.status_code} {r.headers.get('location')}")
    r = a.post("/bas/items", data={})
    b = js(r)
    add("422 JSON 모양 {code, message, fields[{name, reason}]}", r.status_code == 422 and b.get("code") == "validation_error" and isinstance(b.get("fields"), list)
        and all(isinstance(x, dict) and "name" in x and "reason" in x for x in b.get("fields") or []) and bool(b.get("fields")), str(b)[:100])
    r = login("field").get("/sys/users")
    add("403 JSON {code: forbidden, message: 접근 권한이 없습니다}", r.status_code == 403 and js(r).get("code") == "forbidden" and js(r).get("message") == "접근 권한이 없습니다", str(js(r))[:80])
    r = login("field").get("/sys/users", headers=HTML)
    add("403 브라우저 → 403 오류 화면", r.status_code == 403 and "접근 권한이 없습니다" in r.text, f"{r.status_code}")
    r = a.get("/nope-qa1-path")
    add("없는 주소 404 JSON {code: not_found}", r.status_code == 404 and js(r).get("code") == "not_found", str(js(r))[:80])
    r = a.get("/popup/nope")
    add("팝업 없는 종류 404", r.status_code == 404, f"{r.status_code}")
    # 503 — DB 끊김
    old = os.environ["MES_PG_DSN"]
    os.environ["MES_PG_DSN"] = "postgresql:///mes_qa1_no_such_db"
    try:
        r = ANON.get("/health")
        add("DB 끊김 → /health 503 · db.ok false · 접속 문자열 없음", r.status_code == 503 and js(r).get("db", {}).get("ok") is False and "mes_qa1_no_such_db" not in r.text and "postgresql" not in r.text, f"{r.status_code}")
        r = a.get("/bas/items")
        add("DB 끊김 → 화면 503 {code: db_unavailable, message: 서비스 일시 중단} · 접속 문자열 없음",
            r.status_code == 503 and js(r).get("code") == "db_unavailable" and "mes_qa1_no_such_db" not in r.text, f"{r.status_code} {str(js(r))[:60]}")
        r = a.get("/bas/items", headers=HTML)
        add("DB 끊김 → 브라우저 503 오류 화면", r.status_code == 503 and "서비스 일시 중단" in r.text and "mes_qa1_no_such_db" not in r.text, f"{r.status_code}")
        r = a.get("/kpi/board?device=board", headers=HTML)
        add("DB 끊김 → 현황판 오류 화면에도 자동 새로고침 유지", r.status_code == 503 and ("data-refresh-seconds" in r.text or "http-equiv=\"refresh\"" in r.text), f"{r.status_code}")
    finally:
        os.environ["MES_PG_DSN"] = old
    # 501 모양
    if WRITE_MODE:
        obid = (q1("select id from ifc_outbox order by id desc limit 1") or {}).get("id")
        if obid:
            r = a.post(f"/ifc/erp/{obid}/retry", headers=HTML)
            add("501 브라우저 → 오류 화면에 `미확정 (D-02)`", r.status_code == 501 and "D-02" in r.text and "미확정" in r.text, f"{r.status_code}")
    # 화면 GET JSON 모양 (D-18)
    r = a.get("/bas/items")
    b = js(r)
    add("화면 GET JSON — ctx + screen_id · user · functions · template", r.status_code == 200 and all(k in b for k in ("screen_id", "user", "functions", "template")),
        f"없는 키 {[k for k in ('screen_id', 'user', 'functions', 'template') if k not in b]}")
    return res


def channels_check() -> tuple[list[str], int]:
    a = login("admin")
    ch = P.channels
    bad, n = [], 0
    for dev in ("pop", "mobile", "board"):
        allowed = set(ch.get(dev, []))
        for s in nav.SCREENS:
            if nav.menu(s.menu_code).hidden:
                continue
            url = (s.probe or s.path)
            url += ("&" if "?" in url else "?") + f"device={dev}"
            r = a.get(url)
            n += 1
            want = 200 if s.screen_id in allowed else 403
            if r.status_code != want:
                bad.append(f"{dev}:{s.screen_id} {r.status_code} (기대 {want})")
    # 세션 채널 — 로그인 때 고른 device 가 남는다
    c = login("admin", device="pop", fresh=True)
    r1, r2 = c.get("/bas/items"), c.get("/pop/work")
    if not (r1.status_code == 403 and r2.status_code == 200):
        bad.append(f"로그인 device=pop 세션: BAS-01 {r1.status_code} (기대 403) · POP-01 {r2.status_code} (기대 200)")
    n += 2
    return bad, n


# ════════════════════════════════════════════════════════════════════════
def placeholder_and_200() -> tuple[int, int, list[str]]:
    a = login("admin")
    bad, ok, ph = [], 0, []
    for s in [x for x in nav.COMMON if x.auth] + nav.SCREENS:
        if nav.menu_of_screen(s.screen_id) and nav.menu_of_screen(s.screen_id).hidden:
            continue
        r = a.get(s.probe or s.path)
        if r.status_code == 200:
            ok += 1
            if js(r).get("placeholder"):
                ph.append(s.screen_id)
        else:
            bad.append(f"{s.screen_id} {r.status_code}")
    return ok, len(ph), bad + [f"placeholder {x}" for x in ph]


def main() -> int:
    t0 = time.time()
    fh: list[str] = []
    raw: list[str] = []
    tag = f"[{PACK}] " if not WRITE_MODE else ""
    ctx: dict = {}
    core_fns = list(contracts.functions())
    pack_fns = list(contracts.pack_functions())
    # ① 기능
    if WRITE_MODE:
        try:
            ctx = core_functions()
        except Exception as exc:  # noqa: BLE001 — 흐름이 끊긴 지점을 실측에 남긴다 (조용히 넘어가지 않는다)
            import traceback
            R.notes.append(f"흐름 중단 {type(exc).__name__}: {exc} — {traceback.format_exc().splitlines()[-3:]}")
        batch_functions()
        targets = core_fns
    else:
        readonly_functions(core_fns + pack_fns)
        targets = [f for f in core_fns + pack_fns if not f.is_batch]      # 이관 배치는 쓰기라 코어 QA DB 에서만
    n_pass = sum(1 for f in targets if R.verdict(f.id) == "PASS")
    n_fail = [f.id for f in targets if R.verdict(f.id) == "FAIL"]
    n_unv = [f.id for f in targets if R.verdict(f.id) == "미검증"]
    n_checks = sum(len(R.fn.get(f.id, [])) for f in targets)
    st = "PASS" if not n_fail and not n_unv else "FAIL"
    R.row("G-C02", f"기능 {len(targets)} 계약 호출 (정상 + 오류 계약)", st,
          f"{tag}PASS {n_pass}/{len(targets)} · FAIL {len(n_fail)} {n_fail[:12]} · 미검증 {len(n_unv)} {n_unv[:6]} · 검사 {n_checks}건 · DB {DB_NAME}"
          + (f" · {R.notes[0][:160]}" if R.notes and R.notes[0].startswith("흐름") else ""))
    if not WRITE_MODE and pack_fns:
        pf = [f.id for f in pack_fns if R.verdict(f.id) != "PASS"]
        R.row("G-C02", "팩 기능 F-X 읽기 · 호출", "PASS" if not pf else "FAIL", f"{tag}팩 기능 {len(pack_fns)} · 통과 못한 {len(pf)} {pf[:8]}")
    # ② RBAC
    mx = rbac_matrix()
    cells = mx["cells"]
    core_cells = [(m, r) for (m, r) in cells if m in {x.code for x in nav.ALL_MENUS}]
    bad_cells = [k for k in core_cells if cells[k]["fails"]]
    data_bad = [k for k in core_cells if not cells[k].get("data_ok", True)]
    lv = {"입력": 0, "조회": 0, "없음": 0}
    for k in core_cells:
        lv[cells[k]["level"]] = lv.get(cells[k]["level"], 0) + 1
    n_core_cells = len(core_cells)
    R.row("G-C17", "권한 칸 데이터 = core.yaml" if WRITE_MODE else "권한 칸 데이터 = 병합본", "PASS" if not data_bad and (not WRITE_MODE or n_core_cells == 48) else "FAIL",
          f"{tag}칸 {n_core_cells} (입력 {lv['입력']} · 조회 {lv['조회']} · 없음 {lv['없음']}) · DB 불일치 {[f'{m}×{r}' for m, r in data_bad][:6] or 0}")
    R.row("G-C17", "역할 × 기능 전부 (없음 · 조회 쓰기 403 · 입력 통과)", "PASS" if not mx["bad"] else "FAIL",
          f"{tag}역할 {len(LOGIN_OF)} {sorted(LOGIN_OF)} · 호출 {mx['tried']} (허용 {mx['allowed']} · 거부 {mx['denied']}) · 위반 {len(mx['bad'])} {mx['bad'][:4]}"
          + (f" · 로그인 계정 없는 역할 {NO_LOGIN} (미검증)" if NO_LOGIN else ""))
    R.row("G-C17", "칸별 판정 (화면 GET + 기능)", "PASS" if not bad_cells else "FAIL",
          f"{tag}{n_core_cells - len(bad_cells)}/{n_core_cells} 칸 PASS · FAIL {[f'{m}×{r}' for m, r in bad_cells][:8]}")
    if WRITE_MODE:
        sc = {("QA", "F-MAT-04"): True, ("QA", "F-MAT-01"): False, ("ADMIN", "F-SHP-07"): True, ("ADMIN", "F-SHP-01"): False,
              ("ADMIN", "F-KPI-06"): True, ("PROD", "F-KPI-06"): False, ("ADMIN", "F-IFC-04"): True, ("PROD", "F-IFC-04"): False}
        wrong = [f"{r}×{f}" for (r, f), want in sc.items() if rbac.can_do(r, f) != want]
        R.row("G-C17", "범위(scopes) 4종 — 입고검사 · 승인 · 지표 · 재전송", "PASS" if not wrong else "FAIL", f"8 조합 · 어긋남 {wrong or 0} (호출 판정은 위 전수에 포함)")
    # ④ 응답 모양 · G-C03
    ok200n, n_ph, bad200 = placeholder_and_200()
    R.row("G-C03", "화면 51 + 공통 200 · placeholder 0", "PASS" if not bad200 else "FAIL", f"{tag}200 {ok200n} · placeholder {n_ph} · 문제 {bad200[:6] or 0}")
    sh = shapes(ctx)
    bad_sh = [f"{n}: {m}" for n, ok, m in sh if not ok]
    R.row("G-C03", "응답 모양 · 인증 없는 경로 · 503 (api-contract §2)", "PASS" if not bad_sh else "FAIL", f"{tag}검사 {len(sh)} · 통과 못한 {len(bad_sh)} {bad_sh[:4]}")
    # ⑤ 채널
    chb, chn = channels_check()
    R.row("G-C13", "채널 밖 화면 403 (core.yaml: channels)", "PASS" if not chb else "FAIL", f"{tag}호출 {chn} · 위반 {len(chb)} {chb[:5]}")
    # ③ 용어
    a = login("admin")
    detail = []
    if ctx.get("plot_no"):
        detail = [("TRC-01d", f"/trc/forward?no={ctx['lot1'].get('lot_no')}"), ("TRC-02d", f"/trc/backward?no={ctx['plot_no']}"),
                  ("POP-02d", "/pop/result?id=1"), ("MAT-02d", f"/mat/inspections?no={ctx['lot1'].get('lot_no')}")]
    if WRITE_MODE:
        pages = screen_html(a, detail)
        fh = forbidden_runtime(pages)
        R.row("G-C23", "화면 HTML 금지어 0 (DB · 시드 값 포함)", "PASS" if not fh else "FAIL", f"화면 {len(pages)} · 금지어 {sum(len(v) for v in CORE_YAML['forbidden_terms'].values())}개 · 노출 {len(fh)} {fh[:4]}")
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from check_terms import scan_core, scan_raw_terms_in_templates
            st_bad, n_files = scan_core()
            raw_tpl = scan_raw_terms_in_templates()
            R.row("G-C23", "코어 파일 금지어 0 (정적)", "PASS" if not st_bad else "FAIL", f"파일 {n_files} · 위반 {len(st_bad)} {st_bad[:3]}")
        except Exception as exc:  # noqa: BLE001
            raw_tpl = []
            R.row("G-C23", "코어 파일 금지어 0 (정적)", "미검증", f"check_terms 불러오기 실패 {type(exc).__name__}")
        raw, n_pages = raw_neutral_runtime(a, detail)
        R.row("G-C23", "날것 중립어 0 — 용어 표지 치환 후 화면 글 (t() 누락)", "PASS" if not raw else "FAIL",
              f"화면 {n_pages} · 표지 뒤에도 남은 곳 {len(raw)} {raw[:3]} · (정적 템플릿 스캔 {len(raw_tpl)})")
    else:
        raw, n, nk = pack_terms_runtime(a)
        bad = raw
        mbad = [f"{fid} `{','.join(unreplaced(m + ' ' + ' '.join(ls)))}` «{(m + ' ' + ' '.join(ls))[:50]}»" for fid, m, ls in MSGS if unreplaced(m + ' ' + ' '.join(ls))]
        R.row("G-P05", "팩 용어 — JSON 오류 message · fields.label 치환", "PASS" if not mbad else "FAIL", f"{tag}오류 응답 {len(MSGS)} · 치환 안 된 {len(mbad)} {mbad[:4]}")
        R.row("G-P05", "팩 용어 — 치환 안 된 terms 키 노출 0 (화면 글)", "PASS" if not bad else "FAIL", f"{tag}화면 {n} · 바뀌는 키 {nk} · 노출 {len(bad)} {bad[:4]}")
        pages = screen_html(a)
        fh = forbidden_runtime(pages)
        R.row("G-C23", "팩 배포 화면의 금지어 (참고 — 팩 용어는 허용)", "WARN" if fh else "PASS", f"{tag}{len(fh)} (팩 terms · 팩 화면이 내는 업종어는 정상)")
    # 출력
    w = max(len(i) for _, i, _, _ in R.rows)
    for g, item, stt, m in R.rows:
        print(f"{g}  {item:<{w}}  {stt}  {m}")
    print(f"(소요 {time.time() - t0:.0f}s · {'쓰기' if WRITE_MODE else '읽기 · 호출만'} · DB {DB_NAME}{' · ' + ' / '.join(R.notes) if R.notes else ''})")
    out = _arg("--json")
    if out:
        Path(out).write_text(json.dumps({
            "pack": PACK, "db": DB_NAME, "rows": R.rows, "notes": R.notes,
            "functions": {f.id: {"verdict": R.verdict(f.id), "checks": R.fn.get(f.id, []), "name": f.name, "owner": f.owner, "api": f.api} for f in targets},
            "cells": {f"{m}|{r}": {k: v for k, v in c.items()} for (m, r), c in cells.items()},
            "rbac_bad": mx["bad"], "shapes": sh, "channels_bad": chb,
            "terms": {"forbidden_runtime": fh, "raw": raw},
        }, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 1 if any(s == "FAIL" for _, _, s, _ in R.rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
