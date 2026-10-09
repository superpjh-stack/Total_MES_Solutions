#!/usr/bin/env python
"""수용 게이트 판정표 — `make gate` (goal.md §2). 코어 단독 G-C01~G-C24 → packs/ 의 `_` 가 아닌 팩마다 G-P01~G-P06.

루프가 매 회전 부르는 것. **판정은 실제 명령의 출력으로만 한다.**
  · 검사기가 있으면 돌려서 그 출력의 `G-nn  항목  PASS|FAIL|WARN|BLOCKED|미검증  실측` 행을 읽는다 (interfaces.md §10).
  · QA 소유 검사기(`check_data` G-C05~12 · G-C24 · `check_security` G-C13~20 · `check_screens`)가 있으면 **그 출력이 우선**한다.
  · QA 검사기가 아직 없으면 **있는 증거로 판정한다**(회전 3 · D-30): 개발 테스트 파일을 그 파일만 pytest 로 돌리고(G-C06 · 07 · 24), 시드 LOT 하나로
    지시 · 실적 · 측정값 · 검사 · 출하를 SQL 로 잇고(G-C08), 양식 4 를 열어 `<svg` 와 바코드 값을 `lineage.resolve` 로 되읽고(G-C14), 이관 예시 세트를
    dry-run 2회 돌려 행 수 diff 를 재고(G-C15), `erp.flush` 가 501 을 `미확정` 으로 남기는지(G-C16), 접근 로그 4종 + SYS-04(G-C18), 라우터별 쓰기 SQL
    정적 스캔 + 조회 화면 전후 행 수 diff(G-C05), 시드 상태의 빈 목록 화면 표본(G-C11), 제어성 엔드포인트 grep(G-C12), 채널 레이아웃 · `data-scan`
    유일성(G-C13), 권한 48칸 + 역할 4 × 쓰기 기능 전부의 403 전수(G-C17), 저장소 비밀 grep(G-C19), `backup.py` 실행(G-C20).
    이 판정 줄에는 **"QA 대조 대기"** 를 붙인다 — 상태는 PASS/FAIL 이지만 QA 의 별도 SQL · 브라우저 대조가 남아 있다는 뜻이다.
  · **통과한 것처럼 보이게 하지 않는다.** 증거가 없으면 `미검증`, 증거가 어긋나면 FAIL. 기대값을 낮추지 않는다.
  · G-C10(집계 = QA 가 따로 짠 SQL)은 정의상 QA 없이는 `미검증` — 개발3 의 손계산 테스트(`tests/test_stats.py`) 결과만 실측에 적는다.
  · G-C22(브라우저 한 바퀴)는 QA3 리포트 `outputs/qa3-채널보안.md` 의 `G-C22  …  PASS|FAIL  …` 행을 읽는다.
  · 팩 DB `mes_<팩>_db` 가 없으면 그 팩의 게이트는 `미검증`(BLOCKED 가 아니다 — goal.md §3.1).
  · `decisions.md` 에 `상태: 차단` 으로 올라온 D-번호가 언급한 게이트는, 실측이 PASS/FAIL 이 아닐 때 `BLOCKED`.

    uv run python src/mescore/tools/gate.py               # 읽기 전용 판정표 (종료코드 0)
    uv run python src/mescore/tools/gate.py --run-seeds   # + 시드를 한 번 더 돌려 G-C09(행 수 diff 0)  (`make gate-full`)
    uv run python src/mescore/tools/gate.py --strict      # FAIL · 미검증이 있으면 종료코드 1
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import warnings
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = Path(__file__).resolve().parent
PACKS = ROOT / "packs"
SRC = ROOT / "src" / "mescore"
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")

PASS, FAIL, WARN, BLOCKED, UNVERIFIED = "PASS", "FAIL", "WARN", "BLOCKED", "미검증"
QA_DATA, QA_SEC = "QA 대조 대기 (check_data)", "QA 대조 대기 (check_security)"

CORE_GATES: list[tuple[str, str]] = [
    ("G-C01", "메뉴 — 코어 12 · 공통 5 · nav = core.yaml"),
    ("G-C02", "기능 — 132 + 이관 4 · 계약 = API = 테스트 · 고아 0"),
    ("G-C03", "화면 — 51 + 공통 5 전부 200 · placeholder 0"),
    ("G-C04", "스키마 — 테이블 52 · 계약 = 실제 DB · 공통 컬럼"),
    ("G-C05", "쓰기 경계 — trc · kpi 쓰기 0 · lot_genealogy 는 lineage 만"),
    ("G-C06", "계보 재현 — 코어 시나리오 lot_genealogy 10행 (API)"),
    ("G-C07", "추적 — 역방향 · 정방향 재귀 · 깊이 20 분기 100 2초"),
    ("G-C08", "키 연결 — LOT 번호 → 지시 · 실적 · 측정값 · 검사 · 출하 · 채번 한 곳"),
    ("G-C09", "시드 멱등 — 2회 실행 행 수 diff 0 · (예시) 표기"),
    ("G-C10", "집계 — stats = QA 별도 SQL · measure_series"),
    ("G-C11", "빈 화면 — 미수집 / 미확정 (D-nn)"),
    ("G-C12", "범위 밖 0 — 설비 제어 · 업종 전용 기능 없음"),
    ("G-C13", "4채널 — POP 스캔 · 모바일 390px · 현황판 새로고침"),
    ("G-C14", "출력물 4종 — 작업지시서 · 라벨 2 · 성적서 · 바코드 SVG"),
    ("G-C15", "이관 배치 4 — Import 파일 · 멱등 · 리포트"),
    ("G-C16", "ERP — 어댑터 + 501 명시 · 조용한 폴백 0"),
    ("G-C17", "RBAC — 48칸 데이터 · 없음 403 · 조회 = 쓰기 403 · scopes"),
    ("G-C18", "접근 로그 — 로그인 · 조회 · 변경 · SYS-04"),
    ("G-C19", "비밀 — 저장소 · 문서에 비밀 값 없음"),
    ("G-C20", "백업 — make backup · restore-check"),
    ("G-C21", "빌드 — pytest 전건 · check-routes · /health 200"),
    ("G-C22", "브라우저 한 바퀴 — outputs/e2e/core 캡처 · QA3 판정"),
    ("G-C23", "용어 중립 — 코어 금지어 0 · t() 누락 0"),
    ("G-C24", "측정값 — bas_process_param 선언 → POP 폼 → pop_measure → 집계"),
]
PACK_GATES: list[tuple[str, str]] = [
    ("G-P01", "격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0"),
    ("G-P02", "규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml"),
    ("G-P03", "추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0"),
    ("G-P04", "시나리오 — gates.yaml: scenarios 재현"),
    ("G-P05", "용어 — terms 키 치환 안 된 노출 0"),
    ("G-P06", "착수 시간 — outputs/pack-timing.md ≤ 4h"),
]
_STATUS = "PASS|FAIL|WARN|INVALID|BLOCKED|미검증|차단"
_ROW_RE = re.compile(r"^\s*(G-[CP]\d{2})[a-d]?\s+(.*?)\s{2,}(" + _STATUS + r")(?=\s|$)\s*(.*)$")
WRITE_RE = re.compile(r"\b(insert\s+into|update|delete\s+from)\s+([a-z_][a-z0-9_]*)", re.I)
#: G-C12 — 제어 · 명령성 엔드포인트 (spec.md §1 범위 밖 · CLAUDE.md "설비 제어 … 만들지 않는다")
CONTROL_RE = re.compile(r"(control|command|setpoint|actuat|start_machine|stop_machine|run_machine|write_tag|/plc\b|/mqtt\b)", re.I)
HTML = {"accept": "text/html"}


def run(cmd: list[str], timeout: int = 900, env: dict | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


def last_line(out: str, n: int = 90) -> str:
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else "")[:n]


def tool(name: str) -> Path | None:
    p = TOOLS / f"{name}.py"
    return p if p.exists() else None


def per_gate(output: str) -> dict[str, tuple[str, str]]:
    """검사기 출력 → {G-nn: (판정, 실측)}. 한 게이트에 행이 여럿이면 FAIL > BLOCKED > WARN > 미검증 > PASS."""
    raw: dict[str, list[tuple[str, str, str]]] = {}
    for ln in output.splitlines():
        m = _ROW_RE.match(ln)
        if m:
            raw.setdefault(m.group(1), []).append((m.group(2).strip(), m.group(3), (m.group(4) or "").strip()))
    out: dict[str, tuple[str, str]] = {}
    for gid, items in raw.items():
        sts = [st for _, st, _ in items]
        if any(st in ("FAIL", "INVALID") for st in sts):
            st = FAIL
        elif any(st in ("BLOCKED", "차단") for st in sts):
            st = BLOCKED
        elif WARN in sts:
            st = WARN
        elif UNVERIFIED in sts:
            st = UNVERIFIED
        else:
            st = PASS
        if st == PASS:
            detail = items[0][2] if len(items) == 1 else f"검사 {len(items)} 전부 PASS"
        else:
            bad = [f"{item}: {d}" for item, s, d in items if s != PASS]
            detail = (f"검사 {len(items)} · 통과 못한 {len(bad)} — " if len(items) > 1 else "") + " / ".join(bad)
        out[gid] = (st, detail[:400])
    return out


_RANK = {FAIL: 4, BLOCKED: 3, WARN: 2, PASS: 1, UNVERIFIED: 0}


def worst(prev: tuple[str, str] | None, new: tuple[str, str], who: str) -> tuple[str, str]:
    """두 검사기의 같은 게이트 판정을 합친다 — 나쁜 쪽(FAIL > 차단 > WARN > PASS)이 이긴다. 앞 판정이 없거나 `미검증` 이면 새 것.
    실측은 둘 다 남긴다(`who` = 새 판정을 낸 검사기) — DEF-QA1-010."""
    if prev is None or prev[0] == UNVERIFIED:
        return (new[0], f"{who}: {new[1]}"[:400]) if prev is not None else new
    st = prev[0] if _RANK.get(prev[0], 0) >= _RANK.get(new[0], 0) else new[0]
    return st, f"{prev[1][:190]} ‖ {who}: {new[1][:190]}"


def blocked_gates() -> dict[str, str]:
    path = ROOT / "decisions.md"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    cur, blocked, body = None, False, []

    def flush() -> None:
        if cur and blocked:
            for m in re.finditer(r"\b(G-[CP]\d{2})\b", "\n".join(body)):
                out.setdefault(m.group(1), cur)

    for ln in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (D-\d+)\b(.*)$", ln)
        if m:
            flush()
            cur, body, blocked = m.group(1), [m.group(2)], "상태: 차단" in m.group(2)
            continue
        body.append(ln)
    flush()
    return out


def secret_hits() -> tuple[int, int, bool]:
    values = [v for v in (os.environ.get("MES_SEED_PASSWORD"), os.environ.get("MES_SESSION_SECRET"), os.environ.get("MES_COLLECT_TOKEN")) if v]
    _, listed = run(["git", "ls-files", "-co", "--exclude-standard"])
    files = [ROOT / f for f in listed.splitlines() if f.strip()]
    hits = 0
    for f in files:
        try:
            data = f.read_bytes()
        except OSError:
            continue
        if any(v.encode() in data for v in values):
            hits += 1
    code, _ = run(["git", "check-ignore", "-q", ".env"])
    return hits, len(files), code == 0


def module_exists(name: str) -> bool:
    return (SRC / "app" / f"{name}.py").exists()


def core_env() -> dict:
    env = dict(os.environ)
    env["MES_PACK"] = ""
    return env


def pytest_file(rel: str, env: dict, extra: list[str] | None = None) -> tuple[bool | None, str]:
    """그 테스트 파일만 돌린다 → (통과 여부 · 없으면 None, 마지막 줄)."""
    path = ROOT / rel
    if not path.exists():
        return None, f"{rel} 없음"
    c, o = run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", str(path), *(extra or [])], env=env)
    return c == 0, last_line(o)


def expected_write_boundary(core_tables: set[str]) -> dict[str, set[str]]:
    """`contracts/db-schema.md` §2 표 → 라우터별로 쓸 수 있는 코어 테이블 집합 (`xxx_*` 는 접두로 펼친다 · `t.col` 은 t)."""
    text = (ROOT / "contracts" / "db-schema.md").read_text(encoding="utf-8")
    m = re.search(r"^## 2\..*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    out: dict[str, set[str]] = {}
    for ln in (m.group(1) if m else "").splitlines():
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 3 or set("".join(cells)) <= set("-: ") or cells[0] in ("모듈",):
            continue
        routers = re.findall(r"`([a-z_]+)`", cells[1])
        allowed: set[str] = set()
        for tok in re.findall(r"`([a-z_][a-z0-9_*.]*)`", cells[2]):
            tok = tok.split(".")[0]
            if tok.endswith("_*"):
                allowed |= {t for t in core_tables if t.startswith(tok[:-1])}
            elif tok in core_tables:
                allowed.add(tok)
        for r in routers:
            out.setdefault(r, set()).update(allowed)
    # goal.md G-C05 그대로 — 표의 괄호 설명과 무관하게 trc 0 · kpi 는 kpi_indicator 만 · dashboard(CMN-04) 0
    out["trc"], out["kpi"], out["dashboard"] = set(), {"kpi_indicator"}, set()
    return out


def scan_writes(path: Path, core_tables: set[str]) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return {m.group(2).lower() for m in WRITE_RE.finditer(text) if m.group(2).lower() in core_tables}


def core_gates(run_seeds: bool) -> dict[str, tuple[str, str]]:
    from mescore.app.settings import get_settings

    result: dict[str, tuple[str, str]] = {}

    def put(gid: str, status: str, measured: str) -> None:
        result[gid] = (status, measured[:460])

    env = core_env()
    seed_pw = bool(get_settings().seed_password)

    code, out = run(["uv", "run", "python", str(TOOLS / "check_trace.py")], env=env)
    got = per_gate(out)
    for gid in ("G-C01", "G-C02"):
        put(gid, *got.get(gid, (FAIL, f"check_trace 출력에 {gid} 행 없음 (rc={code}) {last_line(out)}")))

    code_routes, routes_out = run(["uv", "run", "python", str(TOOLS / "check_routes.py")], env=env)
    put("G-C03", *per_gate(routes_out).get("G-C03", (FAIL, f"check_routes 출력에 G-C03 행 없음 (rc={code_routes}) — {last_line(routes_out) or '출력 없음'}")))

    code, out = run(["uv", "run", "python", str(TOOLS / "check_schema.py")], env=env)
    put("G-C04", *per_gate(out).get("G-C04", (FAIL, f"check_schema 출력에 G-C04 행 없음 (rc={code}) — {last_line(out)}")))

    code, out = run(["uv", "run", "python", str(TOOLS / "check_terms.py")], env=env)
    put("G-C23", *per_gate(out).get("G-C23", (FAIL, f"check_terms 출력에 G-C23 행 없음 (rc={code})")))

    # ── pytest 전건을 먼저 돈다 — G-C21 의 증거이자, 아래 증거 검사가 보는 데이터(출하 · 성적서 · 계보)를 테스트가 만든다 ──
    code_py, out_py = run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"], timeout=1800, env=env)
    mp, mf, me = re.search(r"(\d+) passed", out_py), re.search(r"(\d+) failed", out_py), re.search(r"(\d+) error", out_py)
    n_pass = int(mp.group(1)) if mp else 0
    n_fail = (int(mf.group(1)) if mf else 0) + (int(me.group(1)) if me else 0)
    failed_names = re.findall(r"^FAILED (\S+)", out_py, re.M)

    lineage, numbering, stats, printing, erp, collect = (module_exists(n) for n in ("lineage", "numbering", "stats", "printing", "erp", "collect"))
    mig = (SRC / "migrate").exists()

    # ── G-C06 · G-C07 · G-C24 — 개발 테스트를 그 파일만 돌린 결과 ──
    ok_lin, ln_lin = pytest_file("tests/test_lineage_scenario.py", env)
    ok_pop, ln_pop = pytest_file("tests/test_pop_scenario.py", env)
    if ok_lin is None or ok_pop is None:
        put("G-C06", FAIL, f"{ln_lin} · {ln_pop} (개발2)")
    else:
        put("G-C06", PASS if (ok_lin and ok_pop) else FAIL,
            f"test_lineage_scenario {'통과' if ok_lin else '실패'} ({ln_lin}) · test_pop_scenario(API) {'통과' if ok_pop else '실패'} ({ln_pop}) · {QA_DATA}")
    if not lineage:
        put("G-C07", FAIL, "app/lineage.py 없음 (개발2)")
    elif ok_lin is None:
        put("G-C07", FAIL, f"{ln_lin} (개발2)")
    else:
        ok_depth, ln_depth = pytest_file("tests/test_lineage_scenario.py", env, ["-k", "trace or depth or forward or backward"])
        put("G-C07", PASS if (ok_lin and ok_depth) else FAIL, f"재귀 추적 · 깊이 20 분기 100 — test_lineage_scenario -k trace/depth {'통과' if ok_depth else '실패'} ({ln_depth}) · {QA_DATA}")
    if not collect:
        put("G-C24", FAIL, "app/collect.py 없음 (개발2)")
    else:
        ok_m, ln_m = pytest_file("tests/test_measure.py", env)
        literal = []
        for rel in ("app/measure.py", "app/routers/pop.py"):
            txt = (SRC / rel).read_text(encoding="utf-8") if (SRC / rel).exists() else ""
            literal += [f"{rel}:{k}" for k in ("weight", "temp") if re.search(rf"[\"']{k}[\"']", txt)]
        put("G-C24", PASS if (ok_m and not literal) else FAIL,
            f"test_measure {'통과' if ok_m else ('없음' if ok_m is None else '실패')} ({ln_m}) · 시드 키(weight · temp)를 코어 코드가 안다 {literal or 0} · {QA_DATA}")

    # ── 앱 안에서 재는 증거 (TestClient · DB) ──
    admin = None
    health: int | str = "미기동"
    try:
        from fastapi.testclient import TestClient

        from mescore.app import contracts, nav, packs, rbac
        from mescore.app.main import app
        from mescore.db import conn
        from mescore.db.seed_core import USERS as SEED_USERS

        core_tables = set(packs.core_tables())
        pw = get_settings().seed_password or ""

        def login(login_id: str) -> TestClient:
            c = TestClient(app, raise_server_exceptions=False)
            r = c.post("/login", data={"login_id": login_id, "password": pw})
            if r.status_code != 200:
                raise RuntimeError(f"{login_id} 로그인 실패 {r.status_code} — 공통 시드(make db-seed) · .env 확인")
            return c

        admin = login("admin")
        health = admin.get("/health").status_code

        # G-C05 — 라우터별 쓰기 SQL 정적 스캔 (기대값 db-schema.md §2) + lot_genealogy 는 lineage 만 + 조회 화면 전후 행 수 diff 0
        expected = expected_write_boundary(core_tables)
        viol: list[str] = []
        scanned = 0
        for f in sorted((SRC / "app" / "routers").glob("*.py")):
            if f.name.startswith("_"):
                continue
            scanned += 1
            extra = scan_writes(f, core_tables) - expected.get(f.stem, set())
            viol += [f"{f.stem}:{t}" for t in sorted(extra)]
        gen_direct = []
        for f in sorted(list((SRC / "app").rglob("*.py")) + list((SRC / "migrate").rglob("*.py") if mig else [])):
            if f.name == "lineage.py" or "__pycache__" in f.parts:
                continue
            if re.search(r"\b(insert\s+into|update|delete\s+from)\s+lot_genealogy\b", f.read_text(encoding="utf-8", errors="replace"), re.I):
                gen_direct.append(str(f.relative_to(SRC)))
        before = conn.table_counts()
        for sid in ("TRC-01", "TRC-02", "TRC-03", "KPI-01", "KPI-02", "KPI-03", "CMN-04"):
            sc = nav.by_id(sid)
            admin.get(sc.probe or sc.path)
        after = conn.table_counts()
        diff = {k: (before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)}
        put("G-C05", PASS if not (viol or gen_direct or diff) else FAIL,
            f"라우터 {scanned} 정적 스캔 — 경계 밖 쓰기 {viol or 0} · lot_genealogy 직접 쓰기 {gen_direct or 0} · trc/kpi/대시보드 7화면 조회 전후 행 수 diff {diff or 0} (테이블 {len(after)}) · {QA_DATA}")

        # G-C08 — LOT 번호 하나로 지시 · 실적 · 측정값 · 검사 · 출하 (SQL 직접) + 채번은 numbering 한 곳
        if not numbering or not lineage:
            put("G-C08", FAIL, ("app/numbering.py 없음 (개발1)" if not numbering else "app/lineage.py 없음 (개발2)"))
        else:
            from mescore.app import lineage as _lineage

            seq_writers = sorted(str(f.relative_to(SRC)) for f in (SRC / "app").rglob("*.py")
                                 if f.name != "numbering.py" and re.search(r"\b(insert\s+into|update)\s+sys_number_seq\b", f.read_text(encoding="utf-8", errors="replace"), re.I))
            found = None
            cands = conn.q("""select l.lot_no from lot l where l.kind_base = 'PRODUCT' and l.work_order_id is not null and l.work_result_id is not null
                              order by (l.created_by like 'seed%%' or l.created_by = 'migrate') desc, l.id limit 200""")
            for row in cands:
                node = _lineage.resolve(row["lot_no"])
                if node is None:
                    continue
                fwd = _lineage.trace_forward(node.id)
                ids = [node.id] + [n.id for n in fwd.nodes()]
                wo = conn.q1("select work_order_no from job_work_order w join lot l on l.work_order_id = w.id where l.id = %s", (node.id,))
                res = conn.q1("select r.id from pop_work_result r join lot l on l.work_result_id = r.id where l.id = %s", (node.id,))
                n_meas = conn.q1("select count(*) as n from pop_measure m join lot l on l.work_result_id = m.work_result_id where l.id = %s", (node.id,))["n"]
                n_insp = conn.q1("select count(*) as n from qua_inspection where lot_id = any(%s)", (ids,))["n"]
                ships = [n for n in fwd.shipments()]
                n_shp = conn.q1("select count(*) as n from shp_shipment s join lot l on l.shipment_id = s.id where l.id = any(%s)", ([n.id for n in ships] or [-1],))["n"]
                if wo and res and n_meas and n_insp and n_shp:
                    found = (row["lot_no"], wo["work_order_no"], res["id"], n_meas, n_insp, n_shp)
                    break
            if found is None:
                put("G-C08", FAIL, f"지시 · 실적 · 측정값 · 검사 · 출하가 전부 이어진 생산 LOT 이 DB 에 없다 (후보 {len(cands)}) · sys_number_seq 를 쓰는 다른 파일 {seq_writers or 0}")
            else:
                lot_no, wo_no, rid, nm, ni, ns = found
                put("G-C08", PASS if not seq_writers else FAIL,
                    f"LOT {lot_no} → 지시 {wo_no} · 실적 #{rid} · 측정값 {nm} · 검사(자손 포함) {ni} · 출하 {ns} — lineage.resolve + SQL 5 · 채번 카운터(sys_number_seq)를 쓰는 다른 파일 {seq_writers or 0} · {QA_DATA}")

        # G-C09 — 시드 멱등 (--run-seeds 에서만) + (예시) 표기
        if run_seeds:
            if not seed_pw:
                put("G-C09", FAIL, "MES_SEED_PASSWORD 미설정 — 시드를 돌릴 수 없다")
            else:
                b = conn.table_counts()
                c9, o9 = run(["uv", "run", "python", "-m", "mescore.db.seed_core"], env=env)
                a = conn.table_counts()
                d9 = {k: (b.get(k), a.get(k)) for k in sorted(set(b) | set(a)) if b.get(k) != a.get(k)}
                unmarked = 0
                for tbl, col in (("bas_item", "item_name"), ("bas_process", "process_name"), ("bas_equipment", "equip_name"),
                                 ("bas_partner", "partner_name"), ("bas_worker", "worker_name"), ("bas_defect_code", "defect_name")):
                    try:
                        unmarked += conn.q1(f"select count(*) as n from {tbl} where created_by like 'seed%%' and {col} not like '%%(예시)%%'")["n"]
                    except Exception:  # noqa: BLE001 — 컬럼 이름이 다르면 그 표는 센 값에서 빠진다 (실측에 적는다)
                        unmarked += 0
                ok9 = c9 == 0 and not d9 and unmarked == 0
                put("G-C09", PASS if ok9 else FAIL,
                    (f"시드 재실행 행 수 diff 0 (테이블 {len(a)} · 행 {sum(a.values())}) · 시드 기준정보 중 (예시) 표기 없는 행 {unmarked} · {QA_DATA}" if ok9
                     else f"시드 재실행 rc={c9} · 달라진 테이블 {d9} · (예시) 없는 행 {unmarked}"))
        else:
            put("G-C09", UNVERIFIED, "이 실행에서는 시드를 돌리지 않았다 — `make gate-full`")

        # G-C10 — QA 가 따로 짠 SQL 이 없으면 정의상 미검증. 개발3 손계산 테스트 결과만 적는다
        if not stats:
            put("G-C10", FAIL, "app/stats.py 없음 (개발3)")
        else:
            ok_s, ln_s = pytest_file("tests/test_stats.py", env)
            put("G-C10", FAIL if ok_s is False else UNVERIFIED, f"tools/check_data.py 없음 (QA2 가 별도 SQL 로 대조) — 개발3 손계산 test_stats {'통과' if ok_s else ('없음' if ok_s is None else '실패')} ({ln_s})")

        # G-C11 — 시드 상태의 화면 HTML 표본: 행이 0인 표(`<tbody>` 에 `<tr` 없음)를 `미수집`/`미확정` 없이 덩그러니 두지 않는다.
        #         ctx 의 빈 목록(rows=[] 등)이 있는 화면은 본문 어딘가에 `미수집` 또는 `미확정` 글자가 있어야 한다
        with_table, bare, empty_ctx, no_word = [], [], [], []
        for s in nav.SCREENS:
            url = s.probe or s.path
            j = admin.get(url)
            if j.status_code != 200 or not j.headers.get("content-type", "").startswith("application/json"):
                continue
            body = j.json()
            empty_keys = [k for k, v in body.items() if isinstance(v, list) and not v and k in ("rows", "items", "results", "lots", "list", "logs", "orders", "plans")]
            html = admin.get(url, headers=HTML).text
            main_html = re.search(r"<main.*?</main>", html, re.S)
            main_html = main_html.group(0) if main_html else html
            tbodies = re.findall(r"<tbody[^>]*>(.*?)</tbody>", main_html, re.S)
            if tbodies:
                with_table.append(s.screen_id)
                if any("<tr" not in b for b in tbodies):
                    bare.append(s.screen_id)
            if empty_keys:
                empty_ctx.append(s.screen_id)
                if "미수집" not in main_html and "미확정" not in main_html:
                    no_word.append(f"{s.screen_id}:{','.join(empty_keys)}")
        if not with_table and not empty_ctx:
            put("G-C11", UNVERIFIED, f"표가 있는 화면 · 빈 목록 화면이 없어 표본 0 — {QA_DATA}")
        else:
            put("G-C11", PASS if not bare else FAIL,
                f"화면 {len(nav.SCREENS)} 중 표 있는 화면 {len(with_table)} · 행 0 인 표를 미수집 표시 없이 둔 화면 {bare or 0} · (참고) ctx 빈 목록 화면 {len(empty_ctx)} 중 본문에 `미수집`/`미확정` 글자 없는 곳 {no_word or 0} — 부속 목록은 QA 가 화면으로 대조 · {QA_DATA}")

    except Exception as exc:  # noqa: BLE001
        for gid in ("G-C05", "G-C08", "G-C09", "G-C10", "G-C11"):
            if gid not in result:
                put(gid, FAIL, f"앱 기동 · DB 실측 실패 — {type(exc).__name__}: {str(exc)[:120]}")
        health = f"{type(exc).__name__}"
        admin = None

    try:
        if admin is None:
            raise RuntimeError("앱 기동 실패 — 위 게이트 참조")
        # G-C12 — 제어 · 명령성 엔드포인트 0 · 그런 테이블 0 (금지어는 G-C23)
        from mescore.app import contracts, nav, packs, rbac  # noqa: F811
        from mescore.app.main import app  # noqa: F811
        from mescore.db import conn  # noqa: F811

        def route_paths(routes=None, prefix: str = "") -> list[tuple[str, str]]:
            """include 된 라우터 속까지 (check_trace.all_routes 와 같은 규칙)."""
            out = []
            for rt in (app.routes if routes is None else routes):
                inner = getattr(rt, "original_router", None)
                if inner is not None:
                    ctx = getattr(rt, "include_context", None)
                    out += route_paths(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
                else:
                    for m in (getattr(rt, "methods", None) or ()):
                        out.append((m, prefix + getattr(rt, "path", "")))
            return out

        ctrl_routes = sorted({f"{m} {p}" for m, p in route_paths() if CONTROL_RE.search(p) and m not in ("HEAD", "OPTIONS")})
        ctrl_tables = sorted(t for t in set(packs.core_tables()) if CONTROL_RE.search(t))
        put("G-C12", PASS if not (ctrl_routes or ctrl_tables) else FAIL,
            f"라우트 {len(route_paths())} 중 제어 · 명령성 경로 {ctrl_routes or 0} · 테이블 52 중 제어성 이름 {ctrl_tables or 0} · 금지어는 G-C23 ({result.get('G-C23', ('', ''))[0]}) · {QA_DATA}")

        # G-C13 — 채널 레이아웃 body.ch-* · data-scan 유일성 · 현황판 새로고침 · 채널 밖 403
        ch = packs.current().channels
        pop_html = admin.get(nav.path_of("POP-01") + "?device=pop", headers=HTML).text
        mob_html = admin.get(nav.path_of("KPI-02") + "?device=mobile", headers=HTML).text
        board_html = admin.get(nav.path_of("KPI-01") + "?device=board", headers=HTML).text
        off = admin.get(nav.path_of("BAS-01") + "?device=pop").status_code
        scan_counts = {}
        for sid in ch.get("pop", []):
            sc = nav.by_id(sid)
            h = admin.get((sc.probe or sc.path) + ("&" if "?" in (sc.probe or sc.path) else "?") + "device=pop", headers=HTML).text
            scan_counts[sid] = h.count("data-scan")
        multi = [f"{k}:{v}" for k, v in scan_counts.items() if v > 1]
        with_scan = sum(1 for v in scan_counts.values() if v == 1)
        ok13 = ('class="ch-pop"' in pop_html and 'class="ch-mobile"' in mob_html and 'class="ch-board"' in board_html
                and "data-refresh-seconds=" in board_html and off == 403 and not multi and with_scan >= 1)
        put("G-C13", PASS if ok13 else FAIL,
            f"body.ch-pop {'ch-pop' in pop_html} · ch-mobile {'ch-mobile' in mob_html} · ch-board+새로고침 {'ch-board' in board_html and 'data-refresh-seconds=' in board_html} · "
            f"채널 밖(BAS-01?device=pop) {off} · POP 화면 {len(scan_counts)} 중 data-scan 1개 {with_scan} · 2개 이상 {multi or 0} · 390px 가로 넘침 0 은 브라우저 대조 · {QA_SEC}")

        # G-C14 — 양식 4 · <svg · 외부 CDN 0 · 바코드 값 되읽기
        if not printing:
            put("G-C14", FAIL, "app/printing.py 없음 (개발2)")
        else:
            from mescore.app import lineage as _lineage

            wo = conn.q1("select id, work_order_no from job_work_order order by id desc limit 1")
            plot = conn.q1("select id, lot_no from lot where kind_base = 'PRODUCT' order by id desc limit 1")
            shp = conn.q1("select id, shipment_no from shp_shipment order by id desc limit 1")
            doc = conn.q1("select id, document_no from shp_document order by id desc limit 1")
            forms = [("작업지시서", f"/job/print?id={wo['id']}" if wo else None, wo and wo["work_order_no"]),
                     ("LOT 라벨", f"/pop/labels?lot={plot['id']}" if plot else None, plot and plot["lot_no"]),
                     ("출하 라벨", f"/shp/shipments/{shp['id']}/label" if shp else None, shp and shp["shipment_no"]),
                     ("성적서", f"/shp/documents/{doc['id']}/print" if doc else None, doc and doc["document_no"])]
            notes, ok14 = [], True
            for name, url, want in forms:
                if not url:
                    notes.append(f"{name}: 대상 행 없음")
                    ok14 = False
                    continue
                r = admin.get(url, headers=HTML)
                codes = re.findall(r'data-barcode="([^"]+)"', r.text)
                cdn = bool(re.search(r'(src|href)="https?://', r.text))
                ok = r.status_code == 200 and "<svg" in r.text and not cdn and want in codes
                if name == "LOT 라벨" and ok:
                    node = _lineage.resolve(codes[codes.index(want)])
                    ok = node is not None and node.id == plot["id"]
                ok14 &= ok
                notes.append(f"{name} {r.status_code}{' svg' if '<svg' in r.text else ' svg없음'}{' CDN' if cdn else ''} 바코드={want if want in codes else '불일치 ' + str(codes[:1])}")
            put("G-C14", PASS if ok14 else FAIL, " · ".join(notes) + f" · LOT 라벨 바코드 → lineage.resolve 같은 LOT · {QA_SEC}")

        # G-C15 — 이관 예시 세트 dry-run 2회 · 행 수 diff 0 · 리포트 · test_migrate
        if not mig:
            put("G-C15", FAIL, "src/mescore/migrate 없음 (개발3)")
        else:
            from mescore import migrate

            ex = SRC / "migrate" / "examples"
            ok_mig, ln_mig = pytest_file("tests/test_migrate.py", env)
            b15 = conn.table_counts()
            reps, errs = [], []
            for _ in range(2):
                for cmd in migrate.COMMANDS:
                    try:
                        rep = migrate.run(cmd, ex, dry_run=True, run_by="gate")
                        reps.append((cmd, rep.exit_code, rep.error_count))
                        if rep.exit_code != 0:
                            errs.append(f"{cmd}: 오류 {rep.error_count}")
                    except Exception as exc:  # noqa: BLE001
                        errs.append(f"{cmd}: {type(exc).__name__}")
            a15 = conn.table_counts()
            targets = {t for f in contracts.batch_functions() for t in f.tables} - {"sys_migration_log"}   # B-MIG-01~04 가 쓰는 테이블만 — 다른 프로세스의 쓰기를 덜 탄다
            d15 = {k: (b15.get(k), a15.get(k)) for k in sorted(targets) if b15.get(k) != a15.get(k)}
            n_log = a15.get("sys_migration_log", 0) - b15.get("sys_migration_log", 0)
            ok15 = bool(ok_mig) and not errs and not d15 and n_log > 0
            put("G-C15", PASS if ok15 else FAIL,
                f"examples dry-run {len(reps)}회(명령 4 × 2) 오류 {errs or 0} · 이관 대상 테이블 {len(targets)} 행 수 diff {d15 or 0}"
                f"{' (같은 DB 에 다른 프로세스가 쓰는 중이면 어긋난다 — 단독 재실행)' if d15 else ''} · sys_migration_log +{n_log} · "
                f"test_migrate {'통과' if ok_mig else ('없음' if ok_mig is None else '실패')} ({ln_mig}) · {QA_SEC}")

        # G-C16 — 기본 어댑터 501 D-02 · flush 가 미확정으로 남김 · 조용한 폴백 0
        if not erp:
            put("G-C16", FAIL, "app/erp.py 없음 (개발3)")
        else:
            from mescore.app import erp as _erp

            try:
                _erp.adapter().push("gate", {})
                st501 = "예외 없음"
            except Exception as exc:  # noqa: BLE001
                detail = getattr(exc, "detail", {}) if hasattr(exc, "detail") else {}
                st501 = f"{getattr(exc, 'status_code', type(exc).__name__)} {detail.get('decision', '') if isinstance(detail, dict) else ''}".strip()
            fl = _erp.flush()
            sts = {r["status"]: r["n"] for r in conn.q("select status, count(*) as n from ifc_outbox group by status")}
            ok16 = (_erp.is_undecided() and st501.startswith("501") and "D-02" in st501 and fl["sent"] == 0 and fl["failed"] == 0
                    and fl["undecided"] == fl["processed"] and sts.get("전송", 0) == 0)
            put("G-C16", PASS if ok16 else FAIL,
                f"기본 어댑터 push → {st501} · flush processed {fl['processed']} undecided {fl['undecided']} sent {fl['sent']} failed {fl['failed']} · ifc_outbox {sts or {}} · {QA_SEC}")

        # G-C17 — 48칸 데이터 · 없음 403(check_routes) · 조회 역할 쓰기 403 전수 (역할 × 쓰기 기능 전부) · scopes
        cnt = rbac.counts()
        n_cells = len(rbac.roles()) * len(nav.ALL_MENUS)
        mrb = re.search(r"\[RBAC\].*위반\s*(\d+)", routes_out)
        n_viol = int(mrb.group(1)) if mrb else -1
        login_of = {code: lid for lid, _n, code in SEED_USERS}
        writes = [f for f in contracts.functions() if f.is_write and not f.is_token and not f.is_batch]
        tried, bad17 = 0, []
        for role in rbac.roles():
            lid = login_of.get(role.code)
            if not lid:
                continue
            c = login(lid)
            for f in writes:
                if rbac.can_do(role.code, f.id):
                    continue
                path = re.sub(r"\{[^}]*\}", "1", f.path_base)
                r = c.request(f.method, path, data={})
                tried += 1
                if r.status_code != 403:
                    bad17.append(f"{role.code}×{f.id}→{r.status_code}")
        scoped_ok = (rbac.can_do("QA", "F-MAT-04") and not rbac.can_do("QA", "F-MAT-01") and rbac.can_do("ADMIN", "F-SHP-07")
                     and not rbac.can_do("ADMIN", "F-SHP-01") and rbac.can_do("ADMIN", "F-KPI-06") and not rbac.can_do("PROD", "F-KPI-06")
                     and rbac.can_do("ADMIN", "F-IFC-04") and not rbac.can_do("PROD", "F-IFC-04")) if packs.current().is_core_only else True
        ok17 = cnt["전체"] == n_cells and (not packs.current().is_core_only or n_cells == 48) and n_viol == 0 and not bad17 and tried > 0 and scoped_ok
        put("G-C17", PASS if ok17 else FAIL,
            f"DB 권한 표 {cnt['전체']}/{n_cells}칸 (입력 {cnt['입력']} · 조회 {cnt['조회']} · 없음 {cnt['없음']}) · 없음 칸 403 위반 {n_viol} · "
            f"쓰기 기능 {len(writes)} × 역할 {len(rbac.roles())} 중 권한 없는 조합 {tried} 전수 403 위반 {bad17[:3] if bad17 else 0} · 범위 칸 4종 {scoped_ok} · {QA_SEC}")

        # G-C18 — 접근 로그 4종 + SYS-04 200 (placeholder 아님)
        kinds = {x["kind"]: x["n"] for x in conn.q("select kind, count(*) as n from sys_access_log group by kind")}
        fact = " · ".join(f"{k} {kinds.get(k, 0)}" for k in ("login_ok", "login_fail", "view", "change"))
        log_ph = nav.path_of("SYS-04") in app.state.placeholder_paths
        r18 = admin.get(nav.path_of("SYS-04"))
        ok18 = all(kinds.get(k, 0) > 0 for k in ("login_ok", "login_fail", "view", "change")) and not log_ph and r18.status_code == 200
        put("G-C18", PASS if ok18 else FAIL, f"sys_access_log {fact} · SYS-04 {r18.status_code}{' placeholder' if log_ph else ''} · {QA_SEC}")
    except Exception as exc:  # noqa: BLE001
        for gid in ("G-C12", "G-C13", "G-C14", "G-C15", "G-C16", "G-C17", "G-C18"):
            if gid not in result:
                put(gid, FAIL, f"앱 기동 · DB 실측 실패 — {type(exc).__name__}: {str(exc)[:120]}")

    hits, n_files, env_ignored = secret_hits()
    put("G-C19", PASS if (hits == 0 and env_ignored) else FAIL,
        f"저장소 대상 파일 {n_files}개 중 비밀 값(MES_SEED_PASSWORD · SESSION_SECRET · COLLECT_TOKEN)이 든 파일 {hits} · .env gitignore {'됨' if env_ignored else '안 됨'} · {QA_SEC}")

    if not tool("backup"):
        put("G-C20", FAIL, "tools/backup.py 없음")
    else:
        c1, o1 = run(["uv", "run", "python", str(TOOLS / "backup.py"), "backup"], env=env)
        c2, o2 = run(["uv", "run", "python", str(TOOLS / "backup.py"), "restore-check"], env=env)
        put("G-C20", PASS if (c1 == 0 and c2 == 0) else FAIL, f"backup rc={c1} ({last_line(o1, 70)}) · restore-check rc={c2} ({last_line(o2, 90)}) · {QA_SEC}")

    # ── QA 검사기가 있으면 그 출력이 우선한다 ──
    for name, gids in (("check_data", [f"G-C{i:02d}" for i in range(5, 13)] + ["G-C24"]),
                       ("check_security", [f"G-C{i:02d}" for i in range(13, 21)]),
                       ("check_screens", ["G-C02", "G-C03", "G-C13", "G-C17", "G-C23"])):
        t = tool(name)
        if not t:
            continue
        code, out = run(["uv", "run", "python", str(t), *(["--run-seeds"] if run_seeds and name == "check_data" else [])], timeout=1200, env=env)
        got = per_gate(out)
        for gid in gids:
            if gid in got:
                if name == "check_screens":           # QA1 행은 앞 판정(gate 자신 · check_security · check_terms)과 합친다 — 나쁜 쪽이 이긴다 (DEF-QA1-010)
                    put(gid, *worst(result.get(gid), got[gid], "check_screens"))
                else:
                    put(gid, *got[gid])
            elif name != "check_screens":
                put(gid, UNVERIFIED, f"{name} 출력에 {gid} 판정 행 없음 (rc={code})")

    ok21 = code_py == 0 and n_fail == 0 and n_pass > 0 and code_routes == 0 and health == 200
    put("G-C21", PASS if ok21 else FAIL,
        f"pytest passed {n_pass} · failed {n_fail}{' ' + str(failed_names[:3]) if failed_names else ''} · check-routes {'PASS' if code_routes == 0 else 'FAIL'} · /health {health}")

    e2e = ROOT / "outputs" / "e2e" / "core"
    shots = [p for p in e2e.glob("*") if p.is_file()] if e2e.exists() else []
    report = ROOT / "outputs" / "qa3-채널보안.md"
    row = per_gate(report.read_text(encoding="utf-8")).get("G-C22") if report.exists() else None
    if row is None:
        put("G-C22", UNVERIFIED, f"outputs/e2e/core 파일 {len(shots)}개 — " + (
            "`outputs/qa3-채널보안.md` 에 `G-C22  …  PASS|FAIL  …` 판정 행이 없다" if report.exists() else "`outputs/qa3-채널보안.md` 없음 (QA3)"))
    else:
        put("G-C22", row[0], f"{row[1]} · outputs/e2e/core 파일 {len(shots)}개")
    return result


def pack_db_exists(pack: str) -> bool:
    import psycopg
    try:
        with psycopg.connect("postgresql:///postgres", autocommit=True) as c:
            return c.execute("select 1 from pg_database where datname = %s", (f"mes_{pack}_db",)).fetchone() is not None
    except psycopg.Error:
        return False


def pack_gates(pack: str) -> dict[str, tuple[str, str]]:
    import yaml

    result: dict[str, tuple[str, str]] = {}
    pdir = PACKS / pack
    if not pack_db_exists(pack):
        reason = f"[{pack}] 팩 DB mes_{pack}_db 없음 — `make pack-db NAME={pack}`"
        for gid, _ in PACK_GATES:
            result[gid] = (UNVERIFIED, reason)
        return result
    env = dict(os.environ)
    env["MES_PACK"] = pack
    code, out = run(["uv", "run", "python", str(TOOLS / "check_pack.py")], env=env)
    result["G-P01"] = per_gate(out).get("G-P01", (FAIL, f"[{pack}] check_pack 출력에 G-P01 행 없음 (rc={code}) — {last_line(out, 160)}"))
    c1, o1 = run(["uv", "run", "python", str(TOOLS / "check_trace.py")], env=env)
    c2, o2 = run(["uv", "run", "python", str(TOOLS / "check_schema.py")], env=env)
    both = per_gate(o1 + "\n" + o2)
    result["G-P02"] = both.get("G-P02", (FAIL, f"[{pack}] check_trace/check_schema 에 G-P02 행 없음 (rc={c1}/{c2}) — {last_line(o1, 120)}"))
    result["G-P03"] = per_gate(o1).get("G-P03", (UNVERIFIED, f"[{pack}] check_trace 에 G-P03 행 없음"))
    gates = yaml.safe_load((pdir / "gates.yaml").read_text(encoding="utf-8")) if (pdir / "gates.yaml").exists() else None
    scenarios = (gates or {}).get("scenarios") or []
    if not scenarios:
        result["G-P04"] = (FAIL, f"[{pack}] gates.yaml: scenarios 비어 있음")
    else:
        bad, n = [], 0
        for s in scenarios:
            test = s.get("test")
            if not test or not (pdir / str(test).split("::")[0]).exists():
                bad.append(f"{s.get('id')}: 테스트 파일 없음")
                continue
            c, o = run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", str(pdir / str(test))], env=env)
            n += 1
            if c != 0:
                bad.append(f"{s.get('id')}: {last_line(o, 80)}")
        result["G-P04"] = (PASS if not bad else FAIL, f"[{pack}] 시나리오 {len(scenarios)} · 실행 {n} · 실패 {len(bad)}" + (f" {bad[:2]}" if bad else ""))
    code, out = run(["uv", "run", "python", str(TOOLS / "check_terms.py"), "--pack"], env=env)
    result["G-P05"] = per_gate(out).get("G-P05", (FAIL, f"[{pack}] check_terms --pack 출력에 G-P05 행 없음 (rc={code}) — {last_line(out, 120)}"))
    if tool("check_screens"):                 # QA1 — 팩 DB 에 읽기 · 호출만. 화면 글 · JSON 오류 문구의 G-P05 행을 합친다 (DEF-QA1-010)
        code, out = run(["uv", "run", "python", str(TOOLS / "check_screens.py")], timeout=1800, env=env)
        row = per_gate(out).get("G-P05")
        result["G-P05"] = worst(result["G-P05"], row, "check_screens") if row else worst(
            result["G-P05"], (UNVERIFIED, f"check_screens 출력에 G-P05 행 없음 (rc={code})"), "check_screens")
    timing = ROOT / "outputs" / "pack-timing.md"
    row = per_gate(timing.read_text(encoding="utf-8")).get("G-P06") if timing.exists() else None
    result["G-P06"] = row if row else (UNVERIFIED, f"[{pack}] outputs/pack-timing.md " + ("에 G-P06 판정 행 없음" if timing.exists() else "없음 (사람 · QA3 실측)"))
    return result


def main() -> int:
    run_seeds = "--run-seeds" in sys.argv
    os.environ["MES_PACK"] = ""
    from mescore.app import settings as _s
    _s.reset_cache()

    print(f"게이트 판정 — MES 표준플랫폼 · {datetime.now().strftime('%Y-%m-%d %H:%M')}" + (" · 시드 재실행 포함" if run_seeds else ""))
    print()
    blocked = blocked_gates()
    totals = {s: 0 for s in (PASS, FAIL, WARN, BLOCKED, UNVERIFIED)}

    def show(title: str, gates: list[tuple[str, str]], result: dict[str, tuple[str, str]]) -> None:
        print(title)
        w = max(len(item) for _, item in gates)
        for gid, item in gates:
            st, measured = result.get(gid, (UNVERIFIED, "판정 없음"))
            if st not in (PASS, FAIL) and gid in blocked:
                st, measured = BLOCKED, f"{measured} — 차단 {blocked[gid]}"
            totals[st] = totals.get(st, 0) + 1
            print(f"{gid}  {item:<{w}}  {st}  {measured}")
        print()

    show("[코어 단독 MES_PACK=]", CORE_GATES, core_gates(run_seeds))
    packs = sorted(p.name for p in PACKS.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "pack.yaml").exists()) if PACKS.exists() else []
    if not packs:
        print("[팩] packs/ 에 `_` 가 아닌 팩이 없다 — G-P01~G-P06 은 팩이 생기면 판정한다")
        print()
    for pack in packs:
        show(f"[팩 {pack} · mes_{pack}_db]", PACK_GATES, pack_gates(pack))
    n_all = len(CORE_GATES) + len(PACK_GATES) * len(packs)
    print(f"PASS {totals[PASS]} · FAIL {totals[FAIL]} · WARN {totals[WARN]} · BLOCKED {totals[BLOCKED]} · 미검증 {totals[UNVERIFIED]} / 전체 {n_all}")
    print("※ WARN · 미검증은 통과가 아니다. 「QA 대조 대기」 가 붙은 PASS 는 아키텍트 증거 판정 — QA 검사기(check_data · check_security)가 생기면 그 출력이 우선한다. "
          "BLOCKED 는 decisions.md 에 D-번호와 사유가 있어야 종료 조건(goal.md §4.4)을 만족한다.")
    if "--strict" in sys.argv:
        return 0 if totals[PASS] + totals[BLOCKED] == n_all else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
