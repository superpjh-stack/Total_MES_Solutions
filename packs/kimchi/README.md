# `kimchi` 팩 — 임진강김치 MES 참조 팩 (기획자3 · 2026-10-09 · 기획 산출물)

> **코드는 없다.** 개발3이 웨이브 B 에서 이 폴더의 기획 산출물(`pack.yaml` · `seed/` · `schema_ext.md` · `hooks.md` · `function-list.md` · `gates.yaml` · `scenarios.md` · `migrate.yaml`)을 그대로 구현한다.
> 근거 사업: `../Limjingang Kimchi MES Platform` (읽기만). 정본: `docs/design/design.json` — TD3 화면 **64** · TD4 프로그램 66 · TD5 테이블 **67**(컬럼 635) · TD3 `role_matrix` 6역할 × 6영역.
> 코어 계약: `spec.md` §3 · §3.3 · §3.8 · §8.3 · §12 · `contracts/pack-contract.md` 전부. **코어 수정 0** 이 전제다(G-P01).
> 지어내지 않는다 — 임진강 산출물에 없는 임계값 · 규격은 `(미확정)`. 실제 고객 · 제품 고유명은 쓰지 않는다(품목 종류명까지만).

## 0. 한 줄 소개

김치 제조 9공정(입고/보관 → 절단/전처리 → 세척/절임 → 세척/선별 → 탈수 → 혼합(버무림) → 금속검출 → 포장/출고 → 냉장·숙성)을 코어 위에 얹는 팩. 핵심 시나리오(`spec.md` §8.3): **입고 → 절임통 투입(염도 기록) → 혼합 → 금속검출 합격 → 포장 → 출하 → 역추적**.

이 팩의 뼈대 결정 셋:

| # | 결정 | 근거 |
|---|---|---|
| 1 | 임진강의 **공정별 로그 테이블 18개**를 `pop_measure`(실적당 1값) / `eqp_collect`(센서 시계열) / `x_kimchi_*_log`(수기·집계 로그) / `qua_insp_item`(검사 항목) 넷으로 나눈다 — §3 | `spec.md` §3.3 경계 · `pack-contract.md` §3 |
| 2 | 임진강의 **공정 체인 추적**(`LOT_NO` 문자열이 테이블마다 따로)을 `lot` + `lot_genealogy` 로 바꾼다. LOT 은 입고 · 전처리 · 절임통 · 혼합 · 포장 · 숙성 · 출하 7단계에서 생긴다 — §5 | `spec.md` §2.4 · §13 |
| 3 | **알람은 둘로 나눈다** — 센서 시계열 이탈(온습도 · 염도 · 소독수)은 팩 테이블 `x_kimchi_env_alarm`(확인 · 해제 이력), 검사 · 측정값 이탈(CCP · 금속검출 NG · 중량 · 손실률)은 코어 `qua_issue(source=hook)` — §7 | `spec.md` §3.8 "알람은 E5 `on_collect` [가설]" |

규모(기대값 = `gates.yaml`): 팩 화면 **8** · 팩 테이블 **7** · 팩 기능 **24** · 팩 모듈 6(`cond` `wsh` `tank` `pkg` `age` `alm`) · 역할 6 · 권한 칸 18 메뉴 × 6 = **108** · 공정 측정값 19 · 검사 항목 9 · 계보 kind 2(`TANK` `AGING`) · relation 2(`혼합` `숙성`).

---

## 1. 코어 매핑표 — 임진강 화면 64 → 코어 화면 51

분류: **1:1**(코어 화면이 그대로 그 일을 한다) · **용어**(코어 화면 + `terms`/`attrs`/시드만으로 된다) · **팩**(팩 화면 `X-`) · **범위 밖**(AI Agent · 대시보드 설정 등 — `spec.md` §4.2 제외 항목 또는 임진강 D-01 범위 미확정).

| TD3 | 임진강 화면 | 분류 | 코어/팩 화면 | 어떻게 |
|---|---|---|---|---|
| 001 | 제품품목기준관리 | 용어 | BAS-01 품목 | `item_type` 완제품/원부자재 → 코어 `ITEM_TYPE`(제품/원재료) 치환. 용량(kg) · 포장단위 · 출고구분(홈쇼핑/일반출고)은 `attrs.bas_item`(표시용) |
| 002 | 레시피BOM관리 | 용어 | BAS-02 BOM | `terms: BOM → 레시피BOM`. 기준생산량 · 적용일 · 보안등급은 `attrs.bas_bom`. **열람 권한 별도 통제(`BOM_READ_YN`)는 코어에 없다 → §8 C-4** |
| 003 | 공정CCP기준관리 | 용어 | QUA-01 검사 계획 + BAS-04 공정 측정값 정의 | CCP 항목(금속검출 · 덤퍼/버무림 · 중량)은 `inspection_items.csv`(E3), 냉장 온도 CCP 는 `process_params.csv` 의 `collect` 범위. HACCP 문서번호 → `attrs.qua_insp_plan` |
| 004 | 설비탱크기준관리 | 1:1 | BAS-05 설비 | 절임통 8 · 냉장고 3 · 센서 · 충진기 … `equipment_example.csv`. PLC 태그 매핑 = `bas_process_param.collect_tag` + `attrs.bas_equipment(plc_tag · comm_type · equip_type)` |
| 005 | 거래처관리 | 1:1 | BAS-06 거래처 | 납품조건 · 담당자 → `attrs`. 개인정보 마스킹은 코어 템플릿 규약 |
| 006 | 작업자관리 | 1:1 | BAS-07 작업자 | 입사일 → `attrs`. 계정 연결 = `bas_worker.user_id` |
| 007 | 공통코드관리 | 1:1 | BAS-09 공통코드 | 그룹–상세 2단 = `bas_code(group_code, code)`. `codes.csv` |
| 008 | 수주등록조회 | 1:1 | ORD-01 수주 | 접수경로(카카오톡/팩스/직접) · 출고구분 → `attrs.ord_order` |
| 009 | 수주변경이력관리 | 1:1 | ORD-02 수주 이력 | `ord_order_hist` 그대로 |
| 010 | 납기캘린더조회 | 1:1 | ORD-03 납기 달력 | 홈쇼핑/일반출고 분할 열은 `attrs` 집계라 코어 화면에 없다 → §8 C-6 |
| 011 | 수주대비출고현황 | 용어 | ORD-01 수주(상세별 지시 · 출하 수량) + SHP-03 출하 현황 | 코어 F-ORD-04 계약 "상세별 지시 · 출하 수량" 이 잔량 · 진행률을 준다 |
| 012 | 생산계획수립 | 1:1 | ORD-04 생산계획 | 룰 기반 자동 생성은 임진강도 미확정 → 코어 수동 등록 + 확정 |
| 013 | 작업지시서관리 | 1:1 | JOB-01 작업지시 · JOB-02 지시 현황(현황판) · JOB-03 출력 | 현장 자동 표시 = `channels.board` 에 JOB-02 |
| 014 | 원부자재입고등록 | 1:1 | MAT-01 입고 | 입고 = 원부자재 로트(`lot kind=MATERIAL`) 생성. 유통기한 → `attrs.lot.expire_date` |
| 015 | 입고이력조회 | 1:1 | MAT-03 원재료 LOT + TRC-01 정방향 추적 | '역추적' 버튼 = TRC 링크 |
| 016 | 실시간재고관리 | 용어 | MAT-04 재고 | 보관위치(원품/탈수/숙성 냉장고 · 자재창고) → `attrs.lot.location`(표시). 위치별 집계가 필요하면 §8 C-7 |
| 017 | 레시피기반소요량계산 | 1:1 | MAT-05 소요량 + POP-03 투입 스캔 | 이론 = BOM × 지시, 실제 = `pop_input` 합, 차이 = 화면 계산 |
| 018 | 원물입고검사관리 | 1:1 | MAT-02 입고검사 | 이물 · 부패 · 외관 = `inspection_items.csv` 입고 유형 3항목 |
| 019 | 전처리중량관리 | 용어 | POP-02 작업 종료(측정값) | `input_weight_kg` · `output_weight_kg` 측정값 → 훅 `on_result_closed` 가 `loss_rate_pct` 계산 · 20% 초과 `deviated` + `qua_issue` (§7). 산식 측정값은 코어에 없다 → §8 C-3 |
| 020 | 세척조건관리 | 팩 | **X-COND-01** 품목별 공정 조건 기준 | 세척 기준이 **품목별**이라 `bas_process_param`(공정별 범위)에 못 들어간다 → `x_kimchi_item_std`. §8 C-2 |
| 021 | 소독수농도관리 | 팩 | **X-WSH-01** 소독수 농도 로그 | 센서(Interface Module) 시계열은 `eqp_collect`(`sanitizer_ppm`), 수기 기록 · 접촉시간 · 투입비율은 `x_kimchi_sanitizer_log`. 10ppm 미달 알람 = `on_collect` |
| 022 | 세척실적데이터수집 | 용어 | POP-02 작업 종료 + EQP-04 수집값 조회 | `wash_time_min` · `wash_volume_l` · `wash_weight_kg` 측정값(manual; PLC 연동 확정 시 `collect` 로 바꾸기만) |
| 023 | 절임조건설정 | 팩 | **X-COND-01** | 품목 × 크기구분별 기준 염도 · 절임시간 · 허용편차 → `x_kimchi_item_std` |
| 024 | 절임통운영관리 | 팩 | **X-TANK-01** 절임통 운영 · **X-TANK-02** 염도 추이 | 절임통 배치 = `pop_work_result` + `x_kimchi_tank`(1:1 ext). 염도 센서 시계열 = `eqp_collect`, 완료 시 대표값 = `pop_measure.salinity_pct`(agg last). 종료 시 LOT `kind=TANK` |
| 025 | 과절임부족정보관리 | 용어 | QUA-04 이상 · 시정 | `qua_issue`(공정=세척/절임 · LOT=절임 배치) + `attrs.qua_issue(deviation_type · deviation_qty)`. 불량 연계 = `qua_defect` |
| 026 | 양념계량관리 | 용어 | POP-03 투입 스캔 + MAT-05 소요량 | 양념 자품목별 실제 투입량 = `pop_input.qty`, 기준 = BOM, 편차율 = MAT-05 화면 계산. `terms: 투입 → 투입(계량)` 은 쓰지 않는다(중립어 유지) |
| 027 | 속넣기충진기데이터수집 | 1:1 | EQP-04 수집값 조회 | `work_speed` · `set_volume` 태그(`collect`). 통신 인터페이스 보유 여부 미확정(임진강 D-08) |
| 028 | 버무림CCP관리 | 용어 | QUA-02 검사 결과(공정 검사) | 검사 항목 `mix_ccp`(기준값 미확정). 판정 → `on_inspection_judged` → 이탈 시 `qua_issue` |
| 029 | 중량검사관리 | 용어 | QUA-02 검사 결과(최종 검사) | 검사 항목 `pack_weight_kg`(허용범위 미확정). 저울 연동 확정 시 `collect` 로 자동 입력(§8 C-5) |
| 030 | 자동테이핑기실적관리 | 팩 | **X-PKG-01** 테이핑기 실적 | 수집 원본 `eqp_collect`(`pack_count` · `run_state`) → `on_collect` 가 작업지시별 누계를 `x_kimchi_taping_log` 에 집계 |
| 031 | 출하냉장고관리 | 팩 | **X-AGE-02** 냉장고 입출고 | 완제품 배치의 냉장고 입 · 출고 이력 `x_kimchi_cold_move` + 현재 위치 `x_kimchi_lot_ext.location_equipment_id`. FIFO = 숙성 시작일 오름차순 |
| 032 | 숙성재고관리 | 팩 | **X-AGE-01** 숙성 재고 | 숙성 투입 = `lineage.split(relation=숙성)` → `kind=AGING` LOT + `x_kimchi_lot_ext(aging_start_date · aging_due_date)`. 3주는 기본값, 품목별 차등 미확정 |
| 033 | 냉장고온도습도모니터링 | 팩 | EQP-04 수집값 조회 + **X-ALM-01** 알람 이력 | 시계열 = `eqp_collect`(`temp_c` · `humidity_pct` · `set_temp_c`), 이탈 = `on_collect` → `x_kimchi_env_alarm`. 상 · 하한 미확정 |
| 034 | 공정별불량요소관리 | 1:1 | BAS-08 불량코드 + QUA-02(불량 등록) + QUA-03 불량 집계 | `kpi_target_yn` → `attrs.bas_defect_code` |
| 035 | 금속검출기관리 | 용어 | QUA-02 검사 결과(공정 검사) + X-ALM-01 | 검사 항목 `metal_detect`(OK/NG) · `inspect_qty` · `ng_qty`. NG → `on_inspection_judged` → `qua_issue`. PLC 자동 등록은 2단계(§8 C-5). **출하 금지 = `validate_shipment`** |
| 036 | 이슈이력관리 | 1:1 | QUA-04 이상 · 시정 | 재발방지 → `attrs.qua_issue.prevent_desc` |
| 037 | 사용자계정관리 | 1:1 | SYS-01 사용자 | |
| 038 | 권한역할관리 | 1:1 | SYS-02 역할 + SYS-03 권한 표 | 역할 6 = `roles`. 레시피 조회 칸은 §8 C-4 |
| 039 | 시스템로그조회 | 1:1 | SYS-04 접근 로그 | |
| 040 | 데이터백업이력조회 | 1:1 | SYS-06 백업 · 이관 | |
| 041 | 생산성KPI조회 | 용어 | KPI-02 집계 + KPI-03 지표 정의 | 시간당 생산량 = `kpi_extra`(§7) → `kpi_indicator.calc_kind=pack:throughput_kg_per_h` |
| 042 | 품질KPI조회 | 용어 | KPI-02 집계 | 완제품 불량률 = `kpi_extra` `pack:fg_defect_rate` |
| 043 | 재고KPI조회 | 범위 밖 | — | 임진강 D-01 범위 미확정 + 코어 집계 종류(생산 · 품질 · 납기 · 설비)에 재고 없음 |
| 044 | KPI지표관리 | 1:1 | KPI-03 지표 정의 | 계산식 잠금 · 변경이력 = 접근 로그(`change`) |
| 045 | 설비가동관리 | 1:1 | EQP-01 가동 현황 | 상태 기록(제어 아님) |
| 046 | 설비점검관리 | 1:1 | EQP-02 점검 | 차기 예정일 → `attrs.eqp_check` |
| 047 | 설비고장관리 | 1:1 | EQP-03 고장 | |
| 048 | 작업지시서목록 | 1:1 | POP-01 작업 목록(스캔) | |
| 049 | 라인목록 | 범위 밖 | — | 임진강 라인 편제 미정의. 필요하면 `attrs.bas_equipment.line` |
| 050 | 생산진행조회 | 1:1 | POP-02 작업 시작 · 종료 | 가동/정지/완료 = 시작 · 정지 · 종료 |
| 051 | 설비목록 | 1:1 | EQP-01 가동 현황(POP 채널) | |
| 052 | 발주목록 | 용어 | MAT-01 입고(POP 채널) + MAT-02 입고검사 | 발주(PO) 는 코어 · 임진강 둘 다 테이블이 없다 → 입고 등록 + 입고 불량 = 입고검사 불합격 |
| 053 | 출고지시서목록 | 1:1 | SHP-02 LOT 스캔 · 승인(POP 채널) | 출고 불량 = QUA-02 불량 등록 |
| 054~061 | 검색 Agent 8 | 범위 밖 | — | `problem.md` §5 제외(선택 팩 `agent`) |
| 062 | 대시보드 | 1:1 | KPI-01 현황판 + CMN-04 대시보드 | KPI 카드 4(시간당 생산량 · 불량률 · 당일 출하 · 숙성 재고) 중 숙성 재고는 `kpi_extra` |
| 063 | 상세대시보드 | 범위 밖 | — | 임진강 D-01 |
| 064 | 대시보드관리 | 범위 밖 | — | `kpi_indicator.visible_yn · seq` 로 부분 대체. 단말별 구성은 코어에 없다 |

**집계** — 1:1 **30** · 용어 **13** · 팩 **8**(020 · 021 · 023 · 024 · 030 · 031 · 032 · 033) · 범위 밖 **13**(043 · 049 · 054~061 · 063 · 064) = 64. 팩 화면 8 로 임진강 화면 8 을 덮는다(020 + 023 → X-COND-01 하나, 024 → X-TANK 둘, 033 → EQP-04 + X-ALM-01).

### 1.1 코어 화면 중 임진강에 대응물이 없는 것

코어 화면 51 중 임진강 TD3 에 대응이 없어 **팩이 숨기지 않고 그대로 켜 두는** 것: SHP-01 출하 등록 · SHP-04 성적서 · TRC-02 역방향 · TRC-03 번호 검색 · IFC-01/02 · SYS-05 채번 규칙 · POP-04 LOT 라벨. 임진강은 로트번호 표준 체계가 미확정(임진강 D-08)이었고 통합 추적 화면이 없었다(임진강 D-18). 이 팩은 코어 TRC 3화면이 그 자리를 채운다 — 메뉴 `hide` 없음.

---

## 2. 확장 지점 분류표 — 임진강 고유 기능 → E1~E7

| 임진강 고유 기능 | 근거 테이블 | 확장 지점 | 어디에 |
|---|---|---|---|
| 입고 전처리 중량 · 손실률 알람 | `RCV_PRETREAT` | **E3** 측정값 + **E5** `on_result_closed` | `process_params.csv` P02 `input_weight_kg` `output_weight_kg` `loss_rate_pct(max 20)` · 훅이 손실률 계산 · 이탈 → `qua_issue` |
| 세척 조건(품목별 기준) | `WSH_STD` | **E4** 팩 테이블 + **E3** | `x_kimchi_item_std` (X-COND-01) · 실적값은 `pop_measure` P03 `wash_*` |
| 세척 실적 | `WSH_RESULT` | **E3** | `pop_measure` P03 `wash_time_min` `wash_volume_l` `wash_weight_kg` · 판정은 훅이 `x_kimchi_item_std` 와 비교 |
| 소독수 농도 로그 | `WSH_SANITIZER_LOG` | **E7** collect + **E4** 로그 + **E5** `on_collect` | 센서 `SW-01` → `eqp_collect(sanitizer_ppm)` · 수기 → `x_kimchi_sanitizer_log` · 10ppm 미달 → `x_kimchi_env_alarm` |
| 절임 기준(품목 × 크기) | `SLT_STD` | **E4** | `x_kimchi_item_std` (염도 9/12/13% · 48h/24h · 허용편차 미확정) |
| 절임통 운영 | `SLT_TANK_OPR` | **E4** 모듈 + **E6** | `x_kimchi_tank`(실적 1:1 ext) · X-TANK-01 · 종료 시 `lineage.retag(TANK)` |
| 염도 로그(센서) | `SLT_SALINITY_LOG` | **E7** collect + **E3** 대표값 | `SS-01/02` → `eqp_collect(salinity_pct)` · 완료 시 `pop_measure.salinity_pct`(agg last) · 센서–절임통 매핑 미확정 |
| 절임 편차(과절임 · 부족) | `SLT_DEVIATION` | 코어 `qua_issue` + **E2** attrs | QUA-04 · `attrs.qua_issue.deviation_type/qty` |
| 양념 계량(작업자별 투입량 · 편차) | `MIX_WEIGHING` | 코어 `pop_input` + BOM | POP-03 · MAT-05. 자동 계량 설비 없음(수동 전제) |
| 충진기 로그 | `MIX_FILLER_LOG` | **E7** collect | `FL-01` `SF-01` → `eqp_collect(work_speed · set_volume)` · EQP-04 |
| CCP 기준 · 결과(버무림) | `BAS_CCP_STD` · `MIX_CCP_RESULT` | **E3** 검사 항목 + **E5** | `inspection_items.csv` 공정 P06 `mix_ccp` · `on_inspection_judged` → `qua_issue` |
| 중량 검사(전수) | `PKG_WEIGHT_INSP` | **E3** 검사 항목 | `inspection_items.csv` 최종 P08 `pack_weight_kg` · 범위 미확정 |
| 테이핑기 로그 | `PKG_TAPING_LOG` | **E7** collect + **E4** 집계 로그 + **E5** `on_collect` | `AP-01` → `eqp_collect(pack_count · run_state)` → `x_kimchi_taping_log` 작업지시별 누계 · X-PKG-01 |
| 출하 냉장고 입출고 | `PKG_COLD_STOCK` | **E4** | `x_kimchi_cold_move` · `x_kimchi_lot_ext.location_equipment_id` · X-AGE-02 |
| 숙성 재고 | `AGE_STOCK` | **E6** `AGING` + **E2** ext | `lineage.split(relation=숙성)` → `kind=AGING` · `x_kimchi_lot_ext(aging_start_date · aging_due_date)` · X-AGE-01 |
| 숙성 환경 로그 | `AGE_ENV_LOG` | **E7** collect | `TH-01~10` `TC-01~04` → `eqp_collect(temp_c · humidity_pct · set_temp_c)` · EQP-04 |
| 숙성 환경 알람 | `AGE_ENV_ALARM` | **E5** `on_collect` + **E4** | `x_kimchi_env_alarm`(확인 · 조치 · 해제) · X-ALM-01 · 임계값 = `process_params` 범위(미확정이면 판정 안 함) |
| 금속검출 로그 | `QUA_METAL_LOG` | **E3** 검사 항목 + **E5** `validate_shipment` · `on_inspection_judged` | 공정 P07 검사 `metal_detect` OK/NG · NG → `qua_issue` · 미통과 LOT 출하 422 |
| 공정별 불량 유형 | `QUA_DEFECT_TYPE` `QUA_DEFECT` | 코어 `bas_defect_code` `qua_defect` + **E2** | `attrs.bas_defect_code.kpi_target_yn` |
| 온습도센서 10식 · 온도조절기 4식 | `BAS_EQUIP` `IF_SENSOR_RAW` | **E7** collect 어댑터 | `equipment_example.csv` `collect_yn=Y` + 태그 매핑(`adapters/collect_tags.py`) |
| 소독수 Interface Module 1식 | 〃 | **E7** | `SW-01` 태그 `sanitizer_ppm` `contact_min` |
| 아이스박스 자동포장기 1대 | 〃 | **E7** + **E4** | `AP-01` 태그 `pack_count` `run_state` · `eqp_run_log(source=collect)` 는 코어 `collect` 가 쓴다 |
| 시간당 생산량 · 완제품 불량률 KPI | `KPI_MASTER` `KPI_RESULT` | **E5** `kpi_extra` | `pack:throughput_kg_per_h` · `pack:fg_defect_rate` · `pack:aging_stock_kg` |
| 역할 6 · 메뉴 10 · 채번 · 공통코드 | `SYS_ROLE` `SYS_ROLE_AUTH` | **E1** | `pack.yaml` `roles` `menus` `numbering` · `permissions.csv` · `codes.csv` |
| 터치PC · 스마트패드 · 현황판 채널 | TD3 `channels` | **E1** | `channels: pop(터치PC) · mobile(스마트패드) · board(현황판)` |
| 레시피BOM 열람 통제 · 재고 KPI · 라인 · 대시보드 구성 · 검색 Agent | — | **안 들어감** | §8 코어 변경 요청 후보 또는 범위 밖 |

전부 E1~E7 에 들어간다(G4). 들어가지 않는 것은 §8 에만 적었다.

---

## 3. 로그 · 측정값 테이블 분류 — 이 팩 기획의 핵심

규칙(`spec.md` §3.3 · `pack-contract.md` §3): **실적 한 건당 키당 한 값**이면 `pop_measure`, **센서가 주기적으로 보내는 시계열**이면 `eqp_collect`(collect 경유), **사람이 때때로 적는 시계열 · 집계용 로그**면 `x_kimchi_*_log`, **합격/불합격을 판정하는 항목**이면 `qua_insp_plan` → `qua_insp_item`.

| # | 임진강 테이블 | 성격 | 간다 | 키 · 비고 |
|---|---|---|---|---|
| 1 | `RCV_PRETREAT` 전처리중량실적 | 실적당 중량 2 + 파생 1 | **`pop_measure`** | P02 `input_weight_kg` `output_weight_kg` `loss_rate_pct`(훅 산출) |
| 2 | `WSH_RESULT` 세척실적 | 실적당 3값 | **`pop_measure`** | P03 `wash_time_min` `wash_volume_l` `wash_weight_kg` |
| 3 | `SLT_SALINITY_LOG` 염도측정이력 | 센서 시계열(절임 중 연속) | **`eqp_collect`** | `SS-01/02` 태그 `salinity_pct`. 완료 대표값만 `pop_measure`(agg last) |
| 4 | `WSH_SANITIZER_LOG` 소독수농도이력 | 센서 시계열 + 수기 접촉시간 | **`eqp_collect`** + **`x_kimchi_sanitizer_log`** | 센서 `sanitizer_ppm`은 collect · 수기(센서 미연동 구간 · 접촉시간 · 투입비율)는 팩 로그 |
| 5 | `MIX_FILLER_LOG` 충진기수집 | 설비 시계열 | **`eqp_collect`** | `work_speed` `set_volume` |
| 6 | `PKG_TAPING_LOG` 테이핑기실적 | 설비 시계열 + 작업지시별 집계 | **`eqp_collect`** + **`x_kimchi_taping_log`** | 원본 collect · 작업지시별 박스 누계 · 가동분은 팩 로그(집계 · 재고 연계용) |
| 7 | `AGE_ENV_LOG` 냉장고온습도이력 | 센서 시계열 | **`eqp_collect`** | `temp_c` `humidity_pct` `set_temp_c` |
| 8 | `AGE_ENV_ALARM` 온습도이탈알람 | 사건 로그(확인 · 조치) | **`x_kimchi_env_alarm`** | `on_collect` 가 만든다 |
| 9 | `QUA_METAL_LOG` 금속검출이력 | LOT 당 판정 | **`qua_insp_item`** | 공정 P07 검사 `metal_detect` · PLC 원본은 `eqp_collect`(2단계) |
| 10 | `MIX_CCP_RESULT` 버무림CCP실적 | 실적당 판정 | **`qua_insp_item`** | 공정 P06 검사 `mix_ccp` |
| 11 | `PKG_WEIGHT_INSP` 중량검사실적 | 포장품 판정(전수) | **`qua_insp_item`** | 최종 P08 검사 `pack_weight_kg` |
| 12 | `RCV_INSPECT` 원물입고검사 | 입고 판정 | **`qua_insp_item`** | 입고 검사 `foreign_matter` `decay` `appearance` |
| 13 | `SLT_TANK_OPR` 절임통운영실적 | 실적 1:1 확장 | **`x_kimchi_tank`** | `pop_work_result` ext |
| 14 | `PKG_COLD_STOCK` 출하냉장고입출고 | 이동 로그 | **`x_kimchi_cold_move`** | LOT × 냉장고 |
| 15 | `SLT_DEVIATION` 과절임부족이력 | 이상 | 코어 **`qua_issue`** | attrs |
| 16 | `MIX_WEIGHING` 양념계량실적 | 투입 | 코어 **`pop_input`** | |
| 17 | `IF_SENSOR_RAW` 센서수집원장 | 원문 | 코어 **`ifc_collect_raw`** | |
| 18 | `EQP_RUN_LOG` 설비가동이력 | 상태 구간 | 코어 **`eqp_run_log`** | |

**집계** — `pop_measure` **2**(+ 염도 대표값 1) · `eqp_collect` **6**(염도 · 소독수 · 충진기 · 테이핑 · 온습도 · 금속 원본) · 팩 로그 **4**(소독수 수기 · 테이핑 집계 · 냉장 이동 · 환경 알람; + 절임통 ext 1) · 검사 항목 **4**(금속 · CCP · 중량 · 입고) · 코어 1:1 **4**. 18 개 중 **코어 테이블을 새로 요구하는 것 0**.

---

## 4. 테이블 매핑표 — 임진강 67 → 코어 / `x_kimchi_*` / `attrs` / 범위 밖

| 임진강 | 코어 / 팩 | 비고 |
|---|---|---|
| `BAS_ITEM` | `bas_item` + `attrs(capacity_kg · pack_unit · ship_type)` | `ITEM_TYPE` 완제품→제품 · 원부자재→원재료/부자재 |
| `BAS_BOM` `BAS_BOM_DTL` | `bas_bom` `bas_bom_dtl` + `attrs(base_qty · valid_from/to · security_lv)` | |
| `BAS_PROCESS` | `bas_process` + `attrs(ccp_yn · collect_cycle)` | 9 공정 `seed/processes.csv` |
| `BAS_CCP_STD` | `qua_insp_plan`(금속 · CCP · 중량) · `bas_process_param`(냉장 온도 · 소독수 · 손실률 범위) | HACCP 문서번호 → attrs |
| `BAS_EQUIP` | `bas_equipment` + `attrs(equip_type · plc_tag · comm_type · collect_item)` | 수집 태그는 `process_params.collect_tag` |
| `BAS_PARTNER` | `bas_partner` + `attrs(manager · delivery_term)` | |
| `BAS_WORKER` | `bas_worker` + `attrs(join_date)` | |
| `BAS_CODE_GRP` `BAS_CODE_DTL` | `bas_code` | 2단 → 1표 |
| `ORD_ORDER` `ORD_ORDER_DTL` `ORD_ORDER_HIST` `ORD_PLAN` | `ord_order` `ord_order_dtl` `ord_order_hist` `ord_plan` | `SHIP_QTY · REMAIN_QTY · PROGRESS_RATE` 는 저장 안 함(계보 · 출하로 계산) |
| `ORD_WORK_ORDER` | `job_work_order` + `attrs(display_yn)` | |
| `MAT_RECEIPT` | `mat_receipt` + `lot(kind=MATERIAL)` | `LOT_NO` → `lot.lot_no` · `EXPIRE_DATE` → `attrs.lot` |
| `MAT_STOCK` `MAT_STOCK_TRX` | `mat_stock` `mat_stock_trx` | `LOCATION_CD` → `attrs.lot.location` |
| `MAT_REQUIRE` | `mat_requirement` + `pop_input`(실제 투입) | |
| `RCV_INSPECT` | `qua_inspection(insp_type=입고)` `qua_insp_item` | |
| `RCV_PRETREAT` | `pop_work_result` + `pop_measure` | |
| `WSH_STD` `SLT_STD` | **`x_kimchi_item_std`** | 품목별 기준 |
| `WSH_RESULT` | `pop_work_result` + `pop_measure` | |
| `WSH_SANITIZER_LOG` | `eqp_collect` + **`x_kimchi_sanitizer_log`** | |
| `SLT_TANK_OPR` | `pop_work_result` + **`x_kimchi_tank`** | |
| `SLT_SALINITY_LOG` | `eqp_collect` (+ `pop_measure` 대표값) | |
| `SLT_DEVIATION` | `qua_issue` + attrs | |
| `MIX_WEIGHING` | `pop_input` | |
| `MIX_FILLER_LOG` | `eqp_collect` | |
| `MIX_CCP_RESULT` | `qua_inspection(공정)` `qua_insp_item` | |
| `PKG_WEIGHT_INSP` | `qua_inspection(최종)` `qua_insp_item` `qua_defect` | |
| `PKG_TAPING_LOG` | `eqp_collect` + **`x_kimchi_taping_log`** | |
| `PKG_COLD_STOCK` | **`x_kimchi_cold_move`** + **`x_kimchi_lot_ext`** | |
| `PKG_SHIP` | `shp_shipment` + `lot(kind=SHIPMENT)` + `lot_genealogy(출하)` | `LOT_NO` 역추적 키 → 계보 |
| `AGE_STOCK` | `lot(kind=AGING)` + **`x_kimchi_lot_ext`** | |
| `AGE_ENV_LOG` | `eqp_collect` | |
| `AGE_ENV_ALARM` | **`x_kimchi_env_alarm`** | |
| `QUA_DEFECT_TYPE` `QUA_DEFECT` | `bas_defect_code` + attrs · `qua_defect` / `pop_scrap` | |
| `QUA_METAL_LOG` | `qua_inspection(공정)` `qua_insp_item` | |
| `QUA_ISSUE` | `qua_issue` + `attrs(prevent_desc)` | |
| `SYS_USER` `SYS_ROLE` `SYS_ROLE_AUTH` `SYS_LOG` `SYS_BACKUP_HIST` | `sys_user` `sys_role` `sys_permission` `sys_access_log` `sys_backup_hist` | `BOM_READ_YN` 은 §8 C-4 |
| `KPI_MASTER` `KPI_RESULT` `KPI_STD_HIST` | `kpi_indicator` `kpi_snapshot` · 변경이력 = `sys_access_log` | 산식은 `kpi_extra` 코드 |
| `EQP_RUN_LOG` `EQP_CHECK` `EQP_FAULT` | `eqp_run_log` `eqp_check` `eqp_fault` | |
| `POP_LINE` | 범위 밖(라인 편제 미정의) | |
| `POP_PROGRESS` | `pop_work_result` `pop_stop` | |
| `POP_RECEIPT` `POP_SHIP_ORDER` | `mat_receipt` / `shp_shipment` + 계보 | POP 채널 입력일 뿐 별도 표 없음 |
| `AGT_*` 6 | 범위 밖 | 선택 팩 `agent` |
| `DSH_CONFIG` `DSH_METRIC_TS` | 범위 밖 / `kpi_snapshot` | |
| `IF_SENSOR_RAW` `IF_ERP_LINK` | `ifc_collect_raw` `ifc_erp_link` | |

**집계** — 코어 1:1 **44** · 팩 `x_kimchi_*` **7**(원천 9표) · `attrs` 만으로 **(위 코어 행에 포함)** · 범위 밖 **9**(`POP_LINE` · `AGT_*` 6 · `DSH_*` 2) → 44 + 7-table-sources 9 + 9 = 62, 나머지 5(`BAS_CCP_STD` · `MAT_REQUIRE` · `KPI_STD_HIST` · `POP_RECEIPT` · `POP_SHIP_ORDER`)는 코어 둘 이상에 **나뉘어** 들어간다. 67 전부 자리가 있다.

---

## 5. 공정 체인 추적 → `lot_genealogy`

임진강은 `MAT_RECEIPT.LOT_NO` → `RCV_PRETREAT.LOT_NO` → `SLT_TANK_OPR`(작업지시) → `MIX_*`(배치번호) → `PKG_SHIP.LOT_NO` 를 **문자열로 따라갔다**(통합 추적 화면 없음, 임진강 D-18). 표준에서는 LOT 이 생기는 자리와 화살표(relation)만 정하면 추적은 코어 재귀 조회다.

```
 MAT-01 입고          POP-02 종료(P02 전처리)   POP-02 종료(P03 절임, 절임통)      POP-02 종료(P06 혼합)         QUA-02 검사(P07)   POP-02 종료(P08 포장)   X-AGE-01 숙성 투입      SHP-02 스캔
 ───────────          ──────────────────────   ────────────────────────────      ─────────────────────         ────────────────   ─────────────────────   ──────────────────      ───────────
 M1 배추 ─────투입───▶ P1 전처리배추 ──투입───▶ T1 절임통1 (kind TANK) ─┐
                                      └──투입───▶ T2 절임통2 (kind TANK) ─┤ 혼합(base 합병)
 M2 고춧가루 ───────────────────────────────────────────────────────투입─┼──▶ X1 혼합배치 ──(금속검출 합격)──투입──▶ K1 포장완제품 ──숙성(base 분할)──▶ A1 숙성배치 (kind AGING) ──출하──▶ S1 출하로트
 M3 마늘 ───────────────────────────────────────────────────────────투입─┘                                        │
                                                                                                                  └──────────────────────────────출하(당일출고)──────────────▶ S1
 kind:  MATERIAL       PRODUCT                 TANK                             PRODUCT                               PRODUCT                 AGING                     SHIPMENT
```

| 단계 | LOT 이 생기는 곳 | kind | 화살표(relation → base) | 만드는 코어 기능 |
|---|---|---|---|---|
| 입고 | MAT-01 | `MATERIAL` | — | F-MAT-01 |
| 전처리(P02) | POP-02 종료 | `PRODUCT` | 배추 LOT → 전처리 LOT `투입` | F-POP-03 + F-POP-06 |
| 절임(P03, 절임통) | POP-02 종료 → 훅 `on_result_closed` 가 `lineage.retag(TANK)` | **`TANK`**(base PRODUCT) | 전처리 LOT → 절임통 배치 `투입`(한 LOT 을 두 통에 나눠 담으면 `투입` 2줄 · 수량 분담) | F-POP-03 · `x_kimchi_tank` 는 실적 ext |
| 혼합(P06) | POP-02 종료(합병 옵션) | `PRODUCT` | 절임통 배치 N → 혼합 배치 **`혼합`(base 합병)** · 양념 원재료 → 혼합 배치 `투입` | F-POP-03 의 `merge(relation=혼합)` 옵션(D-12) + F-POP-06 |
| 금속검출(P07) | LOT 없음 | — | 검사만(`qua_inspection` on 혼합 배치) | F-QUA-04/05 |
| 포장(P08) | POP-02 종료 | `PRODUCT` | 혼합 배치 → 포장 완제품 `투입` | F-POP-03 |
| 숙성(P09, 일반출고만) | X-AGE-01 숙성 투입 → `lineage.split(relation=숙성)` | **`AGING`**(base PRODUCT) | 포장 LOT → 숙성 배치 **`숙성`(base 분할)** — 부분 수량 허용, 남은 수량은 포장 LOT 재고 | F-X-AGE-02 |
| 출하 | SHP-02 스캔 | `SHIPMENT` | 포장 LOT(홈쇼핑 당일출고) 또는 숙성 배치 → 출하 로트 `출하` | F-SHP-05 |

- 왜 절임통이 `TANK` kind 인가: 절임통 배치는 수량 · 품목 · 공정 · 설비(절임통)가 있는 추적 단위이고, 역추적 화면에서 "어느 절임통에서 며칠 절였나"를 노드로 보여야 한다. `v_lot_state` · 추적 SQL 은 `kind_base=PRODUCT` 만 보므로 코어는 바뀌지 않는다.
- 왜 `혼합` 을 `합병` base 로 두는가: 절임통 2~3 통이 한 혼합 배치로 합쳐지는 N:1 이고, 합쳐진 뒤 절임통 배치는 `소진` 이어야 한다(`v_lot_state` 는 `합병` 부모를 소진으로 본다).
- 왜 `숙성` 을 `분할` base 로 두는가: 포장 LOT 일부만 숙성 냉장고에 넣고 나머지는 당일 출고하는 경우가 있다(출고구분 홈쇼핑/일반출고). 분할은 부분 수량을 허용하고 남은 잔량을 `v_lot_stock` 이 계산한다.
- S1 기대값: 계보 **9행**(투입 1 + 투입 2 + 혼합 2 + 투입 2 + 투입 1 + 출하 1) · 역추적 도달 원재료 **3** · 깊이 5. 숙성 S4 는 +2행.

---

## 6. 팩 화면 8 · 모듈 6 · 테이블 7 (요약 — 상세는 `pack.yaml` · `function-list.md` · `schema_ext.md`)

| 화면 | 이름 | 모듈 | 경로 | 채널 | 쓰는 테이블 |
|---|---|---|---|---|---|
| X-COND-01 | 품목별 공정 조건 기준 | `cond` | `/cond/item-standards` | web | `x_kimchi_item_std` |
| X-WSH-01 | 소독수 농도 로그 | `wsh` | `/wsh/sanitizer` | web, pop | `x_kimchi_sanitizer_log` |
| X-TANK-01 | 절임통 운영 | `tank` | `/tank/operations` | web, pop, board | `x_kimchi_tank` |
| X-TANK-02 | 염도 추이 | `tank` | `/tank/salinity` | web, board | — (`eqp_collect` 읽기) |
| X-PKG-01 | 테이핑기 실적 | `pkg` | `/pkg/taping` | web, board | `x_kimchi_taping_log` |
| X-AGE-01 | 숙성 재고 | `age` | `/age/stock` | web, mobile | `lot` `lot_genealogy`(lineage) · `x_kimchi_lot_ext` |
| X-AGE-02 | 냉장고 입출고 | `age` | `/age/cold-moves` | web, mobile | `x_kimchi_cold_move` · `x_kimchi_lot_ext` |
| X-ALM-01 | 알람 이력 | `alm` | `/alm/alarms` | web, pop, board | `x_kimchi_env_alarm` |

코어 템플릿 덮어쓰기(R10): **없음**(계획). 성적서 양식은 코어 `print/document` 그대로.

---

## 7. 알람 — 코어에 알람 모듈이 없다는 점을 어떻게 다루는가

임진강 TD3 standard_note 3 의 기준 이탈 6종: 손실률 20% 초과 · 소독수 10ppm 미달 · 절임 염도 이탈 · 냉장고 온도 이탈 · 금속검출 NG · 중량 미달. 코어에는 "임계값 → 알림 → 확인 · 해제 이력" 모듈이 없다. 판단:

| 이탈 | 발생 지점 | 어디에 남기나 | 왜 |
|---|---|---|---|
| 냉장고 온 · 습도 이탈 | `on_collect` (센서 메시지마다) | **`x_kimchi_env_alarm`** | 분 단위 고빈도. `qua_issue` 는 "이상 → 조치 → 종결" 업무 건이지 센서 알림 큐가 아니다. 같은 설비 · 태그의 미해제 알람이 있으면 **새로 만들지 않고** 마지막 값 · 횟수만 갱신(폭주 방지) |
| 소독수 10ppm 미달 | `on_collect` | `x_kimchi_env_alarm` | 〃 |
| 절임 염도 이탈(허용편차 밖) | `on_collect`(기준은 그 절임통의 진행 중 배치 → `x_kimchi_item_std`) | `x_kimchi_env_alarm` | 〃. 허용편차가 비어 있으면 판정하지 않고 `미확정` |
| 손실률 20% 초과 | `on_result_closed` | `pop_measure.deviated=Y` + **`qua_issue(source=hook)`** | 실적 1건당 1건 — 업무 조치 대상 |
| 금속검출 NG · CCP 이탈 · 중량 미달 | `on_inspection_judged` | `qua_issue(source=hook)` + `lot.insp_status`(코어가 이미) | 검사 판정은 코어 흐름. 출하 금지는 `validate_shipment` |

**결론**: 1차는 팩 테이블 + `qua_issue` 로 충분하다. 코어 알람 모듈은 **참조 팩 둘 이상**(foodservice 의 솥 온도 · printfilm 의 ΔE 는 `pop_measure.deviated` 로 끝나 보임)이 같은 것을 요구할 때 §8 C-1 로 승격한다. 코어가 해 주면 좋은 최소치는 C-1 에 적었다.

---

## 8. 코어 변경 요청 후보 (결정 대장 등재 전 — 아키텍트 판단용)

| # | 요청 | 어느 확장 지점이 모자란가 | 다른 팩도 쓰는가 | 이 팩의 임시 처리 |
|---|---|---|---|---|
| **C-1** | 코어 알람: `collect.receive` 가 `bas_process_param(source=collect)` 의 min/max 를 **자동 판정**하고 `eqp_alarm`(설비 · 태그 · 값 · 발생 · 확인 · 해제) 1표 + EQP-05 화면 | E5 — 팩마다 `on_collect` 에 같은 비교 코드 · 같은 알람 표를 만든다 | foodservice(솥 온도) · 송월(가동) 가능성 | `x_kimchi_env_alarm` + `on_collect`(§7) |
| **C-2** | `bas_process_param` 에 `item_id`(선택) — 품목별 범위 | E3 — 세척 · 절임 기준이 품목 × 크기별인데 코어 범위는 공정별 | printfilm(판사양별 속도) 가능 | `x_kimchi_item_std` + 훅 비교 |
| **C-3** | 파생 측정값: `bas_process_param.formula`(다른 키의 산식) | E3 — 손실률 · 편차율을 훅이 계산해 `pop_measure` 에 쓴다(`write_scope: pop_measure`) | foodservice(1인량 대비 편차) | `on_result_closed` 가 계산 |
| **C-4** | 화면 단위 권한 예외(`sys_permission.screen_overrides` 또는 BAS-02 전용 scope) — 레시피BOM 열람 통제 | E1 — 메뉴 × 역할 칸으로는 `bas` 안의 BAS-02 만 막을 수 없다 | foodservice(레시피 = 영업비밀) **확실** | `permissions.csv` 에 `bas` 칸은 그대로, README 에 한계 명시 · `미확정 (D-504)` |
| **C-5** | `collect` → 검사 결과 자동 등록 헬퍼 `qua.record_inspection(cur, lot_no, insp_type, items)` | E5 — 금속검출 PLC · 저울 연동 시 `on_collect` 가 `qua_inspection` `qua_insp_item` `lot.insp_status` 에 직접 써야 한다(write_scope 3개) | printfilm(ΔE 측정기) 가능 | 2단계(통신 확정 후). 1차는 QUA-02 수기 |
| **C-6** | `stats` 집계의 `attrs` 키 group_by 허용(표시용 속성이지만 출고구분별 납기 집계) | E2 규칙(attrs 를 집계에 쓰면 FAIL) | — | 재현하지 않음(ORD-03 은 합계만) |
| **C-7** | `lot.location_id`(보관 위치 — 설비 또는 창고) | E2 — 냉장고 위치가 검색 · FIFO 정렬에 쓰여 `attrs` 로는 FAIL | foodservice(냉장 보관) 가능 | `x_kimchi_lot_ext.location_equipment_id` |
| **C-8** | `kpi_snapshot` 배치가 `kpi_extra` 지표도 찍기 | E5 — `kpi_extra` 는 조회 시만 계산, 현황판 추이에 팩 지표가 없다 | 전 팩 | 추이 없이 현재값만 |

---

## 9. 미확정 값 (임진강 산출물에 없어 `(미확정)` 으로 둔 것)

| 항목 | 임진강 근거 | 이 팩의 처리 |
|---|---|---|
| 냉장고 온도 · 습도 상 · 하한 | D-08 "냉장고 온도 상·하한 없음" | `process_params.csv` P09/P01 `temp_c` `humidity_pct` min/max 빈 칸 → `on_collect` 판정 안 함 |
| 절임 염도 허용편차 | `SLT_STD.TOLERANCE` NULL | `x_kimchi_item_std.tolerance` NULL → 염도 알람 안 함 |
| 절임 12% 조건의 기준 시간 | TD4-023 "48h 9% · 24h 13%" 만 | 12% 행 시간 빈 칸 |
| 중량 허용 범위 | D-08 | `inspection_items.csv` `pack_weight_kg` min/max 빈 칸 |
| 덤퍼 · 버무림 CCP 수치 | D-08 | `mix_ccp` min/max 빈 칸 |
| 금속검출기 감도 · 대수 · 통신 지원 | D-08 · 035 체크 | `MD-01` 1대 `collect_yn=N`(수기) |
| 염도센서 2식 ↔ 절임통 8기 매핑 | 024 체크 · D-206 | `adapters/collect_tags.py` 매핑 표 빈 칸, 센서 설비 `SS-01/02` 별도 등록 |
| 온습도센서 10식 ↔ 냉장고 배치 | D-206 | `equipment_example.csv` 공정 배치는 임진강 시드(TD2 hardware)대로, 냉장고 연결 빈 칸 |
| 저울 · 충진기 · 속넣기 통신 사양 | 029 · 027 체크 | `collect_yn=N` |
| 로트번호 표준 체계 | D-08 | `numbering` 은 코어 기본형(`가설`) |
| 품목별 숙성 기간 차등 | 032 체크 | 기본 21일, `x_kimchi_item_std(aging_days)` 로 품목별 입력 가능 |
| 세척 횟수 | `spec.md` §8.3 에 있으나 임진강 TD5 에 없음 | `wash_count` 선언(필수 아님) · 비고에 출처 |
| 비가동 사유 · 고장 유형 코드값 · 배추 크기 구분 | D-208 | `codes.csv` 에 `(예시)` 만 |
| 안전재고 · 수집 주기 · 로그 보존 | D-05 · D-08 | 시드 없음 |

---

## 10. 결정 후보 D-5nn (아키텍트가 `decisions.md` 로 옮긴다)

| # | 결정 | 상태 제안 |
|---|---|---|
| D-501 | 절임통 배치 = `pop_work_result`(공정 P03 · 설비 절임통) + `x_kimchi_tank` 1:1 ext, 종료 시 `lineage.retag(TANK)`. 절임통 투입 등록 화면(X-TANK-01)은 코어 F-POP-02 를 호출하지 않고 **자기 라우터에서 `pop_work_result` 를 쓰지 않는다** — 시작 · 종료는 POP-02, X-TANK-01 은 절임통 · 기준 · 예정 완료 · 상태만 ext 에 쓴다 | 가설 |
| D-502 | 혼합 = `merge(relation=혼합)` (base 합병) · 숙성 = `split(relation=숙성)` (base 분할). §5 | 가설 |
| D-503 | 알람 이원화(§7): 센서 이탈 `x_kimchi_env_alarm`, 검사 · 측정값 이탈 `qua_issue(source=hook)` | 가설 |
| D-504 | 레시피BOM 열람 통제는 코어 변경(C-4) 전까지 재현하지 않는다. BAS-02 는 `bas` 칸 권한(조회 이상)으로 열린다 — 임진강 D-10 과 다름 | 차단(코어 변경 요청) |
| D-505 | 역할 6: `PM` `PROD` `QA` `FIELD` `ADMIN` `VENDOR`(TD3 role_matrix 순). 코어 기본 4 를 대체. `VENDOR` 는 `sys` 조회만 | 가설 |
| D-506 | 현장 작업자(`FIELD`) 의 `mat` `shp` 는 `입력`(TD3 052 · 053 POP 입고 · 출고 근거) — role_matrix 의 "수주·계획·재고 조회" 보다 화면 문장을 따른다(임진강 DEF-QA3-004 같은 해석) | 가설 |
| D-507 | 임진강 메뉴 10 → 코어 12 + 팩 6 을 `menus.order` 로 임진강 순서(기준 · 수주 · 자재 · 공정 · 포장 · 품질 · 설비 · 분석 · 시스템)에 맞춘다. `hide` 없음 | 가설 |
| D-508 | 세척 · 절임 품목별 기준은 `x_kimchi_item_std` 한 표(공정 × 품목 × 크기 × 키). 코어 C-2 가 되면 폐기 | 가설 |
| D-509 | 금속검출 · 중량 검사는 1차 QUA-02 수기, PLC · 저울 연동은 C-5 후 2단계 | 가설 |
| D-510 | 손실률 · 편차율 같은 파생 측정값은 훅이 `pop_measure` 에 `source=manual` 로 쓴다(코어 `source` 값에 `hook` 이 없다) — C-3 전까지 | 가설 |
| D-511 | 숙성 기본 21일(임진강 "3주")은 `x_kimchi_item_std.aging_days` 가 없을 때만. 품목별 차등 미확정 | 가설 |
| D-512 | `on_collect` 알람 폭주 방지: 같은 (설비 · 태그) 미해제 알람이 있으면 신규 행 대신 `last_value · count · last_at` 갱신 | 가설 |
| D-513 | 043 재고 KPI · 049 라인 · 063 상세 대시보드 · 064 대시보드 관리는 범위 밖. 임진강 D-01 과 같은 미확정 | 확정 제안 |

---

## 구현 메모 (개발3 · 2026-10-09 · 웨이브 B)

위 기획 산출물을 코드로 옮겼다. 코어(`src/mescore/**`) 수정 0 · `ALTER` 0 · `lot_genealogy` 직접 SQL 0 · 채번 직접 SQL 0 · `pop_measure` 시계열 0.

### 구현 파일

| 파일 | 내용 |
|---|---|
| `schema_ext.sql` | `schema_ext.md` 의 테이블 7 + 뷰 2 (`x_kimchi_v_tank_board` · `x_kimchi_v_aging_stock` — `check_pack` R3 의 `x_kimchi_` 접두 규칙 때문에 `v_kimchi_*` 대신 이 이름) |
| `hooks.py` | `validate_shipment` · `on_inspection_judged` · `on_collect` · `on_result_closed` · `kpi_extra(frm, to, by=None)` — `hooks.md` §1~§5 |
| `alarm.py` | `raise_env` (D-512 합침) · `ack` · `clear` — `x_kimchi_env_alarm` 에 쓰는 유일한 자리 |
| `common.py` | 조회 · 판정 헬퍼 (기준은 전부 데이터에서 · 없으면 None) · `x_kimchi_lot_ext` upsert |
| `adapters/collect_tags.py` | 설비 종류 · 태그 표(`equipment_example.csv` 의 `equip_type` · `collect_tags` 열을 읽는다) · 태그 → 알람 종류 · 센서 ↔ 절임통 고정 매핑 `SENSOR_TO_TANK = {}` (미확정 D-206). 드라이버는 코어 HTTP 수신 그대로 |
| `routers/{cond,wsh,tank,pkg,age,alm}.py` | 기능 24 = 엔드포인트 24 (`function-list.md` 의 API 열 글자 그대로) |
| `templates/{cond,wsh,tank,pkg,age,alm}/*.html` | 화면 8 — `base.html` + `ui` 매크로 · `{{ t("…") }}` |
| `tests/` | `_helpers.py` · S1~S4 · 기능 24 · 용어 · 스모크 = 26건 |

### 기획 문서에서 고친 것 (코드가 돌기 위한 최소 수정 — 전부 데이터 · 머리글)

| 파일 | 고친 것 | 왜 |
|---|---|---|
| ~~`pack.yaml` `screens[].channels` 라벨~~ | **회전 4 되돌림** — 기획 그대로 코드(`web/pop/mobile/board`). 코어 `packs.load` 가 코드 · 라벨 둘 다 받는다(아키텍트 `733074f`) | — |
| ~~`pack.yaml` `menus.rename.trc` `추적`~~ | **회전 4 되돌림** — 기획 그대로 `로트 추적`(겹말 방지 `packs.translate`) | — |
| `pack.yaml` `menus.rename.qua` | 기획 `품질이상` → `품질` (남김) | `t(이상)=품질 이슈` 라 `품질품질 이슈`. 겹말 방지는 치환값이 키를 품을 때(`추적`→`로트 추적`)만 막는다 — 붙여 쓴 합성어는 그대로 치환된다(progress-dev3 §3-22) |
| `pack.yaml` `menus.add[]` | `owner: 개발3` · `channels` 추가 | `contracts._validate` 가 기능의 담당 = 모듈 owner 를 요구(없으면 `kimchi` 가 되어 24건 전부 거부) |
| `function-list.md` | `## 1. 읽는 법` · `## 2. 기능` 머리글 추가 | `contracts` 로더가 `## 2.` 절의 표만 읽는다 |
| `seed/items_example.csv` | 머리글 `capacity_kg` → `attrs.capacity_kg` 등 | `seed_core` 는 `attrs.` 접두 열만 attrs 로 넣는다 (아니면 조용히 버려진다) |
| `seed/permissions.csv` | `shp,PROD` 범위 `승인` → `일반·승인` | 범위를 적으면 **그 범위만** 쓸 수 있다(D-13). 시나리오(1-14)의 PROD 출하 등록 · 스캔 · 승인에 둘 다 필요 |
| `seed/inspection_items.csv` | `metal_detect` · `inspect_qty` · `ng_qty` 의 공정 `P07` → 빈 칸(공정 검사 공통) | 코어 QUA-02 는 **LOT 의 공정**으로 검사 항목을 고른다. 금속검출은 혼합 배치(P06 LOT)에 하므로 P07 전용 행이면 칸이 안 뜬다(§3 요청: 검사 공정 선택) |

고치지 않은 것: `gates.yaml` 의 `expect` 값(아래 "기대값과 다른 실측" 참고 — 기획자 확인 뒤 갱신 요청) · `equipment_example.csv` 의 `equip_type` · `comm_type` · `collect_tags` 열(`seed_core` 설비 시드가 attrs 를 받지 않아 **DB 에는 안 들어간다** — `adapters/collect_tags.py` 가 CSV 를 직접 읽어 보완 · §3 요청) · `processes.csv` 의 `ccp_yn`(같은 이유).

### 기대값과 다른 실측 (gates.yaml `expect` ↔ 코어가 실제로 하는 일)

| 항목 | 기획 | 실측 | 왜 |
|---|---|---|---|
| S1 계보 행 | 9 (혼합 2) | **10 (혼합 3)** · 깊이 5 · 원재료 3 · TANK 2 소진 · salinity 2 — 나머지 같다 | 코어 F-POP-03 에 "합병 옵션" 이 없다. 합병(D-12)은 `POST /pop/result/{id}/merge` 가 **새 LOT** 을 만든다. 그래서 양념 투입 실적 LOT(X1′ · M2 · M3 투입)도 혼합의 부모가 된다: `merge([X1′, T1, T2], relation=혼합)` → X1(P06 · 1090). X1′ 를 첫 부모로 두어 X1 이 혼합 공정 · 품목을 잇는다 |
| S1 `p1_remain_qty` | 150 | **0** (소진) | P1 수량 = 양품 850(출력 중량). 850 − 500 − 350 = 0. 기획의 150 은 P1 을 1000 으로 본 계산 |
| 한 LOT 을 두 통에 | 투입 2줄 | 투입 2줄 — 단 **두 실적 모두 종료 전에 스캔** | 코어 `v_lot_state` 는 PRODUCT 에 자식 계보가 하나라도 생기면 `소진` 으로 본다(잔량 무관). 첫 통 실적을 종료한 뒤 둘째 통에 스캔하면 422 (§3 요청) |
| S4 숙성 투입 | `split(relation=숙성)` 1회 · K1 잔량 400 · 계보 +2 | `split(count=2, qtys=[600, 400])` + 잔량 LOT `retag(PRODUCT)` → 숙성 2행 · 잔량은 **새 번호의 포장 LOT**(400 재고) · K1 소진 · 전량이면 `retag(AGING)`(계보 0행) | 코어 `lineage.split` 은 N ≥ 2 (D-503 은 merge 쪽만 N ≥ 1) — 부분 수량 1 → 1 분할이 없다 (§3 요청) |
| 절임 완료 | `on_result_closed` 가 `x_kimchi_tank.status=완료` 도 | **하지 않는다** — F-X-TANK-03 만 완료 | `function-list` F-X-TANK-03 "완료 전 실적 종료는 422 가 아니다(순서 자유) · 둘 다 끝나야" 를 따랐다. 그래야 종료 뒤 진행 중 배치의 염도 이탈이 TANK LOT(`lot_id`)에 붙는다(S3 `salinity_alarm_lot_kind=TANK`) |
| 기능 단위 권한(F-X-WSH-02 · TANK-02 · AGE-02 = PROD · ADMIN) | 그 역할만 | **메뉴 단위** — FIELD 도 `wsh` `tank` `age` 입력이라 할 수 있다 | 코어 RBAC 은 메뉴 × 역할 칸. 화면 · 기능 단위 예외는 D-502(코어 변경 요청) 전까지 없다 |
| 금속검출 NG 의 LOT 투입 | 코어 F-POP-06 422 | **투입된다** (K2 가 만들어지고 출하 승인에서 422) | `lineage.assert_usable` 은 PRODUCT 의 `insp_status` 를 보지 않는다(재고만). 출하 금지는 `validate_shipment` 가 조상까지 보고 막는다 |

### 훅이 정한 세부 (hooks.md 에 없던 것)

- `validate_shipment` 거부 2 의 "이탈": `item_judgement=불합격` · `deviated` · **select 항목은 값 ≠ 기준(`standard`)** (`metal_detect` 는 범위가 없어 코어가 항목 판정을 비운다 — `NG ≠ OK`). 거부 1 은 그 LOT + 역추적 조상에서 `metal_detect` 가 든 최신 검사가 `합격`이고 값이 기준과 같을 때만 통과. 순서: CCP 불합격 → 금속검출 기록 없음 → 숙성 미완료.
- `on_inspection_judged` 멱등 키: `qua_issue.content` 안의 `[item_key]` 표식 (`qua_issue` 에 항목 컬럼이 없고 `attrs` 를 WHERE 에 쓰면 D-05 WARN). 손실률 이슈는 `[result:<id>:loss_rate_pct]`.
- `on_result_closed`: 절임통 배치에 센서가 연결돼 있고 코어가 채운 `pop_measure.salinity_pct` 가 비어 있으면(실적 설비 = 절임통이라 코어 `fill_collect` 는 센서 값을 못 본다) **센서 구간 last** 로 채운다(source=collect). 손실률은 `source=manual`(D-510).
- `on_collect` 테이핑 집계: `pack_count` 가 직전 누계보다 작으면 리셋으로 보고 이번 값을 증분으로. `run_state` 값 형식은 미확정이라 `1/0 · run/stop · 가동/정지` 만 해석, 그 밖은 NULL.
- `kpi_extra`: kg 환산은 `bas_item.attrs.capacity_kg`, 없으면 제외 + `note`. 일 근무시간 8h(정본 TD1) — `kpi_indicator(throughput_kg_per_h).attrs.work_hours_per_day` 가 있으면 그 값. 목표값은 시드에 없다(KPI-03 입력).

### 코어 시드 순서

회전 4 에서 코어 `seed_core` 가 공정 → 품목 → 설비 → `process_params` → `inspection_items` → 나머지 순으로 넣는다(아키텍트 `6c77eb9`). 임시 `seed_bootstrap.py` 는 지웠다 — 새 DB 도 `make pack-db NAME=kimchi`(또는 `MES_PACK=kimchi make db-seed`) 하나로. 빈 DB 에서 2회 실행 행 수 diff 0 · 팩 테스트 26 통과(2026-10-09 임시 DB 실측).
`equipment_example.csv` 의 `equip_type` · `comm_type` · `collect_tags` · `processes.csv` 의 `ccp_yn` 은 헤더가 `attrs.` 접두가 아니라 DB 에 안 들어간다(시드가 경고) — `adapters/collect_tags.py` 가 CSV 를 직접 읽는다. 헤더를 `attrs.<키>` 로 바꾸는 것은 그 어댑터와 함께 다음 회전.

### 이 팩이 덮어쓴 코어 템플릿 (R10)

(없음)

### 미확정 처리 (실측)

| 항목 | 코드에서 |
|---|---|
| 냉장고 온 · 습도 상 · 하한 | `bas_process_param` min/max NULL → `on_collect` 판정 안 함 (S3 는 픽스처가 임시로 넣고 되돌린다) |
| 절임 염도 허용편차 | `x_kimchi_item_std.tolerance` NULL → 염도 알람 안 함 · X-COND-01 에 `미확정` 배지 |
| 염도센서 ↔ 절임통 | `SENSOR_TO_TANK = {}` · 배치 등록 때 센서를 고르지 않으면 X-TANK-01 타일 `미확정 (D-206)` · X-TANK-02 `미확정 (D-206)` |
| 중량 · CCP 수치 | `qua_insp_plan` min/max NULL → 코어가 항목 판정을 비운다 · 훅도 판정 안 함 |
| 테이핑 `run_state` 값 | 모르는 값은 NULL |
| 숙성 기간 품목별 차등 | `x_kimchi_item_std(P09, aging_days)` 없으면 21 (D-511) — 응답에 `aging_days_source` |

### G-P03 추적표 — `design.json` TD3 화면 64 ↔ 코어/팩 화면 (`tools/import_design.py` 가 읽는 표 · §1 매핑표를 산출물 ID 로 다시 적음 · D-506 N:1 · 1:N 허용)

| 산출물 ID | 화면명 | 코어/팩 화면 | 분류 | 비고 |
|---|---|---|---|---|
| MES-TD3-001 | 제품품목기준관리 | BAS-01 | 용어 | §1 |
| MES-TD3-002 | 레시피BOM관리 | BAS-02 | 용어 | §1 |
| MES-TD3-003 | 공정CCP기준관리 | BAS-04 + QUA-01 | 용어 | §1 |
| MES-TD3-004 | 설비탱크기준관리 | BAS-05 | 1:1 | §1 |
| MES-TD3-005 | 거래처관리 | BAS-06 | 1:1 | §1 |
| MES-TD3-006 | 작업자관리 | BAS-07 | 1:1 | §1 |
| MES-TD3-007 | 공통코드관리 | BAS-09 | 1:1 | §1 |
| MES-TD3-008 | 수주등록조회 | ORD-01 | 1:1 | §1 |
| MES-TD3-009 | 수주변경이력관리 | ORD-02 | 1:1 | §1 |
| MES-TD3-010 | 납기캘린더조회 | ORD-03 | 1:1 | §1 |
| MES-TD3-011 | 수주대비출고현황 | ORD-01 + SHP-03 | 용어 | §1 |
| MES-TD3-012 | 생산계획수립 | ORD-04 | 1:1 | §1 |
| MES-TD3-013 | 작업지시서관리 | JOB-01 + JOB-02 + JOB-03 | 1:1 | §1 |
| MES-TD3-014 | 원부자재입고등록 | MAT-01 | 1:1 | §1 |
| MES-TD3-015 | 입고이력조회 | MAT-03 + TRC-01 | 1:1 | §1 |
| MES-TD3-016 | 실시간재고관리 | MAT-04 | 용어 | §1 |
| MES-TD3-017 | 레시피기반소요량계산 | MAT-05 + POP-03 | 1:1 | §1 |
| MES-TD3-018 | 원물입고검사관리 | MAT-02 | 1:1 | §1 |
| MES-TD3-019 | 전처리중량관리 | POP-02 | 용어 | §1 |
| MES-TD3-020 | 세척조건관리 | X-COND-01 | 팩 | §1 |
| MES-TD3-021 | 소독수농도관리 | X-WSH-01 | 팩 | §1 |
| MES-TD3-022 | 세척실적데이터수집 | EQP-04 + POP-02 | 용어 | §1 |
| MES-TD3-023 | 절임조건설정 | X-COND-01 | 팩 | §1 |
| MES-TD3-024 | 절임통운영관리 | X-TANK-01 + X-TANK-02 | 팩 | §1 |
| MES-TD3-025 | 과절임부족정보관리 | QUA-04 | 용어 | §1 |
| MES-TD3-026 | 양념계량관리 | MAT-05 + POP-03 | 용어 | §1 |
| MES-TD3-027 | 속넣기충진기데이터수집 | EQP-04 | 1:1 | §1 |
| MES-TD3-028 | 버무림CCP관리 | QUA-02 | 용어 | §1 |
| MES-TD3-029 | 중량검사관리 | QUA-02 | 용어 | §1 |
| MES-TD3-030 | 자동테이핑기실적관리 | X-PKG-01 | 팩 | §1 |
| MES-TD3-031 | 출하냉장고관리 | X-AGE-02 | 팩 | §1 |
| MES-TD3-032 | 숙성재고관리 | X-AGE-01 | 팩 | §1 |
| MES-TD3-033 | 냉장고온도습도모니터링 | EQP-04 + X-ALM-01 | 팩 | §1 |
| MES-TD3-034 | 공정별불량요소관리 | BAS-08 + QUA-02 + QUA-03 | 1:1 | §1 |
| MES-TD3-035 | 금속검출기관리 | QUA-02 + X-ALM-01 | 용어 | §1 |
| MES-TD3-036 | 이슈이력관리 | QUA-04 | 1:1 | §1 |
| MES-TD3-037 | 사용자계정관리 | SYS-01 | 1:1 | §1 |
| MES-TD3-038 | 권한역할관리 | SYS-02 + SYS-03 | 1:1 | §1 |
| MES-TD3-039 | 시스템로그조회 | SYS-04 | 1:1 | §1 |
| MES-TD3-040 | 데이터백업이력조회 | SYS-06 | 1:1 | §1 |
| MES-TD3-041 | 생산성KPI조회 | KPI-02 + KPI-03 | 용어 | §1 |
| MES-TD3-042 | 품질KPI조회 | KPI-02 | 용어 | §1 |
| MES-TD3-043 | 재고KPI조회 | — | 범위 밖 | §1 |
| MES-TD3-044 | KPI지표관리 | KPI-03 | 1:1 | §1 |
| MES-TD3-045 | 설비가동관리 | EQP-01 | 1:1 | §1 |
| MES-TD3-046 | 설비점검관리 | EQP-02 | 1:1 | §1 |
| MES-TD3-047 | 설비고장관리 | EQP-03 | 1:1 | §1 |
| MES-TD3-048 | 작업지시서목록 | POP-01 | 1:1 | §1 |
| MES-TD3-049 | 라인목록 | — | 범위 밖 | §1 |
| MES-TD3-050 | 생산진행조회 | POP-02 | 1:1 | §1 |
| MES-TD3-051 | 설비목록 | EQP-01 | 1:1 | §1 |
| MES-TD3-052 | 발주목록 | MAT-01 + MAT-02 | 용어 | §1 |
| MES-TD3-053 | 출고지시서목록 | SHP-02 | 1:1 | §1 |
| MES-TD3-054 | 검색 Agent 8 (1) | — | 범위 밖 | §1 |
| MES-TD3-055 | 검색 Agent 8 (2) | — | 범위 밖 | §1 |
| MES-TD3-056 | 검색 Agent 8 (3) | — | 범위 밖 | §1 |
| MES-TD3-057 | 검색 Agent 8 (4) | — | 범위 밖 | §1 |
| MES-TD3-058 | 검색 Agent 8 (5) | — | 범위 밖 | §1 |
| MES-TD3-059 | 검색 Agent 8 (6) | — | 범위 밖 | §1 |
| MES-TD3-060 | 검색 Agent 8 (7) | — | 범위 밖 | §1 |
| MES-TD3-061 | 검색 Agent 8 (8) | — | 범위 밖 | §1 |
| MES-TD3-062 | 대시보드 | CMN-04 + KPI-01 | 1:1 | §1 |
| MES-TD3-063 | 상세대시보드 | — | 범위 밖 | §1 |
| MES-TD3-064 | 대시보드관리 | — | 범위 밖 | §1 |
