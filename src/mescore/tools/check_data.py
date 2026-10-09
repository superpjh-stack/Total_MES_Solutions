#!/usr/bin/env python
"""QA2 데이터 검사기 — G-C04(뷰 3 검산) · G-C05~G-C12 · G-C24 (`make check-data` · `gate.py` 가 부른다). 담당 QA2.

**고치지 않는다 — 재기만 한다.** 기대값은 개발 코드가 아니라 `goal.md` §2 · `contracts/db-schema.md` §2·§3 · `core.yaml` · `spec.md` §2.2 에서 온다.
집계 · 계보는 **이 파일이 따로 짠 SQL / 계산**으로 다시 구해 `lineage.trace_*` · `stats.*` · 뷰 3 과 대조한다(G-C07 · G-C10 · G-C04).

전용 DB (기본 `mes_qa2_db` · `--db` · `MES_QA2_DB`) 를 **매번 처음부터** 만든다 — 다른 사람이 쓰는 `mes_core_db` · 팩 DB 를 건드리지 않는다.
이름이 `mes_qa2` 로 시작하지 않는 DB 는 거부한다(스키마를 지우기 때문). `MES_PG_DSN` 은 이 도구가 그 DB 로 덮어쓴다.

  1. 스키마 52 + 뷰 3 → 공통 시드 `--core-only`(업무 테이블 0)              → G-C11 빈 화면 · G-C05 조회 전후 diff(빈 DB)
  2. `seed_core` 2회 (= `make db-seed` ×2)                                   → G-C09 행 수 diff 0 · (예시) 표기
  3. 코어 시나리오를 **API 로** 다시 만든다(입고 2 → 실적 2 → 합병 → 분할 3 → 검사 → 출하 · 승인) → G-C06 10행 · G-C07 · G-C08
  4. 임의 계보(분기 5단 · 깊이 20 분기 100 · 무작위 DAG) — 트랜잭션 안에서 만들고 되돌린다      → G-C07 (내 `with recursive` ↔ `lineage.trace_*`)
  5. 측정값 선언 3행(BAS API) → POP 폼 · 422 · 이탈 · collect(IFC API) · 선언 변경 즉시 반영     → G-C24
  6. 뷰 검산(부분 투입 · 취소 투입 · 반제품 투입) · 집계 재료(검사 · 불량 · 수주 · 설비 로그)      → G-C04 뷰 · G-C10 집계 재계산
     + 잔량 공격(회전 6): 종료 합병 옵션 · 열린 투입으로 잔량 0 인 LOT 재사용 · 동시 트랜잭션 · inherit_insp · 부분 분할   → G-C04 (gate 는 안 읽음)
  7. 정적 스캔(라우터 · 공용 모듈 쓰기 SQL) + 채워진 DB 에서 조회 화면 전부 전후 diff           → G-C05 · G-C08 채번 · G-C12

  uv run python src/mescore/tools/check_data.py                 # 코어 (gate 가 부르는 모양 · --run-seeds 는 받기만 — 시드는 늘 돈다)
  uv run python src/mescore/tools/check_data.py --pack printfilm  # 팩 시나리오 재검산(G-P04 대조) + write_scope 정적 스캔 — 같은 전용 DB 에 팩을 올린다
  uv run python src/mescore/tools/check_data.py --pack-readonly kimchi   # 팩 DB(mes_<팩>_db)를 읽기만 하고 같은 SQL 로 대조

출력: `G-nn  항목  PASS|FAIL|WARN|미검증  실측` (interfaces.md §10). 종료코드 0 = FAIL 없음. `-v` 는 내 SQL 원문도 찍는다.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import warnings
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "mescore"
PACKS = ROOT / "packs"
SCHEMA_SQL = SRC / "db" / "schema.sql"
VIEWS_SQL = SRC / "db" / "views.sql"
PGHOST = os.environ.get("PGHOST", "/tmp")
DEFAULT_DB = os.environ.get("MES_QA2_DB") or "mes_qa2_db"
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")

PASS, FAIL, WARN, UNVERIFIED = "PASS", "FAIL", "WARN", "미검증"
HTML = {"accept": "text/html"}
ROWS: list[tuple[str, str, str, str]] = []
VERBOSE = False


def emit(gid: str, item: str, status: str | bool, actual: str) -> None:
    st = status if isinstance(status, str) else (PASS if status else FAIL)
    item = re.sub(r"\s{2,}", " ", item)
    actual = re.sub(r"\s+", " ", str(actual))[:700]
    ROWS.append((gid, item, st, actual))
    print(f"{gid}  {item}  {st}  {actual}", flush=True)


def info(item: str, status: str, actual: str) -> None:
    """게이트 문장 밖의 관찰 — `참고` 로 시작해 gate.py 가 판정에 쓰지 않는다(보고서 결함 목록으로만)."""
    ROWS.append(("참고", item, status, actual))
    print(f"참고  {item}  {status}  {re.sub(chr(10), ' ', actual)[:600]}", flush=True)


def note(text: str) -> None:
    if VERBOSE:
        print(f"    · {text}", flush=True)


# ── 내 SQL (보고서에 원문 그대로 싣는다) ────────────────────────────────
#: 역방향 — 출발 LOT 의 조상 전부. 방문 집합(union)으로 중복 제거 · 최단 깊이는 min(d). 경로를 저장하지 않는다
SQL_UP = """
with recursive up (lot_id, d) as (
    select %(id)s::bigint, 0
    union
    select g.parent_lot_id, up.d + 1 from lot_genealogy g join up on g.child_lot_id = up.lot_id
)
select lot_id, min(d) as d from up group by lot_id"""
#: 정방향 — 자손 전부
SQL_DOWN = """
with recursive dn (lot_id, d) as (
    select %(id)s::bigint, 0
    union
    select g.child_lot_id, dn.d + 1 from lot_genealogy g join dn on g.parent_lot_id = dn.lot_id
)
select lot_id, min(d) as d from dn group by lot_id"""
#: 방문한 노드 집합에서 지나간 화살표 — 역방향은 자식이 집합 안, 정방향은 부모가 집합 안
SQL_EDGES_INTO = "select id, parent_lot_id, child_lot_id, relation, relation_base from lot_genealogy where child_lot_id = any(%(ids)s)"
SQL_EDGES_FROM = "select id, parent_lot_id, child_lot_id, relation, relation_base from lot_genealogy where parent_lot_id = any(%(ids)s)"

#: 뷰 3 을 db-schema.md §3.4 문장으로 다시 — 뷰를 읽지 않는다
SQL_MY_STOCK = """
select l.id, l.kind_base, l.qty,
       (select coalesce(sum(i.qty), 0) from pop_input i where i.material_lot_id = l.id and i.canceled_yn = 'N') as input_qty,
       (select coalesce(sum(g.qty), 0) from lot_genealogy g where g.parent_lot_id = l.id) as child_qty,
       (select coalesce(sum(i.qty), 0) from pop_input i join pop_work_result r on r.id = i.work_result_id
         where i.material_lot_id = l.id and i.canceled_yn = 'N' and r.ended_at is null) as open_input_qty,
       (select count(*) from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '출하') as n_ship_out,
       (select count(*) from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base in ('분할', '합병', '생산')) as n_whole,
       (select count(*) from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '투입') as n_input,
       (select count(*) from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '투입' and g.qty is null) as n_input_noqty
  from lot l"""
SQL_MY_WO = """
select w.id, w.status,
       count(r.id) as n, count(r.id) filter (where r.ended_at is null) as n_open,
       coalesce(sum(r.good_qty), 0) as good, coalesce(sum(r.defect_qty), 0) as defect
  from job_work_order w left join pop_work_result r on r.work_order_id = w.id
 group by w.id, w.status"""


# ── DB 준비 ────────────────────────────────────────────────────────────
def psql(db: str, *args: str) -> None:
    p = subprocess.run(["psql", "-q", "-h", PGHOST, "-d", db, "-v", "ON_ERROR_STOP=1", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"psql {' '.join(args)[:80]} → {p.returncode}: {p.stderr.strip()[:300]}")


def rebuild(db: str, pack: str | None) -> None:
    if not db.startswith("mes_qa2"):
        raise SystemExit(f"전용 DB 이름은 mes_qa2 로 시작해야 한다 — {db!r} 는 지우지 않는다")
    p = subprocess.run(["psql", "-h", PGHOST, "-d", "postgres", "-Atc", f"select 1 from pg_database where datname = '{db}'"], capture_output=True, text=True)
    if p.stdout.strip() != "1":
        subprocess.run(["createdb", "-h", PGHOST, db], check=True)
    for attempt in (1, 2):                                                       # 다른 연결이 막 끝나던 중이면 한 번 더
        psql(db, "-c", "set client_min_messages = warning; drop schema public cascade; create schema public;")
        try:
            psql(db, "-f", str(SCHEMA_SQL))
            break
        except RuntimeError:
            if attempt == 2:
                raise
            time.sleep(1)
    psql(db, "-f", str(VIEWS_SQL))
    if pack and (PACKS / pack / "schema_ext.sql").exists():
        psql(db, "-f", str(PACKS / pack / "schema_ext.sql"))


def child_env(db: str, pack: str | None) -> dict:
    env = dict(os.environ)
    env["MES_PG_DSN"] = f"postgresql:///{db}"
    env["MES_PACK"] = pack or ""
    return env


def run_seed(env: dict, *extra: str) -> tuple[int, str]:
    p = subprocess.run(["uv", "run", "python", "-m", "mescore.db.seed_core", *extra], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    return p.returncode, (p.stdout + p.stderr).strip()


def schema_tables() -> dict[str, str]:
    """schema.sql 의 `-- @table 이름 | 모듈 |` 표식 → {테이블: 모듈}."""
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^-- @table (\w+) \|\s*([^|]+)\|", SCHEMA_SQL.read_text(encoding="utf-8"), re.M)}


def spec_tables() -> set[str]:
    """spec.md §2.2 표 — 코어 테이블 이름 (G-C12 · 업종 테이블 0 의 기대값)."""
    text = (ROOT / "spec.md").read_text(encoding="utf-8")
    m = re.search(r"^### 2\.2.*?$(.*?)^### 2\.3", text, re.S | re.M)
    out: set[str] = set()
    for ln in (m.group(1) if m else "").splitlines():
        if ln.startswith("|") and "(" in ln.split("|")[1]:
            out |= set(re.findall(r"`([a-z_]+)`", ln.split("|")[2]))
    return out


# ── 앱 · API ───────────────────────────────────────────────────────────
class StepError(RuntimeError):
    pass


class Api:
    def __init__(self, app, login_id: str, password: str):
        from fastapi.testclient import TestClient
        self.login_id = login_id
        self.c = TestClient(app, raise_server_exceptions=False)
        r = self.c.post("/login", data={"login_id": login_id, "password": password})
        if r.status_code != 200:
            raise StepError(f"{login_id} 로그인 {r.status_code}")

    def post(self, path: str, data: dict | None = None, status: int = 200, **kw) -> dict:
        r = self.c.post(path, data=data or {}, **kw)
        if r.status_code != status:
            raise StepError(f"{self.login_id} POST {path} → {r.status_code} (기대 {status}) {r.text[:220]}")
        try:
            return r.json()
        except ValueError:
            return {"_text": r.text}

    def get(self, path: str, params: dict | None = None, status: int | None = 200, html: bool = False):
        r = self.c.get(path, params=params, headers=HTML if html else None)
        if status is not None and r.status_code != status:
            raise StepError(f"{self.login_id} GET {path} {params or ''} → {r.status_code} (기대 {status}) {r.text[:200]}")
        return r


def main_text(html: str) -> str:
    m = re.search(r"<main.*?</main>", html, re.S)
    body = m.group(0) if m else html
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S)
    return body


def plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main_text(html)))


def dnum(v) -> float | None:
    return None if v is None else float(v)


def close(a, b, tol: float = 1e-6) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)), abs(float(b)))


# ════════════════════════════════════════════════════════════════════════
# 코어
# ════════════════════════════════════════════════════════════════════════
class Core:
    def __init__(self, db: str):
        self.db = db
        self.env = child_env(db, None)
        self.ctx: dict[str, Any] = {}

    # ── 0. 준비 ─────────────────────────────────────────────────────────
    def boot(self) -> bool:
        t0 = time.time()
        try:
            rebuild(self.db, None)
        except Exception as exc:  # noqa: BLE001 — 준비 실패는 전 게이트 FAIL 로 드러낸다
            for g in ("G-C04", "G-C05", "G-C06", "G-C07", "G-C08", "G-C09", "G-C10", "G-C11", "G-C12", "G-C24"):
                emit(g, "QA2 전용 DB 준비", FAIL, f"{self.db} 스키마 재생성 실패 — {exc}")
            return False
        rc, out = run_seed(self.env, "--core-only")
        if rc != 0:
            for g in ("G-C05", "G-C06", "G-C07", "G-C08", "G-C09", "G-C10", "G-C11", "G-C12", "G-C24"):
                emit(g, "QA2 전용 DB 준비", FAIL, f"공통 시드 --core-only rc={rc} — {out[-200:]}")
            return False
        os.environ.update({"MES_PG_DSN": self.env["MES_PG_DSN"], "MES_PACK": ""})
        from mescore.app import settings as _s
        _s.reset_cache()
        from mescore.app.main import app
        from mescore.db import conn
        self.app, self.conn = app, conn
        self.pw = _s.get_settings().seed_password or ""
        self.tables = schema_tables()
        self.biz = sorted(t for t, m in self.tables.items() if m not in ("sys", "ifc"))
        note(f"DB {self.db} 준비 {time.time() - t0:.1f}s · 코어 테이블 {len(self.tables)} · 업무 테이블 {len(self.biz)}")
        return True

    def api(self, login_id: str) -> Api:
        return Api(self.app, login_id, self.pw)

    def biz_state(self) -> dict[str, tuple[int, str]]:
        out = {}
        for t in self.biz:
            r = self.conn.q1(f"select count(*) as n, coalesce(max(coalesce(updated_at, created_at))::text, '') as m from {t}")
            out[t] = (r["n"], r["m"])
        return out

    # ── G-C11 빈 화면 (업무 테이블 0) ──────────────────────────────────
    def empty_screens(self) -> None:
        from mescore.app import nav
        a = self.api("admin")
        primary = ("rows", "lots", "items", "work_orders", "logs", "orders", "plans", "backups", "migrations")
        bad_status, bare_tbody, no_word, undecided_bare, n_screens = [], [], [], [], 0
        for s in nav.ALL:
            if s.screen_id in ("CMN-01", "CMN-03"):
                continue
            url = s.probe or s.path
            n_screens += 1
            j = a.get(url, status=None)
            h = a.get(url, status=None, html=True)
            if j.status_code != 200 or h.status_code != 200:
                bad_status.append(f"{s.screen_id}:{j.status_code}/{h.status_code}")
                continue
            body = j.json() if j.headers.get("content-type", "").startswith("application/json") else {}
            mh = main_text(h.text)
            for tb in re.findall(r"<tbody[^>]*>(.*?)</tbody>", mh, re.S):
                if "<tr" not in tb:
                    bare_tbody.append(s.screen_id)
                    break
            empty = [k for k in primary if isinstance(body.get(k), list) and not body.get(k)]
            if empty and "미수집" not in mh and "미확정" not in mh:
                no_word.append(f"{s.screen_id}:{','.join(empty)}")
            txt = plain(re.sub(r"<select.*?</select>", " ", h.text, flags=re.S))      # 상태 선택지의 '미확정' 은 값이 아니다
            for m in re.finditer(r"미확정(?!\s*[\(（]\s*D-\d)(?!\s*\d)", txt):
                undecided_bare.append(f"{s.screen_id}:「{txt[max(0, m.start() - 6):m.end() + 12].strip()}」")
                break
        # 값 칸 표본 — 집계 · 현황판 · 수집값 · 대시보드: 값이 없으면 `미수집`
        eq = self.conn.q1("select id from bas_equipment order by id limit 1")
        probes = [("KPI-02", {"kind": k}) for k in ("production", "quality", "delivery", "equipment")]
        probes += [("KPI-01", {}), ("CMN-04", {}), ("EQP-01", {}), ("IFC-01", {})]
        if eq:
            probes.append(("EQP-04", {"equipment_id": eq["id"]}))
        miss_val = []
        for sid, params in probes:
            r = a.get(nav.by_id(sid).probe or nav.path_of(sid), params=params, status=None, html=True)
            if r.status_code != 200 or "미수집" not in main_text(r.text):
                miss_val.append(f"{sid}{params or ''}:{r.status_code}")
        ok = not (bad_status or bare_tbody or no_word or miss_val)
        emit("G-C11", "빈 DB 화면 — 미수집 표시", ok,
             f"업무 테이블 0 인 DB 에서 화면 {n_screens}(코어 51 + 공통) 열기 — 200 아님 {bad_status or 0} · 행 없는 <tbody> {bare_tbody or 0} · "
             f"주 목록이 빈데 미수집/미확정 글자 없음 {no_word or 0} · 값 칸 표본 {len(probes)} 중 미수집 없음 {miss_val or 0}")
        emit("G-C11", "미확정 표기 — (D-nn) 동반", not undecided_bare,
             f"화면 본문의 `미확정` 중 `(D-nn)` 이 바로 붙지 않은 곳 {undecided_bare or 0} (goal.md G-C11: 미정이면 `미확정 (D-nn)`)")

    # ── G-C09 시드 멱등 ────────────────────────────────────────────────
    def seed_twice(self) -> None:
        rc1, out1 = run_seed(self.env)
        a = self.conn.table_counts()
        rc2, out2 = run_seed(self.env)
        b = self.conn.table_counts()
        diff = {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
        emit("G-C09", "시드 2회 행 수 diff 0", rc1 == 0 and rc2 == 0 and not diff,
             f"make db-seed(seed_core) ×2 rc={rc1}/{rc2} · 테이블 {len(b)} · 행 {sum(b.values())} · 달라진 테이블 {diff or 0}" + ("" if rc1 == 0 else f" · {out1[-150:]}"))
        names = [("bas_item", "item_name", "item_code"), ("bas_process", "process_name", "process_code"), ("bas_equipment", "equip_name", "equip_code"),
                 ("bas_partner", "partner_name", "partner_code"), ("bas_worker", "worker_name", "worker_code"), ("bas_defect_code", "defect_name", "defect_code"),
                 ("bas_process_param", "label", "param_key"), ("qua_insp_plan", "label", "item_key"), ("kpi_indicator", "name", "indicator_key")]
        unmarked, checked = [], 0
        cols = {(r["table_name"], r["column_name"]) for r in self.conn.q("select table_name, column_name from information_schema.columns where table_schema = 'public'")}
        for tbl, name_col, code_col in names:
            if (tbl, name_col) not in cols:
                unmarked.append(f"{tbl}.{name_col}: 컬럼 없음")
                continue
            for r in self.conn.q(f"select {code_col} as code, {name_col} as name from {tbl} where created_by like 'seed%%'"):
                checked += 1
                if "(예시)" not in (r["name"] or ""):
                    unmarked.append(f"{tbl}:{r['code']}「{r['name']}」")
        nos = [("lot", "lot_no"), ("ord_order", "order_no"), ("ord_plan", "plan_no"), ("mat_receipt", "receipt_no"), ("job_work_order", "work_order_no"),
               ("shp_shipment", "shipment_no")]
        no_ex = []
        for tbl, col in nos:
            if (tbl, col) not in cols:
                continue
            for r in self.conn.q(f"select {col} as no from {tbl} where created_by like 'seed%%'"):
                checked += 1
                if "EX" not in (r["no"] or ""):
                    no_ex.append(f"{tbl}:{r['no']}")
        emit("G-C09", "시드 값 (예시) 표기", not unmarked and not no_ex,
             f"시드 행 {checked} 검사 — 이름에 (예시) 없음 {unmarked[:8] or 0}{' 외 ' + str(len(unmarked) - 8) if len(unmarked) > 8 else ''} · 번호에 EX 없음 {no_ex[:6] or 0}")

    # ── 기준정보 (BAS API) ─────────────────────────────────────────────
    def masters(self) -> None:
        a = self.api("admin")
        from mescore.app import nav
        P = {s: nav.path_of(s) for s in ("BAS-03", "BAS-04", "BAS-05")}
        c = self.ctx
        c["item_prd"] = self.conn.q1("select id from bas_item where item_code = 'PRD-EX-01'")["id"]
        c["item_raw1"] = self.conn.q1("select id from bas_item where item_code = 'RAW-EX-01'")["id"]
        c["item_raw2"] = self.conn.q1("select id from bas_item where item_code = 'RAW-EX-02'")["id"]
        c["sup"] = self.conn.q1("select id from bas_partner where partner_code = 'SUP-EX-01'")["id"]
        c["defect"] = self.conn.q1("select id from bas_defect_code order by id limit 1")["id"]
        c["proc"] = a.post(P["BAS-03"], {"process_code": "PRC-QA2-01", "process_name": "QA2 시나리오 공정 (예시)", "seq": "91"})["id"]
        c["eq"] = a.post(P["BAS-05"], {"equip_code": "EQ-QA2-01", "equip_name": "QA2 설비 (예시)", "process_id": c["proc"], "collect_yn": "N"})["id"]
        c["param_len"] = a.post(P["BAS-04"], {"param_key": "qa2_len", "process_id": c["proc"], "label": "QA2 길이 (예시)", "unit": "m",
                                              "value_type": "number", "min_value": "0", "max_value": "100", "required_yn": "N", "seq": "1"})["id"]

    # ── G-C06 코어 시나리오 (API) ──────────────────────────────────────
    def scenario(self) -> bool:
        from mescore.app import nav
        c = self.ctx
        prod, qa, admin = self.api("prod"), self.api("qa"), self.api("admin")
        P = {s: nav.path_of(s) for s in ("MAT-01", "MAT-02", "POP-02", "POP-03", "JOB-01", "ORD-01", "ORD-04", "QUA-02", "SHP-01", "SHP-02")}
        today = date.today()
        try:
            o = prod.post(P["ORD-01"], {"partner_code": "CUST-EX-01", "order_date": str(today), "due_date": str(today + timedelta(days=3)),
                                         "item_code": ["PRD-EX-01"], "qty": ["100"], "unit": ["EA"]})
            c["order"] = o
            pl = prod.post(P["ORD-04"], {"order_no": o["order_no"], "line_no": "1", "plan_date": str(today), "plan_qty": "100"})
            prod.post(f"{P['ORD-04']}/{pl['id']}/confirm")
            dtl = self.conn.q1("select d.id from ord_order_dtl d join ord_order o on o.id = d.order_id where o.order_no = %s and d.line_no = 1", (o["order_no"],))
            wo = prod.post(P["JOB-01"], {"item_id": c["item_prd"], "process_id": c["proc"], "equipment_id": c["eq"], "plan_qty": "100",
                                          "plan_date": str(today), "plan_id": pl["id"], "order_dtl_id": dtl["id"]})
            c["wo"] = wo
            m1 = prod.post(P["MAT-01"], {"item_id": c["item_raw1"], "qty": "100", "partner_id": c["sup"], "unit": "kg"})
            m2 = prod.post(P["MAT-01"], {"item_id": c["item_raw2"], "qty": "100", "partner_id": c["sup"], "unit": "kg"})
            for m in (m1, m2):
                qa.post(P["MAT-02"], {"lot_no": m["lot_no"], "judgement": "합격"})

            def run(inputs: list[tuple[str, str]], good: str, length: str) -> dict:
                s = prod.post(f"{P['POP-02']}/start", {"work_order_id": wo["id"]})
                for no, q in inputs:
                    prod.post(P["POP-03"], {"work_result_id": s["id"], "barcode": no, "qty": q})
                e = prod.post(f"{P['POP-02']}/{s['id']}/end", {"good_qty": good, "defect_qty": "1", "m_qa2_len": length})
                return {**e, "result_id": s["id"]}

            p1 = run([(m1["lot_no"], "50")], "50", "12.5")
            p2 = run([(m1["lot_no"], "50"), (m2["lot_no"], "50")], "50", "130")        # 130 > 상한 100 → 이탈 저장
            mg = prod.post(f"{P['POP-02']}/{p2['result_id']}/merge", {"lot_ids": f"{p1['lot_no']},{p2['lot_no']}"})
            sp = prod.post(f"{P['POP-02']}/{p2['result_id']}/split", {"lot_id": mg["id"], "count": "3", "qtys": "30,30,40"})
            s1, s2, s3 = sp["lots"]
            for s in (s1, s2):
                ins = qa.post(P["QUA-02"], {"insp_type": "최종", "lot_no": s["lot_no"]})
                qa.post(f"{P['QUA-02']}/{ins['id']}/judge", {"judgement": "합격"})
            sh = prod.post(P["SHP-01"], {"partner_code": "CUST-EX-01", "ship_date": str(today), "order_no": o["order_no"]})
            for s in (s1, s2):
                prod.post(P["SHP-02"], {"shipment_no": sh["shipment_no"], "barcode": s["lot_no"]})
            admin.post(f"{P['SHP-01']}/{sh['id']}/approve")
            x = self.conn.q1("select id, lot_no from lot where shipment_id = %s and kind_base = 'SHIPMENT'", (sh["id"],))
            if x is None:
                raise StepError("승인된 출하에 출하 LOT 이 없다")
            c.update(m1=m1, m2=m2, p1=p1, p2=p2, mg=mg, s1=s1, s2=s2, s3=s3, ship=sh, x=x, plan=pl)
            return True
        except StepError as exc:
            emit("G-C06", "코어 시나리오 API 재현", FAIL, f"단계 실패 — {exc}")
            return False

    def lineage_rows(self) -> None:
        c = self.ctx
        ids = [c["m1"]["lot_id"], c["m2"]["lot_id"], c["p1"]["lot_id"], c["p2"]["lot_id"], c["mg"]["id"], c["s1"]["id"], c["s2"]["id"], c["s3"]["id"], c["x"]["id"]]
        c["ids"] = ids
        rows = self.conn.q("select parent_lot_id, child_lot_id, relation, relation_base from lot_genealogy where parent_lot_id = any(%(i)s) or child_lot_id = any(%(i)s)", {"i": ids})
        rel = Counter(r["relation"] for r in rows)
        expect = [(c["m1"]["lot_id"], c["p1"]["lot_id"], "투입"), (c["m1"]["lot_id"], c["p2"]["lot_id"], "투입"), (c["m2"]["lot_id"], c["p2"]["lot_id"], "투입"),
                  (c["p1"]["lot_id"], c["mg"]["id"], "합병"), (c["p2"]["lot_id"], c["mg"]["id"], "합병"),
                  (c["mg"]["id"], c["s1"]["id"], "분할"), (c["mg"]["id"], c["s2"]["id"], "분할"), (c["mg"]["id"], c["s3"]["id"], "분할"),
                  (c["s1"]["id"], c["x"]["id"], "출하"), (c["s2"]["id"], c["x"]["id"], "출하")]
        got = {(r["parent_lot_id"], r["child_lot_id"], r["relation"]) for r in rows}
        missing, extra = [e for e in expect if e not in got], [g for g in got if g not in set(expect)]
        ok = len(rows) == 10 and dict(rel) == {"투입": 3, "합병": 2, "분할": 3, "출하": 2} and not missing and not extra
        emit("G-C06", "코어 시나리오 lot_genealogy 10행 (API)", ok,
             f"API 22회(수주 · 계획 확정 · 지시 · 입고 2 · 입고검사 2 · 시작/투입/종료 ×2 · 합병 · 분할 · 최종검사 2 · 출하 · 스캔 2 · 승인) → "
             f"행 {len(rows)} · relation {dict(rel)} · db-schema.md §3.3 표와 다른 화살표 빠짐 {missing or 0} 더함 {extra or 0}")
        base_ok = all(r["relation"] == r["relation_base"] for r in rows)
        emit("G-C06", "relation_base 저장", base_ok, f"코어 relation 5종은 relation = relation_base — 다른 행 {[r for r in rows if r['relation'] != r['relation_base']] or 0}")

    # ── G-C07 추적 ─────────────────────────────────────────────────────
    def my_trace(self, lot_id: int, direction: str, cur=None) -> tuple[dict[int, int], set[int]]:
        q = (lambda s, p: (cur.execute(s, p), [dict(r) for r in cur.fetchall()])[1]) if cur is not None else self.conn.q
        nodes = {r["lot_id"]: r["d"] for r in q(SQL_UP if direction == "backward" else SQL_DOWN, {"id": lot_id})}
        edges = q(SQL_EDGES_INTO if direction == "backward" else SQL_EDGES_FROM, {"ids": list(nodes)})
        return nodes, {e["id"] for e in edges}

    def compare_trace(self, lot_id: int, direction: str, cur=None) -> list[str]:
        from mescore.app import lineage
        tr = (lineage.trace_backward if direction == "backward" else lineage.trace_forward)(lot_id, cur)
        nodes, edges = self.my_trace(lot_id, direction, cur)
        lin_nodes = {n.id for n in tr.nodes()}
        lin_edges = [e.genealogy_id for e in tr.edges]
        errs = []
        if lin_nodes != set(nodes):
            errs.append(f"{direction}({lot_id}) 노드 lineage−내 {sorted(lin_nodes - set(nodes))[:5]} 내−lineage {sorted(set(nodes) - lin_nodes)[:5]}")
        if set(lin_edges) != edges or len(lin_edges) != len(set(lin_edges)):
            errs.append(f"{direction}({lot_id}) 화살표 lineage {len(lin_edges)}(중복 {len(lin_edges) - len(set(lin_edges))}) ≠ 내 {len(edges)}")
        for e in tr.edges:
            near = e.child.id if direction == "backward" else e.parent.id
            if near in nodes and e.depth != nodes[near] + 1:
                errs.append(f"{direction}({lot_id}) 화살표 {e.genealogy_id} depth {e.depth} ≠ 최단 {nodes[near] + 1}")
                break
        return errs

    def trace_core(self) -> None:
        from mescore.app import lineage, nav
        c = self.ctx
        x, m1, m2, s3 = c["x"]["id"], c["m1"]["lot_id"], c["m2"]["lot_id"], c["s3"]["id"]
        bw, fw = lineage.trace_backward(x), lineage.trace_forward(m1)
        my_up, my_up_e = self.my_trace(x, "backward")
        my_dn, my_dn_e = self.my_trace(m1, "forward")
        kinds = {r["id"]: r for r in self.conn.q("select id, kind_base from lot where id = any(%s)", (list(set(my_up) | set(my_dn)),))}
        my_mats = {i for i in my_up if kinds[i]["kind_base"] == "MATERIAL"}
        states = {r["lot_id"]: r["state"] for r in self.conn.q("select lot_id, state from v_lot_state where lot_id = any(%s)", (c["ids"],))}
        ok_b = {n.id for n in bw.materials()} == {m1, m2} == my_mats and len(bw.edges) == 9 == len(my_up_e)
        emit("G-C07", "역방향 — 출하 LOT → 원재료 ①②", ok_b,
             f"lineage.trace_backward 원재료 {sorted(n.no for n in bw.materials())} · 화살표 {len(bw.edges)} / 내 with recursive 원재료 {len(my_mats)} · 화살표 {len(my_up_e)} (기대 2 · 9)")
        stock = [n.id for n in fw.stock()]
        path_ok = ({c["p1"]["lot_id"], c["p2"]["lot_id"], c["mg"]["id"], c["s1"]["id"], c["s2"]["id"], s3, x} <= {n.id for n in fw.nodes()}
                   and stock == [s3] and states.get(s3) == "재고" and m2 not in {n.id for n in fw.nodes()})
        ok_f = path_ok and len(fw.edges) == 9 == len(my_dn_e) and {n.id for n in fw.nodes()} == set(my_dn)
        emit("G-C07", "정방향 — 원재료① → 생산①② → 합병 → 분할①②③ → 출하 · ③ 재고", ok_f,
             f"lineage.trace_forward 노드 {len(fw.nodes())} · 화살표 {len(fw.edges)} · 재고 {[n.no for n in fw.stock()]} / 내 SQL 노드 {len(my_dn)} · 화살표 {len(my_dn_e)} · "
             f"v_lot_state 분할③ {states.get(s3)} · 분할① {states.get(c['s1']['id'])} · 합병 {states.get(c['mg']['id'])} · 원재료① {states.get(m1)} · 원재료② {states.get(m2)}")
        errs = []
        for lid in c["ids"]:
            errs += self.compare_trace(lid, "backward") + self.compare_trace(lid, "forward")
        a = self.api("admin")
        api_errs = []
        for sid, lid, direction in (("TRC-02", x, "backward"), ("TRC-01", m1, "forward"), ("TRC-01", s3, "forward")):
            no = self.conn.q1("select lot_no from lot where id = %s", (lid,))["lot_no"]
            j = a.get(nav.path_of(sid), params={"no": no}).json()
            nodes, edges = self.my_trace(lid, direction)
            api_edges = {e["genealogy_id"] for st in j.get("stages", []) for e in st.get("edges", [])}
            if api_edges != edges or j.get("edge_count") != len(edges):
                api_errs.append(f"{sid}?no={no} 화살표 {sorted(api_edges)[:4]}… {j.get('edge_count')} ≠ 내 {len(edges)}")
        bad = a.get(nav.path_of("TRC-02"), params={"no": "QA2-NO-SUCH-LOT"}, status=None)
        emit("G-C07", "내 with recursive = lineage.trace_* (시나리오 LOT 9 × 2방향 · API 3)", not errs and not api_errs and bad.status_code == 422,
             f"노드 · 화살표 · 최단 깊이 불일치 {errs or 0} · TRC API(JSON) 불일치 {api_errs or 0} · 없는 번호 {bad.status_code}(기대 422)")
        gen_cols = [r["column_name"] for r in self.conn.q("select column_name from information_schema.columns where table_name = 'lot_genealogy'")]
        path_cols = [cname for cname in gen_cols if re.search(r"path|root|level|depth|ancestor", cname)]
        cache = [t for t in self.tables if re.search(r"trace|path|closure|ancestor", t)]
        emit("G-C07", "경로 저장 0", not path_cols and not cache, f"lot_genealogy 컬럼 {len(gen_cols)} 중 경로성 {path_cols or 0} · 경로/클로저 테이블 {cache or 0}")

    def trace_random(self) -> None:
        """임의 분기 5단 · 무작위 DAG · 깊이 20 분기 100 — 한 트랜잭션에서 만들고 되돌린다(lot_genealogy 는 lineage.link/split/merge 만)."""
        from mescore.app import lineage
        rng = random.Random(20261009)
        BY = "qa2"
        c = self.ctx

        class Rollback(Exception):
            pass

        res: dict[str, Any] = {}
        try:
            with self.conn.tx() as cur:
                def raw(qty: float = 1000.0) -> int:
                    cur.execute("""insert into lot (lot_no, kind, kind_base, item_id, qty, unit, insp_status, created_by)
                                   values (%s, 'PRODUCT', 'PRODUCT', %s, %s, 'EA', '합격', 'qa2') returning id""",
                                (f"QA2-R-{rng.getrandbits(48):012X}", c["item_prd"], qty))
                    return cur.fetchone()["id"]

                # (a) 분기 5단 — 각 단에서 분할 2~3 · 1:1 생산 · 합병 2 를 섞고, 앞 단 노드로 건너뛰는 화살표(길이가 다른 경로)도 넣는다
                root = lineage.make_material_lot(cur, item_id=c["item_raw1"], qty=100000, unit="kg", by=BY, insp_status="합격")["id"]
                level = [raw()]
                lineage.link(cur, root, level[0], lineage.INPUT, by=BY, qty=1)
                all_nodes = [root, level[0]]
                for depth in range(5):
                    nxt: list[int] = []
                    for lid in level:
                        op = rng.choice(("split", "produce", "keep"))
                        if op == "split":
                            nxt += [k["id"] for k in lineage.split(cur, parent_id=lid, count=rng.choice((2, 3)), by=BY)]
                        elif op == "produce":
                            ch = raw()
                            lineage.link(cur, lid, ch, lineage.PRODUCE, by=BY, qty=1)
                            nxt.append(ch)
                        else:
                            nxt.append(lid)
                    stock = [i for i in nxt if lineage.node(i, cur).state == "재고"]
                    if len(stock) >= 2:
                        a_, b_ = rng.sample(stock, 2)
                        mg = lineage.merge(cur, parent_ids=[a_, b_], by=BY)["id"]
                        nxt = [i for i in nxt if i not in (a_, b_)] + [mg]
                    if depth >= 2:                                       # 건너뛰기 — 2단 위 노드가 이 단 노드의 부모로 하나 더
                        ch = rng.choice(nxt)
                        anc = rng.choice(all_nodes[1:])
                        if anc != ch and not self.my_trace(ch, "forward", cur)[0].get(anc):
                            lineage.link(cur, anc, ch, lineage.PRODUCE, by=BY, qty=1)
                    all_nodes += [i for i in nxt if i not in all_nodes]
                    level = list(dict.fromkeys(nxt))
                errs = []
                for lid in all_nodes:
                    errs += self.compare_trace(lid, "forward", cur) + self.compare_trace(lid, "backward", cur)
                fw = lineage.trace_forward(root, cur)
                leaves = [n.id for n in fw.stock()]
                leaf_errs = [lf for lf in leaves if [n.id for n in lineage.trace_backward(lf, cur).materials()] != [root]]
                res["branch"] = (len(all_nodes), len(fw.edges), max((e.depth for e in fw.edges), default=0), len(leaves), errs, leaf_errs)

                # (b) 무작위 DAG — 노드 300 · 화살표 ~600 (부모는 늘 앞 번호 → 순환 없음)
                ids = [raw() for _ in range(300)]
                n_link = 0
                for i in range(1, len(ids)):
                    for p in rng.sample(range(i), k=min(i, rng.choice((1, 1, 2, 3)))):
                        lineage.link(cur, ids[p], ids[i], lineage.PRODUCE, by=BY, qty=1)
                        n_link += 1
                errs2 = []
                for lid in rng.sample(ids, 40):
                    errs2 += self.compare_trace(lid, "forward", cur) + self.compare_trace(lid, "backward", cur)
                # 순환 · 자기 참조 거부 (DB 트리거 · CHECK 또는 lineage 422)
                cyc = []
                for p_, ch_ in ((ids[-1], ids[0]), (ids[5], ids[5])):
                    cur.execute("savepoint qa2_cyc")
                    try:
                        lineage.link(cur, p_, ch_, lineage.PRODUCE, by=BY)
                        cyc.append(f"{p_}->{ch_} 받아들임")
                    except Exception:  # noqa: BLE001 — 거부가 기대값
                        pass
                    cur.execute("rollback to savepoint qa2_cyc")
                res["dag"] = (len(ids), n_link, errs2, cyc)

                # (c) 깊이 20 · 분기 100 — LOT 2,001 · 화살표 2,000
                top = raw(100000)
                heads = [k["id"] for k in lineage.split(cur, parent_id=top, count=100, by=BY)]
                for h in heads:
                    prev = h
                    for _ in range(19):
                        ch = raw()
                        lineage.link(cur, prev, ch, lineage.PRODUCE, by=BY, qty=1)
                        prev = ch
                t0 = time.perf_counter()
                fwd = lineage.trace_forward(top, cur)
                t_fw = time.perf_counter() - t0
                leaf = fwd.edges[-1].child.id
                t0 = time.perf_counter()
                bwd = lineage.trace_backward(leaf, cur)
                t_bw = time.perf_counter() - t0
                t0 = time.perf_counter()
                my_n, my_e = self.my_trace(top, "forward", cur)
                t_my = time.perf_counter() - t0
                res["deep"] = (len(fwd.edges), max(e.depth for e in fwd.edges), len(bwd.edges), t_fw, t_bw, len(my_e), max(my_n.values()), t_my,
                               {n.id for n in fwd.nodes()} == set(my_n))
                raise Rollback
        except Rollback:
            pass
        except Exception as exc:  # noqa: BLE001 — 생성 중 예외는 그 자체로 결함
            emit("G-C07", "임의 계보 생성", FAIL, f"{type(exc).__name__}: {str(exc)[:200]}")
            return
        n, ne, md, nl, errs, leaf_errs = res["branch"]
        emit("G-C07", "임의 분기 5단 (분할 · 합병 · 생산 · 건너뛰기)", not errs and not leaf_errs and md >= 5,
             f"노드 {n} · 정방향 화살표 {ne} · 최대 깊이 {md} · 재고 잎 {nl} — 노드 {n} × 2방향 내 SQL 대조 불일치 {errs[:3] or 0} · 잎→원재료 1 아님 {leaf_errs[:3] or 0}")
        nn, nlk, errs2, cyc = res["dag"]
        emit("G-C07", "무작위 DAG 300 노드 대조 · 순환 거부", not errs2 and not cyc,
             f"노드 {nn} · 화살표 {nlk} · 표본 40 × 2방향 불일치 {errs2[:3] or 0} · 순환 · 자기참조 받아들임 {cyc or 0}")
        e, d, eb, tf, tb, my_e, my_d, tmy, same = res["deep"]
        emit("G-C07", "깊이 20 · 분기 100 · 2초", e == 2000 and d == 20 and eb == 20 and tf < 2 and tb < 2 and same and my_e == 2000,
             f"lineage 정방향 화살표 {e} · 깊이 {d} · {tf:.3f}s / 역방향 화살표 {eb} · {tb:.3f}s / 내 SQL 화살표 {my_e} · 깊이 {my_d} · {tmy:.3f}s · 노드 집합 같음 {same}")

    # ── G-C08 키 연결 · 채번 ──────────────────────────────────────────
    def key_links(self) -> None:
        from mescore.app import lineage, nav
        c = self.ctx
        a = self.api("admin")
        s1 = c["s1"]
        node = lineage.resolve(s1["lot_no"])
        mine = {}
        lot = self.conn.q1("select * from lot where id = %s", (s1["id"],))
        anc, _ = self.my_trace(s1["id"], "backward")
        mine["wo"] = self.conn.q1("select id, work_order_no from job_work_order where id = %s", (lot["work_order_id"],))
        mine["results"] = {r["id"] for r in self.conn.q("select id from pop_work_result where work_order_id = %s", (lot["work_order_id"],))} if lot["work_order_id"] else set()
        mine["measures"] = {(r["work_result_id"], r["param_key"]) for r in self.conn.q("select work_result_id, param_key from pop_measure where work_result_id = any(%s)", (list(mine["results"]),))}
        mine["insp"] = {r["id"] for r in self.conn.q("select id from qua_inspection where lot_id = %s", (s1["id"],))}
        mine["insp_anc"] = {r["id"] for r in self.conn.q("select id from qua_inspection where lot_id = any(%s)", (list(anc),))}
        down, _ = self.my_trace(s1["id"], "forward")
        mine["ship"] = {r["shipment_id"] for r in self.conn.q("select shipment_id from lot where id = any(%s) and kind_base = 'SHIPMENT'", (list(down),))}
        found = bool(mine["wo"] and mine["results"] and mine["measures"] and mine["insp"] and mine["ship"])
        # API — LOT 번호 하나로 (TRC-02 링크를 따라간다)
        api_err = []
        j = a.get(nav.path_of("TRC-02"), params={"no": s1["lot_no"]}).json()
        links = j.get("start_links") or {}
        wo_link = links.get("work_order")
        api_results: set[int] = set()
        if not wo_link:
            api_err.append("TRC-02 start_links 에 work_order 없음")
        else:
            path, _, qs = wo_link.partition("?")
            r = a.get(path + "?" + qs, status=None)
            if r.status_code != 200:
                api_err.append(f"지시 링크 {wo_link} → {r.status_code}")
            else:
                api_results = {x["id"] for x in r.json().get("results", [])}
                if api_results != mine["results"]:
                    api_err.append(f"지시 링크 실적 {sorted(api_results)} ≠ 내 {sorted(mine['results'])}")
        api_meas = set()
        for rid in sorted(mine["results"]):
            pj = a.get(nav.path_of("POP-02"), params={"id": rid}).json()
            for k, v in (pj.get("values") or pj.get("measures") or {}).items():
                api_meas.add((rid, k))
        if api_meas != mine["measures"]:
            api_err.append(f"POP-02?id= 측정값 {sorted(api_meas)[:4]} ≠ 내 {sorted(mine['measures'])[:4]}")
        insp_link = links.get("inspection")
        if insp_link:
            path, _, qs = insp_link.partition("?")
            qj = a.get(path + "?" + qs).json()
            api_insp = {h["id"] for h in (qj.get("history") or [])}
            if not mine["insp"] <= api_insp:
                api_err.append(f"검사 링크 이력 {sorted(api_insp)} ⊉ 내 {sorted(mine['insp'])}")
        else:
            api_err.append("TRC-02 start_links 에 inspection 없음")
        xno = c["x"]["lot_no"]
        xj = a.get(nav.path_of("TRC-02"), params={"no": xno}).json()
        sl = (xj.get("start_links") or {}).get("shipment")
        if not sl:
            api_err.append("출하 LOT 의 shipment 링크 없음")
        else:
            path, _, qs = sl.partition("?")
            r = a.get(path + "?" + qs, status=None)
            if r.status_code != 200 or s1["lot_no"] not in r.text:
                api_err.append(f"출하 링크 {sl} → {r.status_code} · 분할① 번호 {'있음' if s1['lot_no'] in r.text else '없음'}")
        emit("G-C08", "LOT 번호 → 지시 · 실적 · 측정값 · 검사 · 출하 (내 SQL)", found and node is not None and node.work_order_no == mine["wo"]["work_order_no"],
             f"분할① {s1['lot_no']} → 지시 {mine['wo'] and mine['wo']['work_order_no']} · 실적 {len(mine['results'])} · 측정값 {len(mine['measures'])} · "
             f"검사(자기 {len(mine['insp'])} · 조상 포함 {len(mine['insp_anc'])}) · 출하 {len(mine['ship'])} · lineage.resolve 지시 {node and node.work_order_no}")
        emit("G-C08", "LOT 번호 → 화면 링크 따라가기 (API)", not api_err,
             f"TRC-02 start_links {sorted(links)} → 지시 · POP-02 측정값 · QUA-02 검사 · SHP-02 출하 — 불일치 {api_err or 0}")

        # 채번 — sys_number_seq 를 쓰는 곳은 numbering.py 뿐 · 이번 실행에서 나온 번호 = sys_number_rule 형식 · 일련번호 최대 = 카운터
        writers = []
        for f in sorted(SRC.rglob("*.py")):
            if "__pycache__" in f.parts or f.name == "numbering.py" or "tools" in f.parts:
                continue
            if re.search(r"\b(insert\s+into|update|delete\s+from)\s+sys_number_seq\b", f.read_text(encoding="utf-8", errors="replace"), re.I):
                writers.append(str(f.relative_to(SRC)))
        rules = {r["kind"]: r for r in self.conn.q("select * from sys_number_rule")}
        src = [("LOT_MATERIAL", "select lot_no as no from lot where kind_base = 'MATERIAL' and created_by not like 'seed%%' and created_by <> 'qa2'"),
               ("LOT_PRODUCT", "select lot_no as no from lot where kind_base = 'PRODUCT' and created_by not like 'seed%%' and created_by <> 'qa2'"),
               ("LOT_SHIPMENT", "select lot_no as no from lot where kind_base = 'SHIPMENT' and created_by not like 'seed%%'"),
               ("WORK_ORDER", "select work_order_no as no from job_work_order where created_by not like 'seed%%'"),
               ("SHIPMENT", "select shipment_no as no from shp_shipment where created_by not like 'seed%%'"),
               ("ORDER", "select order_no as no from ord_order where created_by not like 'seed%%'"),
               ("PLAN", "select plan_no as no from ord_plan where created_by not like 'seed%%'")]
        bad_fmt, bad_seq, n_no = [], [], 0
        for kind, sql in src:
            r = rules.get(kind)
            nos = [x["no"] for x in self.conn.q(sql)]
            if not nos:
                continue
            if r is None:
                bad_fmt.append(f"{kind}: sys_number_rule 없음")
                continue
            dlen = bool(r["date_format"])
            rx = re.compile(rf"^{re.escape(r['prefix'] or '')}({_fmt_regex(r['date_format'])})(\d{{{int(r['seq_digits'])}}})$" if dlen else rf"^{re.escape(r['prefix'] or '')}(\d{{{int(r['seq_digits'])}}})$")
            by_scope: dict[str, int] = defaultdict(int)
            for no in nos:
                n_no += 1
                m = rx.match(no)
                if not m:
                    bad_fmt.append(f"{kind}:{no}")
                    continue
                scope = m.group(1) if dlen else ""
                by_scope[scope or ""] = max(by_scope[scope or ""], int(m.group(m.lastindex)))
            for scope, mx in by_scope.items():
                row = self.conn.q1("select last_seq from sys_number_seq where kind = %s and seq_scope = %s", (kind, scope))
                if row is None or row["last_seq"] != mx:
                    bad_seq.append(f"{kind}/{scope}: 최대 {mx} · 카운터 {row and row['last_seq']}")
        emit("G-C08", "채번 — numbering.py 한 곳 · sys_number_rule 형식", not writers and not bad_fmt and not bad_seq,
             f"sys_number_seq 를 쓰는 다른 파일 {writers or 0} · 이번 실행 번호 {n_no} 중 형식 밖 {bad_fmt[:4] or 0} · 일련번호 최대 ≠ 카운터 {bad_seq[:4] or 0}")

    # ── G-C24 측정값 선언 → 폼 → 기록 → 집계 ──────────────────────────
    def measure(self) -> None:
        from mescore.app import nav, stats
        from mescore.app.settings import get_settings
        admin, prod = self.api("admin"), self.api("prod")
        P = {s: nav.path_of(s) for s in ("BAS-03", "BAS-04", "BAS-05", "JOB-01", "POP-02", "IFC-01")}
        c = self.ctx
        out: list[str] = []
        fails: list[str] = []
        try:
            proc = admin.post(P["BAS-03"], {"process_code": "PRC-QA2-M", "process_name": "QA2 측정 공정 (예시)", "seq": "92"})["id"]
            eq = admin.post(P["BAS-05"], {"equip_code": "EQ-QA2-M", "equip_name": "QA2 수집 설비 (예시)", "process_id": proc, "collect_yn": "Y"})["id"]
            c["eq_m"] = eq
            decl = [{"param_key": "qa2_req", "label": "QA2 필수 (예시)", "required_yn": "Y", "seq": "1"},
                    {"param_key": "qa2_rng", "label": "QA2 범위 (예시)", "min_value": "10", "max_value": "20", "seq": "2"},
                    {"param_key": "qa2_col", "label": "QA2 수집 (예시)", "source": "collect", "collect_tag": "qa2_tag", "agg": "avg", "min_value": "0", "max_value": "5", "seq": "3"}]
            pid = {}
            for d in decl:
                pid[d["param_key"]] = admin.post(P["BAS-04"], {"process_id": proc, "unit": "u", "value_type": "number", **d})["id"]
            core_src = "".join(f.read_text(encoding="utf-8", errors="replace") for f in SRC.rglob("*.py") if "tools" not in f.parts and "__pycache__" not in f.parts)
            known = [k for k in ("qa2_req", "qa2_rng", "qa2_col", "qa2_tag") if k in core_src]

            def start() -> int:
                wo = prod.post(P["JOB-01"], {"item_id": c["item_prd"], "process_id": proc, "equipment_id": eq, "plan_qty": "10", "plan_date": str(date.today())})
                return prod.post(f"{P['POP-02']}/start", {"work_order_id": wo["id"]})["id"]

            r1 = start()
            j = prod.get(P["POP-02"], params={"id": r1}).json()
            fields = [p.get("field") for p in j.get("params", [])]
            h = prod.get(P["POP-02"], params={"id": r1}, html=True).text
            inputs = re.findall(r'name="(m_[a-z0-9_]+)"', h)
            ok_form = fields == ["m_qa2_req", "m_qa2_rng", "m_qa2_col"] and "m_qa2_req" in inputs and "m_qa2_rng" in inputs and "QA2 수집 (예시)" in h
            out.append(f"폼 칸 {fields} · HTML 입력 {sorted(set(inputs))} · 수집 칸 라벨 {'있음' if 'QA2 수집 (예시)' in h else '없음'}")
            if not ok_form:
                fails.append("폼")
            # 필수 누락 422 — 아무것도 저장 안 됨
            r = prod.c.post(f"{P['POP-02']}/{r1}/end", data={"good_qty": "5", "m_qa2_rng": "15"})
            saved = self.conn.q1("select ended_at, product_lot_id, (select count(*) from pop_measure where work_result_id = %s) as n from pop_work_result where id = %s", (r1, r1))
            ok422 = r.status_code == 422 and (r.json().get("fields") or [{}])[0].get("name") == "m_qa2_req" and saved["ended_at"] is None and saved["n"] == 0 and saved["product_lot_id"] is None
            out.append(f"필수 누락 {r.status_code} · 저장 측정값 {saved['n']} · LOT {saved['product_lot_id']}")
            if not ok422:
                fails.append("필수 422")
            # collect — 구간 안 2 · 4 (avg 3) · 구간 밖(시작 전) 9
            started = self.conn.q1("select started_at from pop_work_result where id = %s", (r1,))["started_at"]
            tok = get_settings().collect_token or ""
            col = []
            for v, ts in ((9.0, started - timedelta(minutes=5)), (2.0, started + timedelta(seconds=1)), (4.0, started + timedelta(seconds=2))):
                rr = admin.c.post(P["IFC-01"], json={"equip_code": "EQ-QA2-M", "ts": ts.isoformat(), "tags": {"qa2_tag": v}}, headers={"X-Collect-Token": tok})
                col.append(rr.status_code)
            time.sleep(2.2)
            e = prod.post(f"{P['POP-02']}/{r1}/end", {"good_qty": "5", "m_qa2_req": "1", "m_qa2_rng": "25"})
            rows = {m["param_key"]: m for m in self.conn.q("select * from pop_measure where work_result_id = %s", (r1,))}
            h2 = prod.get(P["POP-02"], params={"id": r1}, html=True).text
            ok_dev = (rows.get("qa2_rng", {}).get("deviated") is True and float(rows["qa2_rng"]["value_num"]) == 25 and e.get("deviated") == ["qa2_rng"]
                      and "이탈" in plain(h2))
            colv = rows.get("qa2_col", {}).get("value_num")
            ok_col = col == [200, 200, 200] and colv is not None and close(colv, 3.0) and rows["qa2_col"]["source"] == "collect" and rows["qa2_col"]["deviated"] is False
            out.append(f"범위 이탈 25 → 200 · deviated {rows.get('qa2_rng', {}).get('deviated')} · 화면 '이탈' {'있음' if '이탈' in plain(h2) else '없음'} · "
                       f"collect 수신 {col} → 대표값(avg) {dnum(colv)} (기대 3 — 구간 밖 9 제외)")
            if not ok_dev:
                fails.append("이탈")
            if not ok_col:
                fails.append("collect")
            # 수신 0 → 미수집(NULL) · 422 아님
            r2 = start()
            e2 = prod.c.post(f"{P['POP-02']}/{r2}/end", data={"good_qty": "3", "m_qa2_req": "2", "m_qa2_rng": "12"})
            v2 = self.conn.q1("select value_num from pop_measure where work_result_id = %s and param_key = 'qa2_col'", (r2,))
            h3 = prod.get(P["POP-02"], params={"id": r2}, html=True).text
            ok_nil = e2.status_code == 200 and v2 is not None and v2["value_num"] is None and "미수집" in plain(h3)
            out.append(f"수신 0 실적 종료 {e2.status_code} · collect 값 {v2 and v2['value_num']} · 화면 미수집 {'있음' if '미수집' in plain(h3) else '없음'}")
            if not ok_nil:
                fails.append("미수집")
            # 선언 변경 즉시 반영 — 범위 칸 필수로 · 4번째 선언 추가 · 수집 칸 사용 안 함
            admin.post(f"{P['BAS-04']}/{pid['qa2_rng']}", {"required_yn": "Y"})
            p4 = admin.post(P["BAS-04"], {"process_id": proc, "param_key": "qa2_new", "label": "QA2 추가 (예시)", "value_type": "number", "seq": "4"})["id"]
            admin.post(f"{P['BAS-04']}/{pid['qa2_col']}", {"use_yn": "N"})
            r3 = start()
            j3 = prod.get(P["POP-02"], params={"id": r3}).json()
            f3 = [p.get("field") for p in j3.get("params", [])]
            e3 = prod.c.post(f"{P['POP-02']}/{r3}/end", data={"good_qty": "1", "m_qa2_req": "1"})
            ok_live = f3 == ["m_qa2_req", "m_qa2_rng", "m_qa2_new"] and e3.status_code == 422 and any(x.get("name") == "m_qa2_rng" for x in e3.json().get("fields", []))
            prod.post(f"{P['POP-02']}/{r3}/end", {"good_qty": "1", "m_qa2_req": "3", "m_qa2_rng": "18", "m_qa2_new": "7"})
            out.append(f"선언 변경 뒤 새 실적 폼 {f3} · 범위 칸 필수화 → 누락 {e3.status_code}")
            old = plain(prod.get(P["POP-02"], params={"id": r1}, html=True).text)
            info("G-C24 선언을 끈 뒤 지난 실적의 기록 값", PASS if "QA2 수집 (예시)" in old else WARN,
                 f"qa2_col 을 use_yn=N 으로 바꾼 뒤 실적 #{r1} 화면에 그 기록(pop_measure 값 3) {'보임' if 'QA2 수집 (예시)' in old else '안 보임 — 화면이 현재 선언만 그려 기록이 사라져 보인다'}")
            if not ok_live:
                fails.append("즉시 반영")
            del p4
            # 집계 — stats.measure_series = 내 계산
            today = date.today()
            agg_err = []
            for key in ("qa2_req", "qa2_rng", "qa2_col", "qa2_new"):
                vals = self.conn.q("select m.value_num, m.deviated from pop_measure m where m.param_key = %s and m.value_num is not null and m.measured_at::date = %s", (key, today))
                nums = [float(v["value_num"]) for v in vals]
                got = stats.measure_series(key, today, today, by="day", agg="avg")
                exp_n = len(nums)
                if exp_n == 0:
                    if got:
                        agg_err.append(f"{key}: 내 0행 · stats {got}")
                    continue
                g = got[0] if got else {}
                if not (g.get("n") == exp_n and close(g.get("value"), sum(nums) / exp_n) and g.get("deviated_count") == sum(1 for v in vals if v["deviated"])):
                    agg_err.append(f"{key}: stats {g} ≠ 내 n {exp_n} avg {sum(nums) / exp_n}")
            out.append(f"stats.measure_series(day · avg) 불일치 {agg_err or 0}")
            if agg_err:
                fails.append("집계")
            if known:
                fails.append(f"코어 코드가 선언 키를 안다 {known}")
            emit("G-C24", "측정값 선언 3행 → 폼 · 422 · 이탈 · collect · 집계 · 즉시 반영", not fails, " · ".join(out) + f" · 코어가 선언 키를 아는 곳 {known or 0}")
        except StepError as exc:
            emit("G-C24", "측정값 선언 3행 → 폼 · 422 · 이탈 · collect · 집계 · 즉시 반영", FAIL, f"단계 실패 — {exc} · 진행 {' · '.join(out)}")

    # ── G-C04 뷰 3 검산 + 집계 재료 ───────────────────────────────────
    def view_material(self) -> None:
        """부분 투입 · 취소 투입 · 반제품 투입 · 이중 스캔 + 집계 재료(검사 판정 3종 · 불량 · 수주 4 · 설비 로그)."""
        from mescore.app import nav
        prod, qa, admin = self.api("prod"), self.api("qa"), self.api("admin")
        P = {s: nav.path_of(s) for s in ("MAT-01", "MAT-02", "POP-02", "POP-03", "JOB-01", "QUA-02", "ORD-01", "SHP-01", "SHP-02", "EQP-01", "EQP-03")}
        c = self.ctx
        today = date.today()
        v = c.setdefault("view", {})
        try:
            def wo(q: str = "50") -> int:
                return prod.post(P["JOB-01"], {"item_id": c["item_prd"], "process_id": c["proc"], "equipment_id": c["eq"], "plan_qty": q, "plan_date": str(today)})["id"]

            def start(w: int) -> int:
                return prod.post(f"{P['POP-02']}/start", {"work_order_id": w})["id"]

            m3 = prod.post(P["MAT-01"], {"item_id": c["item_raw1"], "qty": "100", "partner_id": c["sup"], "unit": "kg"})
            qa.post(P["MAT-02"], {"lot_no": m3["lot_no"], "judgement": "합격"})
            stock0 = self.conn.q1("select qty from mat_stock where item_id = %s", (c["item_raw1"],))
            ra = start(wo())
            prod.post(P["POP-03"], {"work_result_id": ra, "barcode": m3["lot_no"], "qty": "30"})
            i2 = prod.post(P["POP-03"], {"work_result_id": ra, "barcode": m3["lot_no"], "qty": "20"})
            prod.post(f"{P['POP-03']}/{i2['id']}/cancel")
            v["m3"] = (m3["lot_id"], 70.0, 30.0)                               # 기대 잔량 · 소비
            over_m = prod.c.post(P["POP-03"], data={"work_result_id": ra, "barcode": m3["lot_no"], "qty": "71"})
            v["over_material"] = over_m.status_code
            ea = prod.post(f"{P['POP-02']}/{ra}/end", {"good_qty": "40", "defect_qty": "2", "m_qa2_len": "40"})
            v["p3"] = ea["lot_id"]
            stock1 = self.conn.q1("select qty from mat_stock where item_id = %s", (c["item_raw1"],))
            trx = self.conn.q1("select coalesce(sum(qty), 0) as s from mat_stock_trx where item_id = %s", (c["item_raw1"],))
            v["stock"] = (dnum(stock0 and stock0["qty"]), dnum(stock1 and stock1["qty"]), dnum(trx["s"]))
            # 반제품(PRODUCT) 부분 투입 — 생산 LOT 40 중 15 만 다음 실적에 → 종료 뒤 잔량 25 · 상태는?
            rb = start(wo())
            prod.post(P["POP-03"], {"work_result_id": rb, "barcode": ea["lot_no"], "qty": "15"})
            prod.post(f"{P['POP-02']}/{rb}/end", {"good_qty": "15"})
            # 이중 스캔 — 생산 LOT 20 을 실적 E 에 15 · 실적 F 에 15 (둘 다 종료 전, 합 30 > 20)
            re_ = start(wo("20"))
            ee = prod.post(f"{P['POP-02']}/{re_}/end", {"good_qty": "20"})
            v["p5"] = ee["lot_id"]
            rf, rg = start(wo()), start(wo())
            prod.post(P["POP-03"], {"work_result_id": rf, "barcode": ee["lot_no"], "qty": "15"})
            dbl = prod.c.post(P["POP-03"], data={"work_result_id": rg, "barcode": ee["lot_no"], "qty": "15"})
            v["double_scan"] = dbl.status_code
            prod.post(f"{P['POP-02']}/{rf}/end", {"good_qty": "15"})
            if dbl.status_code == 200:
                prod.c.post(f"{P['POP-02']}/{rg}/end", data={"good_qty": "15"})
            # 집계 재료 — 검사 3종(합격 · 불합격+불량 · 조건부) · 조건부
            lots = [r["lot_id"] for r in self.conn.q("select l.id as lot_id from lot l join pop_work_result r on r.id = l.work_result_id where r.id = any(%s)", ([rb],))]
            if lots:
                no = self.conn.q1("select lot_no from lot where id = %s", (lots[0],))["lot_no"]
                ins = qa.post(P["QUA-02"], {"insp_type": "공정", "lot_no": no})
                qa.post(f"{P['QUA-02']}/{ins['id']}/judge", {"judgement": "불합격", "defect_code_id": str(c["defect"]), "defect_qty": "2"})
                ins = qa.post(P["QUA-02"], {"insp_type": "공정", "lot_no": no})
                qa.post(f"{P['QUA-02']}/{ins['id']}/judge", {"judgement": "조건부"})
            # 수주 4 — 늦은 납기 · 대기 · 늦게 승인된 출하
            late = prod.post(P["ORD-01"], {"partner_code": "CUST-EX-01", "order_date": str(today - timedelta(days=5)), "due_date": str(today - timedelta(days=1)),
                                            "item_code": ["PRD-EX-01"], "qty": ["5"], "unit": ["EA"]})
            prod.post(P["ORD-01"], {"partner_code": "CUST-EX-01", "order_date": str(today), "due_date": str(today + timedelta(days=5)),
                                     "item_code": ["PRD-EX-01"], "qty": ["5"], "unit": ["EA"]})
            late2 = prod.post(P["ORD-01"], {"partner_code": "CUST-EX-01", "order_date": str(today - timedelta(days=5)), "due_date": str(today - timedelta(days=2)),
                                             "item_code": ["PRD-EX-01"], "qty": ["5"], "unit": ["EA"]})
            rd = start(wo("5"))
            ed = prod.post(f"{P['POP-02']}/{rd}/end", {"good_qty": "5", "m_qa2_len": "5"})
            ins = qa.post(P["QUA-02"], {"insp_type": "최종", "lot_no": ed["lot_no"]})
            qa.post(f"{P['QUA-02']}/{ins['id']}/judge", {"judgement": "합격"})
            sh = prod.post(P["SHP-01"], {"partner_code": "CUST-EX-01", "ship_date": str(today), "order_no": late2["order_no"]})
            prod.post(P["SHP-02"], {"shipment_no": sh["shipment_no"], "barcode": ed["lot_no"]})
            admin.post(f"{P['SHP-01']}/{sh['id']}/approve")
            v["late_order"] = late["order_no"]
            # 설비 — 가동 2h 전 · 정지 1h 전 · 고장 30분 전 → 10분 전 조치(가동)
            now = datetime.now()
            for st, at in (("가동", now - timedelta(hours=2)), ("정지", now - timedelta(hours=1))):
                prod.post(P["EQP-01"], {"equipment_id": c["eq"], "state": st, "at": at.isoformat(timespec="seconds")})
            for eid, occ, fix in ((c["eq"], 30, 10), (c.get("eq_m"), 90, 80), (c.get("eq_m"), 70, 20)):    # 고장 3 — 설비별 수가 다르다(MTTR 합계 검산)
                if eid is None:
                    continue
                fl = prod.post(P["EQP-03"], {"equipment_id": eid, "symptom": "QA2 시험 고장 (예시)", "occurred_at": (now - timedelta(minutes=occ)).isoformat(timespec="seconds")})
                prod.post(f"{P['EQP-03']}/{fl['id']}/fix", {"fix_action": "QA2 조치 (예시)", "fixed_at": (now - timedelta(minutes=fix)).isoformat(timespec="seconds"), "next_state": "가동"})
            v["ok"] = True
        except StepError as exc:
            v["ok"] = False
            emit("G-C04", "뷰 검산 재료 만들기 (API)", FAIL, f"단계 실패 — {exc}")

    def views(self) -> None:
        v = self.ctx.get("view", {})
        # 1) 뷰 3 전 행 = 내 SQL
        mine = {r["id"]: r for r in self.conn.q(SQL_MY_STOCK)}
        stock = {r["lot_id"]: r for r in self.conn.q("select * from v_lot_stock")}
        state = {r["lot_id"]: r["state"] for r in self.conn.q("select lot_id, state from v_lot_state")}
        bad_stock, bad_state = [], []
        for lid, r in mine.items():
            consumed = r["input_qty"] if r["kind_base"] == "MATERIAL" else (r["child_qty"] + r["open_input_qty"] if r["kind_base"] == "PRODUCT" else 0)   # §3.4 회전 5
            remain = (r["qty"] or 0) - consumed
            s = stock.get(lid)
            if s is None or not close(s["consumed_qty"], consumed) or not close(s["remain_qty"], remain):
                bad_stock.append(f"{lid}: 뷰 {s and (dnum(s['consumed_qty']), dnum(s['remain_qty']))} ≠ 내 {(dnum(consumed), dnum(remain))}")
            if r["kind_base"] == "SHIPMENT":
                st = "출하"
            elif r["kind_base"] == "PRODUCT" and r["n_ship_out"]:
                st = "출하"
            elif r["kind_base"] == "PRODUCT" and r["n_whole"]:
                st = "소진"                                                     # 분할 · 합병 · 생산 — LOT 통째
            elif r["kind_base"] == "PRODUCT" and r["n_input"]:
                st = "소진" if (r["qty"] is None or remain <= 0 or r["n_input_noqty"]) else "재고"   # 부분 투입은 잔량으로 (§3.4 회전 4)
            elif r["kind_base"] == "MATERIAL" and r["qty"] is not None and remain <= 0:
                st = "소진"
            else:
                st = "재고"
            if state.get(lid) != st:
                bad_state.append(f"{lid}: 뷰 {state.get(lid)} ≠ 내 {st}")
        wo_mine = {r["id"]: r for r in self.conn.q(SQL_MY_WO)}
        bad_wo = []
        for r in self.conn.q("select * from v_work_order_progress"):
            m = wo_mine.get(r["work_order_id"])
            if m is None or r["started"] != (m["n"] > 0) or r["closed"] != (m["status"] == "마감") or r["result_count"] != m["n"] \
                    or r["open_count"] != m["n_open"] or not close(r["good_qty"], m["good"]) or not close(r["defect_qty"], m["defect"]):
                bad_wo.append(f"wo {r['work_order_id']}")
        emit("G-C04", "뷰 3 = 내 SQL (전 행)", not (bad_stock or bad_state or bad_wo),
             f"v_lot_stock {len(stock)}행 불일치 {bad_stock[:3] or 0} · v_lot_state {len(state)}행 불일치 {bad_state[:3] or 0} · v_work_order_progress {len(wo_mine)}행 불일치 {bad_wo[:3] or 0}")
        if not v.get("ok"):
            return
        lid, exp_remain, exp_cons = v["m3"]
        s = stock[lid]
        s0, s1, trx = v["stock"]
        ok_part = close(s["remain_qty"], exp_remain) and close(s["consumed_qty"], exp_cons) and state[lid] == "재고" and v["over_material"] == 422 \
            and close(s1, trx)
        emit("G-C04", "부분 투입 · 취소 투입 (원재료)", ok_part,
             f"원재료 100 → 투입 30 + 투입 20 취소 → v_lot_stock 소비 {dnum(s['consumed_qty'])} · 잔량 {dnum(s['remain_qty'])} (기대 30 · 70) · 상태 {state[lid]} · "
             f"잔량 넘는 71 투입 {v['over_material']}(기대 422) · mat_stock {s0}→{s1} = Σ mat_stock_trx {trx}")
        p3, p5 = v["p3"], v["p5"]
        sp, s5 = stock[p3], stock[p5]
        dbl = v["double_scan"]
        emit("G-C04", "반제품 투입 — 종료 전 이중 스캔이 잔량을 넘는가", dbl == 422,
             f"생산 LOT 20 을 실적 E 에 15 스캔(종료 전) 뒤 실적 F 에 15 스캔 → {dbl}(기대 422 — 합 30 > 20). 둘 다 종료 뒤 v_lot_stock 소비 {dnum(s5['consumed_qty'])} · "
             f"잔량 {dnum(s5['remain_qty'])} · 상태 {state[p5]}"
             + ("" if dbl == 422 else " — PRODUCT 소비는 계보(종료 때)로만 세서 종료 전 pop_input 이 잔량 검사에 안 잡힌다(원재료는 잡힌다)"))
        emit("G-C04", "반제품 부분 투입 뒤 상태 (잔량 판정)", state[p3] == "재고" and close(sp["remain_qty"], 25),
             f"생산 LOT 40 중 15 투입 → v_lot_stock 잔량 {dnum(sp['remain_qty'])} · v_lot_state {state[p3]} (db-schema.md §3.4 회전 4: 투입의 부모로만 나오면 잔량으로 — 기대 재고)")

    # ── G-C04 잔량 공격 (회전 6) — 회전 5 새 경로(열린 투입 잔량 · 종료 합병 옵션 · 분할 N≥1 · inherit_insp)로 음수 · 이중 소진을 찾는다 ──
    def stock_attack(self) -> None:
        """gate 는 G-C04 를 이 도구에서 읽지 않는다(check_schema 소관) — 결함 근거 행이다.
        기대: db-schema.md §3.4 회전 5 (PRODUCT 잔량 = qty − Σ자식 계보 − Σ열린 투입) · interfaces.md §4 (assert_usable · split/merge · inherit_insp · make_product_lot)."""
        import threading

        import psycopg
        from psycopg.rows import dict_row

        from mescore.app import lineage, nav
        prod, qa = self.api("prod"), self.api("qa")
        P = {s: nav.path_of(s) for s in ("POP-02", "POP-03", "JOB-01", "QUA-02", "SHP-01", "SHP-02")}
        c, today = self.ctx, date.today()

        def wo(q: str = "50") -> int:
            return prod.post(P["JOB-01"], {"item_id": c["item_prd"], "process_id": c["proc"], "equipment_id": c["eq"], "plan_qty": q, "plan_date": str(today)})["id"]

        def start() -> int:
            return prod.post(f"{P['POP-02']}/start", {"work_order_id": wo()})["id"]

        def lot(q: str = "20") -> dict:
            return prod.post(f"{P['POP-02']}/{start()}/end", {"good_qty": q})

        def stock(lid: int) -> tuple:
            r = self.conn.q1("select s.consumed_qty, s.remain_qty, t.state from v_lot_stock s join v_lot_state t on t.lot_id = s.lot_id where s.lot_id = %s", (lid,))
            return dnum(r["consumed_qty"]), dnum(r["remain_qty"]), r["state"]

        def kids(lid: int) -> dict:
            return dict(Counter(r["relation_base"] for r in self.conn.q("select relation_base from lot_genealogy where parent_lot_id = %s", (lid,))))

        # A1 — 같은 실적이 투입한 LOT 을 종료 합병 옵션(merge_lot_ids)으로 다시 잇는다
        a = lot("20")
        ra = start()
        prod.post(P["POP-03"], {"work_result_id": ra, "barcode": a["lot_no"], "qty": "15"})
        r1 = prod.c.post(f"{P['POP-02']}/{ra}/end", data={"good_qty": "35", "merge_lot_ids": a["lot_no"]})
        s1 = stock(a["lot_id"])
        emit("G-C04", "종료 합병 옵션 — 자기 실적 투입 LOT 을 merge_lot_ids 로", r1.status_code == 422 or (s1[1] is not None and s1[1] >= 0),
             f"생산 LOT 20 을 실적에 15 투입 → 같은 실적 종료에 merge_lot_ids=그 LOT → {r1.status_code} · v_lot_stock 소비 {s1[0]} · 잔량 {s1[1]} · 상태 {s1[2]} · "
             f"자식 계보 {kids(a['lot_id'])} (기대 422 또는 잔량 ≥ 0 — make_product_lot 이 ended_at 을 먼저 쓴 뒤 합병 부모 잔량을 읽어 자기 열린 투입이 빠진다)")

        # A2 — 열린 투입으로 잔량 0 인데 상태는 재고(§3.4 「열린 투입은 상태를 바꾸지 않는다」) → 다른 경로가 이 LOT 을 또 쓰는가
        res = {}
        hold = []
        for key in ("투입(수량 없음)", "분할(수량 없음)", "합병", "종료 합병 옵션", "출하 스캔"):
            x = lot("20")
            if key == "출하 스캔":                                                  # 출하는 미검사 LOT 을 먼저 막는다 — 합격으로 두고 잔량 판정만 본다
                ins = qa.post(P["QUA-02"], {"insp_type": "최종", "lot_no": x["lot_no"]})
                qa.post(f"{P['QUA-02']}/{ins['id']}/judge", {"judgement": "합격"})
            rh = start()
            prod.post(P["POP-03"], {"work_result_id": rh, "barcode": x["lot_no"], "qty": "20"})
            hold.append((key, x, rh))
        sh = prod.post(P["SHP-01"], {"partner_code": "CUST-EX-01", "ship_date": str(today)})
        other = lot("5")
        for key, x, rh in hold:
            r2 = None
            if key == "투입(수량 없음)":
                r2 = start()
                r = prod.c.post(P["POP-03"], data={"work_result_id": r2, "barcode": x["lot_no"]})
            elif key == "분할(수량 없음)":
                r = prod.c.post(f"{P['POP-02']}/{rh}/split", data={"count": "2", "lot_id": str(x["lot_id"])})
            elif key == "합병":
                r = prod.c.post(f"{P['POP-02']}/{rh}/merge", data={"lot_ids": f"{x['lot_no']},{lot('5')['lot_no']}"})
            elif key == "종료 합병 옵션":
                r = prod.c.post(f"{P['POP-02']}/{start()}/end", data={"good_qty": "20", "merge_lot_ids": x["lot_no"]})
            else:
                r = prod.c.post(P["SHP-02"], data={"shipment_no": sh["shipment_no"], "barcode": x["lot_no"]})
            prod.c.post(f"{P['POP-02']}/{rh}/end", data={"good_qty": "20"})          # 잡아 둔 실적 종료 → 투입 20 이 계보로
            if r2 is not None:
                prod.c.post(f"{P['POP-02']}/{r2}/end", data={"good_qty": "1"})
            k = kids(x["lot_id"])
            why = "" if r.status_code == 200 else ((r.json().get("fields") or [{}])[0].get("reason") or r.json().get("message") or r.text)[:40]
            res[key] = (f"{r.status_code}{'(' + why + ')' if why else ''}", stock(x["lot_id"]), k)
        _ = other
        dbl = {k: v for k, v in res.items() if sum(v[2].values()) > 1 or (v[1][1] is not None and v[1][1] < 0)}
        emit("G-C04", "열린 투입으로 잔량 0 인 생산 LOT — 다른 경로가 또 쓰는가", not dbl,
             f"LOT 20 을 실적에 20 투입(종료 전 · 잔량 0 · 상태 재고) 뒤 경로별 응답 · 잡은 실적 종료 후 (소비 · 잔량 · 상태) · 자식 계보 base — "
             + " / ".join(f"{k} {v[0]} {v[1]} {v[2]}" for k, v in res.items())
             + f" — 이중 소진(투입 + 다른 관계 · 또는 잔량 음수) {sorted(dbl) or 0} (기대 전부 422)")

        # A3 — 동시성: 열린 트랜잭션의 투입 ‖ 분할 · 분할 ‖ 분할 (lineage 직접 · 커밋)
        dsn = self.env["MES_PG_DSN"]

        def race(first, second) -> tuple:
            x = lot("20")
            rid = start()
            ca = psycopg.connect(dsn, row_factory=dict_row)
            cb = psycopg.connect(dsn, row_factory=dict_row)
            out = {"b": None, "b_done_before_a_commit": None}
            try:
                with ca.cursor() as cur_a:
                    first(cur_a, x, rid)                                             # A 는 아직 커밋하지 않는다

                    def run_b():
                        try:
                            with cb.cursor() as cur_b:
                                cur_b.execute("set lock_timeout = '5s'")
                                second(cur_b, x, rid)
                            cb.commit()
                            out["b"] = "ok"
                        except Exception as exc:  # noqa: BLE001 — 거부(422 · 잠금 대기 끝) 자체가 판정 근거
                            cb.rollback()
                            out["b"] = type(exc).__name__ + ":" + str(getattr(exc, "detail", exc))[:60]
                    th = threading.Thread(target=run_b)
                    th.start()
                    th.join(1.5)
                    out["b_done_before_a_commit"] = not th.is_alive()
                ca.commit()
                th.join(10)
            finally:
                ca.close()
                cb.close()
            prod.c.post(f"{P['POP-02']}/{rid}/end", data={"good_qty": "1"})
            return out, stock(x["lot_id"]), kids(x["lot_id"])

        def consume15(cur, x, rid):
            lineage.consume_material(cur, work_result_id=rid, material_lot_id=x["lot_id"], qty=15, by="qa2")

        def split1010(cur, x, rid):
            lineage.split(cur, parent_id=x["lot_id"], count=2, qtys=[10, 10], by="qa2")

        def ship_(cur, x, rid):
            s2 = prod.post(P["SHP-01"], {"partner_code": "CUST-EX-01", "ship_date": str(today)})
            lineage.ship(cur, shipment_id=s2["id"], lot_id=x["lot_id"], by="qa2")

        races = {"투입 15 ‖ 분할 10+10": race(consume15, split1010), "분할 ‖ 분할": race(split1010, split1010), "투입 15 ‖ 출하 스캔": race(consume15, ship_)}
        bad = {k: v for k, v in races.items() if (v[1][1] is not None and v[1][1] < 0) or sum(n for b, n in v[2].items() if b != "투입") > (2 if "분할" in k else 1)
               or (len(v[2]) > 1)}
        emit("G-C04", "동시성 — 열린 트랜잭션 투입/분할 ‖ 분할/출하 (잔량 음수 · 이중 소진)", not bad,
             " / ".join(f"{k}: B {v[0]['b']} (A 커밋 전 끝남 {v[0]['b_done_before_a_commit']}) → (소비 · 잔량 · 상태) {v[1]} · 자식 {v[2]}" for k, v in races.items())
             + f" — 어긋남 {sorted(bad) or 0} (기대: 뒤 트랜잭션이 LOT 행 잠금에서 기다렸다 잔량으로 다시 판정 → 422 · 잔량 ≥ 0)")

        # A4 — inherit_insp (interfaces.md §4: 전부 합격 → 합격 · 불합격 하나라도 → 불합격 · 미검사 하나라도 → 미검사 · 그 밖 → 조건부 · 부모 하나면 그 값)
        def judged(j: str | None) -> dict:
            x = lot("10")
            if j:
                ins = qa.post(P["QUA-02"], {"insp_type": "공정", "lot_no": x["lot_no"]})
                qa.post(f"{P['QUA-02']}/{ins['id']}/judge", {"judgement": j, **({"defect_code_id": str(c["defect"]), "defect_qty": "1"} if j == "불합격" else {})})
            return x

        def my_inherit(vals):
            v = [x or "미검사" for x in vals]
            if "불합격" in v:
                return "불합격"
            if all(x == "합격" for x in v):
                return "합격"
            if "미검사" in v:
                return "미검사"
            return "조건부"

        cases = [("합격",), ("조건부",), ("불합격",), ("합격", "합격"), ("합격", "조건부"), ("합격", "불합격"), ("합격", None), ("조건부", None), ("조건부", "불합격")]
        wrong, seen = [], []
        for cs in cases:
            xs = [judged(j) for j in cs]
            rid = start()
            if len(xs) == 1:
                r = prod.c.post(f"{P['POP-02']}/{rid}/split", data={"count": "2", "lot_id": str(xs[0]["lot_id"]), "qtys": "5,5"})
                ids = [ln["id"] for ln in r.json().get("lots", [])] if r.status_code == 200 else []
            else:
                r = prod.c.post(f"{P['POP-02']}/{rid}/merge", data={"lot_ids": ",".join(x["lot_no"] for x in xs)})
                ids = [r.json()["id"]] if r.status_code == 200 else []
            got = sorted({self.conn.q1("select insp_status from lot where id = %s", (i,))["insp_status"] for i in ids})
            exp = my_inherit(list(cs))
            seen.append(f"{'+'.join(j or '미검사' for j in cs)}→{got}")
            if r.status_code != 200 or got != [exp]:
                wrong.append(f"{cs} {r.status_code} {got} ≠ {exp}")
        # 불합격 부모가 종료 합병 옵션으로 새 LOT(미검사)에 들어가면 — 계약상 「새 생산은 미검사」 · 관찰만
        bad_p = judged("불합격")
        rm = prod.c.post(f"{P['POP-02']}/{start()}/end", data={"good_qty": "10", "merge_lot_ids": bad_p["lot_no"]})
        launder = self.conn.q1("select insp_status from lot where id = %s", (rm.json()["lot_id"],))["insp_status"] if rm.status_code == 200 else None
        emit("G-C04", "분할 · 합병 자식 insp_status = inherit_insp 규칙 (API)", not wrong,
             f"경우 {len(cases)} {seen} · 규칙과 다른 것 {wrong or 0}")
        info("G-C04 불합격 생산 LOT → 종료 합병 옵션", WARN if rm.status_code == 200 else PASS,
             f"불합격 LOT 을 merge_lot_ids 로 → {rm.status_code} · 새 LOT insp_status {launder} — interfaces.md §4 「make_product_lot 의 새 LOT 은 늘 미검사」 대로지만 "
             f"lineage.merge 로 합치면 불합격을 잇고 출하 422 인 것과 달리, 이 길로는 불합격 이력이 자식 판정에서 사라진다(코어 출하 검사는 자기 LOT 만 본다)")

        # A5 — 분할 수량 합 < 잔량: 상태 소진인데 v_lot_stock 잔량 > 0 (분할 = LOT 통째 · §3.4)
        y = lot("20")
        rp = prod.c.post(f"{P['POP-02']}/{start()}/split", data={"count": "2", "lot_id": str(y["lot_id"]), "qtys": "5,5"})
        sy = stock(y["lot_id"])
        info("G-C04 부분 분할 — 남는 수량", WARN if rp.status_code == 200 and sy[2] == "소진" and (sy[1] or 0) > 0 else PASS,
             f"LOT 20 → 분할 5+5 → {rp.status_code} · v_lot_stock 잔량 {sy[1]} · 상태 {sy[2]} — 분할은 LOT 통째(소진)라 남는 10 이 재고에서 사라진다(팩 분할 계열 N≥1 도 같다)")

    # ── G-C10 집계 재계산 ─────────────────────────────────────────────
    def stats_recalc(self) -> None:
        from mescore.app import stats
        today = date.today()
        periods = [(today, today), (today - timedelta(days=30), today + timedelta(days=30)), (date(2000, 1, 1), date(2000, 1, 31))]
        errs: dict[str, list[str]] = defaultdict(list)
        n_cmp = Counter()
        for frm, to in periods:
            for by in ("day", "item", "process", "equipment"):
                n_cmp["production"] += 1
                errs["production"] += _cmp_rows(f"production {by} {frm}", stats.production(frm, to, by=by), self.my_production(frm, to, by),
                                                {"day": "day", "item": "item_id", "process": "process_id", "equipment": "equipment_id"}[by],
                                                ("wo_count", "plan_qty", "result_count", "good_qty", "defect_qty", "good_rate", "achieve_rate"))
            for by in ("day", "item"):
                n_cmp["quality"] += 1
                errs["quality"] += _cmp_rows(f"quality {by} {frm}", stats.quality(frm, to, by=by), self.my_quality(frm, to, by), "day" if by == "day" else "item_id",
                                             ("inspection_count", "pass_count", "fail_count", "cond_count", "pass_rate"))
            n_cmp["quality"] += 1
            errs["quality"] += _cmp_rows(f"quality defect {frm}", stats.quality(frm, to, by="defect"), self.my_defect(frm, to), "defect_code_id",
                                         ("defect_count", "defect_qty", "inspection_count"))
            for by in ("day", "partner"):
                n_cmp["delivery"] += 1
                errs["delivery"] += _cmp_rows(f"delivery {by} {frm}", stats.delivery(frm, to, by=by, today=today), self.my_delivery(frm, to, by, today),
                                              "day" if by == "day" else "partner_id", ("due_count", "shipped_count", "on_time", "late", "pending", "on_time_rate"))
            n_cmp["equipment"] += 1
            mine_e = self.my_equipment(frm, to)
            errs["equipment"] += _cmp_rows(f"equipment {frm}", stats.equipment(frm, to), mine_e, "equipment_id",
                                           ("run_seconds", "stop_seconds", "check_seconds", "fault_seconds", "logged_seconds", "run_rate", "stop_count", "fault_count", "mttr_hours", "current_state"),
                                           tol=2e-3)
            keys = [r["param_key"] for r in self.conn.q("select distinct param_key from pop_measure order by 1")]
            for key in keys:
                for by in ("day", "work_order", "equipment"):
                    for agg in ("avg", "min", "max", "sum", "count", "last"):
                        n_cmp["measure_series"] += 1
                        errs["measure_series"] += _cmp_rows(f"measure {key} {by} {agg} {frm}", stats.measure_series(key, frm, to, by=by, agg=agg),
                                                            self.my_measure(key, frm, to, by, agg), {"day": "day", "work_order": "work_order_id", "equipment": "equipment_id"}[by],
                                                            ("value", "n", "deviated_count", "min_value", "max_value"))
            n_cmp["core_metrics"] += 1
            got = stats.core_metrics(frm, to, today=today)
            exp = self.my_core_metrics(frm, to, today)
            for k, val in exp.items():
                if not close(got.get(k), val, 2e-3):
                    errs["core_metrics"].append(f"{k} {frm}: stats {got.get(k)} ≠ 내 {val}")
        for kind in ("production", "quality", "delivery", "equipment", "measure_series", "core_metrics"):
            e = errs[kind]
            emit("G-C10", f"stats.{kind} = QA2 SQL", not e, f"대조 {n_cmp[kind]}회(기간 3 × by/agg) · 불일치 {len(e)} {e[:3] or ''}")
        # totals — 설비 MTTR 합계는 고장 전체 평균인가 (설비별 평균의 평균이 아니다)
        frm, to = periods[1]
        tot = stats.totals("equipment", stats.equipment(frm, to)) or {}
        all_f = self.conn.q1("select avg(extract(epoch from (fixed_at - occurred_at)) / 3600.0) as h from eqp_fault where fixed_at is not null and occurred_at::date between %s and %s", (frm, to))
        info("G-C10 합계 줄 — 설비 MTTR", WARN if not close(tot.get("mttr_hours"), dnum(all_f["h"]), 1e-6) else PASS,
             f"stats.totals(equipment).mttr_hours {tot.get('mttr_hours')} · 복구된 고장 전체 평균 {dnum(all_f['h'])} — 설비가 둘 이상 고장 수가 다르면 '설비별 평균의 평균' 이 된다")

    # 내 집계 — stats.py 의 산식 문장(docstring)만 보고 따로 짠다
    def my_production(self, frm, to, by) -> list[dict]:
        pk = {"day": "plan_date", "item": "item_id", "process": "process_id", "equipment": "equipment_id"}[by]
        plan = self.conn.q(f"select {pk} as k, plan_qty from job_work_order where status <> '취소' and plan_date between %s and %s", (frm, to))
        rk = {"day": "r.ended_at::date", "item": "w.item_id", "process": "r.process_id", "equipment": "r.equipment_id"}[by]
        act = self.conn.q(f"select {rk} as k, r.good_qty, r.defect_qty from pop_work_result r join job_work_order w on w.id = r.work_order_id "
                          "where r.ended_at is not null and r.ended_at::date between %s and %s", (frm, to))
        acc: dict = defaultdict(lambda: {"wo_count": 0, "plan_qty": None, "result_count": 0, "good_qty": None, "defect_qty": None})
        for p in plan:
            a = acc[p["k"]]
            a["wo_count"] += 1
            a["plan_qty"] = (a["plan_qty"] or 0) + (p["plan_qty"] or 0) if p["plan_qty"] is not None or a["plan_qty"] is not None else None
        for r in act:
            a = acc[r["k"]]
            a["result_count"] += 1
            if r["good_qty"] is not None:
                a["good_qty"] = (a["good_qty"] or 0) + r["good_qty"]
            if r["defect_qty"] is not None:
                a["defect_qty"] = (a["defect_qty"] or 0) + r["defect_qty"]
        key = {"day": "day", "item": "item_id", "process": "process_id", "equipment": "equipment_id"}[by]
        out = []
        for k, a in acc.items():
            g, d = a["good_qty"], a["defect_qty"]
            out.append({key: k, **a, "good_rate": _pct(g, (g or 0) + (d or 0)) if (g is not None or d is not None) else None, "achieve_rate": _pct(g, a["plan_qty"])})
        return out

    def my_quality(self, frm, to, by) -> list[dict]:
        rows = self.conn.q("select n.judged_at::date as day, l.item_id, n.judgement from qua_inspection n join lot l on l.id = n.lot_id "
                           "where n.judgement is not null and n.judged_at::date between %s and %s", (frm, to))
        key = "day" if by == "day" else "item_id"
        acc: dict = defaultdict(Counter)
        for r in rows:
            acc[r[key]][r["judgement"]] += 1
            acc[r[key]]["_n"] += 1
        return [{key: k, "inspection_count": c["_n"], "pass_count": c["합격"], "fail_count": c["불합격"], "cond_count": c["조건부"], "pass_rate": _pct(c["합격"], c["_n"])}
                for k, c in acc.items()]

    def my_defect(self, frm, to) -> list[dict]:
        rows = self.conn.q("select d.defect_code_id, d.qty, d.inspection_id from qua_defect d join qua_inspection n on n.id = d.inspection_id "
                           "where n.judgement is not null and n.judged_at::date between %s and %s", (frm, to))
        acc: dict = defaultdict(lambda: {"defect_count": 0, "defect_qty": None, "_i": set()})
        for r in rows:
            a = acc[r["defect_code_id"]]
            a["defect_count"] += 1
            if r["qty"] is not None:
                a["defect_qty"] = (a["defect_qty"] or 0) + r["qty"]
            a["_i"].add(r["inspection_id"])
        return [{"defect_code_id": k, "defect_count": a["defect_count"], "defect_qty": a["defect_qty"], "inspection_count": len(a["_i"])} for k, a in acc.items()]

    def my_delivery(self, frm, to, by, today) -> list[dict]:
        orders = self.conn.q("select id, partner_id, due_date from ord_order where status <> '취소' and due_date between %s and %s", (frm, to))
        ships = defaultdict(list)
        for s in self.conn.q("select order_id, ship_date from shp_shipment where status = '승인' and order_id is not null"):
            ships[s["order_id"]].append(s["ship_date"])
        key = "day" if by == "day" else "partner_id"
        acc: dict = defaultdict(Counter)
        for o in orders:
            k = o["due_date"] if by == "day" else o["partner_id"]
            first = min(ships[o["id"]]) if ships[o["id"]] else None
            a = acc[k]
            a["due_count"] += 1
            if first is not None:
                a["shipped_count"] += 1
                a["on_time" if first <= o["due_date"] else "late"] += 1
            elif o["due_date"] < today:
                a["late"] += 1
            else:
                a["pending"] += 1
        return [{key: k, "due_count": a["due_count"], "shipped_count": a["shipped_count"], "on_time": a["on_time"], "late": a["late"], "pending": a["pending"],
                 "on_time_rate": _pct(a["on_time"], a["on_time"] + a["late"])} for k, a in acc.items()]

    def my_equipment(self, frm, to) -> list[dict]:
        now = self.conn.q1("select now() as n")["n"]
        ws = self.conn.q1("select (%s::date)::timestamptz as t", (frm,))["t"]          # [frm 00:00, to+1일 00:00) — 세션 시간대
        we = self.conn.q1("select ((%s::date) + 1)::timestamptz as t", (to,))["t"]
        eqs = self.conn.q("select id from bas_equipment where use_yn = 'Y'")
        logs = self.conn.q("select equipment_id, state, started_at, ended_at from eqp_run_log")
        faults = self.conn.q("select equipment_id, occurred_at, fixed_at from eqp_fault where occurred_at::date between %s and %s", (frm, to))
        out = []
        for e in eqs:
            sec = Counter()
            stop_count = 0
            cur_state, cur_start = None, None
            for g in logs:
                if g["equipment_id"] != e["id"]:
                    continue
                end = g["ended_at"] or now
                if g["ended_at"] is None and (cur_start is None or g["started_at"] > cur_start):
                    cur_state, cur_start = g["state"], g["started_at"]
                lo, hi = max(g["started_at"], ws), min(end, we)
                if g["started_at"] < we and end > ws:
                    sec[g["state"]] += (hi - lo).total_seconds()
                    if g["state"] == "정지" and g["started_at"] >= ws:
                        stop_count += 1
            fs = [f for f in faults if f["equipment_id"] == e["id"]]
            fixed = [(f["fixed_at"] - f["occurred_at"]).total_seconds() / 3600.0 for f in fs if f["fixed_at"] is not None]
            logged = sec["가동"] + sec["정지"] + sec["점검"] + sec["고장"]
            out.append({"equipment_id": e["id"], "run_seconds": sec["가동"], "stop_seconds": sec["정지"], "check_seconds": sec["점검"], "fault_seconds": sec["고장"],
                        "logged_seconds": logged, "run_rate": _pct(sec["가동"], logged), "stop_count": stop_count, "fault_count": len(fs),
                        "mttr_hours": (sum(fixed) / len(fixed)) if fixed else None, "current_state": cur_state})
        return out

    def my_measure(self, key, frm, to, by, agg) -> list[dict]:
        rows = self.conn.q("select m.id, m.value_num, m.deviated, m.measured_at, m.measured_at::date as day, r.work_order_id, r.equipment_id "
                           "from pop_measure m join pop_work_result r on r.id = m.work_result_id "
                           "where m.param_key = %s and m.value_num is not null and m.measured_at::date between %s and %s", (key, frm, to))
        col = {"day": "day", "work_order": "work_order_id", "equipment": "equipment_id"}[by]
        groups: dict = defaultdict(list)
        for r in rows:
            groups[r[col]].append(r)
        out = []
        for k, rs in groups.items():
            vals = [float(r["value_num"]) for r in rs]
            if agg == "avg":
                val = sum(vals) / len(vals)
            elif agg == "min":
                val = min(vals)
            elif agg == "max":
                val = max(vals)
            elif agg == "sum":
                val = sum(vals)
            elif agg == "count":
                val = len(vals)
            else:
                val = float(max(rs, key=lambda r: (r["measured_at"], r["id"]))["value_num"])
            out.append({col: k, "value": val, "n": len(rs), "deviated_count": sum(1 for r in rs if r["deviated"]), "min_value": min(vals), "max_value": max(vals)})
        return out

    def my_core_metrics(self, frm, to, today) -> dict:
        p = self.my_production(frm, to, "day")
        g = sum((r["good_qty"] or 0) for r in p) if any(r["good_qty"] is not None for r in p) else None
        d = sum((r["defect_qty"] or 0) for r in p) if any(r["defect_qty"] is not None for r in p) else None
        plan = sum((r["plan_qty"] or 0) for r in p) if any(r["plan_qty"] is not None for r in p) else None
        q = self.my_quality(frm, to, "day")
        dl = self.my_delivery(frm, to, "day", today)
        e = self.my_equipment(frm, to)
        on, late = sum(r["on_time"] for r in dl), sum(r["late"] for r in dl)
        return {"production.achieve_rate": _pct(g, plan) if p else None,
                "production.good_rate": (_pct(g, (g or 0) + (d or 0)) if (g is not None or d is not None) else None) if p else None,
                "quality.pass_rate": _pct(sum(r["pass_count"] for r in q), sum(r["inspection_count"] for r in q)) if q else None,
                "delivery.on_time_rate": _pct(on, on + late) if dl else None,
                "equipment.run_rate": _pct(sum(r["run_seconds"] for r in e), sum(r["logged_seconds"] for r in e)) if e else None}

    # ── G-C05 쓰기 경계 ───────────────────────────────────────────────
    def write_boundary(self) -> None:
        core = set(self.tables)
        allowed, col_rules = expected_boundary(core)
        writes, fn_writes, dyn = scan_core_writes(core)
        viol, col_viol, direct_gen = [], [], []
        for router, items in sorted(writes.items()):
            exp = allowed.get(router)
            if exp is None:
                if items:
                    viol.append(f"{router}: §2 표에 없는 라우터인데 씀 {sorted({t for t, _, _ in items})}")
                continue
            for tbl, how, cols in items:
                if tbl not in exp:
                    viol.append(f"{router}:{tbl}({how})")
                elif tbl in col_rules.get(router, {}) and how == "update" and cols is not None:
                    extra = set(cols) - col_rules[router][tbl] - {"updated_at", "updated_by"}
                    if extra:
                        col_viol.append(f"{router}:{tbl}.{sorted(extra)}")
                if tbl == "lot_genealogy" and how != "lineage":
                    direct_gen.append(f"{router}:{how}")
        module_viol = [f"{m}:{sorted(t)}" for m, t in fn_writes.items() if t - MODULE_WRITES.get(m, set())]
        gen_writers = []
        for f in sorted(list(SRC.rglob("*.py")) + list(PACKS.rglob("*.py"))):
            if "__pycache__" in f.parts or f.name == "lineage.py" or "tools" in f.parts or "tests" in f.parts:
                continue
            if re.search(r"\b(insert\s+into|update|delete\s+from|merge\s+into|truncate(\s+table)?)\s+\"?lot_genealogy\b", f.read_text(encoding="utf-8", errors="replace"), re.I):
                gen_writers.append(str(f.relative_to(ROOT)))
        emit("G-C05", "라우터별 쓰기 SQL 정적 스캔 = db-schema.md §2", not viol and not col_viol,
             f"라우터 {len(writes)} · 직접 SQL + lineage/measure/collect/erp/stats/numbering 호출을 테이블로 펼침 · 동적 테이블 {dyn or 0} — "
             f"경계 밖 {viol or 0} · 컬럼 제한(t.col) 밖 UPDATE {col_viol or 0} · trc {sorted({t for t, _, _ in writes.get('trc', [])}) or 0} · "
             f"kpi {sorted({t for t, _, _ in writes.get('kpi', [])})} (kpi_indicator 만)")
        emit("G-C05", "공용 모듈 쓰기 = 계약", not module_viol, f"lineage · measure · collect · erp · stats · numbering · audit · auth · main · printing · templating 의 쓰기 테이블 계약 밖 {module_viol or 0}")
        emit("G-C05", "lot_genealogy 쓰는 코드 = lineage.py 뿐", not gen_writers and not direct_gen,
             f"src/mescore(도구 제외) + packs/ 전 .py 에서 lot_genealogy INSERT/UPDATE/DELETE 하는 다른 파일 {gen_writers or 0} · 라우터 직접 SQL {direct_gen or 0}")

    def read_diff(self, label: str) -> None:
        from mescore.app import nav
        a = self.api("admin")
        urls: list[tuple[str, dict]] = []
        for s in nav.ALL:
            if s.screen_id in ("CMN-01", "CMN-03"):
                continue
            urls.append((s.probe or s.path, {}))
        c = self.ctx
        lots = self.conn.q("select id, lot_no, kind_base from lot order by id")
        for l in lots[:60]:
            urls += [(nav.path_of("TRC-01"), {"no": l["lot_no"]}), (nav.path_of("TRC-02"), {"no": l["lot_no"]}),
                     (nav.path_of("POP-04"), {"lot": l["id"]}), (nav.path_of("QUA-02"), {"no": l["lot_no"]})]
            if l["kind_base"] == "MATERIAL":
                urls += [(f"{nav.path_of('MAT-03')}/{l['id']}/label", {}), (nav.path_of("MAT-02"), {"no": l["lot_no"]})]
        urls.append((nav.path_of("TRC-03"), {"q": "P"}))
        for k in ("production", "quality", "delivery", "equipment"):
            urls.append((nav.path_of("KPI-02"), {"kind": k}))
        urls += [(nav.path_of("KPI-01"), {"device": "board"}), (nav.path_of("JOB-02"), {"range": "week"})]
        for w in self.conn.q("select id, work_order_no from job_work_order order by id limit 30"):
            urls += [(nav.path_of("JOB-03"), {"id": w["id"]}), (nav.path_of("JOB-02"), {"wo": w["id"]}), (nav.path_of("POP-02"), {"wo": w["id"]})]
        for r in self.conn.q("select id from pop_work_result order by id limit 30"):
            urls += [(nav.path_of("POP-02"), {"id": r["id"]}), (nav.path_of("POP-03"), {"result": r["id"]})]
        for s in self.conn.q("select id, shipment_no from shp_shipment order by id"):
            urls += [(nav.path_of("SHP-02"), {"no": s["shipment_no"]}), (f"{nav.path_of('SHP-01')}/{s['id']}/label", {})]
        for d in self.conn.q("select id from shp_document order by id"):
            urls.append((f"{nav.path_of('SHP-04')}/{d['id']}/print", {}))
        for kind in ("item", "partner", "equipment", "lot", "worker"):
            urls.append((f"/popup/{kind}", {"q": "EX"}))
        if c.get("eq"):
            urls.append((nav.path_of("EQP-04"), {"equipment_id": c["eq"]}))
        before = self.biz_state()
        n_req, codes = 0, Counter()
        for url, params in urls:
            for html in (False, True):
                r = a.get(url, params=params, status=None, html=html)
                n_req += 1
                codes[r.status_code // 100] += 1
        after = self.biz_state()
        diff = {t: (before[t], after[t]) for t in self.biz if before[t] != after[t]}
        emit("G-C05", f"조회 화면 전후 업무 테이블 {len(self.biz)} diff 0 ({label})", not diff,
             f"GET {n_req}회(화면 · 추적 · 라벨 · 인쇄 · 팝업 · 집계 — JSON+HTML) 응답 {dict(codes)} · 행 수 · 최종 수정 시각 바뀐 테이블 {diff or 0}")

    # ── G-C12 범위 밖 0 ───────────────────────────────────────────────
    def out_of_scope(self) -> None:
        from mescore.app import nav, packs
        app = self.app

        def walk(routes=None, prefix: str = "") -> list[tuple[str, str]]:
            out = []
            for rt in (app.routes if routes is None else routes):
                inner = getattr(rt, "original_router", None)
                if inner is not None:
                    ctx = getattr(rt, "include_context", None)
                    out += walk(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
                else:
                    for m in (getattr(rt, "methods", None) or ()):
                        out.append((m, prefix + getattr(rt, "path", "")))
            return out

        routes = sorted({(m, p) for m, p in walk() if m not in ("HEAD", "OPTIONS")})
        ctrl_re = re.compile(r"(control|command|cmd|setpoint|actuat|write[_-]?tag|plc|mqtt|modbus|opc|start[_-]?machine|stop[_-]?machine|run[_-]?machine|"
                             r"remote|ai|agent|predict|제어|명령|지령)", re.I)
        ctrl = [f"{m} {p}" for m, p in routes if any(ctrl_re.fullmatch(seg) or re.search(r"(control|command|setpoint|actuat|write[_-]?tag|plc|mqtt|modbus|제어|명령)", seg, re.I)
                                                      for seg in re.split(r"[/{}_-]+", p) if seg)]
        eqp_writes = sorted(p for m, p in routes if m == "POST" and p.startswith("/eqp"))
        forb = [w for ws in packs.current().core.get("forbidden_terms", {}).values() for w in ws] if hasattr(packs.current(), "core") else []
        if not forb:
            import yaml
            forb = [w for ws in (yaml.safe_load((SRC / "core.yaml").read_text(encoding="utf-8")).get("forbidden_terms") or {}).values() for w in ws]
        cols = self.conn.q("select table_name, column_name from information_schema.columns where table_schema = 'public'")
        db_tables = {r["table_name"] for r in self.conn.q("select table_name from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE'")}
        spec = spec_tables()
        names = [p for _, p in routes] + sorted(db_tables) + [f"{r['table_name']}.{r['column_name']}" for r in cols] + [s.name for s in nav.ALL] + [m.name for m in nav.ALL_MENUS]
        def hit(word: str, text: str) -> bool:
            if re.fullmatch(r"[A-Za-z]+", word):
                return re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text) is not None          # 대소문자 구분 — 코어 모듈 코드 `job` 은 spec §2.1 의 것
            return word in text
        term_hits = sorted({f"{w}@{n}" for n in names for w in forb if hit(w, n)})
        libs = []
        for f in sorted((SRC / "app").rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            txt = f.read_text(encoding="utf-8", errors="replace")
            for lib in ("requests", "httpx", "urllib.request", "socket", "paho", "pymodbus", "serial", "opcua", "asyncua", "snap7", "pycomm3", "openai", "anthropic"):
                if re.search(rf"^\s*(import|from)\s+{re.escape(lib)}\b", txt, re.M):
                    libs.append(f"{f.relative_to(SRC)}:{lib}")
        ok = not ctrl and db_tables == spec and len(spec) == 52 and not term_hits and not libs and set(eqp_writes) <= EQP_POST_OK
        emit("G-C12", "범위 밖 0 — 제어 · 업종 전용 기능", ok,
             f"라우트 {len(routes)} 중 제어 · 명령성 {ctrl or 0} · /eqp 쓰기 {eqp_writes} (상태 기록 · 점검 · 고장만) · DB 테이블 {len(db_tables)} = spec §2.2 {len(spec)} "
             f"(빠짐 {sorted(spec - db_tables) or 0} · 더함 {sorted(db_tables - spec) or 0}) · 경로/테이블/컬럼/메뉴/화면 이름의 금지어 {term_hits[:5] or 0} · "
             f"외부 장치 · 연계 · AI 라이브러리 import {libs or 0}")


EQP_POST_OK = {"/eqp/status", "/eqp/checks", "/eqp/faults", "/eqp/faults/{id}/fix"}

#: 공용 모듈이 쓸 수 있는 테이블 — interfaces.md §4~§7 · db-schema.md §2 「공통」 행
MODULE_WRITES: dict[str, set[str]] = {
    "lineage": {"lot", "lot_genealogy", "pop_input", "pop_work_result", "mat_stock", "mat_stock_trx"},
    "measure": {"pop_measure"},
    "collect": {"ifc_collect_raw", "eqp_collect"},
    "erp": {"ifc_outbox", "ifc_erp_link"},
    "stats": {"kpi_snapshot"},
    "numbering": {"sys_number_seq"},
    "audit": {"sys_access_log"},
    "auth": {"sys_session", "sys_access_log", "sys_user"},
    "main": {"ifc_outbox", "sys_access_log"},
    "templating": {"sys_access_log"},
    "rbac": {"sys_session"},
}
#: 라우터가 부르는 공용 쓰기 함수 → 그 함수가 쓰는 테이블 (호출한 라우터의 쓰기로 센다)
CALL_WRITES: dict[str, set[str]] = {
    r"lineage\.make_material_lot": {"lot"},
    r"lineage\.make_product_lot": {"lot", "lot_genealogy", "pop_work_result"},
    r"lineage\.(consume_material|cancel_consume)": {"pop_input", "mat_stock", "mat_stock_trx"},
    r"lineage\.(split|merge|ship)": {"lot", "lot_genealogy"},
    r"lineage\.(unship|link)": {"lot_genealogy"},
    r"lineage\.retag": {"lot"},
    r"measure\.(record|fill_collect)": {"pop_measure"},
    r"collect\.receive": {"ifc_collect_raw", "eqp_collect"},
    r"erp\.(enqueue|flush|retry)": {"ifc_outbox", "ifc_erp_link"},
    r"stats\.snapshot": {"kpi_snapshot"},
}
WRITE_SQL = re.compile(r"\b(insert\s+into|update|delete\s+from|merge\s+into|truncate(?:\s+table)?)\s+\"?([a-z_][a-z0-9_]*)\"?(?:\s+(?:as\s+)?[a-z]\w*)?\s*(set\s+(.*?)(?:\s+where\b|\s+from\b|\s+returning\b|\"\"\"|\"\s*,|\)\s*$|$))?",
                       re.I | re.S)


def _set_cols(text: str | None) -> list[str] | None:
    if not text:
        return None
    return re.findall(r"(?:^|,)\s*([a-z_][a-z0-9_]*)\s*=", text, re.I)


def scan_text_writes(text: str, core: set[str]) -> list[tuple[str, str, list[str] | None]]:
    out = []
    for m in WRITE_SQL.finditer(text):
        tbl = m.group(2).lower()
        if tbl not in core:
            continue
        how = m.group(1).split()[0].lower()
        out.append((tbl, how, _set_cols(m.group(4)) if how == "update" else None))
    return out


def scan_core_writes(core: set[str]):
    writes: dict[str, list] = {}
    dyn: list[str] = []
    for f in sorted((SRC / "app" / "routers").glob("*.py")):
        if f.name == "__init__.py":
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        items = scan_text_writes(txt, core)
        for pat, tbls in CALL_WRITES.items():
            if re.search(pat + r"\(", txt):
                items += [(t, "lineage" if pat.startswith(r"lineage") else "call", None) for t in tbls]
        if re.search(r"(insert\s+into|update|delete\s+from)\s+\{", txt, re.I):
            masters = re.findall(r"Master\(\s*\"[A-Z]+-\d+\",\s*\"(\w+)\"", txt)
            dyn.append(f"{f.stem}:{{m.table}}→{len(masters)}")
            items += [(t, "dynamic", None) for t in masters]
        writes[f.stem] = items
    fn_writes: dict[str, set[str]] = {}
    for f in sorted(list((SRC / "app").glob("*.py")) + list((SRC / "app" / "util").glob("*.py"))):
        txt = f.read_text(encoding="utf-8", errors="replace")
        t = {x[0] for x in scan_text_writes(txt, core)}
        if t:
            fn_writes[f.stem] = t
    return writes, fn_writes, dyn


def expected_boundary(core: set[str]) -> tuple[dict[str, set[str]], dict[str, dict[str, set[str]]]]:
    """db-schema.md §2 표 → (라우터 → 쓸 수 있는 테이블, 라우터 → {테이블: 허용 컬럼}) · `공통` 행은 모든 라우터에 더한다."""
    text = (ROOT / "contracts" / "db-schema.md").read_text(encoding="utf-8")
    m = re.search(r"^## 2\..*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    allowed: dict[str, set[str]] = {}
    cols: dict[str, dict[str, set[str]]] = {}
    common: set[str] = set()
    for ln in (m.group(1) if m else "").splitlines():
        if not ln.startswith("|"):
            continue
        cells = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(cells) < 3 or set("".join(cells)) <= set("-: ") or cells[0] == "모듈":
            continue
        tbls: set[str] = set()
        colr: dict[str, set[str]] = {}
        for tok in re.findall(r"`([a-z_][a-z0-9_*.]*)`", cells[2]):
            if tok.endswith("_*"):
                tbls |= {t for t in core if t.startswith(tok[:-1])}
            elif "." in tok:
                t, col = tok.split(".", 1)
                if t in core:
                    tbls.add(t)
                    colr.setdefault(t, set()).add(col)
            elif tok in core:
                tbls.add(tok)
        if cells[0].replace("*", "") == "공통":
            common |= tbls
            continue
        for r in re.findall(r"`([a-z_]+)`", cells[1]):
            allowed.setdefault(r, set()).update(tbls)
            for t, cs in colr.items():
                cols.setdefault(r, {}).setdefault(t, set()).update(cs)
    allowed["trc"], allowed["kpi"] = set(), {"kpi_indicator"}                      # goal.md G-C05 문장 그대로
    allowed.setdefault("dashboard", set())
    allowed.setdefault("popup", set())
    allowed.setdefault("home", set())
    allowed.setdefault("_dev2", set())
    for r in allowed:
        if r not in ("trc", "dashboard"):                                         # trc · 대시보드는 '어떤 테이블에도' — 공통 행도 주지 않는다
            allowed[r] |= common
    # 컬럼 제한은 그 테이블이 다른 이유로 통째 허용되지 않을 때만 (mat: lot 은 생성 + insp_status)
    for r, d in cols.items():
        for t in list(d):
            if r == "mat" and t == "lot":
                d.pop(t)
    return allowed, cols


def _fmt_regex(pg: str) -> str:
    """to_char 형식 → 정규식 (YYYY YY MM DD HH24 MI 만 숫자, 나머지는 글자 그대로)."""
    out, i = "", 0
    while i < len(pg):
        for tok, n in (("YYYY", 4), ("HH24", 2), ("YY", 2), ("MM", 2), ("DD", 2), ("MI", 2)):
            if pg.startswith(tok, i):
                out += rf"\d{{{n}}}"
                i += len(tok)
                break
        else:
            out += re.escape(pg[i])
            i += 1
    return out


def _pct(n, d) -> float | None:
    if d in (None, 0) or (isinstance(d, (int, float, Decimal)) and float(d) == 0):
        return None
    return float(Decimal(str(n or 0)) / Decimal(str(d)) * 100)


def _norm_key(k):
    if isinstance(k, datetime):
        return k.date().isoformat()
    if isinstance(k, date):
        return k.isoformat()
    return k


def _cmp_rows(label: str, got: list[dict], mine: list[dict], key: str, fields: tuple[str, ...], tol: float = 1e-6) -> list[str]:
    g = {_norm_key(r.get(key)): r for r in got}
    m = {_norm_key(r.get(key)): r for r in mine}
    errs = []
    if set(g) != set(m):
        errs.append(f"{label}: 키 stats {sorted(map(str, g))[:5]} ≠ 내 {sorted(map(str, m))[:5]}")
    for k in set(g) & set(m):
        for f in fields:
            a, b = g[k].get(f), m[k].get(f)
            if isinstance(a, str) or isinstance(b, str):
                if a != b:
                    errs.append(f"{label} {k} {f}: {a} ≠ {b}")
            elif f.endswith("seconds"):
                if not (a is None and b is None) and (a is None or b is None or abs(float(a) - float(b)) > 3.0):
                    errs.append(f"{label} {k} {f}: {a} ≠ {b}")
            elif not close(a, b, tol):
                errs.append(f"{label} {k} {f}: {a} ≠ {b}")
    return errs


# ════════════════════════════════════════════════════════════════════════
# 팩 — G-P04 시나리오를 내 SQL 로 · write_scope 정적 스캔
# ════════════════════════════════════════════════════════════════════════
def pack_scope_scan(pack: str, core: set[str]) -> None:
    import yaml
    man = yaml.safe_load((PACKS / pack / "pack.yaml").read_text(encoding="utf-8")) or {}
    scope = man.get("write_scope") or {}
    ext = {r for r in re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(x_\w+)", (PACKS / pack / "schema_ext.sql").read_text(encoding="utf-8"), re.I)} \
        if (PACKS / pack / "schema_ext.sql").exists() else set()
    viol, n_files, gen = [], 0, []
    for f in sorted((PACKS / pack).rglob("*.py")):
        if "__pycache__" in f.parts or "tests" in f.parts:
            continue
        n_files += 1
        rel = f.relative_to(PACKS / pack)
        txt = f.read_text(encoding="utf-8", errors="replace")
        mod = rel.stem if rel.parts[0] == "routers" else ("hooks" if rel.stem in ("hooks", "alarm", "common") else rel.stem)
        allowed = set(scope.get(mod) or []) | ({t for v in scope.values() for t in (v or [])} if rel.parts[0] not in ("routers",) and mod not in scope else set())
        items = scan_text_writes(txt, core | ext)
        for pat, tbls in CALL_WRITES.items():
            if re.search(pat + r"\(", txt):
                items += [(t, "call", None) for t in tbls if t in ("lot", "lot_genealogy")]
        for tbl, how, _ in items:
            if tbl.startswith(f"x_{pack}_"):
                continue
            if tbl == "lot_genealogy" and how != "call":
                gen.append(f"{rel}:{how}")
            if tbl not in allowed:
                viol.append(f"{rel}:{tbl}({how})")
    seeds = [str(f.relative_to(PACKS / pack)) for f in (PACKS / pack).rglob("seed*.py")]
    emit("G-P01", f"[{pack}] write_scope 밖 쓰기 정적 스캔 (QA2)", not viol and not gen,
         f"파일 {n_files} · write_scope {dict((k, v) for k, v in scope.items())} · 밖 {sorted(set(viol))[:8] or 0} · lot_genealogy 직접 {gen or 0} · 시드 스크립트 {seeds or 0}(시드는 write_scope 대상 밖으로 봄)")


def pack_scenarios(pack: str, conn, label: str) -> None:
    """팩 DB 의 데이터(팩 시나리오 테스트가 남긴 것)를 내 SQL 로 대조 — 개발 테스트의 단언은 보지 않는다."""
    readonly = "읽기" in label
    def trace(lot_id: int, direction: str):
        nodes = {r["lot_id"]: r["d"] for r in conn.q(SQL_UP if direction == "backward" else SQL_DOWN, {"id": lot_id})}
        edges = conn.q(SQL_EDGES_INTO if direction == "backward" else SQL_EDGES_FROM, {"ids": list(nodes)})
        return nodes, edges

    import yaml
    gates = yaml.safe_load((PACKS / pack / "gates.yaml").read_text(encoding="utf-8")) or {}
    S = {str(x.get("id")): (x.get("expect") or {}) for x in gates.get("scenarios") or []}    # 기대값은 gates.yaml 에서만 (코어 파일에 팩 용어를 쓰지 않는다)

    if pack == "printfilm":
        E = S.get("S1", {})
        best = None
        for x in conn.q("select id, lot_no from lot where kind_base = 'SHIPMENT' order by id desc limit 200"):
            up, up_e = trace(x["id"], "backward")
            mats = [i for i, k in ((r["id"], r["kind_base"]) for r in conn.q("select id, kind_base from lot where id = any(%s)", (list(up),))) if k == "MATERIAL"]
            if len(mats) != E.get("backward_materials") or len(up_e) != E.get("backward_edges"):
                continue
            ids = set(up)
            for m in mats:
                ids |= set(trace(m, "forward")[0])
            rows = conn.q("select relation, relation_base, parent_lot_id from lot_genealogy where parent_lot_id = any(%(i)s) and child_lot_id = any(%(i)s)", {"i": list(ids)})
            rel, base = Counter(r["relation"] for r in rows), Counter(r["relation_base"] for r in rows)
            m1 = min(mats)
            fw_nodes, fw_e = trace(m1, "forward")
            pack_kinds = conn.q1("select count(*) as n from lot where id = any(%s) and kind <> kind_base", (list(ids),))["n"]     # 팩 LOT 종류
            st = Counter(r["state"] for r in conn.q("select state from v_lot_state where lot_id = any(%s) and kind_base = 'PRODUCT'", (list(ids),)))
            fwd_edges = max(len(trace(m, "forward")[1]) for m in mats)
            best = (x["lot_no"], len(rows), dict(rel), dict(base), len(up_e), fwd_edges, pack_kinds, dict(st))
            break
        if best is None:
            emit("G-P04", f"[printfilm] S1 계보 10행 (내 SQL · {label})", FAIL, "원재료 2 · 역방향 화살표 9 인 출하 LOT 이 DB 에 없다 — 시나리오 데이터 없음")
            return
        no, n, rel, base, bw, fw, rolls, st = best
        exp_st = {"소진": E.get("consumed_lots"), "출하": E.get("shipped_lots"), "재고": E.get("stock_lots")}
        ok = n == E.get("genealogy_rows") and rel == E.get("by_relation") and base == E.get("by_relation_base") and bw == E.get("backward_edges") \
            and fw == E.get("forward_edges_from_m1") and rolls == E.get("roll_lots") and st == exp_st
        emit("G-P04", f"[printfilm] S1 계보 10행 (내 SQL · {label})", ok,
             f"출하 LOT {no} — 행 {n} · relation {rel} · base {base} · 역방향 화살표 {bw} · 정방향(M①) {fw} · 팩 종류 LOT {rolls} · 상태 {st} "
             f"(gates.yaml S1.expect: {E.get('genealogy_rows')} · {E.get('by_relation')} · {E.get('backward_edges')} · {E.get('forward_edges_from_m1')} · {E.get('roll_lots')} · {exp_st})")
    elif pack == "foodservice":
        rows = conn.q("""select r.period_from, i.item_code, r.required_qty, r.stock_qty, r.shortage_qty from mat_requirement r join bas_item i on i.id = r.item_id
                          where r.source = 'hook' and i.item_code in ('MAT-1001', 'MAT-1002') order by r.period_from, r.id""")
        bad_short = [f"{r['period_from']} {r['item_code']}" for r in rows if not close(r["shortage_qty"], max(float(r["required_qty"]) - float(r["stock_qty"]), 0))]
        first = rows[0]["period_from"] if rows else None
        got = {r["item_code"]: (dnum(r["required_qty"]), dnum(r["stock_qty"]), dnum(r["shortage_qty"])) for r in rows if r["period_from"] == first}
        exp = {"MAT-1001": (1200 * 12.0 / 100, 120.0, 1200 * 12.0 / 100 - 120.0), "MAT-1002": (1200 * 3.5 / 100, 80.0, 0.0)}   # gates.yaml 산식 그대로
        ok_req = got == exp and not bad_short
        emit("G-P04", f"[foodservice] S1 소요량 144/120/24 (내 SQL · {label})", ok_req,
             f"mat_requirement(source=hook) 첫 기간 {first} {got or '없음'} · 내 산식 1200×12.000/100 · 1200×3.500/100 → {exp} · 전 {len(rows)}행 중 부족 ≠ max(소요−가용,0) {bad_short or 0}")
        # 배치 측정값 — eqp_collect 를 실적 구간으로 내가 다시 집계해 pop_measure 와 대조
        # 회전 6: 측정값을 쓴 시각(m.created_at)까지 들어온 수집 행만 센다 — 뒤에 늦게 들어온 행(과거 ts)은 그 실적의 대표값 근거가 아니다.
        # 읽기 전용(누적 팩 DB)에서는 팩 테스트 _helpers 가 지난 실행의 eqp_collect 를 지우므로, 근거 행이 0 인데 값이 있는 실적은 「근거 지워짐」 으로 따로 센다.
        mism, n, gone = [], 0, []
        for r in conn.q("""select m.work_result_id, m.param_key, m.value_num, m.created_at as m_at, p.agg, coalesce(p.collect_tag, p.param_key) as tag, w.equipment_id, w.started_at, w.ended_at
                             from pop_measure m join bas_process_param p on p.id = m.param_id join pop_work_result w on w.id = m.work_result_id
                            where m.source = 'collect' and w.ended_at is not null order by m.id desc limit 60"""):
            vals = conn.q("""select value_num, ts from eqp_collect where equipment_id = %s and tag = %s and ts >= %s and ts <= %s and value_num is not null
                              and created_at <= %s order by ts""",
                          (r["equipment_id"], r["tag"], r["started_at"], r["ended_at"], r["m_at"]))
            v = [float(x["value_num"]) for x in vals]
            exp = None if not v else {"avg": sum(v) / len(v), "max": max(v), "min": min(v), "last": v[-1]}.get(r["agg"] or "last")
            if readonly and not v and r["value_num"] is not None:
                gone.append(r["work_result_id"])
                continue
            n += 1
            if not close(dnum(r["value_num"]), exp, 1e-6):
                mism.append(f"실적 {r['work_result_id']} {r['param_key']} {dnum(r['value_num'])} ≠ 내 {exp}")
        s1 = conn.q("""select m.param_key, m.value_num from pop_measure m where m.work_result_id = (select m2.work_result_id from pop_measure m2 where m2.param_key = 'TEMP'
                         and m2.value_num = 161.25 order by m2.id desc limit 1)""")
        emit("G-P04", f"[foodservice] S1 배치 측정값 = eqp_collect 재집계 (내 SQL · {label})", n > 0 and not mism,
             f"collect 측정값 {n}행 재집계 불일치 {mism[:3] or 0}{f' · 근거 수집 행이 지워진 실적 {sorted(set(gone))[:5]} 제외(팩 테스트 정리)' if gone else ''} · S1 실적① 값 {({r['param_key']: dnum(r['value_num']) for r in s1}) or '없음'} (gates.yaml: RPM 73.5 · STIR_TIME 30 · TEMP 161.25)")
        bad = []
        for x in conn.q("select id, lot_no from lot where kind_base = 'SHIPMENT' order by id desc limit 50"):
            up, up_e = trace(x["id"], "backward")
            kinds = Counter(r["kind_base"] for r in conn.q("select kind_base from lot where id = any(%s)", (list(up),)))
            if kinds.get("MATERIAL") == 2 and len(up_e) == 6:
                bad = None
                emit("G-P04", f"[foodservice] S1 계보 6행 · 역추적 원료 2 (내 SQL · {label})", True, f"출하 LOT {x['lot_no']} — 역방향 화살표 {len(up_e)} · 원료 LOT {kinds['MATERIAL']} · 배치 {kinds.get('PRODUCT')}")
                break
        if bad is not None:
            emit("G-P04", f"[foodservice] S1 계보 6행 · 역추적 원료 2 (내 SQL · {label})", FAIL, "역방향 화살표 6 · 원료 2 인 출고 LOT 없음")
    elif pack == "kimchi":
        hit = None
        for x in conn.q("select id, lot_no from lot where kind_base = 'SHIPMENT' order by id desc limit 100"):
            up, up_e = trace(x["id"], "backward")
            info = {r["id"]: r for r in conn.q("select l.id, l.kind, l.kind_base, s.state from lot l join v_lot_state s on s.lot_id = l.id where l.id = any(%s)", (list(up),))}
            mats = [i for i, r in info.items() if r["kind_base"] == "MATERIAL"]
            tanks = [i for i, r in info.items() if r["kind"] == "TANK"]
            if len(mats) == 3 and len(tanks) == 2:
                depth = max(up.values())
                hit = (x["lot_no"], len(up_e), len(mats), depth, len(tanks), sorted({info[t]["state"] for t in tanks}), Counter(e["relation"] for e in up_e))
                tank_results = conn.q("select work_result_id from lot where id = any(%s)", (tanks,))
                sal = conn.q1("select count(*) as n from pop_measure where param_key = 'salinity_pct' and work_result_id = any(%s)", ([r["work_result_id"] for r in tank_results],))["n"]
                p1 = conn.q("select distinct g.parent_lot_id as id from lot_genealogy g where g.child_lot_id = any(%s) and g.relation_base = '투입'", (tanks,))
                p1s = [conn.q1("select s.remain_qty, t.state from v_lot_stock s join v_lot_state t on t.lot_id = s.lot_id where s.lot_id = %s", (r["id"],)) for r in p1]
                ids = set(up) | {r["id"] for r in p1}
                n_rows = conn.q1("select count(*) as n from lot_genealogy where parent_lot_id = any(%(i)s) and child_lot_id = any(%(i)s)", {"i": list(ids)})["n"]
                hit += (sal, n_rows, [(dnum(x["remain_qty"]), x["state"]) for x in p1s])
                break
        if hit is None:
            emit("G-P04", f"[kimchi] S1 계보 · 역추적 (내 SQL · {label})", FAIL, "원재료 3 · TANK 2 에 닿는 출하 LOT 없음")
        else:
            no, ne, nm, d, nt, tst, rel, sal, n_rows, p1 = hit
            ok = nm == 3 and d == 5 and nt == 2 and tst == ["소진"] and sal == 2
            emit("G-P04", f"[kimchi] S1 계보 · 역추적 (내 SQL · {label})", ok,
                 f"출하 LOT {no} — 역방향 화살표 {ne} {dict(rel)} · 원재료 {nm} · 최대 깊이 {d} · TANK {nt} 상태 {tst} · salinity_pct 측정값 {sal} "
                 f"(gates.yaml: backward_materials 3 · backward_depth 5 · tank_lots 2 · tank_state 소진 · salinity_measure_rows 2)")
            emit("G-P04", f"[kimchi] S1 행 수 · P1 잔량 = gates.yaml (내 SQL · {label})", n_rows == 9 and p1 == [(150.0, "재고")],
                 f"시나리오 LOT 사이 lot_genealogy {n_rows}행(gates.yaml genealogy_rows 9) · 전처리 P1 잔량/상태 {p1}(gates.yaml p1_remain_qty 150 · 재고)"
                 + ("" if n_rows == 9 and p1 == [(150.0, "재고")] else " — 기대값 출처(gates.yaml)와 재현이 다르다"))
        # S4 AGING 배치 — gates.yaml S4.expect (genealogy_delta 2 · aging_lot_kind AGING · k1_remain_qty 400) 를 내 SQL 로
        g = conn.q1("""select g.parent_lot_id as k1 from lot_genealogy g join lot a on a.id = g.child_lot_id
                        where g.relation_base = '분할' and a.kind = 'AGING' and g.qty = 600 order by g.id desc limit 1""")
        if g is None:
            emit("G-P04", f"[kimchi] S4 AGING (내 SQL · {label})", FAIL, "AGING 600 화살표 없음 — 시나리오 데이터 없음")
        else:
            k1 = conn.q1("select l.lot_no, l.qty, s.remain_qty, t.state from lot l join v_lot_stock s on s.lot_id = l.id join v_lot_state t on t.lot_id = l.id where l.id = %s", (g["k1"],))
            ch = conn.q("""select a.kind, a.kind_base, a.insp_status, g.relation, g.qty from lot_genealogy g join lot a on a.id = g.child_lot_id
                            where g.parent_lot_id = %s order by g.id""", (g["k1"],))
            age = [r for r in ch if r["kind"] == "AGING"]
            ok4 = len(ch) == 2 and age and all(r["kind_base"] == "PRODUCT" for r in age) and close(k1["remain_qty"], 400)
            emit("G-P04", f"[kimchi] S4 AGING — K1 잔량 · 자식 (내 SQL · {label})", ok4,
                 f"K1 {k1['lot_no']} qty {dnum(k1['qty'])} · v_lot_stock 잔량 {dnum(k1['remain_qty'])} · 상태 {k1['state']} · 자식 계보 {len(ch)} "
                 f"{[(r['relation'], r['kind'], dnum(r['qty']), r['insp_status']) for r in ch]} (gates.yaml S4: genealogy_delta 2 · aging_lot_kind AGING · base PRODUCT · k1_remain_qty 400)")
        if _has_table(conn, "x_kimchi_env_alarm"):
            al = conn.q("select * from x_kimchi_env_alarm order by id")
            cnt = [r.get("count") or r.get("alarm_count") or r.get("occur_count") for r in al]
            emit("G-P04", f"[kimchi] S3 알람 (내 SQL · {label})", len(al) >= 3 and any((c or 0) >= 2 for c in cnt),
                 f"x_kimchi_env_alarm 행 {len(al)} · 반복 이탈 합친 count {cnt[:6]} (gates.yaml: 행 3 · 첫 알람 count 2 — S3 1회분 기준)")


def _has_cols(conn, table: str, cols: tuple[str, ...]) -> bool:
    got = {r["column_name"] for r in conn.q("select column_name from information_schema.columns where table_name = %s", (table,))}
    return set(cols) <= got


def _has_table(conn, table: str) -> bool:
    return conn.q1("select 1 as x from information_schema.tables where table_name = %s", (table,)) is not None


def run_pack(pack: str, db: str, readonly: bool) -> None:
    core = set(schema_tables())
    pack_scope_scan(pack, core)
    if readonly:
        os.environ.update({"MES_PG_DSN": f"postgresql:///mes_{pack}_db", "MES_PACK": pack})
        from mescore.db import conn
        pack_scenarios(pack, conn, f"mes_{pack}_db 읽기")
        return
    import yaml
    rebuild(db, pack)
    env = child_env(db, pack)
    rc, out = run_seed(env)
    extra = PACKS / pack / "seed_pack.py"
    if rc == 0 and extra.exists():                                                  # 팩이 따로 둔 시드 한 벌(README) — 있으면 그것까지
        p = subprocess.run(["uv", "run", "python", str(extra)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        rc, out = p.returncode, (p.stdout + p.stderr).strip()
    if rc != 0:
        emit("G-P04", f"[{pack}] 팩 시드", FAIL, f"seed rc={rc} {out[-200:]}")
        return
    gates = yaml.safe_load((PACKS / pack / "gates.yaml").read_text(encoding="utf-8")) or {}
    ran = []
    for s in gates.get("scenarios") or []:
        test = s.get("test")
        if not test:
            continue
        p = subprocess.run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", str(PACKS / pack / test)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        last = [ln for ln in (p.stdout + p.stderr).strip().splitlines() if ln.strip()]
        ran.append(f"{s.get('id')}:{'ok' if p.returncode == 0 else 'FAIL'}")
        note(f"{pack} {s.get('id')} {test} → {last[-1] if last else ''}")
    emit("G-P04", f"[{pack}] 시나리오 테스트로 데이터 만들기 ({db})", all(x.endswith("ok") for x in ran), f"gates.yaml scenarios {ran} — 판정은 아래 내 SQL 행")
    os.environ.update({"MES_PG_DSN": env["MES_PG_DSN"], "MES_PACK": pack})
    from mescore.db import conn
    pack_scenarios(pack, conn, db)


# ════════════════════════════════════════════════════════════════════════
def main() -> int:
    global VERBOSE
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--run-seeds", action="store_true", help="gate-full 호환 — 시드는 늘 돈다")
    ap.add_argument("--pack")
    ap.add_argument("--pack-readonly")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose
    t0 = time.time()
    if args.pack or args.pack_readonly:
        run_pack(args.pack or args.pack_readonly, args.db, bool(args.pack_readonly))
    else:
        core = Core(args.db)

        def step(gid: str, item: str, fn, *a):
            """한 단계가 예외로 죽어도 그 게이트 FAIL 행을 남기고 다음 단계로 — 판정 행이 빠져 `미검증` 이 되지 않게."""
            try:
                return fn(*a)
            except Exception as exc:  # noqa: BLE001 — 예외 자체가 판정 근거(조용히 넘기지 않고 FAIL 로 찍는다)
                emit(gid, item, FAIL, f"검사 단계 예외 {type(exc).__name__}: {str(exc)[:240]}")
                return None

        if core.boot():
            step("G-C11", "빈 DB 화면", core.empty_screens)
            step("G-C05", "조회 전후 diff (빈 DB)", core.read_diff, "빈 DB")
            step("G-C09", "시드 멱등", core.seed_twice)
            step("G-C06", "기준정보 준비 (BAS API)", core.masters)
            if step("G-C06", "코어 시나리오 API 재현", core.scenario):
                step("G-C06", "lot_genealogy 10행", core.lineage_rows)
                step("G-C07", "추적 대조", core.trace_core)
                step("G-C08", "키 연결", core.key_links)
            else:
                for g, item in (("G-C07", "추적"), ("G-C08", "키 연결")):
                    emit(g, item, FAIL, "G-C06 시나리오 실패로 대조 대상 없음")
            step("G-C07", "임의 계보", core.trace_random)
            step("G-C24", "측정값", core.measure)
            step("G-C04", "뷰 검산 재료", core.view_material)
            step("G-C04", "뷰 검산", core.views)
            step("G-C04", "잔량 공격 (회전 5 새 경로)", core.stock_attack)
            step("G-C10", "집계 재계산", core.stats_recalc)
            step("G-C05", "쓰기 경계 정적 스캔", core.write_boundary)
            step("G-C05", "조회 전후 diff (채워진 DB)", core.read_diff, "채워진 DB")
            step("G-C12", "범위 밖 0", core.out_of_scope)
        for g in [f"G-C{i:02d}" for i in range(5, 13)] + ["G-C24"]:               # 어떤 게이트도 판정 행 없이 끝나지 않는다
            if not any(r[0] == g for r in ROWS):
                emit(g, "판정 행 없음", FAIL, "check_data 가 이 게이트를 재지 못했다 — 위 단계 오류 참조")
    fails = [r for r in ROWS if r[2] == FAIL]
    print(f"# check_data — 행 {len(ROWS)} · FAIL {len(fails)} · WARN {sum(1 for r in ROWS if r[2] == WARN)} · {time.time() - t0:.0f}s · DB {args.db}", flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
