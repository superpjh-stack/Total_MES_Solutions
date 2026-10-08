# 확장 스키마 설계 — `x_foodservice_*` (기획자1 · 2026-10-09 · 초안)

> 개발1 이 이 문서를 `schema_ext.sql` 로 옮긴다. 규칙은 `contracts/pack-contract.md` §3 · §4 R2 · R3: **집계 · 검색 · 정렬 · FK · 유니크에 쓰는 값은 ext, 표시만은 `attrs`**, 코어 테이블 `ALTER` 0, 팩 테이블은 `x_foodservice_` 접두 + 공통 컬럼 5(`id` · `created_at` · `created_by` · `updated_at` · `updated_by`) + `attrs jsonb not null default '{}'`.
> `x_foodservice_<코어>_ext` 는 코어 `id` 를 PK 겸 FK(1:1 · `on delete cascade`). 1:N 테이블은 `x_foodservice_<이름>`.
> 테이블 **8**(ext 7 + 1:N 1). `gates.yaml: tables: 8`. 근거 컬럼은 TD5 `design.json td5.details`.

## 1. 요약

| # | 테이블 | 종류 | 코어 | 왜 ext 인가(attrs 가 아닌 이유) | 니즈푸드 원천 |
|---|---|---|---|---|---|
| 1 | `x_foodservice_item_ext` | 1:1 | `bas_item` | 조리 공정 FK(지시 기본값 · 검색) · 보관기준온도(판정) | BAS_MENU.COOK_PROC_CD · BAS_MATERIAL.STORAGE_TEMP |
| 2 | `x_foodservice_bom_ext` | 1:1 | `bas_bom` | 배치 기준인분 — 소요량 · 배치수 **집계** | BAS_RECIPE_BOM.BATCH_SERVE_QTY |
| 3 | `x_foodservice_process_ext` | 1:1 | `bas_process` | 표준 소요시간(지연 판정) · 배치 기준수량(배치수 산출) | BAS_PROCESS_STD.STD_LEAD_MIN · BATCH_STD_QTY |
| 4 | `x_foodservice_equipment_ext` | 1:1 | `bas_equipment` | 냉장/냉동 구분 · 임계온도(이탈 판정) | EQP_STATUS + AD2-053 |
| 5 | `x_foodservice_order_ext` | 1:1 | `ord_order` | 납기시간(출고지시 정렬) · 급식유형(검색) | SAL_ORDER.DUE_TM · SERVICE_TYPE_CD |
| 6 | `x_foodservice_lot_ext` | 1:1 | `lot` | 유통기한(FIFO 정렬 · 경과 거부) · 배치번호(검색 · 유니크) | MAT_RECEIPT.EXPIRY_DT · PRD_BATCH_RESULT.BATCH_NO |
| 7 | `x_foodservice_insp_plan_ext` | 1:1 | `qua_insp_plan` | 샘플링 빈도 N솥당 M솥(계획 샘플수 계산) · 적용시작일(유효 기준 선택) | BAS_SAMPLE_STD.SAMPLE_FREQ · APPLY_FROM_DT |
| 8 | `x_foodservice_env_alarm` | 1:N | `bas_equipment` · `eqp_collect` | 보관온도 · 환경 이탈 기록(시계열 아님 — 이탈 사건만) | EQP_COLLECT.OUT_OF_SPEC_YN 의 대체 |

`attrs` 로 둔 것(여기 없음): `pack.yaml: attrs` 참조 — 메뉴유형 · 1인 제공량 · 알레르기 · 자재구분 · 보관조건 · 유통기한관리 여부 · 여유율 · 조리순서 · 주의사항 · 사업자번호 · 납품지 · 직무 · 조리라인 · 설비유형 · 통신방식 · 제조사모델 · 입력구분 · 보관위치 · 이동구분 · 이슈유형 · 점검구분 · 이상유형 · 소속구분.

## 2. 컬럼

공통 컬럼 5 + `attrs` 는 적지 않는다. 타입은 코어 규약(소문자 snake_case · `*_id` FK · `*_yn char(1)`).

### `x_foodservice_item_ext` — 메뉴 · 원부자재 확장
| 컬럼 | 타입 | NULL | 뜻 · 제약 | 원천 |
|---|---|---|---|---|
| `id` | bigint PK → `bas_item.id` | N | 1:1 · cascade | |
| `cook_process_id` | bigint → `bas_process.id` | Y | 조리공정구분(가공(무침)/취사/조리/볶음 중 하나). 메뉴(`item_type=제품`)만. `validate_job_work_order` 가 지시 `process_id` 기본값으로 쓴다 | BAS_MENU.COOK_PROC_CD |
| `storage_temp` | numeric(5,1) | Y | 보관기준온도(℃) — 입고 시 보관온도 상한 판정(니즈푸드 `alarm.judge_storage_temp`). 값 없음 = `(미확정)` | BAS_MATERIAL.STORAGE_TEMP |
| CHECK | — | | `cook_process_id` 는 `bas_process.process_code in ('PRC-030','PRC-040','PRC-050','PRC-060')` — 라우터/훅 검증(DB CHECK 로는 코드 조인이 안 됨) | |

### `x_foodservice_bom_ext` — 레시피 확장
| 컬럼 | 타입 | NULL | 뜻 · 제약 | 원천 |
|---|---|---|---|---|
| `id` | bigint PK → `bas_bom.id` | N | | |
| `batch_serve_qty` | numeric(10,2) | N | 배치(솥) 1솥 산출 인분. `CHECK (batch_serve_qty > 0)`. 1인량 = `bas_bom_dtl.qty ÷ batch_serve_qty`(D-502) | BAS_RECIPE_BOM.BATCH_SERVE_QTY |

### `x_foodservice_process_ext` — 조리 공정 기준
| 컬럼 | 타입 | NULL | 뜻 · 제약 | 원천 |
|---|---|---|---|---|
| `id` | bigint PK → `bas_process.id` | N | | |
| `std_lead_min` | integer | Y | 표준 소요시간(분) — 실적 `ended_at − started_at` 이 이보다 크면 '지연' 표시(JOB-02 · kpi). NULL = `(미확정 D-08)` → 판정 안 함 | BAS_PROCESS_STD.STD_LEAD_MIN |
| `batch_std_qty` | numeric(10,2) | Y | 배치(솥) 기준수량(인분). 계획 배치수 = ceil(계획인분 ÷ 이 값). NULL 이면 활성 레시피 `batch_serve_qty` 로 대체(니즈푸드 D-202) | BAS_PROCESS_STD.BATCH_STD_QTY |
| `collect_type` | text | Y | 자동(PLC) / 반자동(POP) / 수동 — 표시 · 필터. `seed/processes.csv` 가 채운다 | BAS_PROCESS_STD.COLLECT_TYPE_CD |

### `x_foodservice_equipment_ext` — 설비 임계
| 컬럼 | 타입 | NULL | 뜻 · 제약 | 원천 |
|---|---|---|---|---|
| `id` | bigint PK → `bas_equipment.id` | N | | |
| `storage_kind` | text | Y | `냉장` · `냉동` · NULL(구분 미확인 D-10). CHECK in ('냉장','냉동') | TD3-033 목업 '#5(냉장)' |
| `temp_limit` | numeric(5,1) | Y | 상한(℃). 냉장 5 · 냉동 -18(AD2-053). NULL 이면 `on_collect` 가 판정하지 않는다 | AD2-053 |
| `humi_limit` | numeric(5,1) | Y | 상대습도 상한(%RH) — AD2-052 "명시되어 있지 않다" → NULL | — |
| `collect_path` | text | Y | PLC(Ethernet) / RS-485→Edge — 표시 · 필터 | EQP_COLLECT.COLLECT_PATH_CD |

### `x_foodservice_order_ext` — 수주 확장
| 컬럼 | 타입 | NULL | 뜻 · 제약 | 원천 |
|---|---|---|---|---|
| `id` | bigint PK → `ord_order.id` | N | | |
| `due_time` | time | Y | 납기시간(HH:MI). SHP-02 출고지시 목록 · ORD-03 달력의 정렬 키 | SAL_ORDER.DUE_TM |
| `service_type` | text | Y | 이동급식 / 위탁급식. CHECK. 검색 조건(TD3-010) | SAL_ORDER.SERVICE_TYPE_CD |

### `x_foodservice_lot_ext` — LOT 확장 (원료 LOT · 배치 LOT 공용)
| 컬럼 | 타입 | NULL | 뜻 · 제약 | 원천 |
|---|---|---|---|---|
| `id` | bigint PK → `lot.id` | N | | |
| `expiry_date` | date | Y | 유통기한 — `kind=MATERIAL`. FIFO 추천 정렬(`on_work_order_created`) · 경과 투입 거부(`validate_pop_input`). 인덱스 `(expiry_date)` | MAT_RECEIPT.EXPIRY_DT |
| `batch_seq` | integer | Y | 배치 순번 — `kind=BATCH`. 같은 지시 안 종료 순 | — |
| `batch_no` | text | Y | `B-01` 형식(TD3-017 목업). **유니크 `(work_order_id, batch_no)`** — `work_order_id` 는 `lot.work_order_id` 라 ext 에 중복 보관: `work_order_id bigint → job_work_order.id` | PRD_BATCH_RESULT.BATCH_NO |
| `work_order_id` | bigint → `job_work_order.id` | Y | 유니크 제약용 복제(`lot.work_order_id` 와 같아야 한다 — 훅이 채움) | |
| `work_result_id` | bigint → `pop_work_result.id` | Y | 배치를 만든 실적 | PRD_BATCH_RESULT.RESULT_ID |
| `input_type` | text | Y | 자동(PLC) / POP수동 / 스마트패드 — `on_result_closed` 가 collect 행 유무로 보정(hooks.md §4) | PRD_BATCH_RESULT.INPUT_TYPE_CD |
| CHECK | | | `kind=MATERIAL` 행은 `batch_*` NULL, `kind=BATCH` 행은 `expiry_date` NULL — 라우터/훅 검증 | |

### `x_foodservice_insp_plan_ext` — 샘플링 검식 기준
| 컬럼 | 타입 | NULL | 뜻 · 제약 | 원천 |
|---|---|---|---|---|
| `id` | bigint PK → `qua_insp_plan.id` | N | | |
| `sample_freq` | text | Y | 원문 "10솥당 1솥" · "입고 건별 1회" | BAS_SAMPLE_STD.SAMPLE_FREQ |
| `sample_n` | integer | Y | N솥당 — 원문에서 파싱(`(\d+)솥당\s*(\d+)솥`, 니즈푸드 D-204). 파싱 불가면 NULL | |
| `sample_k` | integer | Y | M솥 | |
| `sample_qty` | numeric(10,2) | Y | 빈도 형식이 아닐 때의 샘플링 수량 | BAS_SAMPLE_STD.SAMPLE_QTY |
| `apply_from` | date | Y | 적용시작일 — 같은 품목 · 유형의 기준이 여럿이면 최신 `apply_from <= 오늘` 을 쓴다. "적용시작일 중복 구간 불가"(TD3-005 체크)는 유니크 `(qua_insp_plan.insp_type, item_id, apply_from)` 로 — `item_id` · `insp_type` 은 코어 행에 있으므로 ext 에 복제 없이 **훅 검증**(`validate_qua_insp_plan`, 선택) | BAS_SAMPLE_STD.APPLY_FROM_DT |

계획 샘플수 = `max(1, ceil(대상 배치수 ÷ sample_n) × sample_k)` — `kpi_extra.plan_batch_count` 와 함께 표시(일자별 일정 화면은 D-507).

### `x_foodservice_env_alarm` — 보관온도 · 환경 이탈 기록 (1:N)
| 컬럼 | 타입 | NULL | 뜻 · 제약 | 원천 |
|---|---|---|---|---|
| `id` | bigserial PK | N | | |
| `equipment_id` | bigint → `bas_equipment.id` | N | | |
| `collect_id` | bigint → `eqp_collect.id` | Y | 원천 수집 행 | |
| `tag` | text | N | `PV_TEMP` · `TEMP` · `HUMI` | |
| `ts` | timestamptz | N | 수집 시각 | |
| `value_num` | numeric(14,3) | N | | |
| `limit_value` | numeric(14,3) | N | 판정에 쓴 임계 | |
| `kind` | text | N | `상한 초과` · `하한 미달` | |
| `acked_at` · `acked_by` | timestamptz · text | Y | 확인 처리(화면 없음 — 이관 단계) | |
| 유니크 | `(equipment_id, tag, ts)` | | 멱등 | |
| 인덱스 | `(ts desc)` · `(equipment_id, ts desc)` | | | |

## 3. 뷰 (선택 · `views_ext.sql` 가 허용되면)

| 뷰 | 뜻 |
|---|---|
| `v_foodservice_batch` | `lot(kind=BATCH)` + `x_foodservice_lot_ext` + `pop_work_result` + `pop_measure`(RPM · STIR_TIME · TEMP 를 열로 피벗) + `v_lot_stock.remain_qty` — TD3-018 · 013 그리드 모양. 팩 라우터가 없으므로 **QA 대조용**(`gates.yaml` 시나리오 검산) |
| `v_foodservice_fifo` | `lot(kind=MATERIAL)` 중 합격 · 잔량 > 0 을 `expiry_date, made_at` 순으로 — `on_work_order_created` 추천 쿼리와 같은 SQL |

## 4. `check_pack` 이 볼 것

- `alter table` 0 · 트리거 0 · 모든 테이블 `x_foodservice_` 접두 · 공통 컬럼 5 + `attrs`.
- FK 가 코어를 가리키는 것은 허용, 코어가 팩을 가리키는 것은 없음.
- `attrs->>` 를 WHERE · GROUP BY 에 쓰는 SQL 0 — 검색 · 정렬 키는 전부 위 ext 컬럼이다.
