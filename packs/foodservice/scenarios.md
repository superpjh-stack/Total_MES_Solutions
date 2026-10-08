# QA 테스트 시나리오 — `foodservice` (기획자1 · 2026-10-09 · 초안)

> QA2(G-P04 시나리오를 자기 SQL 로 대조) · QA1(G-P05 용어 · 권한) · QA3(채널 · 팩 격리)가 그대로 쓴다. 화면 경로는 코어 `contracts/screen-map.md`, 오류 코드는 `api-contract.md`. 기대값은 `gates.yaml` 과 같다.
> 입력값은 전부 니즈푸드 TD3 목업 `(예시)` 행 또는 그 산식 검산이다. 날짜 `D` = 테스트 실행일.
> 화면 문구는 용어 치환 뒤의 급식어로 적었다(괄호 안은 코어 중립어). 치환 전 중립어가 보이면 G-P05 FAIL.

## 0. 준비

| 단계 | 조작 | 기대 |
|---|---|---|
| 0-1 | `MES_PACK=foodservice make db-schema db-seed` ×2 | 두 번째 실행 행 수 diff 0. `gates.yaml: seed_counts` 와 일치 |
| 0-2 | `MES_PACK=foodservice make pack-check` | 병합 규칙 위반 0. `terms` 키 16개 전부 `terms_keys` 안. 역할 6(ADMIN 포함). 권한 72칸 |
| 0-3 | `make check-pack` | 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · write_scope 밖 0 · 덮어쓴 템플릿 = `print/work_order.html` 1건 |
| 0-4 | 로그인 화면 | 역할별 계정 6(관리자 · 생산관리 담당 · 영양사 · 현장 작업자 · 출고 담당 · 외부업체). 비밀번호는 `MES_SEED_PASSWORD` — 문서에 적지 않는다 |
| 0-5 | 관리자 로그인 → 메인 | 좌측 메뉴 12 가 `기준정보 · 영업 · 수주 · 자재 · 입고 · 조리 지시 · 조리 실적 (POP) · 품질 · 검식 · 설비 · 출고 · 배치 추적 · KPI · 현황판 · 시스템 · 설비 수집` 순서 |

## 1. 핵심 시나리오 S1 — 수주(식수) → 조리 지시 → 소요량 자동 → 배치 실적 → 검식 → 출고 → 역추적

역할: 1-1~1-3 관리자(또는 생산관리 담당), 1-4~1-5 현장 작업자, 1-6 영양사, 1-7~1-8 출고 담당, 1-9 관리자.

| 단계 | 화면 (코어 ID) | 조작 · 입력값 | 기대 화면 | 기대 DB |
|---|---|---|---|---|
| 1-1 | 메뉴(품목) BAS-01 | 시드 확인: `MENU-0001 (예시)제육볶음 · 제품 · 인분 · 메뉴유형 주찬 · 1인 제공량 150.00` / `MAT-1001 (예시)돈육 앞다리 · 원재료 · kg · 냉장 · 유통기한관리 Y` / `MAT-1002 (예시)양파` | 제목 **'메뉴'**(품목 아님). 그리드에 `attrs` 열(메뉴유형 · 1인 제공량(g) · 자재구분 · 보관조건) | `bas_item` 6 · `x_foodservice_item_ext(MENU-0001).cook_process_id` = PRC-060 |
| 1-2 | 레시피(BOM) BAS-02 | 시드 확인: 제육볶음 V1.0 활성 · 돈육 12.000 kg · 양파 3.500 kg · **배치 기준인분 100.00** | 제목 '레시피'. 구성품 2줄 + 배치 기준인분 칸 | `bas_bom` 1(use_yn Y) · `bas_bom_dtl` 2 · `x_foodservice_bom_ext.batch_serve_qty` 100 |
| 1-3a | 입고 MAT-01 (POP 채널 가능) | 돈육 앞다리 · 공급처 VEN-007 · 120.000 kg · 입고일 D-1 · **유통기한 D+4** · 보관위치 냉장보관실 → 저장. 양파 80.000 kg · 유통기한 D+10 | 303 + 알림 '입고했습니다'. 원료 LOT 번호 `L{YYMMDD}NN` | `mat_receipt` 2 · `lot(kind=MATERIAL)` 2 · `x_foodservice_lot_ext.expiry_date` 2행 · `mat_stock_trx` 2 |
| 1-3b | 입고 MAT-01 | 돈육을 **유통기한 비우고** 저장 | **422** `hook_rejected` "유통기한관리 대상 자재는 유통기한이 필요합니다" | 행 수 변화 0 |
| 1-3c | 입고검사(검식) MAT-02 (영양사 또는 현장 작업자 — scopes 입고검사) | LOT 스캔 → 외관 이상 없음 Y · 중량 120.400 · 판정 합격 ×2 | `lot.insp_status=합격` | `qua_inspection(insp_type=입고)` 2 · `qua_insp_item` 4~6 |
| 1-4 | 수주 ORD-01 | 거래처 CUS-001 (예시)○○산업 구내식당 · 수주일 D-2 · 납기 D · 납기시간 11:30 · 급식유형 위탁급식 · 상세 1줄: 제육볶음 **1,200 인분** → 저장 | 수주번호 `SO-{YYMMDD}-01`. 'SCM연계' 버튼 → **501** `미확정 (D-511)` | `ord_order` 1 · `ord_order_dtl` 1(qty 1200 · unit 인분) · `x_foodservice_order_ext.due_time` 11:30 |
| 1-5 | 조리 지시(작업지시) JOB-01 | 메뉴 제육볶음 · 공정 **비움**(훅이 가공(볶음) 채움) · 계획 수량 1200 · 단위 인분 · 계획일 D · 수주 상세 연결 → 저장 | 지시번호 `WO-{YYMMDD}-0001`(4자리). 상태 대기. 레시피 버전 V1.0 고정 표시 | `job_work_order` 1(`bom_id` = V1.0 · `process_id` = PRC-060) · **`mat_requirement(source=hook)` 2행: 돈육 `required_qty 144.000 · stock_qty 120.000 · shortage 24.000` · 양파 `42.000 · 80.000 · 0.000`** · `job_lot` 2(돈육 `lot_id` = 유통기한 D+4 LOT) |
| 1-5b | 소요량 MAT-05 | 기간 D 조회 | 위 2행이 `source=hook` 표시로 · 부족 품목(돈육 24.000) 강조. TD3-015 목업과 같은 값 | 읽기만 |
| 1-5c | 조리 지시서 출력 JOB-03 | 지시 선택 → 출력 | **덮어쓴 양식**: 레시피 구성품 · 배합량 · 배치 기준인분 · 조리순서 · 주의사항 · 투입 LOT 추천(유통기한 순) · 지시 번호 바코드 | 읽기만 |
| 1-6a | 작업 목록 POP-01 (`?device=pop`) | 지시 번호 스캔 `?no=WO-…` | POP-02 로. 큰 글씨. 없는 번호 `?no=WO-000000-9999` → **그 화면 422 재렌더** | `sys_access_log` view 1 |
| 1-6b | 조리 시작(작업 시작) POP-02 | 설비 **EQ-STIR-01** · 작업자 선택 → 조리 시작 | 실적 1 진행 중 | `pop_work_result` 1(`started_at`) |
| 1-6c | 수집 수신 API | `POST /ifc/collect` `X-Collect-Token` — `equip_code EQ-STIR-01`, 4점(ts = 시작 +0/10/20/30분): `{RPM: 75.0, STIR_TIME: 0, TEMP: 150.0}` · `{74.0, 10, 157.5}` · `{73.0, 20, 165.0}` · `{72.0, 30, 172.5}` | 200 ×4. 같은 메시지 재전송 → 200 `duplicate: true` | `ifc_collect_raw` 4 · `eqp_collect` 12 |
| 1-6d | 원료 투입(투입 스캔) POP-03 | 돈육 LOT 스캔 · 12.000 kg → 양파 LOT 스캔 · 3.500 kg | 투입 2건. 추천 LOT 과 다른 LOT 을 찍으면 저장되고 경고 문구 | `pop_input` 2 |
| 1-6e | 조리 완료(작업 종료) POP-02 | 양품 **100** · 불량 **2** · 조리 조건(측정값) 칸 3개(교반속도 · 교반시간 · 조리온도)는 **collect 라 비워 둔다** → 종료 | 알림 + 배치 LOT 번호 `P{YYMMDD}-0001`. 측정값 표시 RPM **73.5** · 교반시간 **30** · 조리온도 **161.25**(이탈 표시 없음 — 범위 미확정) | `pop_work_result.ended_at` · `pop_measure` 3(source=collect) · `lot` 1(**kind=BATCH** · kind_base PRODUCT · qty 100 인분) · `x_foodservice_lot_ext.batch_no` **B-01** · `lot_genealogy(투입)` 2 |
| 1-6f | 같은 지시 2솥째 | 1-6b~1-6e 반복(양품 100 · 불량 0 · 수집 없이) | 배치 LOT `…-0002` · 측정값 `미수집` | 실적 2 · BATCH LOT 2 · `batch_no` B-02 · 계보 투입 4 |
| 1-6g | 배치 라벨 POP-04 | 배치 LOT 라벨 출력 → 바코드를 POP-01 스캔칸에 | 그 LOT 이 열린다(G-C14) | 읽기만 |
| 1-7a | 검식 결과(검사 결과) QUA-02 (영양사) | 배치 LOT 1 스캔 · 유형 **최종** · 외관 `양호` · 맛 `양호` · 측정온도 **78.5** · 관능점수 **86.00** · 이물 발견 N · 코멘트 `(예시)` → 저장 → 판정 **합격** | `lot.insp_status=합격`. 관능점수 기준 `(미확정 D-505)` 표시 | `qua_inspection(insp_type=최종)` 1 · `qua_insp_item` 5~7 · `qua_issue` 0 |
| 1-8a | 출고(출하) 등록 SHP-01 (출고 담당) | 거래처 CUS-001 · 출고일 D · 수주 연결 → 저장 | 번호 `SH-{YYMMDD}-01` 상태 등록 | `shp_shipment` 1 |
| 1-8b | LOT 스캔 · 승인 SHP-02 (POP) | 배치 LOT 1 스캔 → 2 스캔 → **승인**(관리자 — scopes 승인) | 200/303. 출고 LOT 생성 | `lot(kind=SHIPMENT)` 1 · `lot_genealogy(출하)` 2 · 상태 승인. **계보 총 6행** |
| 1-9 | 배치 추적(역방향) TRC-02 | 출고 LOT 번호 입력 | 출고 LOT → 배치 B-01 · B-02 → 돈육 LOT · 양파 LOT(**원재료 2**). 노드마다 지시 · 실적 · 조리 조건 · 검식 링크 | 쓰기 0 |
| 1-10 | KPI 집계 KPI-02 · 현황판 KPI-01 | 기간 D | `kpi_extra`: 시간당 생산량 값 있음(가동시간 = 두 실적 합) · **완제품 불량률 0.99 %** · 레시피 표준화율 33.3 %(활성 레시피 1 ÷ 메뉴 3 — 분모 `(미확정 D-10)` 표시) · 검식 적합률 100 % | 쓰기 0 |

QA2 대조 SQL(예): `select item_id, required_qty, shortage_qty from mat_requirement where source='hook'` → 144.000/24.000 · 42.000/0.000. `select count(*) from lot_genealogy` → 6. `select kind, kind_base from lot where lot_no like 'P%'` → BATCH/PRODUCT.

## 2. 거부 시나리오 S2~S7

| ID | 화면 | 조작 | 기대 |
|---|---|---|---|
| S2 | SHP-02 승인 | S1 에서 **1-7 검식을 건너뛰고** 배치 LOT 스캔 → 승인 | **422** `hook_rejected` "검식 합격 전 배치는 출고할 수 없습니다". `shp_shipment.status` 등록 그대로. 코어 F-SHP-05 는 `insp_status=미검사` 로 스캔 단계에서 먼저 422 를 낼 수도 있다 — 그 경우도 PASS(둘 중 하나) |
| S3 | QUA-02 판정 | 배치 LOT 1 · 최종 · **이물 발견 Y** · 관능점수 74.00 → 판정 **불합격** | 303. `qua_issue` 1행 `source=hook` · `process_id` = 가공(볶음) · `attrs.issue_type=이물` · `status=발생`. QUA-04 에 보인다. `lot.insp_status=불합격` → 이후 출고 스캔 422 |
| S4 | JOB-01 | 메뉴 (예시)시금치무침(레시피 없음) · 500 인분 | **422** `hook_rejected` "활성 레시피가 없는 메뉴입니다". `mat_requirement(source=hook)` 0 |
| S5 | BAS-02 | 제육볶음 V2.0 을 **사용 Y** 로 등록(V1.0 활성 상태) | **422** `hook_rejected` "메뉴당 활성 레시피는 1건". V1.0 을 N 으로 바꾼 뒤 다시 → 200 |
| S6 | `POST /ifc/collect` | `EQ-TC-05` PV_TEMP **7.2** → 다음 `4.8` | 200 ×2. `x_foodservice_env_alarm` 1행(상한 초과 · limit 5). `EQ-TC-06`(구분 미확정) 7.2 → 200 · 알람 0 |
| S7 | POP-03 | 유통기한 **D-1** 인 원료 LOT 투입 | **422** `hook_rejected` "유통기한이 지난 원료 LOT". 스캔칸 유지 |
| S8-a | JOB-01 | 원재료(돈육)에 조리 지시 | 422 "레시피는 메뉴에만" / "원재료에 조리 지시 금지" |
| S8-b | QUA-04 | 이슈유형 **클레임** · 고객사 비움 | 422 "클레임은 고객사 필수" |

## 3. 역할별 권한 케이스 (G-C17 팩판 · `seed/permissions.csv`)

로그인 후 메뉴 노출과 쓰기 응답을 본다. `없음` = 메뉴 숨김 + 직접 URL **403**. `조회` = 화면 200 · POST **403**. `입력` = POST 200/303.

| 역할 | 보여야 하는 메뉴 | 숨겨야 하는 메뉴 | 쓰기 200 | 쓰기 403 | 비고 |
|---|---|---|---|---|---|
| 관리자 ADMIN | 12 전부 | — | 기준정보 · 수주 · 조리 지시 · 입고(+입고검사) · 조리 실적 · 설비 · 출고(+승인) · KPI 지표 · 시스템 · 재전송 | **검식 판정 403**(정본 '품질관리: 조회') | TD3 role_matrix 행 1 |
| 생산관리 담당 PRODUCTION | sys · ifc 뺀 10 | 시스템 · 설비 수집 | 수주 · 조리 지시 · 입고 · 조리 실적 · 설비 · 출고 | 메뉴 등록 403 · 검식 403 · KPI 지표 403 · 출고 **승인** 403(scope) | |
| 영양사 NUTRITIONIST | sys · ifc 뺀 10 | 시스템 · 설비 수집 | 메뉴 · 레시피 · **공정 · 설비 · 거래처도 200**(D-504 — 결함 아님) · 검식 결과 · 판정 · 이슈 | 수주 · 조리 지시 · 입고 · 조리 실적 · 출고 403 | 영양사 입고검사: mat 조회라 **403** — 정본 '영양·자재 조회'. 입고검사는 현장 작업자 |
| 현장 작업자 WORKER | bas ord job mat pop qua eqp shp (8) | 배치 추적 · KPI · 시스템 · 설비 수집 | 입고 · 입고검사(scope) · 조리 시작/완료 · 투입 · 검식 결과 · 설비 상태/고장 · 출고 등록/스캔 | 메뉴 403 · 조리 지시 등록 403 · 수주 403 · 출고 승인 403 · `/trc/backward` **403** · `/kpi/board` 403 | POP 채널 |
| 출고 담당 SHIPPING | bas ord job mat pop shp trc kpi (8) | 품질 · 검식 · 설비 · 시스템 · 설비 수집 | 출고 등록 · 스캔 | 조리 실적 403 · 입고 403 · `/qua/inspections` **403** · 승인 403 | |
| 외부업체 VENDOR | pop · ifc 뺀 10 | 조리 실적 · 설비 수집 | 없음 | 전부 403. `/pop/work` **403** | 시스템 조회(접근 로그) 200 — 정본 '로그 조회' |

추가: 관리자가 SYS-03 에서 영양사 `job` 칸을 `입력` 으로 바꾸면 **다음 요청부터** 영양사 조리 지시 등록 200(`rbac.invalidate`). 사용자 중지 → 그 세션 다음 요청 401.

## 4. 채널 (G-C13 팩판 · `pack.yaml: channels`)

| 채널 | 열려야 | 403 이어야 |
|---|---|---|
| `?device=pop` | POP-01~04 · MAT-01~03 · SHP-01 · 02 · QUA-02 · EQP-01~03 | BAS-01 · ORD-01 · SYS-01 |
| `?device=mobile`(390px 가로 스크롤 0) | ORD-03 · JOB-02 · MAT-04 · SHP-03 · TRC-01~03 · KPI-02 | POP-02 · BAS-02 |
| `?device=board`(자동 새로고침) | KPI-01 · JOB-02 · EQP-01 | SYS-01 |

## 5. 용어 (G-P05)

전 화면 · 메뉴 · 알림 · 출력물에서 `품목 · BOM · 생산 LOT · 작업지시 · 실적 · 검사 · 출하 · 작업 시작 · 작업 종료 · 투입 · 측정값 · 이상 · 추적 · 원재료 LOT · 출하 LOT · 공정` 이 **날것으로 보이면 FAIL**. 기대 치환: 메뉴 · 레시피 · 배치(솥) · 조리 지시 · 조리 실적 · 검식 · 출고 · 조리 시작 · 조리 완료 · 원료 투입 · 조리 조건 · 품질 이슈 · 배치 추적 · 원료 LOT · 출고 LOT · 조리 공정. JSON 응답 `message` 도 치환, `fields[].name` 은 컬럼명 그대로.
LOT 상태 표시어: 재고 → **잔여**, 소진 → **투입됨**, 출하 → **출고**.

## 6. 팩 격리 (G-P01 · QA3)

1. `make check-pack` 전 항목 0. 2. `packs/foodservice/` 를 임시로 지우고 `uv run pytest tests/` 전건 통과. 3. `schema_ext.sql` 에 `alter table` · 트리거 0. 4. `hooks.py` 의 INSERT/UPDATE 대상이 `mat_requirement · qua_issue · job_lot · x_foodservice_*` 뿐(`lot` 은 `lineage.retag` 호출만). 5. 덮어쓴 템플릿 = `print/work_order.html` 1건.

## 7. 조용한 실패 사냥 (QA3)

- DB 를 끊고 MAT-05 · KPI-02 → **503**, 빈 표 아님. 수집 토큰 틀리면 401. `kpi_extra` 원천 0건 → `미수집`(0 아님). 레시피 표준화율 분모 라벨에 `(미확정 D-10)` 이 실제로 보이는지.
- 측정값 범위가 비어 있으니(미확정) 어떤 값도 '이탈' 로 표시되면 안 된다. 범위를 BAS-04 에서 넣으면(예: RPM 60~90) 그 뒤 실적부터 이탈 표시 — 코어 G-C24 그대로.
