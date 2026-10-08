#!/usr/bin/env python
"""수용 게이트 판정표 — `make gate` (goal.md §2). 코어 단독 G-C01~G-C24 → packs/ 의 `_` 가 아닌 팩마다 G-P01~G-P06.

루프가 매 회전 부르는 것. **판정은 실제 명령의 출력으로만 한다.**
  · 검사기가 있으면 돌려서 그 출력의 `G-nn  항목  PASS|FAIL|WARN|BLOCKED|미검증  실측` 행을 읽는다 (interfaces.md §10).
  · QA 소유 검사기(`check_data` G-C05~12 · G-C24 · `check_security` G-C13~20)가 없으면 그 게이트는 `미검증`. 여기서 잴 수 있는 사실(스텁 · 파일 유무)은 실측 칸에 적는다.
  · **통과한 것처럼 보이게 하지 않는다.** 검사기 없이 PASS 를 주지 않는다.
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
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = Path(__file__).resolve().parent
PACKS = ROOT / "packs"
sys.path.insert(0, str(ROOT / "src"))

PASS, FAIL, WARN, BLOCKED, UNVERIFIED = "PASS", "FAIL", "WARN", "BLOCKED", "미검증"

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


def run(cmd: list[str], timeout: int = 900, env: dict | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


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
    return (ROOT / "src" / "mescore" / "app" / f"{name}.py").exists()


def core_env() -> dict:
    env = dict(os.environ)
    env["MES_PACK"] = ""
    return env


def core_gates(run_seeds: bool) -> dict[str, tuple[str, str]]:
    from mescore.app.settings import get_settings

    result: dict[str, tuple[str, str]] = {}

    def put(gid: str, status: str, measured: str) -> None:
        result[gid] = (status, measured)

    env = core_env()
    seed_pw = bool(get_settings().seed_password)

    code, out = run(["uv", "run", "python", str(TOOLS / "check_trace.py")], env=env)
    got = per_gate(out)
    for gid in ("G-C01", "G-C02"):
        put(gid, *got.get(gid, (FAIL, f"check_trace 출력에 {gid} 행 없음 (rc={code}) {(out.strip().splitlines() or [''])[-1][:120]}")))

    code_routes, routes_out = run(["uv", "run", "python", str(TOOLS / "check_routes.py")], env=env)
    put("G-C03", *per_gate(routes_out).get("G-C03", (FAIL, f"check_routes 출력에 G-C03 행 없음 (rc={code_routes}) — {(routes_out.strip().splitlines() or ['출력 없음'])[-1][:120]}")))

    code, out = run(["uv", "run", "python", str(TOOLS / "check_schema.py")], env=env)
    put("G-C04", *per_gate(out).get("G-C04", (FAIL, f"check_schema 출력에 G-C04 행 없음 (rc={code}) — {(out.strip().splitlines() or [''])[-1][:120]}")))

    code, out = run(["uv", "run", "python", str(TOOLS / "check_terms.py")], env=env)
    put("G-C23", *per_gate(out).get("G-C23", (FAIL, f"check_terms 출력에 G-C23 행 없음 (rc={code})")))

    # 자체 실측 — 판정은 QA 검사기가 한다
    lineage, numbering, stats, printing, erp, collect = (module_exists(n) for n in ("lineage", "numbering", "stats", "printing", "erp", "collect"))
    scenario = ROOT / "tests" / "test_lineage_scenario.py"
    put("G-C05", UNVERIFIED, "tools/check_data.py 없음 (QA2)" + ("" if lineage else " · app/lineage.py 없음 (개발2)"))
    if not scenario.exists():
        put("G-C06", FAIL, "tests/test_lineage_scenario.py 없음 (개발2 R1)")
    else:
        c, o = run(["uv", "run", "pytest", "-q", str(scenario)], env=env)
        put("G-C06", UNVERIFIED if c == 0 else FAIL, f"test_lineage_scenario {'통과' if c == 0 else '실패'} — {(o.strip().splitlines() or [''])[-1][:80]} · check_data(QA2) 대기")
    put("G-C07", UNVERIFIED if lineage else FAIL, "tools/check_data.py 없음 (QA2)" if lineage else "app/lineage.py 없음 (개발2)")
    put("G-C08", UNVERIFIED if numbering else FAIL, "tools/check_data.py 없음 (QA2)" if numbering else "app/numbering.py 없음 (개발1)")
    if run_seeds:
        if not seed_pw:
            put("G-C09", FAIL, "MES_SEED_PASSWORD 미설정 — 시드를 돌릴 수 없다")
        else:
            from mescore.db import conn
            before = conn.table_counts()
            c, o = run(["uv", "run", "python", "-m", "mescore.db.seed_core"], env=env)
            after = conn.table_counts()
            diff = {k: (before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)}
            ok = c == 0 and not diff
            put("G-C09", UNVERIFIED if ok else FAIL,
                (f"시드 재실행 행 수 diff 0 (테이블 {len(after)} · 행 {sum(after.values())}) — (예시) 표기 검사는 check_data(QA2) 대기" if ok
                 else f"시드 재실행 rc={c} · 달라진 테이블 {diff}"))
    else:
        put("G-C09", UNVERIFIED, "이 실행에서는 시드를 돌리지 않았다 — `make gate-full`")
    put("G-C10", UNVERIFIED if stats else FAIL, "tools/check_data.py 없음 (QA2)" if stats else "app/stats.py 없음 (개발3)")
    put("G-C11", UNVERIFIED, "tools/check_data.py 없음 (QA2)")
    put("G-C12", UNVERIFIED, "tools/check_data.py 없음 (QA2) · 금지어는 G-C23")
    put("G-C13", UNVERIFIED, "tools/check_security.py 없음 (QA3) — 채널 레이아웃(body.ch-*) · data-scan · 새로고침 훅은 있다")
    put("G-C14", UNVERIFIED if printing else FAIL, "tools/check_security.py 없음 (QA3)" if printing else "app/printing.py 없음 (개발2)")
    mig = (ROOT / "src" / "mescore" / "migrate").exists()
    put("G-C15", UNVERIFIED if mig else FAIL, "tools/check_security.py 없음 (QA3)" if mig else "src/mescore/migrate 없음 (개발3)")
    put("G-C16", UNVERIFIED if erp else FAIL, "tools/check_security.py 없음 (QA3)" if erp else "app/erp.py 없음 (개발3)")
    put("G-C24", UNVERIFIED if collect else FAIL, "tests/test_measure.py · check_data(QA2) 대기" if collect else "app/collect.py 없음 (개발2)")

    try:
        import warnings
        warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")
        from fastapi.testclient import TestClient

        from mescore.app import nav, rbac
        from mescore.app.main import app
        from mescore.db import conn

        cnt = rbac.counts()
        mrb = re.search(r"\[RBAC\].*위반\s*(\d+)", routes_out)
        n_viol = int(mrb.group(1)) if mrb else -1
        ok17 = cnt["전체"] == 48 and n_viol == 0
        put("G-C17", UNVERIFIED if ok17 else FAIL,
            f"자체 실측 DB 권한 표 {cnt['전체']}칸 (입력 {cnt['입력']} · 조회 {cnt['조회']} · 없음 {cnt['없음']}) · 없음 칸 403 위반 {n_viol} · 쓰기 403 전수는 check_security(QA3)")
        kinds = {x["kind"]: x["n"] for x in conn.q("select kind, count(*) as n from sys_access_log group by kind")}
        fact = " · ".join(f"{k} {kinds.get(k, 0)}" for k in ("login_ok", "login_fail", "view", "change"))
        log_ph = nav.path_of("SYS-04") in app.state.placeholder_paths
        put("G-C18", FAIL if log_ph else UNVERIFIED, f"sys_access_log {fact} · " + ("로그 화면(SYS-04) placeholder — 조회 불가 (개발1)" if log_ph else "check_security(QA3) 대기"))
        health = TestClient(app).get("/health").status_code
    except Exception as exc:  # noqa: BLE001
        for gid in ("G-C17", "G-C18"):
            put(gid, FAIL, f"앱 기동 실패 — {type(exc).__name__}: {str(exc)[:100]}")
        health = f"{type(exc).__name__}"

    hits, n_files, env_ignored = secret_hits()
    put("G-C19", FAIL if (hits or not env_ignored) else UNVERIFIED,
        f"자체 실측 저장소 대상 파일 {n_files}개 중 비밀 값이 든 파일 {hits} · .env gitignore {'됨' if env_ignored else '안 됨'} · check_security(QA3) 대기")
    put("G-C20", UNVERIFIED if tool("backup") else FAIL, "tools/check_security.py 없음 (QA3) — backup.py 는 있다" if tool("backup") else "tools/backup.py 없음")

    for name, gids in (("check_data", [f"G-C{i:02d}" for i in range(5, 13)] + ["G-C24"]),
                       ("check_security", [f"G-C{i:02d}" for i in range(13, 21)]),
                       ("check_screens", ["G-C02", "G-C03", "G-C17"])):
        t = tool(name)
        if not t:
            continue
        code, out = run(["uv", "run", "python", str(t), *(["--run-seeds"] if run_seeds and name == "check_data" else [])], timeout=1200, env=env)
        got = per_gate(out)
        for gid in gids:
            if gid in got:
                if name == "check_screens" and result.get(gid, ("", ""))[0] == FAIL:
                    continue
                put(gid, *got[gid])
            elif name != "check_screens":
                put(gid, UNVERIFIED, f"{name} 출력에 {gid} 판정 행 없음 (rc={code})")

    code, out = run(["uv", "run", "pytest", "-q"], timeout=1800, env=env)
    mp, mf, me = re.search(r"(\d+) passed", out), re.search(r"(\d+) failed", out), re.search(r"(\d+) error", out)
    n_pass = int(mp.group(1)) if mp else 0
    n_fail = (int(mf.group(1)) if mf else 0) + (int(me.group(1)) if me else 0)
    ok21 = code == 0 and n_fail == 0 and n_pass > 0 and code_routes == 0 and health == 200
    put("G-C21", PASS if ok21 else FAIL, f"pytest passed {n_pass} · failed {n_fail} · check-routes {'PASS' if code_routes == 0 else 'FAIL'} · /health {health}")

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
        reason = f"[{pack}] 팩 DB mes_{pack}_db 없음 — `MES_PACK={pack} make setup db-reset`"
        for gid, _ in PACK_GATES:
            result[gid] = (UNVERIFIED, reason)
        return result
    env = dict(os.environ)
    env["MES_PACK"] = pack
    code, out = run(["uv", "run", "python", str(TOOLS / "check_pack.py")], env=env)
    result["G-P01"] = per_gate(out).get("G-P01", (FAIL, f"[{pack}] check_pack 출력에 G-P01 행 없음 (rc={code})"))
    c1, o1 = run(["uv", "run", "python", str(TOOLS / "check_trace.py")], env=env)
    c2, o2 = run(["uv", "run", "python", str(TOOLS / "check_schema.py")], env=env)
    both = per_gate(o1 + "\n" + o2)
    result["G-P02"] = both.get("G-P02", (FAIL, f"[{pack}] check_trace/check_schema 에 G-P02 행 없음 (rc={c1}/{c2})"))
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
            c, o = run(["uv", "run", "pytest", "-q", str(pdir / str(test))], env=env)
            n += 1
            if c != 0:
                bad.append(f"{s.get('id')}: {(o.strip().splitlines() or [''])[-1][:80]}")
        result["G-P04"] = (PASS if not bad else FAIL, f"[{pack}] 시나리오 {len(scenarios)} · 실행 {n} · 실패 {len(bad)}" + (f" {bad[:2]}" if bad else ""))
    code, out = run(["uv", "run", "python", str(TOOLS / "check_terms.py"), "--pack"], env=env)
    result["G-P05"] = per_gate(out).get("G-P05", (FAIL, f"[{pack}] check_terms --pack 출력에 G-P05 행 없음 (rc={code})"))
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
    print("※ WARN · 미검증은 통과가 아니다. BLOCKED 는 decisions.md 에 D-번호와 사유가 있어야 종료 조건(goal.md §4.4)을 만족한다.")
    if "--strict" in sys.argv:
        return 0 if totals[PASS] + totals[BLOCKED] == n_all else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
