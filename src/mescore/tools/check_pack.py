#!/usr/bin/env python
"""G-P01 팩 격리 — `MES_PACK=<팩> make check-pack` (`contracts/pack-contract.md` §4 R1 · R2 · R4~R10).

  R1  코어 파일(src/mescore/**) 해시 변동 0 — outputs/core.sha256 대비 (tools/core_hash.py)
  R2  schema_ext.sql 에 코어 테이블 ALTER · DROP · 트리거 · 코어 이름 CREATE 없음 · 팩 테이블은 x_<팩>_ 접두 (R3)
  R4·R5·R6  pack.yaml 병합 규칙 — packs.load 가 PackError 를 내지 않는다
  R7  팩 라우터 · 훅의 쓰기 SQL(insert|update|delete … <테이블>) 대상이 x_<팩>_* + write_scope 뿐
  R8  lot_genealogy · sys_number_seq 직접 INSERT/UPDATE 없음
  R9  팩을 올린 채 tests/test_arch_*.py 전건 통과 (D-36 · CR-11 — 코어 단독 tests/ 전건은 gate G-C21). `--no-r9` 로 건너뛴다
  R10 코어 템플릿을 덮어쓴 파일 목록 (WARN) — README.md 에 적혀 있어야 한다
  D-05 attrs->> 를 WHERE 에서 쓰면 WARN, 집계(group by · sum 등) 에서 쓰면 FAIL

출력: `G-P01  항목  PASS|FAIL|WARN  [팩] 실측`. 종료코드 0 = FAIL 없음.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import core_hash  # noqa: E402

WRITE_RE = re.compile(r"\b(insert\s+into|update|delete\s+from)\s+([a-z_][a-z0-9_]*)", re.I)
CORE_DDL_RE = re.compile(r"\b(alter\s+table|drop\s+table|create\s+(?:or\s+replace\s+)?trigger\s+\w+\s+(?:before|after)\s+\w+(?:\s+or\s+\w+)*\s+on)\s+([a-z_][a-z0-9_]*)", re.I)
CREATE_RE = re.compile(r"\bcreate\s+(?:table|view|index|unique\s+index)\s+(?:if\s+not\s+exists\s+)?([a-z_][a-z0-9_]*)", re.I)


def main() -> int:
    pack = os.environ.get("MES_PACK") or ""
    if not pack:
        print("G-P01  팩 격리  미검증  MES_PACK 비어 있음")
        return 0
    rows: list[tuple[str, str, str]] = []

    def add(item: str, status: str, actual: str) -> None:
        rows.append((item, status, f"[{pack}] {actual}"))

    pdir = ROOT / "packs" / pack
    if not pdir.exists():
        print(f"G-P01  팩 폴더  FAIL  [{pack}] packs/{pack} 없음")
        return 1

    # R1
    if core_hash.OUT.exists():
        changed, added, removed = core_hash.diff()
        add("R1 코어 파일 해시 변동 0", "PASS" if not (changed or added or removed) else "FAIL",
            f"바뀜 {len(changed)} · 생김 {len(added)} · 없어짐 {len(removed)}" + (f" {(changed + added + removed)[:3]}" if changed or added or removed else ""))
    else:
        add("R1 코어 파일 해시 변동 0", "FAIL", "outputs/core.sha256 없음 — `make core-hash`")

    # R4~R6
    from mescore.app import packs
    core_tables = set(packs.core_tables())
    try:
        p = packs.load(pack)
        add("R4~R6 pack.yaml 병합 규칙 (packs.load)", "PASS", f"모듈 {len(p.modules)} · 화면 {len(p.screens)} · 역할 {len(p.roles)} · 용어 {len(p.terms)}"
            + (f" · WARN {p.warnings[:2]}" if p.warnings else ""))
    except packs.PackError as exc:
        add("R4~R6 pack.yaml 병합 규칙 (packs.load)", "FAIL", str(exc).splitlines()[0][:160])
        p = None

    # R2 · R3
    ext = pdir / "schema_ext.sql"
    if ext.exists():
        code = "\n".join(ln.split("--")[0] for ln in ext.read_text(encoding="utf-8").splitlines())
        ddl_bad = [f"{m.group(1).split()[0]} {m.group(2)}" for m in CORE_DDL_RE.finditer(code) if m.group(2).lower() in core_tables]
        created = [m.group(1) for m in CREATE_RE.finditer(code)]
        prefix_bad = [c for c in created if not c.startswith(f"x_{pack}_")]
        add("R2 · R3 코어 테이블 ALTER · DROP · 트리거 0 · 팩 객체는 x_<팩>_ 접두",
            "PASS" if not ddl_bad and not prefix_bad else "FAIL",
            f"코어 DDL {ddl_bad or 0} · 생성 {len(created)} · 접두 밖 {prefix_bad or 0}")
    else:
        add("R2 · R3 schema_ext.sql", "PASS", "schema_ext.sql 없음 (팩 테이블 0)")

    # R7 · R8 — 라우터 · 훅 · 어댑터 · 시드 스크립트의 쓰기 SQL
    allowed = set()
    if p is not None:
        for tbls in p.write_scope.values():
            allowed |= set(tbls)
    py_files = sorted(x for x in pdir.rglob("*.py") if "tests" not in x.parts and "__pycache__" not in x.parts)
    outside, direct = [], []
    for f in py_files:
        text = f.read_text(encoding="utf-8")
        for m in WRITE_RE.finditer(text):
            table = m.group(2).lower()
            if table in ("lot_genealogy", "sys_number_seq"):
                direct.append(f"{f.relative_to(pdir)}:{table}")
            elif table in core_tables and table not in allowed:
                outside.append(f"{f.relative_to(pdir)}:{table}")
    add("R7 write_scope 밖 코어 테이블 쓰기 0", "PASS" if not outside else "FAIL", f"파일 {len(py_files)} · scope {sorted(allowed) or '[]'} · 밖 {outside[:3] if outside else 0}")
    add("R8 lot_genealogy · sys_number_seq 직접 쓰기 0", "PASS" if not direct else "FAIL", f"직접 쓰기 {direct[:3] if direct else 0}")

    # D-05 attrs
    attrs_where, attrs_agg = [], []
    for f in py_files:
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            if "attrs->>" in ln or "attrs ->>" in ln:
                low = ln.lower()
                if re.search(r"\b(group by|sum\(|avg\(|count\(|max\(|min\()", low):
                    attrs_agg.append(f"{f.relative_to(pdir)}:{i}")
                elif " where " in f" {low} " or low.strip().startswith("where"):
                    attrs_where.append(f"{f.relative_to(pdir)}:{i}")
    add("D-05 attrs 를 집계 SQL 에 쓰지 않는다 (WHERE 는 WARN)", "FAIL" if attrs_agg else ("WARN" if attrs_where else "PASS"),
        f"집계 {attrs_agg[:2] if attrs_agg else 0} · WHERE {attrs_where[:2] if attrs_where else 0}")

    # R10 템플릿 덮어쓰기
    if p is not None:
        over = packs.overridden_templates()
        readme = (pdir / "README.md").read_text(encoding="utf-8") if (pdir / "README.md").exists() else ""
        unlisted = [t for t in over if t not in readme]
        add("R10 코어 템플릿 덮어쓰기 목록 (README.md 에 적는다)", "WARN" if over and not unlisted else ("FAIL" if unlisted else "PASS"),
            f"덮어쓴 템플릿 {over or 0}" + (f" · README 에 없음 {unlisted}" if unlisted else ""))

    # R9 (CR-11 · D-36) — 팩을 올린 채 tests/test_arch_*.py 전건. 코어 단독(MES_PACK=) tests/ 전건은 gate 의 G-C21 이 같은 실행에서 판정한다
    if "--no-r9" not in sys.argv:
        import subprocess

        arch = sorted(str(f.relative_to(ROOT)) for f in (ROOT / "tests").glob("test_arch_*.py"))
        proc = subprocess.run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", *arch], cwd=ROOT, env={**os.environ, "MES_PACK": pack},
                              capture_output=True, text=True, timeout=900)
        tail = next((ln.strip() for ln in reversed(proc.stdout.splitlines()) if re.search(r"\d+ (passed|failed|error)", ln)), "출력 없음")
        failed = [ln.split(" ", 1)[1].split(" - ")[0] for ln in proc.stdout.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
        add("R9 팩을 올린 채 tests/test_arch_*.py 통과 (코어 단독 tests/ 전건은 G-C21)", "PASS" if proc.returncode == 0 else "FAIL",
            f"파일 {len(arch)} · {tail}" + (f" {failed[:3]}" if failed else ""))

    w = max(len(i) for i, _, _ in rows)
    for item, st, actual in rows:
        print(f"G-P01  {item:<{w}}  {st}  {actual}")
    return 1 if any(st == "FAIL" for _, st, _ in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
