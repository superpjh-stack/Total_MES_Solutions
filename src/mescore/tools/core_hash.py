#!/usr/bin/env python
"""코어 파일 해시 — `make core-hash` (R1 · G-P01 의 기준값).

    uv run python src/mescore/tools/core_hash.py            # src/mescore/** 의 sha256 을 outputs/core.sha256 에 찍는다 (아키텍트가 코어를 고칠 때만)
    uv run python src/mescore/tools/core_hash.py --check    # 지금 파일과 대조 — 바뀐 · 생긴 · 없어진 파일을 찍고 있으면 종료코드 1

`tools/check_pack.py` 가 `--check` 와 같은 함수(`diff()`)로 "팩 작업이 코어를 건드리지 않았는가" 를 판정한다.
`__pycache__` · `.pyc` 는 세지 않는다.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "src" / "mescore"
OUT = ROOT / "outputs" / "core.sha256"


def current() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(CORE.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            out[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def recorded() -> dict[str, str]:
    if not OUT.exists():
        return {}
    out: dict[str, str] = {}
    for ln in OUT.read_text(encoding="utf-8").splitlines():
        if "  " in ln:
            h, path = ln.split("  ", 1)
            out[path.strip()] = h.strip()
    return out


def diff() -> tuple[list[str], list[str], list[str]]:
    """(바뀐, 생긴, 없어진) 파일 목록 — outputs/core.sha256 대비."""
    now, was = current(), recorded()
    changed = sorted(p for p in now if p in was and now[p] != was[p])
    added = sorted(p for p in now if p not in was)
    removed = sorted(p for p in was if p not in now)
    return changed, added, removed


def main() -> int:
    if "--check" in sys.argv:
        if not OUT.exists():
            print(f"FAIL {OUT.relative_to(ROOT)} 없음 — `make core-hash` 로 기준을 찍는다")
            return 1
        changed, added, removed = diff()
        print(f"코어 해시 대조 — 파일 {len(current())} · 바뀜 {len(changed)} · 생김 {len(added)} · 없어짐 {len(removed)}")
        for label, items in (("바뀜", changed), ("생김", added), ("없어짐", removed)):
            for p in items:
                print(f"  {label}  {p}")
        return 1 if (changed or added or removed) else 0
    now = current()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(f"{h}  {p}\n" for p, h in now.items()), encoding="utf-8")
    print(f"outputs/core.sha256 — 코어 파일 {len(now)}개의 sha256 을 찍었다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
