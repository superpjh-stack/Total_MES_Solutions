#!/usr/bin/env python
"""G-P03 추적표 — 설계 산출물(`design.json`) 의 화면 목록 ↔ 코어/팩 화면 매핑 (`make check-trace --pack` 이 부른다 · 개발1 · D-506).

    uv run python src/mescore/tools/import_design.py --design <design.json> [--mapping packs/<팩>/README.md] [--pack <팩>] [--md]
    MES_PACK=foodservice uv run python src/mescore/tools/import_design.py          # gates.yaml 의 design_source · design_mapping 을 쓴다
    uv run python src/mescore/tools/import_design.py --pack printfilm               # 〃 (--pack 이 MES_PACK 보다 먼저 · CR-10)

입력
  design.json  니즈푸드 · 임진강 형식 — `td3.screen_list` 의 행 `[번호, 산출물 ID, 메뉴, 화면명, 프로그램 ID, 구분]` (TD3 화면 목록)
  설계도 HTML  엘컴화인 형식 — `<div class="ia-menu"><h4>대메뉴 <span>n</span></h4><ul><li>중메뉴</li>…` 의 중메뉴 = 산출물.
               HTML 에는 ID 가 없어 매핑표의 원본 화면 칸(`BAS-01 품목 관리`)과 **화면명**(괄호 · 공백 무시)으로 맞춰 ID 를 붙인다.
               `gates.yaml: design_expect.screens` 가 있으면 중메뉴 수가 같아야 한다(다르면 FAIL). 분류 칸에 `밖` 이 들면 범위 밖.
  mapping      `gates.yaml: mapping_table` · `design_mapping` · `design_expect.mapping` 순(기본 README.md).
               `packs/<팩>/README.md` §2 의 표 — 열 `# | 산출물 | 화면명 | 코어 화면 | 분류 | 비고`. 코어 화면 칸에 화면 ID(BAS-01 · X-FSV-01 …)가
               여럿이면 1:N, 같은 화면 ID 에 산출물 여럿이면 N:1 — 둘 다 고아가 아니다(D-506). 분류 `범위 밖` 은 매핑 없음이 정상(고아 아님).
               매핑 파일이 없으면 **빈 양식**을 출력한다(모든 산출물이 고아).
출력
  매핑표(마크다운 · `--md`) + 요약 행 `G-P03  추적표  PASS|FAIL  산출물 N · 매핑 n · 범위 밖 n · 고아 n · N:1 n · 1:N n · 모르는 화면 ID n`
  고아 = 어느 화면에도 안 가고 `범위 밖` 도 아닌 산출물 ID. 모르는 화면 ID = nav 에 없는 ID (팩이 로드돼 있으면 X- 화면도 안다).
종료코드 0 = 고아 0 · 모르는 화면 ID 0.
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

SCREEN_ID_RE = re.compile(r"(?<![A-Z]-)\b(?:X-)?[A-Z]{2,4}-\d{2}\b")   # `F-MAT-09`(기능 ID) 는 화면이 아니다
DESIGN_ID_RE = re.compile(r"\b[A-Z]+-TD\d-\d{3}\b")
OUT_OF_SCOPE = "범위 밖"
IA_MENU_RE = re.compile(r'<div class="ia-menu[^"]*">\s*<h4>(.*?)</h4>\s*<ul>(.*?)</ul>', re.S)
LI_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class DesignScreen:
    design_id: str
    menu: str
    name: str
    program_id: str
    kind: str


@dataclass
class Mapping:
    design_id: str
    name: str
    screens: list[str]
    category: str
    note: str


def is_out_of_scope(category: str) -> bool:
    return OUT_OF_SCOPE in category or "밖" in category.replace("*", "")


def norm_name(text: str) -> str:
    """화면명 비교용 — 괄호 안 · 공백 · 강조 기호를 지운다 (`추적 (정방향, 역방향)` = `추적`)."""
    t = re.sub(r"\(.*?\)", "", text.replace("*", ""))
    return re.sub(r"\s+", "", t)


@dataclass
class Result:
    designs: list[DesignScreen]
    mappings: list[Mapping]
    orphans: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    unknown_screens: list[str] = field(default_factory=list)
    n_to_1: dict[str, list[str]] = field(default_factory=dict)
    one_to_n: dict[str, list[str]] = field(default_factory=dict)
    unlisted: list[str] = field(default_factory=list)      # 매핑표에는 있는데 설계 원본에 없는 ID
    problems: list[str] = field(default_factory=list)      # 원본 화면 수 ≠ gates.yaml 기대값 등 (FAIL)


# ── 읽기 ────────────────────────────────────────────────────────────────
def read_design(path: Path) -> list[DesignScreen]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = (data.get("td3") or {}).get("screen_list") or []
    out: list[DesignScreen] = []
    for r in rows:
        if isinstance(r, dict):
            did = str(r.get("id") or r.get("screen_id") or "")
            out.append(DesignScreen(did, str(r.get("menu", "")), str(r.get("name", "")), str(r.get("program_id", "")), str(r.get("kind", ""))))
        elif isinstance(r, (list, tuple)) and len(r) >= 4:
            out.append(DesignScreen(str(r[1]), str(r[2]), str(r[3]), str(r[4]) if len(r) > 4 else "", str(r[5]) if len(r) > 5 else ""))
    out = [d for d in out if DESIGN_ID_RE.fullmatch(d.design_id)]
    if not out:
        raise SystemExit(f"{path}: td3.screen_list 에서 산출물 ID(MES-TD3-nnn 형식)를 찾지 못했다")
    return out


def read_design_html(path: Path) -> list[DesignScreen]:
    """설계도 HTML 의 IA 그림 — 대메뉴(h4) × 중메뉴(li). ID 는 비워 두고(`HTML-nn`) 매핑표와 이름으로 맞춘다."""
    text = path.read_text(encoding="utf-8")
    out: list[DesignScreen] = []
    for h4, ul in IA_MENU_RE.findall(text):
        menu = htmllib.unescape(TAG_RE.sub("", re.sub(r"<span>.*?</span>", "", h4))).strip()
        for li in LI_RE.findall(ul):
            name = htmllib.unescape(TAG_RE.sub("", li)).strip()
            out.append(DesignScreen(f"HTML-{len(out) + 1:02d}", menu, name, "", "중메뉴"))
    if not out:
        raise SystemExit(f"{path}: `ia-menu` 블록(대메뉴 h4 + 중메뉴 li)을 찾지 못했다")
    return out


def read_mapping_by_name(path: Path) -> list[Mapping]:
    """HTML 원본용 매핑표 — 머리행에 `코어/팩 화면`(또는 `코어 화면`) 열과 원본 화면 열(`… 화면` · ID + 이름)이 있는 첫 표.
    `#` 칸이 숫자인 행만(`확장` 행은 원본 HTML 밖 — unlisted 로 센다). design_id = 원본 칸의 ID(없으면 이름)."""
    if not path.exists():
        return []
    for header, rows in _md_tables(path.read_text(encoding="utf-8")):
        screen_col = next((i for i, h in enumerate(header) if "화면" in h and ("코어" in h or "팩" in h)), None)
        src_col = next((i for i, h in enumerate(header) if "화면" in h and i != screen_col), None)
        if screen_col is None or src_col is None:
            continue
        cat_col = next((i for i, h in enumerate(header) if "분류" in h or "판정" in h), None)
        note_col = next((i for i, h in enumerate(header) if "비고" in h), None)
        out = []
        for r in rows:
            if len(r) <= max(screen_col, src_col):
                continue
            m = re.match(r"\s*([A-Z]{2,4}-\d{2})\s+(.*)$", r[src_col])
            did, name = (m.group(1), m.group(2)) if m else (r[src_col], r[src_col])
            mp = Mapping(did, name.strip(), SCREEN_ID_RE.findall(r[screen_col]),
                         r[cat_col] if cat_col is not None and cat_col < len(r) else "", r[note_col] if note_col is not None and note_col < len(r) else "")
            mp.listed = bool(r[0].strip().isdigit())  # type: ignore[attr-defined]
            out.append(mp)
        if out:
            return out
    return []


def attach_ids(designs: list[DesignScreen], mappings: list[Mapping]) -> list[DesignScreen]:
    """HTML 중메뉴에 매핑표의 원본 ID 를 붙인다 — 이름(괄호 · 공백 무시)이 같은 행을 순서대로 하나씩 쓴다."""
    pool = [m for m in mappings if getattr(m, "listed", True)]
    used: set[int] = set()
    for d in designs:
        key = norm_name(d.name)
        hit = next((i for i, m in enumerate(pool) if i not in used and norm_name(m.name) == key), None)
        if hit is not None:
            used.add(hit)
            d.design_id = pool[hit].design_id
    return designs


def _md_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    tables, cur = [], []
    for ln in text.splitlines() + [""]:
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            cur.append(cells)
        elif cur:
            tables.append((cur[0], cur[1:]))
            cur = []
    return tables


def read_mapping(path: Path, anchor: str | None = None) -> list[Mapping]:
    """README 의 매핑표 — 머리행에 `산출물`(또는 TD3 ID 가 든 열) 과 `코어 화면` 이 있는 첫 표."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if anchor:
        m = re.search(rf"^##\s*{re.escape(anchor.lstrip('#'))}\b.*$", text, re.M)
        if m:
            text = text[m.start():]
    for header, rows in _md_tables(text):
        id_col = next((i for i, h in enumerate(header) if "산출물" in h or "니즈푸드" in h or "TD3" in h or "ID" in h), None)
        screen_col = next((i for i, h in enumerate(header) if "화면" in h and ("코어" in h or "팩" in h)), None)
        if id_col is None or screen_col is None:
            continue
        name_col = next((i for i, h in enumerate(header) if h.endswith("화면명") or h == "화면명"), None)
        cat_col = next((i for i, h in enumerate(header) if "분류" in h), None)
        note_col = next((i for i, h in enumerate(header) if "비고" in h), None)
        out = []
        for r in rows:
            if len(r) <= max(id_col, screen_col):
                continue
            ids = DESIGN_ID_RE.findall(r[id_col])
            if not ids:
                continue
            screens = SCREEN_ID_RE.findall(r[screen_col])
            out.append(Mapping(ids[0], r[name_col] if name_col is not None and name_col < len(r) else "", screens,
                               r[cat_col] if cat_col is not None and cat_col < len(r) else "", r[note_col] if note_col is not None and note_col < len(r) else ""))
        if out:
            return out
    return []


def known_screen_ids() -> set[str]:
    from mescore.app import nav
    return {s.screen_id for s in nav.ALL}


# ── 판정 ────────────────────────────────────────────────────────────────
def analyze(designs: list[DesignScreen], mappings: list[Mapping], known: set[str]) -> Result:
    res = Result(designs, mappings)
    by_id = {m.design_id: m for m in mappings}
    design_ids = {d.design_id for d in designs}
    screen_to_designs: dict[str, list[str]] = {}
    for d in designs:
        m = by_id.get(d.design_id)
        if m is None or (not m.screens and not is_out_of_scope(m.category)):
            res.orphans.append(d.design_id)
            continue
        if not m.screens:
            res.out_of_scope.append(d.design_id)
            continue
        if len(m.screens) > 1:
            res.one_to_n[d.design_id] = list(m.screens)
        for sid in m.screens:
            screen_to_designs.setdefault(sid, []).append(d.design_id)
            if known and sid not in known:
                res.unknown_screens.append(f"{d.design_id}→{sid}")
    res.n_to_1 = {sid: ids for sid, ids in screen_to_designs.items() if len(ids) > 1}
    res.unlisted = sorted(set(by_id) - design_ids)
    return res


def render_md(res: Result) -> str:
    by_id = {m.design_id: m for m in res.mappings}
    lines = ["| # | 산출물 ID | 화면명 | 코어/팩 화면 | 분류 | 판정 |", "|---|---|---|---|---|---|"]
    for i, d in enumerate(res.designs, start=1):
        m = by_id.get(d.design_id)
        if d.design_id in res.orphans:
            verdict = "**고아**"
        elif d.design_id in res.out_of_scope:
            verdict = "범위 밖"
        elif d.design_id in res.one_to_n:
            verdict = f"1:N ({len(res.one_to_n[d.design_id])})"
        else:
            sid = m.screens[0]
            verdict = f"N:1 ({len(res.n_to_1[sid])})" if sid in res.n_to_1 else "1:1"
        lines.append(f"| {i} | {d.design_id} | {d.name} | {' + '.join(m.screens) if m and m.screens else '—'} | {m.category if m else '미매핑'} | {verdict} |")
    return "\n".join(lines)


def summary_line(res: Result, pack: str | None) -> tuple[str, bool]:
    ok = not res.orphans and not res.unknown_screens and not res.problems
    mapped = len(res.designs) - len(res.orphans) - len(res.out_of_scope)
    label = f"[{pack}] 추적표" if pack else "추적표"
    text = (f"산출물 {len(res.designs)} · 매핑 {mapped} · 범위 밖 {len(res.out_of_scope)} · 고아 {len(res.orphans)} · N:1 {len(res.n_to_1)} · 1:N {len(res.one_to_n)}"
            f" · 모르는 화면 ID {len(res.unknown_screens)}" + (f" {res.unknown_screens[:3]}" if res.unknown_screens else "")
            + (f" · 고아 예 {res.orphans[:3]}" if res.orphans else "") + (f" · 설계 원본에 없는 매핑 {len(res.unlisted)}" if res.unlisted else "")
            + "".join(f" · {p}" for p in res.problems))
    return f"G-P03  {label}  {'PASS' if ok else 'FAIL'}  {text}", ok


def pack_settings(pack: str) -> dict:
    import yaml
    gates = ROOT / "packs" / pack / "gates.yaml"
    return (yaml.safe_load(gates.read_text(encoding="utf-8")) or {}) if gates.exists() else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--design", help="design.json 또는 설계도 HTML 경로 (없으면 팩 gates.yaml: design_source)")
    ap.add_argument("--mapping", help="매핑표 마크다운 (없으면 gates.yaml: mapping_table · design_mapping · design_expect.mapping · 기본 packs/<팩>/README.md)")
    ap.add_argument("--pack", default=os.environ.get("MES_PACK") or None, help="팩 이름 (기본 MES_PACK)")
    ap.add_argument("--md", action="store_true", help="매핑표를 마크다운으로 함께 찍는다")
    ap.add_argument("--no-nav", action="store_true", help="nav 를 로드하지 않는다 (화면 ID 존재 검사를 건너뛴다)")
    a = ap.parse_args(argv)
    if a.pack:
        os.environ["MES_PACK"] = a.pack        # nav 가 팩 화면(X-…)까지 알게 — --pack 이 환경변수보다 먼저

    design_path, mapping_path, anchor = a.design, a.mapping, None
    g = pack_settings(a.pack) if a.pack else {}
    expect = g.get("design_expect") or {}
    if a.pack and not design_path and g.get("design_source"):
        design_path = str((ROOT / g["design_source"]).resolve())
    if a.pack and not mapping_path:
        dm = str(g.get("mapping_table") or g.get("design_mapping") or expect.get("mapping") or "README.md")
        mapping_path, _, anchor = dm.partition("#")
        mapping_path = str(ROOT / "packs" / a.pack / mapping_path)
    label = f"[{a.pack}] 추적표" if a.pack else "추적표"
    if not design_path:
        print(f"G-P03  {label}  미검증  설계 원본 경로가 없다 (--design 또는 gates.yaml: design_source)")
        return 2
    dp = Path(design_path)
    if not dp.exists():
        print(f"G-P03  {label}  미검증  설계 원본 없음 — {dp}")
        return 2
    problems: list[str] = []
    if dp.suffix.lower() in (".html", ".htm"):
        mappings = read_mapping_by_name(Path(mapping_path)) if mapping_path else []
        designs = attach_ids(read_design_html(dp), mappings)
        want = expect.get("screens")
        if want is not None and int(want) != len(designs):
            problems.append(f"원본 중메뉴 {len(designs)} ≠ gates.yaml design_expect.screens {want}")
        mappings = [m for m in mappings if getattr(m, "listed", True)] + [m for m in mappings if not getattr(m, "listed", True)]
    else:
        designs = read_design(dp)
        mappings = read_mapping(Path(mapping_path), anchor or None) if mapping_path else []
    known = set() if a.no_nav else known_screen_ids()
    res = analyze(designs, mappings, known)
    res.problems = problems
    if a.md or not mappings:
        print(render_md(res))
        if not mappings:
            print(f"\n(매핑표 없음 — {mapping_path or '경로 미지정'}. 위 빈 양식의 `코어/팩 화면` 칸을 채워 packs/<팩>/README.md 에 둔다)")
        print()
    line, ok = summary_line(res, a.pack)
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
