# `foodservice` 팩 — 급식 MES (기획자1 · 2026-10-09 · 기획 산출물 초안)

> **한 줄**: 니즈푸드 급식 MES(화면 49 · 테이블 37)를 코어 수정 0 으로 재현하는 참조 팩. 메뉴 · 레시피 · 식수(인분) 소요량 · 배치(솥) 실적 · 교반기 수집값 · 검식을 **코어 + 용어 + 확장 테이블 + 훅**으로 표현한다. 팩 화면은 0 이다(§4).
> **근거 사업**: 주식회사 니즈푸드 MES (SF26177598 · 2026년도 부처협업형(K-푸드) 스마트공장 · 공급기업 로뎀솔루션) — `../NeedsFood MES Platform`
> **정본 경로**: `../NeedsFood MES Platform/docs/design/design.json` (TD3 화면 49 `td3.screens[*].screens[*]` · TD4 프로그램 50 · TD5 테이블 37 · `td3.role_matrix` 6역할 × 8영역 · `td1.kpi_effects`) · `src/needsfood/app/nav.py` · `src/needsfood/db/schema.sql` · `db/seed*.py` · `contracts/`
> **이 폴더의 파일**: `README.md`(이 문서) · `pack.yaml` · `seed/*.csv` · `function-list.md` · `hooks.md` · `schema_ext.md` · `gates.yaml` · `scenarios.md` · `migrate.yaml`. 코드(`hooks.py` · `schema_ext.sql` · `tests/`)는 웨이브 B 에서 개발1 이 이 문서들을 보고 만든다.
> **지어내지 않았다.** 니즈푸드 산출물에 없는 값은 `(미확정)` 이다. 실제 고객명 · 메뉴명은 쓰지 않았다 — 시드는 정본 목업의 `(예시)` 행만.

---

## 1. 읽는 순서 (개발1 · QA)

| 순서 | 파일 | 무엇을 정하는가 |
|---|---|---|
| 1 | `README.md` §2~§6 | 니즈푸드 화면 49 · 테이블 37 이 코어 어디로 가는지, 고유 기능이 확장 지점 E1~E7 중 어디인지 |
| 2 | `pack.yaml` | E1 · E2 · E3 · E6 · E7 선언 전부. 코드 없이 끝나는 것 |
| 3 | `seed/` | 권한 72칸 · 공정 측정값 7 · 검사 항목 13 · 공통코드 · 공정 9 · 설비 14 · KPI 3 · 예시 데이터 |
| 4 | `schema_ext.md` | `x_foodservice_*` 8 테이블 → 개발1 이 `schema_ext.sql` 로 옮긴다 |
| 5 | `hooks.md` | 훅 12개의 입력 · 출력 · 거부 조건 · 쓰는 테이블 → `hooks.py` |
| 6 | `gates.yaml` · `scenarios.md` | G-P02~G-P05 기대값과 QA 시나리오 |
| 7 | `migrate.yaml` | 니즈푸드 운영 DB → 표준 Import 파일 헤더 매핑(이관 단계) |
| 8 | §8 결정 후보 D-5nn | 오케스트레이터가 `decisions.md` 로 옮긴다 |

---

## 2. 코어 매핑표 — 니즈푸드 화면 49 → 코어 화면 51

분류: **1:1** = 코어 화면 그대로(용어 치환만으로 끝남) · **용어+확장** = 코어 화면 + `terms` + `attrs`/ext 테이블/훅이 있어야 산출물 문장이 나옴 · **팩 화면** = `X-` 화면 필요 · **범위 밖**.
집계: **1:1 18 · 용어+확장 23 · 팩 화면 0 · 범위 밖 8 = 49**. 코어 화면 하나에 니즈푸드 화면 둘이 가는 곳(N:1)과 니즈푸드 화면 하나가 코어 둘로 갈라지는 곳(1:N)은 비고에 적었다(D-508 — `import_design.py`/`check_trace` 가 N:1 을 고아로 세면 안 된다).

| # | 니즈푸드 | 화면명 | 코어 화면 | 분류 | 비고 (무엇이 더 있어야 하는가) |
|---|---|---|---|---|---|
| 1 | MES-TD3-001 | 메뉴(식단)관리 | BAS-01 품목 | 용어+확장 | `품목→메뉴`. `item_type=제품`. 메뉴유형 · 1인 제공량(g) · 알레르기 표기는 `attrs`, 조리공정구분은 `x_foodservice_item_ext.cook_process_id`(지시 공정 기본값 · 검색). N:1 — 003 과 같은 화면 |
| 2 | MES-TD3-002 | 레시피BOM관리 | BAS-02 BOM | 용어+확장 | `BOM→레시피`. 배합량 = `bas_bom_dtl.qty`(1솥 기준), **배치 기준인분** = `x_foodservice_bom_ext.batch_serve_qty`(집계). 조리순서 · 주의사항 = `bas_bom.attrs`. "메뉴당 활성 버전 1건" = `validate_bas_bom` |
| 3 | MES-TD3-003 | 원부자재관리 | BAS-01 품목 | 용어+확장 | `item_type=원재료/부자재`. 자재구분 · 보관조건 · 유통기한관리 여부 · 여유율(%) `attrs`, 보관기준온도 `item_ext.storage_temp`(판정). N:1 — 001 과 같은 화면, 구분 필터로 가른다 |
| 4 | MES-TD3-004 | 공정기준관리 | BAS-03 공정 + BAS-04 공정 측정값 정의 | 용어+확장 | 1:N. 공정 9 = `bas_process`. 관리항목 상·하한 = `bas_process_param`(E3, 범위 `(미확정 D-08)`). 표준 소요시간 · 배치 기준수량 = `x_foodservice_process_ext`. 조리라인 = 공통코드 `LINE` |
| 5 | MES-TD3-005 | 샘플링검식 기준관리 | QUA-01 검사 계획 | 용어+확장 | `검사→검식`. 검식항목 · 합격 점수(=`min_value`) = `qua_insp_plan`. 샘플링 빈도("10솥당 1솥") = `x_foodservice_insp_plan_ext` |
| 6 | MES-TD3-006 | 거래처관리 | BAS-06 거래처 | 1:1 | 사업자번호 · 납품지 주소 `attrs`. 담당자 · 연락처 마스킹은 코어 규칙 |
| 7 | MES-TD3-007 | 작업자관리 | BAS-07 작업자 | 1:1 | 직무 · 담당 조리라인 `attrs`(공통코드 `JOB` · `LINE`). 계정 연결 = `bas_worker.user_id` |
| 8 | MES-TD3-008 | 공통코드관리 | BAS-09 공통코드 | 1:1 | — |
| 9 | MES-TD3-009 | 수주정보관리 | ORD-01 수주 | 용어+확장 | 수량 단위 = 인분. 납기시간 · 급식유형 = `x_foodservice_order_ext`(정렬 · 검색). 'SCM연계' 버튼 = ERP 어댑터 null → 501 `미확정 (D-511)`. 수주 '확정' 은 코어 상태 `진행`(D-507) |
| 10 | MES-TD3-010 | 납기캘린더조회 | ORD-03 납기 달력 | 1:1 | — |
| 11 | MES-TD3-011 | 수주대비 출고현황조회 | SHP-03 출하 현황 | 용어+확장 | 수주인분 vs 출고인분 차이는 `kpi_extra`(관리지표 `order_ship_gap`)로. 화면 열은 코어 것 |
| 12 | MES-TD3-012 | 원료재고관리 | MAT-01 입고 + MAT-02 입고검사 | 용어+확장 | 1:N. 유통기한 = `x_foodservice_lot_ext.expiry_date`(FIFO 정렬). 보관위치 · 입고 시 보관온도 `attrs`. 입고검사 항목(중량 · 사진) = `inspection_items.csv` 입고 유형 |
| 13 | MES-TD3-013 | 완제품재고관리 | MAT-04 재고 | 용어+확장 | 완제품 재고 = `lot(kind=BATCH)` 잔량(`v_lot_stock`). '일마감' 은 코어에 없음 — 범위 축소(D-507). 조정 = F-MAT-09 |
| 14 | MES-TD3-014 | 재고이동 조정관리 | MAT-04 재고(F-MAT-09 재고 조정) | 용어+확장 | 이동 · 조정 · 폐기 · 반품 = `mat_stock_trx.trx_type=조정` + 사유(`attrs.move_type` · `from_loc` · `to_loc`) |
| 15 | MES-TD3-015 | 레시피기반 소요량계산 | MAT-05 소요량 | 용어+확장 | 훅 `on_work_order_created` 가 `mat_requirement(source=hook)` 행을 만든다. '발주요청' 은 범위 밖(코어에 발주 없음 · D-507) |
| 16 | MES-TD3-016 | 생산계획관리 | ORD-04 생산계획 | 용어+확장 | 계획 배치(솥)수 = 계획인분 ÷ 배치 기준인분(표시 계산 · 저장 안 함). '자동생성' 은 코어에 없음(코어 변경 요청 후보 §7-③) |
| 17 | MES-TD3-017 | 작업지시서(레시피)관리 | JOB-01 작업지시 + JOB-03 작업지시서 출력 | 용어+확장 | 1:N. `작업지시→조리 지시`. 1 지시 = 메뉴 × 생산일(식수), **1솥 = 1실적**(D-501). BOM 버전 고정 = `job_work_order.bom_id`. 레시피 · 조리순서 · 주의사항은 `print/work_order.html` 덮어쓰기(§6) |
| 18 | MES-TD3-018 | 배치(솥)별 생산실적관리 | POP-02 작업 시작·종료 | 용어+확장 | `실적→조리 실적` · `생산 LOT→배치(솥)`. RPM · 교반시간 · 온도 = `pop_measure`(source=collect, 코어가 채움). 완제품LOT 1건 = `lineage.make_product_lot` → 훅이 `kind=BATCH` 재태깅 + 배치번호 |
| 19 | MES-TD3-019 | 검식계획관리 | QUA-01 검사 계획 | 용어+확장 | 일자별 검식 일정(대상 배치수 ÷ 샘플링 빈도 → 계획 샘플수)은 코어에 없음 — 계획 샘플수는 `kpi_extra` 표시로 축소, 일정 화면은 이관 단계 `X-FSV-01` 후보(D-507) |
| 20 | MES-TD3-020 | 검식결과관리 | QUA-02 검사 결과 | 용어+확장 | 검식 = `qua_inspection(insp_type=최종|공정)` on BATCH LOT. 측정온도 · 관능점수 · 이물여부 · 코멘트 · 사진경로 = `qua_insp_item`. 불합격 → `on_inspection_judged` 가 이슈 생성 |
| 21 | MES-TD3-021 | 품질이슈관리 | QUA-04 이상 · 시정 | 용어+확장 | `이상→품질 이슈`. 이슈유형(이물/품질이상/클레임/반품) · 고객사 `attrs`. 원인 공정 = `qua_issue.process_id` |
| 22 | MES-TD3-022 | 공정진행관리 | JOB-02 지시 현황 (+ POP-02) | 용어+확장 | 진행 = 실적 유무(`v_work_order_progress`). 진척률 · 표준 소요시간 대비 지연 판정은 `process_ext.std_lead_min` 이 있을 때만(`(미확정 D-08)`) |
| 23 | MES-TD3-023 | 공정지연관리 | POP-02 (F-POP-04 정지 기록) | 용어+확장 | 지연사유(자재지연/설비이상/인력부족/재작업) = 공통코드 `STOP_REASON` 추가. 설비이상 연결 `attrs.fault_id` |
| 24 | MES-TD3-024 | 설비 가동관리 | EQP-01 가동 현황 (+ BAS-05 설비) | 1:1 | 설비 마스터는 BAS-05. 통신방식 · 제조사모델 `attrs`, 냉장/냉동 구분 · 임계 = `x_foodservice_equipment_ext` |
| 25 | MES-TD3-025 | 설비 점검관리 | EQP-02 점검 | 1:1 | 점검구분 · 점검예정일 `attrs` |
| 26 | MES-TD3-026 | 설비 고장관리 | EQP-03 고장 | 1:1 | 이상유형(고장/오작동/통신단절/센서이상) `attrs` |
| 27 | MES-TD3-027 | 생산성 KPI 조회 | KPI-02 집계 | 용어+확장 | `kpi_extra`: 시간당 생산량(인분/h) 300→350 |
| 28 | MES-TD3-028 | 품질 KPI 조회 | KPI-02 집계 | 용어+확장 | `kpi_extra`: 완제품 불량률 7.5→6.5 % · 검식 적합률(관리) |
| 29 | MES-TD3-029 | KPI 지표 관리 | KPI-03 지표 정의 | 1:1 | `kpi_indicator` 3행 시드(`seed/kpi_indicators.csv`). '산식검증' 은 코어에 없음 — 범위 축소 |
| 30 | MES-TD3-030 | 작업지시서 목록 | POP-01 작업 목록(스캔) | 1:1 | 레시피 보기 = JOB-03 출력 링크 |
| 31 | MES-TD3-031 | 라인목록 | POP-01 작업 목록(스캔) | 용어+확장 | 조리라인(솥그룹) 타일 → POP-01 의 `attrs.line` 필터로 축소. 라인 정의는 공통코드 `LINE` 뿐(정본 제약) |
| 32 | MES-TD3-032 | 생산진행조회 | POP-02 작업 시작·종료 | 1:1 | 가동 · 일시정지 · 완료 · 실적입력 = F-POP-02/04/03 |
| 33 | MES-TD3-033 | 설비목록 | EQP-01 가동 현황 (pop 채널) | 1:1 | 최근 수집값 = `collect.latest`. '이탈여부' 열은 코어에 없음(§7-①) |
| 34 | MES-TD3-034 | 발주목록 | MAT-01 입고 (pop 채널) | 용어+확장 | 발주(MAT_PO) 대사는 범위 밖 — 입고 등록만. 발주 테이블은 이관 단계 `x_foodservice_po` 후보(D-507) |
| 35 | MES-TD3-035 | 출고지시서 목록 | SHP-02 LOT 스캔 · 승인 (pop 채널) | 1:1 | `출하→출고`. 납기시간순 정렬 = `order_ext.due_time` |
| 36 | MES-TD3-036 | AI 질의등록 | — | 범위 밖 | 선택 팩 `agent`(spec §3.8) |
| 37 | MES-TD3-037 | AI 응답조회 | — | 범위 밖 | 〃 |
| 38 | MES-TD3-038 | 생산요약 | — | 범위 밖 | 〃 |
| 39 | MES-TD3-039 | 불량요약 | — | 범위 밖 | 〃 |
| 40 | MES-TD3-040 | 비가동요약 | — | 범위 밖 | 〃 |
| 41 | MES-TD3-041 | 일일리포트 생성 | — | 범위 밖 | 〃 |
| 42 | MES-TD3-042 | 주간리포트 생성 | — | 범위 밖 | 〃 |
| 43 | MES-TD3-043 | AI 분석이력 | — | 범위 밖 | 〃 |
| 44 | MES-TD3-044 | 대시보드 | KPI-01 현황판 | 1:1 | 카드 4(시간당 생산량 · 불량률 · 금일 출고 · 설비 이상) = `stats.board` + `kpi_extra` |
| 45 | MES-TD3-045 | 상세대시보드 | KPI-02 집계 | 1:1 | 드릴다운 = `?kind=` 4종 |
| 46 | MES-TD3-046 | 사용자 계정관리 | SYS-01 사용자 | 1:1 | 잠금해제 · 비밀번호 초기화 = F-SYS-02/03 |
| 47 | MES-TD3-047 | 권한역할 관리 | SYS-02 역할 + SYS-03 권한 표 | 1:1 | 1:N. 화면 단위 권한 → 메뉴 단위(§7-②) |
| 48 | MES-TD3-048 | 시스템 로그 조회 | SYS-04 접근 로그 | 1:1 | — |
| 49 | MES-TD3-049 | 데이터 백업 이력조회 | SYS-06 백업 · 이관 | 1:1 | — |

공통 화면 4(메인시안 · 로그인 · 팝업 · 대시보드) + 오류 → CMN-02 · CMN-01 · CMN-05 · CMN-04 · CMN-03. 인터페이스 프로그램 MES-TD4-050(`POST /if/equip`) → 코어 `POST /ifc/collect`(F-IFC-01).

---

## 3. 확장 지점 분류표 — 니즈푸드 고유 기능 전부 → E1~E7

`spec.md` §3.8 의 니즈푸드 5행을 기능 단위로 전개했다. **E1~E7 어디에도 온전히 들어가지 않는 것은 §7 로 보냈다.** 건수: E1 7 · E2 10 · E3 4 · E4 1 · E5 11 · E6 1 · E7 4 = **38** (+ §7 코어 변경 요청 후보 5).

| # | 고유 기능 | 확장 지점 | 어떻게 | 근거(정본) |
|---|---|---|---|---|
| E1-1 | 급식 용어(메뉴 · 레시피 · 조리 지시 · 배치(솥) · 조리 실적 · 검식 · 출고 · 인분) | E1 `terms` | `pack.yaml: terms` 16키 — `spec.md` §12 중립어 안에서만 | TD3 화면명 · CLAUDE.md "이 회사 용어" |
| E1-2 | 역할 6(관리자 · 생산관리 · 영양사 · 현장 작업자 · 출고 담당 · 외부업체) | E1 `roles` | 코어 4 를 **대체**. `ADMIN` 포함 | TD3 `role_matrix` rows 6 |
| E1-3 | 권한 매트릭스 6역할 × 8영역 → 12메뉴 | E1 `permissions` | `seed/permissions.csv` 72칸(§5) | TD3 `role_matrix` · 니즈푸드 `contracts/screen-map.md` §6 |
| E1-4 | 채번(SO · PP · WO · L · P · SH) | E1 `numbering` | `{접두}-{YYMMDD}-{nn}` 형식(D-29 가설) · 원료 LOT `L{YYMMDD}{NN}`(D-101) · 완제품 `P{YYMMDD}-{NNNN}`(D-201) | TD3 목업 번호 · 니즈푸드 decisions |
| E1-5 | 공통코드(메뉴유형 · 조리공정 · 자재구분 · 보관조건 · 조리라인 · 급식유형 · 지연사유 · 이슈유형 · 입력구분 · 설비유형 · 통신방식 …) | E1 `seeds` | `seed/codes.csv`. 코어 예약 그룹(`STOP_REASON`)에는 코드 추가만 | 니즈푸드 `db/seed.py COMMON_CODES` |
| E1-6 | 채널: 터치PC 3 · 스마트패드 2 · 현황판 1 | E1 `channels` | 터치PC · 스마트패드 → `pop`, 현황판 → `board`, 조회용 → `mobile` | TD3 `channels` · TD2 components |
| E1-7 | 메뉴 10(홈 · 기준 · 영업 · 자재 · 생산 · 품질 · 공정 · 설비 · POP · 시스템) | E1 `menus` | 코어 12 를 `rename` · `order` 로. 숨김 0 | TD3 `menu_shortcuts` |
| E2-1 | 메뉴유형 · 1인 제공량(g) · 알레르기 표기 · 제공단위 | E2 `attrs[bas_item]` | 표시만 | TD5 `BAS_MENU` |
| E2-2 | 조리공정구분(무침/취사/조리/볶음) · 보관기준온도 | E2 ext `x_foodservice_item_ext` | 지시 공정 기본값(FK) · 보관온도 판정값 | TD5 `BAS_MENU.COOK_PROC_CD` · `BAS_MATERIAL.STORAGE_TEMP` |
| E2-3 | 자재구분 · 보관조건 · 유통기한관리 여부 · 여유율(%) · 주거래처 | E2 `attrs[bas_item]` | 표시 · 입고 폼 필수 여부 | TD5 `BAS_MATERIAL` |
| E2-4 | 배치(솥) 기준인분 · 조리순서 · 주의사항 | E2 ext `x_foodservice_bom_ext.batch_serve_qty` + `attrs[bas_bom]` | 기준인분은 소요량 · 배치수 **집계**에 쓰므로 ext | TD5 `BAS_RECIPE_BOM` |
| E2-5 | 표준 소요시간(분) · 배치(솥) 기준수량 | E2 ext `x_foodservice_process_ext` | 지연 판정 · 배치수 산출 | TD5 `BAS_PROCESS_STD` |
| E2-6 | 유통기한(FIFO 추천 기준) · 배치(솥)번호 | E2 ext `x_foodservice_lot_ext` | 정렬 · 검색 키 | TD5 `MAT_RECEIPT.EXPIRY_DT` · `PRD_BATCH_RESULT.BATCH_NO` |
| E2-7 | 냉장/냉동 구분 · 임계온도(5 ℃ / -18 ℃) · 통신방식 · 제조사모델 | E2 ext `x_foodservice_equipment_ext` + `attrs[bas_equipment]` | 임계는 판정값 → ext, 나머지 표시 | AD2-053 · TD5 `EQP_STATUS` |
| E2-8 | 납기시간 · 급식유형 · 연계출처 | E2 ext `x_foodservice_order_ext`(납기시간 · 급식유형) + `attrs`(연계출처) | 출고지시 납기시간순 정렬 · 급식유형 검색 | TD5 `SAL_ORDER` |
| E2-9 | 샘플링 빈도("10솥당 1솥") · 판정기준 문장 | E2 ext `x_foodservice_insp_plan_ext` + `qua_insp_plan.standard` | 계획 샘플수 산출(D-204) | TD5 `BAS_SAMPLE_STD` |
| E2-10 | 보관위치 · 이동구분 · 입력구분 · 조리라인 · 이슈유형 · 점검구분 · 이상유형 | E2 `attrs`(mat_stock_trx · pop_work_result · job_work_order · qua_issue · eqp_check · eqp_fault) | 표시 · 필터 | TD5 각 `*_CD` |
| E3-1 | 교반기 RPM · 교반시간 · 조리온도 자동 수집(가공(취사) · 가공(볶음)) | E3 `process_params` source=collect | `seed/process_params.csv` 6행(agg avg · max · avg). 범위 `(미확정 D-08)` | TD1 data_collection · TD5 `PRD_BATCH_RESULT.AVG_RPM/STIR_MIN/AVG_TEMP` · decisions-dev2 D-206 |
| E3-2 | 조리시간(가공(조리) 반자동) | E3 `process_params` source=manual | 1행 | TD1 process_steps 가공(조리) |
| E3-3 | 검식(최종검사): 외관/맛/온도/이물 · 관능점수 · 코멘트 · 사진 | E3 `inspection_items` insp_type=최종 | 5행. 합격 점수 척도 `(미확정 D-505)` | TD5 `QUA_INSP_RESULT` · AD2-020 |
| E3-4 | 공정중 검사(신규) · 수입검사(외관 · 중량 · 사진) | E3 `inspection_items` insp_type=공정 · 입고 | 3 + 3행. 공정중 기준 `(미확정 D-08)` | TD1 process_steps · TD5 `MAT_RECEIPT.INSP_WEIGHT/INSP_PHOTO_PATH` |
| E4-1 | 보관온도 · 환경 이탈 기록(온도조절기 7 · 온습도 5) | E4 테이블 `x_foodservice_env_alarm`(화면 없음) | `on_collect` 가 쓴다. 표시는 `kpi_extra` 건수 | AD2-052 · 053 |
| E5-1 | 레시피 활성 버전 1건 · 배치 기준인분 > 0 | E5 `validate_bas_bom` | `hooks.md` §1 | TD3-002 체크 |
| E5-2 | 활성 레시피 없는 메뉴 지시 금지 · 단위 인분 · 공정 = 조리공정 | E5 `validate_job_work_order` | §2 | TD4-017 · 니즈푸드 `prd.create_work_order` |
| E5-3 | 식수(인분) × 1인량 → 소요량 | E5 `on_work_order_created` → `mat_requirement(source=hook)` | §3. 1인량 = 배합량 ÷ 배치 기준인분 | TD3-015(144.000 kg = 1,200 × 12.000/100) · AD2-015 |
| E5-4 | 배치 1건 = 완제품LOT 1건 · 배치번호 · 수집값 대표값 | E5 `on_result_closed` | §4. 코어가 collect 값을 채운 뒤 `kind=BATCH` 재태깅 + 배치번호 | TD3-018 체크 · D-201 |
| E5-5 | 검식 불합격 → 품질이슈 자동 등록 · 원인 공정 | E5 `on_inspection_judged` → `qua_issue(source=hook)` | §5 | TD1 공정중 검사 · 최종검사 |
| E5-6 | 검식 미합격 배치 출고 금지 · LOT 미지정 출고 차단 | E5 `validate_shipment` | §6 | TD3-035 체크 · AD2-020 기능 3 |
| E5-7 | 보관온도 이탈 판정(냉장 5 ℃ · 냉동 -18 ℃) | E5 `on_collect` → `x_foodservice_env_alarm` | §7 | AD2-053 |
| E5-8 | KPI 3(시간당 생산량 · 완제품 불량률 · 레시피 표준화율) + 관리지표 | E5 `kpi_extra` | §8 | TD1 kpi_effects · 니즈푸드 `app/kpi.py` |
| E5-9 | 투입 LOT FIFO 추천(유통기한 오름차순) · 유통기한 경과 LOT 투입 거부 | E5 `validate_pop_input`(추천과 다르면 경고 · 경과면 거부) | §9 | TD4-017 기능 3 · AD2-012 |
| E5-10 | 유통기한관리 자재는 입고 때 유통기한 필수 · 유통기한을 LOT ext 로 | E5 `validate_mat_receipt` + `on_lot_created` | §10 | TD3-012 제약 · TD5 `BAS_MATERIAL.EXPIRY_MNG_YN` |
| E5-11 | 클레임 이슈는 고객사 필수 | E5 `validate_qua_issue` | §11 | TD3-021 체크 |
| E6-1 | 배치(솥) LOT 종류 | E6 `lineage.lot_kinds: BATCH(base PRODUCT)` · `states` 표시어 | 관계 추가 없음(투입 · 출하 로 충분) | TD5 `PRD_BATCH_RESULT.PROD_LOT_NO` |
| E7-1 | Edge Collector → MES 수집(교반기 PLC Ethernet · RS-485 센서) | E7 collect = 코어 HTTP `POST /ifc/collect` 그대로. 드라이버 null | 태그 `RPM STIR_TIME TEMP HUMI PV_TEMP` | TD4-050 · 니즈푸드 `api-contract.md` §3 |
| E7-2 | SCM(2021) 수주 · 발주 연계 | E7 erp = null → 501 `미확정 (D-511)` | 규격 미정의(니즈푸드 D-03) | AD2-009 · TD2 components |
| E7-3 | 작업지시서(레시피 · 조리순서 · 주의사항 · 투입 LOT 추천) | E7 양식 `templates/print/work_order.html` **덮어쓰기** | §6 덮어쓴 템플릿 목록 | TD3-017 · 030 |
| E7-4 | 라벨 · 성적서 | E7 코어 양식 그대로(급식에는 바코드 라벨 없음 — 스마트패드 수기 입력이 정본) | `printing` null | AD2-012 제약 "바코드를 사용하지 않고" |

---

## 4. 팩 화면 0 — 근거

`spec.md` §8.3 은 foodservice 추가 모듈을 "없음(코어 + ext)" 으로 두었다. §2 매핑에서 코어 화면으로 가지 못한 니즈푸드 기능은 넷(검식 일자별 일정 019 · 발주 대사 034/MAT_PO · 완제품 일마감 013 · 생산계획 자동생성 016)인데, 전부 **G-P04 핵심 시나리오(수주 → 조리 지시 → 소요량 → 배치 실적 → 검식 → 출고) 밖**이고 `goal.md` §2.8 이 "참조 팩의 전체 화면 1:1 재현" 을 범위 밖으로 둔다. 그래서 웨이브 B 에서는 라우터 · 템플릿을 만들지 않고, 넷은 D-507 로 이관 단계에 넘긴다(그때 `X-FSV-01 검식 일정` · `X-FSV-02 발주` 가 후보). `function-list.md` 참조.

---

## 5. 테이블 매핑표 — 니즈푸드 테이블 37 → 코어 / `x_foodservice_*` / `attrs` / 범위 밖

집계: **코어만 22 · 코어 + ext 10 · 범위 밖 5 = 37**. ext 테이블 8 은 `schema_ext.md`.

| # | 니즈푸드 | 코어 테이블 | ext / attrs | 비고 |
|---|---|---|---|---|
| 1 | BAS_MENU | `bas_item`(item_type=제품) | `x_foodservice_item_ext`(cook_process_id) · attrs(menu_type · serve_qty_g · allergy_note · serve_unit) | |
| 2 | BAS_RECIPE_BOM | `bas_bom` + `bas_bom_dtl` | `x_foodservice_bom_ext`(batch_serve_qty) · attrs(cook_step_desc · caution_note) | 헤더(버전 · 활성) / 구성품 행 분리 |
| 3 | BAS_MATERIAL | `bas_item`(item_type=원재료/부자재) | `x_foodservice_item_ext`(storage_temp) · attrs(material_type · storage_cond · expiry_mng_yn · spare_rate · partner_code) | |
| 4 | BAS_PROCESS_STD | `bas_process` + `bas_process_param` | `x_foodservice_process_ext`(std_lead_min · batch_std_qty) · attrs(line · collect_type) | 관리항목 상·하한 = param min/max |
| 5 | BAS_SAMPLE_STD | `qua_insp_plan` | `x_foodservice_insp_plan_ext`(sample_freq · sample_n · sample_k · apply_from) | 합격 점수 = `min_value` |
| 6 | BAS_PARTNER | `bas_partner` | attrs(biz_no · delivery_addr) | |
| 7 | BAS_WORKER | `bas_worker` | attrs(job · line · join_date) | |
| 8 | BAS_COMMON_CODE | `bas_code` | — | |
| 9 | SAL_ORDER | `ord_order` | `x_foodservice_order_ext`(due_time · service_type) · attrs(src_system · if_dt) | 총 수주인분 = Σ 상세 |
| 10 | SAL_ORDER_DTL | `ord_order_dtl` | — | 출고인분 = 계보 `출하` 합 |
| 11 | SAL_SHIP | `shp_shipment` + `lot(kind=SHIPMENT)` + `lot_genealogy(출하)` | — | 출고지시번호 = `shipment_no` |
| 12 | MAT_RECEIPT | `mat_receipt` + `lot(MATERIAL)` + `qua_inspection(입고)` + `mat_stock_trx` | `x_foodservice_lot_ext`(expiry_date) · attrs(storage_loc · storage_temp_at_receipt) | 가용재고 = `v_lot_stock` |
| 13 | MAT_PROD_STOCK | `lot(kind=BATCH)` + 뷰 `v_lot_stock` | — | 테이블 없음. 일마감 범위 축소(D-507) |
| 14 | MAT_STOCK_MOVE | `mat_stock_trx`(trx_type=조정) | attrs(move_type · from_loc · to_loc) | |
| 15 | MAT_PO | — | — | **범위 밖**(코어에 발주 없음). 이관 단계 `x_foodservice_po` 후보 |
| 16 | PRD_PLAN | `ord_plan` | attrs(line · resched_reason) | 배치수는 계산 표시 |
| 17 | PRD_WORK_ORDER | `job_work_order` + `job_lot` | attrs(line · caution_note) | BOM 버전 = `bom_id` · 투입 LOT 추천 = `job_lot.lot_id` |
| 18 | PRD_BATCH_RESULT | `pop_work_result` + `pop_measure` + `lot(kind=BATCH)` | `x_foodservice_lot_ext`(batch_no · batch_seq) · attrs(input_type) | AVG_RPM · STIR_MIN · AVG_TEMP = `pop_measure` 3행 |
| 19 | QUA_INSP_PLAN | (`qua_insp_plan` 에 기준만) | — | 일자별 일정 행은 코어에 없음 — 범위 축소(D-507) |
| 20 | QUA_INSP_RESULT | `qua_inspection` + `qua_insp_item` | — | |
| 21 | QUA_ISSUE | `qua_issue` | attrs(issue_type · partner_code · prod_lot_no) | |
| 22 | PRC_PROGRESS | `pop_work_result` + 뷰 `v_work_order_progress` | — | |
| 23 | PRC_DELAY | `pop_stop` | attrs(fault_id · delay_desc) | 사유 = `STOP_REASON` 코드 추가 |
| 24 | EQP_STATUS | `bas_equipment` + `eqp_run_log` | `x_foodservice_equipment_ext`(storage_kind · temp_limit) · attrs(equip_type · maker_model · comm_type · install_loc) | |
| 25 | EQP_INSPECT | `eqp_check` | attrs(inspect_type · plan_date) | |
| 26 | EQP_FAULT | `eqp_fault` | attrs(fault_type · status) | |
| 27 | EQP_COLLECT | `ifc_collect_raw` + `eqp_collect` | `x_foodservice_env_alarm`(이탈 기록) | `OUT_OF_SPEC_YN` 은 코어에 없음(§7-①) |
| 28 | KPI_INDICATOR | `kpi_indicator` | — | `calc_kind=pack:<key>` |
| 29 | KPI_RESULT | `kpi_snapshot` | — | |
| 30 | AIA_QUERY | — | — | 범위 밖 |
| 31 | AIA_ANSWER | — | — | 범위 밖 |
| 32 | AIA_REPORT | — | — | 범위 밖 |
| 33 | AIA_VECTOR_DOC | — | — | 범위 밖 |
| 34 | SYS_USER | `sys_user` | attrs(org_type) | |
| 35 | SYS_ROLE | `sys_role` + `sys_permission` | — | 화면 단위 → 메뉴 단위(§7-②) |
| 36 | SYS_LOG | `sys_access_log` | — | |
| 37 | SYS_BACKUP_HIST | `sys_backup_hist` | — | |

---

## 6. 덮어쓴 코어 템플릿 (pack-contract R10)

| 파일 | 왜 |
|---|---|
| `templates/print/work_order.html` | 작업지시서에 레시피(구성품 · 배합량 · 배치 기준인분) · 조리순서 · 주의사항 · 투입 LOT 추천(유통기한 순)을 찍는다 — TD3-017 "레시피 · 주의사항 미리보기" · TD4-017 기능 2 |

~~`templates/sys/logs.html`~~ — 웨이브 B 에 SYS-04 「상세」 칸 `|t` 한 줄을 위해 덮어썼던 것은 **회전 4 에 지웠다**: 코어 `sys/logs.html` 이 기능명 · 대상에 `|t` 를 거친다(개발1 · `progress-dev1.md` §2 회전 4).

그 밖의 코어 템플릿은 덮어쓰지 않는다. `check_pack` WARN 목록이 이 1건과 같아야 한다.

---

## 7. 코어 변경 요청 후보 — E1~E7 로 다 못 담은 것

팩 안에서 우회할 수는 있지만 **코어가 바뀌면 다른 팩(kimchi · printfilm)도 같이 쓰는 것**들이다. 오케스트레이터가 `decisions.md` 에 `코어 변경 요청` 으로 올려 주기를 요청한다.

| # | 요구 | 어느 확장 지점이 왜 모자란가 | 코어 어디를 어떻게 | 다른 팩 |
|---|---|---|---|---|
| ① | 설비 단위 임계값과 이탈 표시 — 온도조절기 7(냉장 5 ℃ · 냉동 -18 ℃) · 온습도 5 의 수집값 이탈을 EQP-01 · EQP-04 화면에 '이탈' 로 보이기 | E3 는 **공정** 측정값(`bas_process_param` → `pop_measure`)이라 공정과 무관한 보관 · 환경 설비에는 선언 자리가 없다. E5 `on_collect` + E4 `x_foodservice_env_alarm` 으로 기록은 되지만 코어 화면(EQP-01 가동 현황 · EQP-04 수집값 조회)에는 나오지 않는다 | `bas_equipment_param`(설비 ID · 태그 · 하한 · 상한) 또는 `bas_process_param.process_id` NULL 허용 + `equipment_id`, 그리고 `eqp_collect.deviated` 를 `collect.receive` 가 채움. EQP-01/04 가 `deviated` 를 강조 | kimchi 냉장고 온습도 알람(spec §3.8 `[가설]` 과 같은 자리) · 송월 |
| ② | 화면 단위 권한 — 영양사는 기준정보 중 **메뉴 · 레시피 · 검식기준만** 등록·수정 | E1 `permissions` 칸은 메뉴(모듈) × 역할이고 `scopes` 는 기능의 `범위` 값(일반 · 입고검사 · 승인 …)뿐이라 "bas 의 BAS-01 · 02 · QUA-01 만 입력" 을 표현할 수 없다. 이 팩은 영양사 `bas=입력` 으로 **넓혀** 두었다(D-504) | `sys_permission.scopes` 에 화면 ID(`BAS-01`)를 허용하거나 `sys_permission` 에 `screen_id` 선택 컬럼. `rbac.require_fn` 이 기능의 화면이 scope 에 있는지 본다 | kimchi · printfilm 도 역할을 6~8 로 늘리면 같은 문제(problem.md Q7) |
| ③ | 수주 확정 → 생산계획 자동 생성 · 지시 취소 → 훅 행 되돌림 | E5 훅 목록에 `on_order_confirmed`(수주 상태 변경) · `on_work_order_canceled` 가 없다. 소요량 행(`source=hook`)을 만든 지시가 취소돼도 되돌릴 자리가 없다 | `interfaces.md` §9 에 `on_order_status_changed(cur, order, before, after, user)` · `on_work_order_canceled(cur, wo, user)` 추가. 코어 `ord` 가 수주 상태 변경(F-ORD-02)에서, `job` 이 F-JOB-04 에서 부른다 | printfilm Job 취소 시 Roll 예약 해제 · kimchi 절임통 배정 해제 |
| ④ | 산출물 ID ↔ 코어 화면 **N:1 · 1:N** 매핑 허용 | G-P03 "1:1 · 고아 0" 으로 쓰여 있다. 니즈푸드는 001+003→BAS-01, 004→BAS-03+04, 012→MAT-01+02, 017→JOB-01+03, 047→SYS-02+03 이 생긴다(§2). `import_design.py` 가 1:1 만 받으면 고아 6 이 찍힌다 | `tools/import_design.py` · `check_trace.py` 의 매핑 입력을 `산출물 ID → [코어 화면…]` 다대다로. G-P03 판정은 "산출물 ID 마다 코어/팩 화면 1개 이상 · 범위 밖 표시 허용" 으로 | kimchi 64화면 → 코어 51 도 N:1 이 많다 |
| ⑤ | `kpi_extra` 가 기간만 받는다 | KPI-02 '메뉴별' 드릴다운(TD3-028 버튼 `메뉴별`) 과 조리라인별 집계를 팩 지표로 내려면 `by` 인자가 필요하다 | `kpi_extra(frm, to, by=None)` 로 시그니처 확장(선택 인자라 기존 팩 호환) | kimchi 절임통별 · printfilm 설비별 |

E1~E7 로 **충분한 것**(코어 변경 불필요)이지만 적어 두는 것: 발주(MAT_PO) 는 코어 범위 밖이 맞고 팩 테이블로 가능 · 검식 일자별 일정은 팩 화면으로 가능 · 샘플링 빈도는 ext 로 가능.

---

## 8. 결정 후보 D-5nn — 오케스트레이터가 `decisions.md` 로 옮긴다

| # | 제목 | 내용 · 상태 |
|---|---|---|
| D-501 | **배치(솥) = 코어 실적 1건** | 니즈푸드 "1솥 = 1지시" 를 이 팩에서는 "1 조리 지시 = 메뉴 × 생산일(식수 전체) · 1솥 = 1 `pop_work_result` = 생산 LOT(`kind=BATCH`) 1건" 으로 둔다. 코어가 같은 지시에 실적을 순차로 여러 건 허용하므로(F-POP-02 "미종료 실적이 있으면 422" 만) 배치 분해 화면이 필요 없다. 배치번호 `B-nn` 은 지시 안 실적 순번. **가설** — 이관 때 지시 ↔ 솥 1:1 로 되돌리려면 `migrate.yaml` 에서 `PRD_WORK_ORDER` N건 → `job_work_order` 1 + 실적 N 으로 접는다 |
| D-502 | **레시피 수량 기준** | `bas_bom_dtl.qty` = 배치 1솥 기준 배합량(정본 `MIX_QTY` 그대로), `x_foodservice_bom_ext.batch_serve_qty` = 배치 기준인분. **1인량 = qty ÷ batch_serve_qty**, 소요량 = 식수 × 1인량 × (1 + loss_rate). 검산: 1,200인분 × 12.000/100 = 144.000 kg = TD3-015 목업. 가설 |
| D-503 | 역할 6 이 코어 4 를 대체 | `ADMIN PRODUCTION NUTRITIONIST WORKER SHIPPING VENDOR`. 코어 기본 권한표(goal.md §6)는 쓰지 않고 TD3 role_matrix 해석값(§5 · `seed/permissions.csv`)을 쓴다. 확정 요청 |
| D-504 | 영양사 기준정보 권한을 모듈 전체 `입력` 으로 넓힘 | §7-② 가 해결되기 전까지. 영양사가 공정 · 설비 · 거래처도 고칠 수 있다 — QA 는 이것을 결함으로 보지 않는다. 가설 |
| D-505 | 관능점수 척도 충돌 | TD3-005 목업 합격 점수 `80.00`(0~100, 체크 "합격 점수 0~100") vs AD2-020 제약 "관능 5점 척도 평균 4.0 이상". `inspection_items.csv` 의 `sensory_score` 는 하한 **비움 + `(미확정)`**. 도입기업 확정 대기 — 차단 아님(검식 판정은 사람이 합격/불합격을 고른다) |
| D-506 | 공정 측정값 범위 · 표준 소요시간 · 배치 기준수량 미확정 | 니즈푸드 D-08 승계. `process_params.csv` min/max 비움, `x_foodservice_process_ext` 값 NULL. TD3-004 목업 "교반속도 60~90rpm · 조리온도 160~180℃" 는 **예시 행**이라 넣지 않았다. 범위 이탈 표시는 값이 들어오면 코어 G-C24 가 그대로 한다 |
| D-507 | 범위 축소 4건 → 이관 단계 | 019 검식 일자별 일정(`X-FSV-01` 후보 · `x_foodservice_insp_schedule`) · 034/MAT_PO 발주 대사(`X-FSV-02` · `x_foodservice_po`) · 013 완제품 일마감 · 016 생산계획 자동생성(§7-③). 핵심 시나리오 밖(goal.md §2.8). 수주 '확정' 은 코어 `ord_order.status=진행` 으로 본다 |
| D-508 | 산출물 매핑 N:1 · 1:N | §2 의 5곳. `gates.yaml: design_source` 로 G-P03 을 돌릴 때 고아로 세면 안 된다(§7-④) |
| D-509 | 환경 설비 이탈은 팩 테이블에만 | §7-① 전까지 `x_foodservice_env_alarm` + `kpi_extra` 건수. 코어 EQP 화면에는 안 보인다 |
| D-510 | 채번 형식은 TD3 목업에서 | SO·PP·WO·SH `{접두}-{YYMMDD}-{nn}`(WO 만 4자리 — 목업 `WO-260812-0101`), 원료 LOT `L{YYMMDD}{NN}`, 완제품(배치) `P{YYMMDD}-{NNNN}`. 출하 LOT · 성적서 번호는 니즈푸드에 없어 코어 기본. 가설(니즈푸드 D-29 · D-101 · D-201 과 같다) |
| D-511 | SCM 연계 = ERP 어댑터 null | `POST /ord/orders` 의 'SCM연계' 는 코어 `erp` 501 `미확정 (D-511)`. 니즈푸드 D-03 승계 |
| D-512 | `write_scope` 의 키 · `permissions.csv` scopes 구분자 | 팩 라우터가 없어 훅만 코어 테이블에 쓴다. `pack.yaml: write_scope: { hooks: [...] }` 로 적었다 — `_template` 이 다른 키를 쓰면 그것으로 바꾼다. `seed/permissions.csv` 의 `scopes` 열은 `일반\|입고검사` 처럼 `\|` 로 여러 값을 적었다(`sys_permission.scopes text[]`) — 로더 형식이 다르면 그것으로. 아키텍트 확인 요청 |
| D-513 | `품목 → 메뉴` 치환의 부작용 | 원부자재도 `bas_item` 이라 BAS-01 제목이 '메뉴' 로 나온다(003 원부자재관리). 화면 안에서는 `item_type` 라벨(원재료 · 부자재)로 구분. 이관 단계에서 `품목: 메뉴·자재` 로 바꿀지 결정 |
| D-514 | 설비의 공정 FK | `bas_equipment.process_id` 가 NOT NULL 이면 교반기(취사 · 볶음 겸용) · 센서(공정 무관)를 넣을 수 없다. `seed/equipment.csv` 는 `process_code` 를 비웠다 — 아키텍트가 NULL 허용을 확인해 주기 바란다(설비 라인 배정은 니즈푸드 D-08 미확정) |

---

## 9. 미확정 값 목록 (지어내지 않은 것)

| 값 | 어디 | 출처의 상태 |
|---|---|---|
| 교반속도 · 교반시간 · 조리온도 상·하한 | `seed/process_params.csv` min/max | 니즈푸드 D-08(차단). 목업 예시만 존재 |
| 표준 소요시간(분) · 배치(솥) 기준수량 | `x_foodservice_process_ext` | D-08 |
| 조리라인(솥그룹) 정의 | `seed/codes.csv` `LINE` — 목업 `(예시)` 3건만 | D-08 · TD3 review |
| 공정중 검사 기준값 · 빈도 | `inspection_items.csv` insp_type=공정 | D-08 · TD1 "착수 시 확정" |
| 관능점수 척도 · 합격 점수 | `inspection_items.csv` `sensory_score` min | D-505 |
| 온·습도 임계치 | `x_foodservice_equipment_ext.temp_limit`(온습도센서) | AD2-052 "명시되어 있지 않다" |
| 온도조절기 #1~#4 · #6 · #7 의 냉장/냉동 구분 · 냉장 · 냉동고 대수 | `seed/equipment.csv` `storage_kind` | D-10. #5 만 목업 `(냉장)` |
| 레시피 표준화율 분모(전체 레시피 모집단) | `kpi_extra` recipe_std_rate | D-10 |
| 출하 LOT · 성적서 채번 | `pack.yaml: numbering` 에 없음 → 코어 기본 | 니즈푸드에 없음 |
| SCM 연계 규격 | `adapters.erp: null` | D-03 |
| 불량사유 코드값 | `codes.csv` 에 없음(`bas_defect_code` 비움) | D-10 — 도입기업 입력 |
| 교반기 제어 방식(EOCR vs 인버터) | 코어 무관(제어 없음) | D-13 — 참고 |

---

## 10. 구현 메모 (개발1 · 웨이브 B · 2026-10-09)

기획 문서(§1~§9)는 손대지 않았다. 코드 · 시드 · 테스트를 더했고, 코어가 받지 못하는 꼴만 바꿨다. 실측은 `progress-dev1.md` §4.

### 10.1 만든 것

| 파일 | 내용 |
|---|---|
| `schema_ext.sql` | `schema_ext.md` 의 8 테이블 그대로 (`x_foodservice_item_ext · bom_ext · process_ext · equipment_ext · order_ext · lot_ext · insp_plan_ext · env_alarm`) · 공통 컬럼 6 · 코어 ALTER 0 |
| `hooks.py` | `hooks.md` 12 (`validate_bas_bom` · `validate_job_work_order` · `on_work_order_created` · `on_result_closed` · `on_inspection_judged` · `validate_shipment` · `on_collect` · `kpi_extra` 7지표 · `validate_pop_input` · `validate_mat_receipt` · `on_lot_created` · `validate_qua_issue`) + `on_work_order_canceled`(D-505 · 소요량 되돌림) + ext 복사 `after_save_bas_item / bas_bom / bas_process / bas_equipment / ord_order / qua_insp_plan`(D-504) + `sync_ext`(이관 · 수동 적재 뒤 따라잡기). 쓰기 대상 = `mat_requirement · job_lot · qua_issue · lot(lineage.retag) · x_foodservice_*` 뿐 |
| `templates/print/work_order.html` | 조리 지시서 — 레시피 절(버전 고정 · 배치 기준인분 · 조리순서 · 주의사항 · 배합량 · 1인량) + 소요 품목의 지정 LOT = FIFO 추천. 레시피는 `validate_job_work_order` 가 지시 시점에 `job_work_order.attrs.recipe` 로 고정한 스냅샷을 찍는다 |
| `templates/sys/logs.html` | §6 참조 — 「상세」 칸 `\|t` 한 줄 (G-P05) |
| `seed/*_ext.csv` · `seeds[]` | 회전 5 — `seed_pack.py` 삭제(CR-9). `make db-seed` 한 번: seeds[] 6 + ext 3(`{file, table, key}` — item · process · equipment) · 역할 6 계정(seed_core) · 레시피 `seed/bom_example.csv`(seed_dev1 이 F-BAS-05 순서로 · `after_save_bas_bom` 훅이 bom_ext). 2회 실행 행 수 diff 0 |
| `tests/` | `gates.yaml` S1~S8 8파일 + `test_hooks_unit.py` + `test_pack_smoke.py` = 19 테스트. 코어 API 만 부른다(픽스처용 SQL 은 시작 시각 당기기 · 앞선 실행의 수집값 정리 뿐) |

### 10.2 기획값과 다르게 둔 것 (코어가 받는 꼴로)

| 어디 | 기획 | 구현 | 왜 |
|---|---|---|---|
| `seed/permissions.csv` scopes | `일반\|입고검사` | `일반·입고검사` | 로더 `packs._read_permissions_csv` 가 `·` `,` 만 가른다 (D-512 "로더 형식이 다르면 그것으로") |
| `seed/items_example.csv` 헤더 | `menu_type …` | `attrs.menu_type …` | `seed_core` 의 `items*` 로더가 `attrs.<키>` 열만 attrs 로 읽는다. `cook_process_code` · `storage_temp` 도 attrs 로 들어가고 `sync_ext` 가 ext 로 복사 |
| `seed/inspection_items.csv` 공정 · 최종 행 | `process_code PRC-070 / PRC-080` | 비움 | 코어 `qua.plan_for_lot` 이 `(process_id is null or = lot.process_id)` 로 고르므로 배치 LOT(조리 공정 PRC-060)에 PRC-080 항목이 붙지 않는다 |
| `seed/kpi_indicators.csv` | note 에 `3,500` 따옴표 없음 | 따옴표 | CSV 열 밀림 |
| `pack.yaml: seeds` | `bom_example.csv` · `kpi_indicators.csv` 포함 | `kpi_indicators.csv` 포함(`attrs.base_value · formula`) · `bom_example.csv` 는 seeds[] 밖(seed_dev1 이 읽는다) · ext CSV 3 추가 | seeds[] 가 BOM(헤더 + 구성품)을 받지 않는다 — 코어 변경 요청(progress-dev1.md §6) |
| `pack.yaml: attrs` | — | `bas_item.cook_process_code/storage_temp` · `bas_bom.batch_serve_qty(필수)` · `bas_process.collect_type/std_lead_min/batch_std_qty` · `bas_equipment.storage_kind/temp_limit/humi_limit/collect_path` · `ord_order.due_time/service_type` · `lot.expiry_date/storage_loc/storage_temp` · `qua_insp_plan.sample_freq/sample_qty/apply_from` 추가 | ext 값의 **입력 경로**. 코어 폼은 `attr_<키>` 만 받으므로 `hooks.md` §10 의 "폼 → attrs → 훅이 ext 복사" 를 전 ext 에 적용했다. `mat_receipt` 의 보관위치 · 보관온도는 `lot` 로 옮겼다 — 코어 F-MAT-01 이 `read_attrs(form, "lot")` 로 읽어 lot · mat_receipt 둘 다에 저장한다 |
| `pack.yaml: menus.rename` | `pop: 조리 실적 (POP)` · `trc: 배치 추적` | 기획값 그대로(회전 5) | rename 값은 t() 를 거치지 않는 최종 이름(D-38) |
| `pack.yaml: attrs` 라벨 | `조리공정구분` · `연결 설비이상` · `이상유형` | `공정구분` · `연결 설비고장` · `고장유형` | 라벨은 `t()` 를 거친다(D-38) — `공정구분` → `조리 공정구분`. `이상` 은 이 팩에서 `품질 이슈` 라 설비 고장 라벨에 쓰지 않는다 |
| `function-list.md` 절 번호 | 표가 §1 · `(없음)` 행 | 머리행만 있는 표를 §2 로 | 코어 `contracts._parse` 가 §2 에서 13열 표를 읽고 행을 기능으로 센다 |
| `gates.yaml: template_overrides` | 1건 | 2건 (`sys/logs.html` 추가) | §6 |
| ISSUE 채번 | `(미확정)` QI-… | 코어 `ISSUE` 규칙(`Q-YYMMDD-nnn` · D-202)을 쓴다 | 니즈푸드 목업 `QI-260812-01` 은 `pack.yaml: numbering` 에 넣지 않았다 — 도입기업 확인 전까지 코어 기본 |

### 10.3 가설 · 미확정으로 둔 것 (D-5nn 후보 — 오케스트레이터가 옮긴다)

- **급식 규칙의 적용 범위 = 팩 품목**: `hooks._pack_item` — `x_foodservice_item_ext` 행이 있거나 `bas_item.attrs` 에 팩 속성 키(`menu_type · material_type · expiry_mng_yn …`)가 있는 품목에만 `validate_bas_bom · validate_job_work_order · on_work_order_created · on_result_closed(BATCH 재태깅) · validate_shipment(원료 출고 금지)` 가 돈다. 검식 규칙은 `kind=BATCH` LOT 에만. 코어 예시 데이터(`-EX-` · attrs `{}`)는 중립 흐름으로 통과 — pack-contract R9(팩을 올린 채 코어 테스트)를 위한 가설.
- `validate_shipment` R1' (같은 지시 안 최종 합격 1건이면 다른 배치도 통과 · 불합격 1건이면 전부 거부) — `hooks.md` §6 의 가설 그대로. 영양사 확인 필요.
- `x_foodservice_lot_ext.input_type`: collect 측정값이 있으면 `자동(PLC)`, 없으면 로그인 채널 pop → `POP수동` · mobile → `스마트패드` · 그 밖 NULL(미확정). 코어 F-POP-03 이 실적 attrs 를 받지 않아 폼 값은 없다.
- `kpi_extra` 의 `target · base · note` 는 DB `kpi_indicator`(target_value · `attrs.base_value` · `attrs.formula` — 시드는 `seed/kpi_indicators.csv`)에서 읽는다(회전 5). `recipe_std_rate` 분모 note `(미확정 D-10)` · 범위 NULL 측정값은 어떤 값도 이탈이 아니다(D-506).
- `x_foodservice_insp_plan_ext` 는 0행 — 샘플링 빈도 원문이 니즈푸드 시드에 없고 코어 QUA-01 폼이 attrs 를 받지 않는다(`after_save_qua_insp_plan` 은 dict 로 단위 검증).
- `validate_pop_input` 의 FIFO 경고는 `row["attrs"]["fifo_warning"]` 에 남기지만 코어 `pop_input` 저장 경로가 attrs 를 쓰지 않아 화면에 나오지 않는다(거부는 하지 않는다 — 사양 그대로).
- 로그인 화면의 개발용 바로 로그인 버튼(D-605)은 코어 역할 4 이름이라 이 팩에서는 `관리자` 만 맞다 — 코어 `login.html`(개발1 웨이브 A 파일) 몫.

### 10.4 실행 순서

```
createdb -h /tmp mes_foodservice_db
MES_PACK=foodservice MES_PG_DSN=postgresql:///mes_foodservice_db make db-schema
MES_PACK=foodservice MES_PG_DSN=postgresql:///mes_foodservice_db make db-seed                                       # 2회 멱등 (seeds[] · 레시피 seed_dev1 · 역할 6 계정)
MES_PACK=foodservice MES_PG_DSN=postgresql:///mes_foodservice_db uv run pytest -q packs/foodservice/tests           # 19 passed
MES_PACK=foodservice MES_PG_DSN=postgresql:///mes_foodservice_db make pack-check check-pack check-schema check-trace check-terms
MES_PACK=foodservice uv run python src/mescore/tools/import_design.py                                                # G-P03
MES_PACK=foodservice MES_PG_DSN=postgresql:///mes_foodservice_db MES_PORT=8041 make run
```
