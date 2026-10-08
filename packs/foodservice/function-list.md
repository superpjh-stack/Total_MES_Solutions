# 팩 기능 목록 — `foodservice` (기획자1 · 2026-10-09 · 초안)

> 코어 `contracts/function-list.md` 와 같은 열. 팩 화면 기능은 `F-X-<MOD>-nn`. `gates.yaml: functions` 가 이 표의 줄 수와 같아야 한다(G-P02).

## 1. 팩 화면 0 — 코어 + 용어 + 확장 테이블 + 훅으로 충분

**줄 수 0.** §2 의 표는 머리행만 있다(코어 `contracts.py` 로더가 §2 에서 이 표를 읽는다 — 개발1 이 절 번호를 맞췄다).

### 근거

1. `spec.md` §8.3 참조 팩 표가 foodservice 의 추가 모듈을 **"없음(코어 + ext)"** 으로 정했다. 니즈푸드 고유 기능은 레시피 소요량(훅) · 배치 실적(코어 실적 + `BATCH` kind + E3 측정값) · 검식(E3 검사 항목)이고 셋 다 코어 화면 위에서 돈다.
2. `README.md` §2 매핑에서 니즈푸드 화면 49 중 41 이 코어 화면으로 간다(1:1 18 · 용어+확장 23). 코어 화면으로 가지 못한 것은 AI Agent 8(범위 밖)과 범위 축소 4건(검식 일자별 일정 019 · 발주 대사 034 · 완제품 일마감 013 · 생산계획 자동생성 016)인데, 넷 다 **G-P04 핵심 시나리오 밖**이고 `goal.md` §2.8 이 참조 팩의 전체 화면 1:1 재현을 범위 밖으로 둔다(D-507).
3. 니즈푸드가 전용 화면으로 가진 "배치(솥) 단위 분해"(017 지시생성)는 이 팩에서 **1솥 = 코어 실적 1건**(D-501)으로 두어 화면이 필요 없다 — F-POP-02 작업 시작을 솥마다 반복하면 실적 N건 · 배치 LOT N건이 생긴다.
4. "레시피 · 조리순서 · 주의사항을 현장 화면에"(030 · 017)는 코어 JOB-03 작업지시서 출력의 양식 `print/work_order.html` 을 덮어써서 해결한다(E7 · README §6) — 라우터가 아니라 템플릿이다.
5. 소요량(015)은 코어 MAT-05 가 `mat_requirement` 를 그대로 보여 주고, 훅이 만든 행은 `source=hook` 으로 구분된다(F-MAT-10 계약 "팩 훅이 만든 행은 덮지 않는다").

### 이관 단계에 팩 화면이 생기면 (D-507 · 지금은 만들지 않는다)

| 후보 ID | 화면 | 모듈 | 경로 | 테이블 | 니즈푸드 |
|---|---|---|---|---|---|
| X-FSV-01 | 검식 일정 (일자별 대상 배치 · 계획 샘플수) | fsv | `/fsv/insp-schedule` | `x_foodservice_insp_schedule` | MES-TD3-019 |
| X-FSV-02 | 발주 목록 · 입고 대사 | fsv | `/fsv/purchase-orders` | `x_foodservice_po` | MES-TD3-034 · MAT_PO |

그때 기능 ID 는 `F-X-FSV-01 ~` 로 이 표에 더하고 `gates.yaml: screens/functions` 를 올린다.

## 2. 기능 (줄 수 0)

| ID | 모듈 | 화면 | 기능명 | 유형 | 쓰는 테이블 | 채널 | 권한 | 범위 | API | 훅 | 담당 | 계약 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## 3. 훅이 코어 기능에 끼어드는 자리 (기능이 아니라 참고)

| 코어 기능 | 훅 | 사양 |
|---|---|---|
| F-BAS-05 · 06 BOM 등록 · 수정 | `validate_bas_bom` | `hooks.md` §1 |
| F-JOB-01 작업지시 등록 | `validate_job_work_order` · `on_work_order_created` | §2 · §3 |
| F-POP-03 작업 종료 | `on_result_closed` | §4 |
| F-POP-06 투입 스캔 | `validate_pop_input` | §9 |
| F-MAT-01 입고 등록 | `validate_mat_receipt` | §10 |
| F-QUA-05 검사 판정 · F-MAT-04 입고검사 판정 | `on_inspection_judged` | §5 |
| F-QUA-08 이상 등록 | `validate_qua_issue` | §11 |
| F-SHP-07 출하 승인 | `validate_shipment` | §6 |
| F-IFC-01 수집 메시지 수신 | `on_collect` | §7 |
| F-KPI-08 지표 조회 · F-KPI-01 현황판 | `kpi_extra` | §8 |
