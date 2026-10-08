"""E5 훅 — 코어 사건에 업종 규칙을 끼운다 (contracts/pack-contract.md §5 · interfaces.md §9). 전부 선택 — 이름이 맞으면 등록된다.

규칙 (D-06)
- 동기 · 코어와 **같은 트랜잭션**(`cur`) · 거부는 `raise HookError(t("…"), fields=[...])` → 422 `hook_rejected` · 전체 되돌림.
- 그 밖 예외는 500 (조용히 삼키지 않는다). 외부 전송은 `after_commit_*` 에서만 — 트랜잭션 밖, 실패해도 응답은 성공, `ifc_outbox` 에 남는다 (D-20).
- 코어 테이블에 쓰려면 `pack.yaml: write_scope.hooks` 에 있어야 한다. `lot_genealogy` 는 `lineage` 로만, 번호는 `numbering` 으로만.
- `row` · `wo` · `result` 등은 저장될(또는 저장된) 행의 dict (attrs 포함). `user` 는 `rbac.User`.

이 파일은 **빈 서명**이다 — 필요한 것만 남기고 채운다. 남겨 둔 빈 함수는 no-op 와 같다.
"""

from __future__ import annotations

from mescore.app.packs import t  # noqa: F401 — 메시지는 t() 를 거친다
from mescore.app.util.http import HookError  # noqa: F401


# ── 저장 직전 검증 — validate_<코어 테이블>(cur, row, user). 모든 코어 INSERT/UPDATE 라우터가 부른다 ──
def validate_bas_item(cur, row: dict, user) -> None:
    """예: 필수 속성(attrs) 검사. 거부: raise HookError(t("…"), fields=[{"name": "attrs.key", "label": "…", "reason": "…"}])"""


def validate_lot(cur, row: dict, user) -> None:
    """예: 업종 LOT 종류별 필수 값."""


# ── 사건 뒤 ──
def on_order_created(cur, order: dict, user) -> None:
    """F-ORD-01 수주 저장 후."""


def on_work_order_created(cur, wo: dict, user) -> None:
    """F-JOB-01 지시 저장 후. 예: BOM × 수량 → mat_requirement (write_scope.hooks 에 mat_requirement)."""


def on_work_order_closed(cur, wo: dict, user) -> None:
    """F-JOB-03 마감 후."""


def on_result_started(cur, result: dict, user) -> None:
    """F-POP-02 작업 시작 저장 후."""


def on_result_closed(cur, result: dict, user) -> None:
    """F-POP-03 — 측정값 · 생산 LOT 생성 **후**(코어가 collect 측정값을 채운 다음). result["product_lot"] 이 있다.
    팩 kind 로 바꾸려면 lineage.retag(cur, lot_id, kind)."""


def on_lot_created(cur, lot: dict, user) -> None:
    """LOT 행 생성 후 (make_product_lot · split · merge · F-MAT-01). 예: 라벨 자동 출력 큐."""


def on_inspection_judged(cur, insp: dict, user) -> None:
    """F-QUA-05 · F-MAT-04 판정 저장 후. 예: 불합격 · 기준 이탈 → qua_issue (write_scope.hooks 에 qua_issue)."""


def validate_shipment(cur, shipment: dict, lots: list[dict], user) -> None:
    """F-SHP-07 승인 직전. 예: 특정 검사 미통과 LOT 이 있으면 HookError."""


def on_collect(cur, raw: dict, user=None) -> None:
    """collect.receive 정제 후. 예: 가동 구간 → 실적 자동 생성 (write_scope.hooks 에 pop_work_result)."""


# ── 트랜잭션 밖 — after_commit_<event>(payload). 코어 라우터가 http.after_commit(request, "<event>", payload) 로 큐에 넣는다 ──
def after_commit_shipment_approved(payload: dict) -> None:
    """예: erp.enqueue(...) · 프린터 호출. 실패는 서버 로그 + ifc_outbox."""


# ── 현황 집계 ──
def kpi_extra(frm, to) -> list[dict]:
    """stats.indicators 가 병합한다 — [{"key": "...", "label": "...", "value": 0, "unit": "%"}]. 비면 []."""
    return []
