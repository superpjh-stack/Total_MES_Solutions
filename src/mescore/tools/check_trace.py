#!/usr/bin/env python
"""G-C01 메뉴 · G-C02 기능 (· G-P02 규모 · G-P03 추적표) — `make check-trace`.

기대값은 **core.yaml(+pack.yaml 병합본) · function-list.md · goal.md 의 수**에서 끌어온다. 코드가 스스로 적은 숫자를 믿지 않는다.

  G-C01  core.yaml 모듈 12 · 화면 51 · 공통 5 ↔ nav ↔ screen-map.md §1 렌더본 · 경로 중복 0 · 채널 4 안 · 화면 채널 ⊆ 모듈 채널 · 권한 48칸 모양
  G-C02  function-list.md 136줄(화면 132 + 배치 4) · 모듈별 수(36·10·7·11·8·11·8·10·3·8·16·4) · 화면 51 마다 1줄 이상 · 쓰는 테이블 ∈ db-schema.md
         · 권한 열 = core.yaml permissions 에서 계산한 입력 역할 · 한 기능 = API 하나(라우트 등록) = 테스트 하나 이상(`@pytest.mark.fn`) · 고아 라우트 0
         · 이관 배치 4 ↔ `mescore.migrate.COMMANDS`
  G-P02  (MES_PACK) 팩 화면 수 · 기능 수 = gates.yaml (테이블 수는 check_schema)
  G-P03  (MES_PACK) gates.yaml: design_source 가 있으면 `tools/import_design.py --pack <팩>` 출력 마지막 `G-P03 … PASS|FAIL|미검증` 줄 그대로 (도구가 없으면 미검증)

출력: `G-nn  항목  PASS|FAIL|미검증  실측`. 종료코드 0 = G-C01 · G-C02 FAIL 없음.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")

import importlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

TESTS_DIR = ROOT / "tests"
FN_MARK_RE = re.compile(r"mark\.fn\(([^)]*)\)")
FN_ID_RE = re.compile(r"""["']([FB]-(?:X-)?[A-Z0-9]{2,}-\d{2})["']""")


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []

    def add(self, gate: str, item: str, ok: bool | None, actual: str) -> None:
        self.rows.append((gate, item, "미검증" if ok is None else ("PASS" if ok else "FAIL"), actual))

    def failed(self, gate: str) -> int:
        return sum(1 for g, _, st, _ in self.rows if g == gate and st == "FAIL")


def norm_path(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path.split("?", 1)[0])


def all_routes(routes, prefix: str = ""):
    for rt in routes:
        inner = getattr(rt, "original_router", None)
        if inner is not None:
            ctx = getattr(rt, "include_context", None)
            yield from all_routes(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
        elif getattr(rt, "methods", None):
            yield prefix + getattr(rt, "path", ""), rt.methods


def write_roles(pack, module: str, scope: str) -> list[str]:
    """병합본 permissions 에서 그 모듈의 그 범위 기능을 입력할 수 있는 역할 이름 (D-13)."""
    names = {r["code"]: r["name"] for r in pack.roles}
    return [names[r["code"]] for r in pack.roles
            if pack.permission(module, r["code"])["level"] == "입력" and scope in pack.permission(module, r["code"])["scopes"]]


def check_menu(r: Report) -> None:
    g = "G-C01"
    try:
        from mescore.app import nav, packs
    except Exception as exc:  # noqa: BLE001
        r.add(g, "nav import", False, f"{type(exc).__name__}: {exc}")
        return
    p = packs.current()
    core_menus = [m for m in nav.ALL_MENUS if not m.is_pack]
    r.add(g, "core.yaml 모듈 12 · 화면 51 · 공통 5 = nav", (len(core_menus), len(nav.CORE_SCREENS), len(nav.COMMON)) == (12, 51, 5),
          f"모듈 {len(core_menus)} · 화면 {len(nav.CORE_SCREENS)} · 공통 {len(nav.COMMON)}" + (f" · 팩 모듈 {len(nav.ALL_MENUS) - len(core_menus)} · 팩 화면 {len(nav.PACK_SCREENS)}" if p.name else ""))
    counts = [len(m.screens) for m in sorted(core_menus, key=lambda m: [x["code"] for x in p.core_modules].index(m.code))]
    r.add(g, "모듈별 화면 수 = screen-map.md (9·4·3·5·4·4·4·4·3·3·6·2)", counts == [9, 4, 3, 5, 4, 4, 4, 4, 3, 3, 6, 2], " · ".join(map(str, counts)))
    paths = [s.path for s in nav.ALL]
    r.add(g, "화면 ID · 경로 중복 0", len({s.screen_id for s in nav.ALL}) == len(nav.ALL) and len(set(paths)) == len(paths),
          f"화면 ID {len({s.screen_id for s in nav.ALL})}/{len(nav.ALL)} · 경로 {len(set(paths))}/{len(paths)}")
    bad = [s.screen_id for m in nav.ALL_MENUS for s in m.screens if not set(s.channels) <= set(nav.CHANNELS)]
    r.add(g, "화면 채널이 4채널 안 (모듈 채널은 '주로 쓰는 채널' — 화면이 모바일을 더할 수 있다)", not bad, f"벗어남 {len(bad)} {bad[:3] if bad else ''}".strip())
    ch_bad = [f"{dev}:{sid}" for dev, ids in p.channels.items() for sid in ids if sid not in {s.screen_id for s in nav.SCREENS}]
    declared = {dev: len(ids) for dev, ids in p.channels.items()}
    r.add(g, "채널별 화면 선언(channels) 이 화면 ID 를 가리킨다", not ch_bad, f"{declared} · 모르는 ID {ch_bad[:3] if ch_bad else 0}")
    cells = [(m["code"], role["code"]) for m in p.modules for role in p.roles]
    levels = [p.permission(mc, rc)["level"] for mc, rc in cells]
    n = {lv: levels.count(lv) for lv in ("입력", "조회", "없음")}
    r.add(g, "권한 표 = 모듈 × 역할 전 칸 (코어 12 × 4 = 48)", len(cells) == len(p.modules) * len(p.roles) and (p.name or len(cells) == 48),
          f"칸 {len(cells)} · 입력 {n['입력']} · 조회 {n['조회']} · 없음 {n['없음']}")
    try:
        import gen_contracts
        text = gen_contracts.SCREEN_MAP_MD.read_text(encoding="utf-8")
        same = gen_contracts.replace_block(text, "screens", gen_contracts.render_screens(), gen_contracts.SCREEN_MAP_MD) == text
        r.add(g, "screen-map.md §1 렌더본 = core.yaml", same, "일치" if same else "다르다 — `make contracts`")
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        r.add(g, "screen-map.md §1 렌더본 = core.yaml", False, f"{type(exc).__name__}: {exc}")


def check_functions(r: Report) -> None:
    g = "G-C02"
    try:
        from mescore.app import contracts, nav, packs
        fns = contracts.functions()
    except Exception as exc:  # noqa: BLE001
        r.add(g, "function-list.md 로드", False, f"{type(exc).__name__}: {str(exc)[:200]}")
        return
    p = packs.current()
    screen_fns = [f for f in fns if not f.is_batch]
    batch_fns = [f for f in fns if f.is_batch]
    r.add(g, "계약 136줄 = 화면 기능 132 + 이관 배치 4", (len(screen_fns), len(batch_fns)) == (132, 4),
          f"{len(fns)}줄 = 화면 {len(screen_fns)} + 배치 {len(batch_fns)} · ID 중복 {len(fns) - len({f.id for f in fns})}")
    got = [(code, sum(1 for f in screen_fns if f.module == code)) for code in contracts.MODULE_COUNTS]
    r.add(g, "모듈별 기능 수 = goal.md (36·10·7·11·8·11·8·10·3·8·16·4)", [n for _, n in got] == list(contracts.MODULE_COUNTS.values()),
          " · ".join(str(n) for _, n in got))
    empty = [s.screen_id for s in nav.CORE_SCREENS if not contracts.functions_of(s.screen_id)]
    r.add(g, "화면 51 마다 기능 1줄 이상", not empty, f"기능 없는 화면 {len(empty)} {empty[:3] if empty else ''}".strip())
    try:
        known = contracts.db_tables()
        missing = sorted({t for f in fns for t in f.tables if t not in known})
        r.add(g, "쓰는 테이블이 db-schema.md 에 있다", not missing, f"없는 테이블 {len(missing)} {missing[:3] if missing else ''}".strip())
    except Exception as exc:  # noqa: BLE001
        r.add(g, "쓰는 테이블이 db-schema.md 에 있다", False, f"{type(exc).__name__}: {exc}")
    readers = [f"{f.id}:{','.join(f.tables)}" for f in screen_fns if f.module in ("trc", "kpi") and f.tables and f.module == "trc"]
    kpi_bad = [f"{f.id}:{','.join(f.tables)}" for f in screen_fns if f.module == "kpi" and set(f.tables) - {"kpi_indicator"}]
    r.add(g, "trc 쓰기 0 · kpi 는 kpi_indicator 만 (G-C05 의 계약 쪽)", not readers and not kpi_bad, f"trc {readers or 0} · kpi {kpi_bad or 0}")
    bad = [f"{f.id}({list(f.roles)}≠{write_roles(p, f.module, f.scope)})" for f in screen_fns
           if f.is_write and not f.is_token and list(f.roles) != write_roles(p, f.module, f.scope)]
    scoped = sorted(f"{f.id}({f.scope})" for f in screen_fns if f.is_write and not f.is_token and f.scope != contracts.SCOPE_GENERAL)
    n_scopes = len({x[x.index('(') + 1:-1] for x in scoped})
    r.add(g, "권한 열 = core.yaml permissions 의 입력 역할 (범위 4종 · D-13)", not bad and n_scopes == 4,
          f"불일치 {len(bad)} {bad[:2] if bad else ''} · 범위 기능 {' '.join(scoped)}".replace("  ", " "))
    try:
        from mescore.app.main import app
        placeholder = set(app.state.placeholder_paths)
        routes = {(m, norm_path(path)) for path, methods in all_routes(app.routes) for m in methods if not (m == "GET" and path in placeholder)}
        linked = [f for f in screen_fns if (f.method, norm_path(f.path)) in routes]
        miss = [f.id for f in screen_fns if f not in linked]
        r.add(g, "기능 132 ↔ 라우트 (API 열의 메서드 · 경로가 등록됨 · placeholder 제외)", len(linked) == 132,
              f"이어진 기능 {len(linked)}/132" + (f" · 미연결 예 {miss[:3]}" if miss else ""))
        fn_apis = {(f.method, norm_path(f.path)) for f in contracts.all_functions() if not f.is_batch}
        screen_gets = {("GET", s.path) for s in nav.SCREENS}
        prefixes = tuple(f"/{m.module}/" for m in nav.ALL_MENUS)
        extra = {(str(x["method"]).upper(), norm_path(str(x["path"]))) for x in packs.extra_routes()}   # core.yaml: extra_routes (D-12 · D-601)
        orphans = sorted(f"{m} {pth}" for m, pth in routes if pth.startswith(prefixes) and m not in ("HEAD", "OPTIONS")
                         and (m, pth) not in fn_apis and (m, pth) not in screen_gets and (m, pth) not in extra)
        r.add(g, "고아 라우트 0 (계약에 없는 엔드포인트 · core.yaml extra_routes 제외)", not orphans,
              f"고아 {len(orphans)} {orphans[:3] if orphans else ''} · 허용 라우트 {len(extra)} {sorted(f'{m} {p}' for m, p in extra)}".replace("  ", " ").strip())
    except Exception as exc:  # noqa: BLE001
        r.add(g, "기능 132 ↔ 라우트", False, f"{type(exc).__name__}: {str(exc)[:160]}")
    seen: set[str] = set()
    files = sorted(TESTS_DIR.glob("test_*.py")) if TESTS_DIR.exists() else []
    for pth in files:
        for args in FN_MARK_RE.findall(pth.read_text(encoding="utf-8")):
            seen.update(FN_ID_RE.findall(args))
    ids = {f.id for f in fns}
    tested = ids & seen
    r.add(g, "기능 136 ↔ 테스트 (@pytest.mark.fn 표식)", tested == ids,
          f"표식이 붙은 기능 {len(tested)}/136 · 테스트 파일 {len(files)}" + (f" · 계약에 없는 ID {sorted(seen - ids)[:3]}" if seen - ids - {f.id for f in contracts.pack_functions()} else ""))
    try:
        mig = importlib.import_module("mescore.migrate")
        commands = set(getattr(mig, "COMMANDS", {}) or {})
        have = [f.id for f in batch_fns if f.path in commands]
        r.add(g, "이관 배치 4 ↔ 명령 (mescore.migrate.COMMANDS)", len(have) == 4, f"이어진 배치 {len(have)}/4")
    except ModuleNotFoundError:
        r.add(g, "이관 배치 4 ↔ 명령 (mescore.migrate.COMMANDS)", False, "이어진 배치 0/4 · src/mescore/migrate 없음 (개발3)")


def check_pack_scale(r: Report) -> None:
    from mescore.app import contracts, nav, packs

    p = packs.current()
    if p.name is None or p.name.startswith("_"):
        return
    gates = yaml.safe_load(p.gates_path.read_text(encoding="utf-8")) if p.gates_path else None
    if not gates:
        r.add("G-P02", f"[{p.name}] 규모", False, "gates.yaml 없음")
        r.add("G-P03", f"[{p.name}] 추적표", None, "gates.yaml 없음")
        return
    try:
        n_fn = len(contracts.pack_functions())
    except Exception as exc:  # noqa: BLE001
        r.add("G-P02", f"[{p.name}] 팩 function-list.md", False, f"{type(exc).__name__}: {str(exc)[:160]}")
        n_fn = -1
    ok = len(nav.PACK_SCREENS) == int(gates.get("screens", -1)) and n_fn == int(gates.get("functions", -1))
    r.add("G-P02", f"[{p.name}] 팩 화면 · 기능 수 = gates.yaml", ok,
          f"화면 {len(nav.PACK_SCREENS)}/{gates.get('screens')} · 기능 {n_fn}/{gates.get('functions')} (테이블은 check_schema)")
    src = gates.get("design_source")
    if not src:
        r.add("G-P03", f"[{p.name}] 추적표", True, "design_source 없음 — 산출물 ID 매핑 대상 없음")
    elif not (Path(__file__).resolve().parent / "import_design.py").exists():
        r.add("G-P03", f"[{p.name}] 추적표", None, f"design_source {src} · tools/import_design.py 없음 (개발1)")
    else:
        ok, actual = run_import_design(p.name)
        r.add("G-P03", f"[{p.name}] 추적표", ok, actual)


G_P03_LINE_RE = re.compile(r"^G-P03\s+\[(?P<pack>[^\]]+)\]\s+추적표\s+(?P<st>PASS|FAIL|미검증)\s+(?P<actual>.*)$")


def run_import_design(pack: str) -> tuple[bool | None, str]:
    """`import_design.py --pack <팩>` 을 돌려 출력 **마지막** `G-P03  [<팩>] 추적표  PASS|FAIL|미검증  …` 줄을 그대로 판정으로 쓴다 (CR-10 · 개발1 ⑦).
    종료코드 0 PASS · 1 FAIL · 2 미검증 — 줄과 종료코드가 어긋나거나 줄이 없으면 FAIL(조용히 통과시키지 않는다)."""
    import subprocess

    tool = Path(__file__).resolve().parent / "import_design.py"
    env = {**os.environ, "MES_PACK": pack}
    proc = subprocess.run(["uv", "run", "python", str(tool), "--pack", pack], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    used = "--pack"
    if proc.returncode not in (0, 1, 2) and "--pack" in (proc.stderr or ""):          # --pack 이 아직 없는 도구 — 기존 인자(MES_PACK)로
        proc = subprocess.run(["uv", "run", "python", str(tool)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        used = "MES_PACK (--pack 없음)"
    lines = [m for m in (G_P03_LINE_RE.match(x.strip()) for x in (proc.stdout or "").splitlines()) if m]
    if not lines:
        tail = ((proc.stderr or proc.stdout or "").strip().splitlines() or ["출력 없음"])[-1][:160]
        return False, f"import_design({used}) rc={proc.returncode} — G-P03 줄 없음: {tail}"
    m = lines[-1]
    st = m.group("st")
    want = {"PASS": 0, "FAIL": 1, "미검증": 2}[st]
    if m.group("pack") != pack or proc.returncode != want:
        return False, f"import_design({used}) 판정 줄 [{m.group('pack')}] {st} ↔ 종료코드 {proc.returncode} 어긋남"
    return {"PASS": True, "FAIL": False, "미검증": None}[st], f"{m.group('actual')} (import_design --pack)"


def main() -> int:
    r = Report()
    check_menu(r)
    check_functions(r)
    if os.environ.get("MES_PACK"):
        check_pack_scale(r)
    w = max(len(i) for _, i, _, _ in r.rows)
    print("G-C01 메뉴 · G-C02 기능 추적 (tools/check_trace.py) — 기대값은 core.yaml · function-list.md · goal.md")
    print("-" * 100)
    for g, i, st, a in r.rows:
        print(f"{g}  {i:<{w}}  {st}  {a}")
    print("-" * 100)
    for g in ("G-C01", "G-C02"):
        n = sum(1 for x in r.rows if x[0] == g)
        print(f"{g} 판정: {'PASS' if r.failed(g) == 0 else 'FAIL'} (검사 {n} · 실패 {r.failed(g)})")
    return 1 if (r.failed("G-C01") or r.failed("G-C02")) else 0


if __name__ == "__main__":
    sys.exit(main())
