"""kimchi 팩 시드 부트스트랩 — 새 `mes_kimchi_db` 에 처음 시드를 넣을 때 쓴다 (개발3 · 2026-10-09).

    MES_PACK=kimchi uv run python packs/kimchi/seed_bootstrap.py      # 두 번 돌려도 행 수가 같다 (G-C09)

왜 있나: 코어 `seed_core.seed_pack()` 은 `process_params` · `inspection_items` 를 `seeds[]`(processes.csv) **보다 먼저** 넣어,
공정 9 가 아직 없는 새 DB 에서는 `bas_process_param.process_id` NOT NULL 위반으로 `make db-seed` 가 멈춘다(코어 변경 요청 — progress-dev3.md §3).
여기서는 **SQL 없이** 코어 함수만 순서를 바꿔 부른다 — seeds[] (공정 · 코드 · 품목 · 설비) → 코어 시드 전체(process_params 포함).
공정이 이미 있는 DB 에서는 `make db-seed` 와 같다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mescore.app import packs  # noqa: E402
from mescore.db import seed_core  # noqa: E402


def main() -> int:
    p = packs.current()
    if p.name != "kimchi":
        raise SystemExit("MES_PACK=kimchi 로 부른다")
    params, items = p.process_params, p.inspection_items
    p.process_params, p.inspection_items = None, None
    try:
        first = seed_core.seed_pack()                 # processes.csv · codes · items · equipment 먼저 (코어 함수 그대로)
    finally:
        p.process_params, p.inspection_items = params, items
    print(f"선행 시드 {first}")
    return seed_core.main([])


if __name__ == "__main__":
    raise SystemExit(main())
