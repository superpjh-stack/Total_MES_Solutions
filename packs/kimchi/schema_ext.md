# 확장 스키마 설계 — `kimchi` 팩 `schema_ext.sql` 의 기획 (기획자3 · 2026-10-09)

> 규칙(`pack-contract.md` §3 · §4 R2 · R3): 테이블은 `x_kimchi_` 접두 · 공통 컬럼 5(`id bigserial pk` `created_at` `created_by` `updated_at` `updated_by`) + `attrs jsonb not null default '{}'` · 코어 `ALTER` · 트리거 없음 · 1:1 ext 는 코어 `id` 가 PK 겸 FK(`on delete cascade`) · FK 는 코어를 가리킬 수 있고 코어는 팩을 모른다.
> **시계열을 `pop_measure` 에 쌓지 않는다.** 센서 시계열은 전부 `eqp_collect`(코어) — 이 팩 테이블에 센서 원시값 시계열은 없다. 팩 로그 4 는 수기 · 집계 · 사건 로그다.
> 아래 표에서 공통 컬럼 5 + `attrs` 는 생략. `★` 유니크.

## 1. `x_kimchi_item_std` — 품목별 공정 조건 기준 (E4 · 원천 `WSH_STD` + `SLT_STD`)

| 컬럼 | 형 | 뜻 |
|---|---|---|
| `process_id` | →`bas_process` not null | 세척/절임 P03, 냉장·숙성 P09(`aging_days`) |
| `item_id` | →`bas_item` not null | 품목 |
| `size_type` | text null | 원물 크기구분(`bas_code SIZE_TYPE`) — 절임 기준만. NULL = 전체 |
| `param_key` | text not null | `bas_process_param.param_key` 또는 `aging_days`. 라우터가 존재 검증 |
| `std_value` | numeric(12,3) null | 기준값(염도 9/12/13 · 시간 48/24 · 소독수 10 · 숙성 21 …). NULL = `미확정` |
| `min_value` · `max_value` | numeric(12,3) null | 하한 · 상한(세척 시간 · 물 · 중량) |
| `tolerance` | numeric(12,3) null | 허용편차(염도). NULL 이면 알람 판정 안 함(미확정 임진강 D-08) |
| `unit` | text null | |
| `haccp_chk_yn` | char(1) default 'N' | HACCP 정합 확인(TD5 `SLT_STD.HACCP_CHK_YN`) |
| `valid_from` | date not null | 적용 시작일 |
| `use_yn` | char(1) default 'Y' | |

유니크 ★ `(process_id, item_id, coalesce(size_type,''), param_key, valid_from)`. 인덱스 `(item_id, param_key)`.

## 2. `x_kimchi_tank` — 절임통 운영 배치 (E4 · 원천 `SLT_TANK_OPR`) — `pop_work_result` 1:1 ext

| 컬럼 | 형 | 뜻 |
|---|---|---|
| `id` | →`pop_work_result.id` **PK 겸 FK** cascade | 절임 실적 1 = 절임통 배치 1 (D-501) |
| `equipment_id` | →`bas_equipment` not null | 절임통(TK-nn). 실적의 `equipment_id` 와 같아야 한다(라우터 검증) |
| `std_id` | →`x_kimchi_item_std` null | 적용한 절임 조건(염도 행). 시간 행은 같은 품목 · 크기에서 읽는다 |
| `target_salinity_pct` · `target_hours` | numeric | 투입 당시 기준 **스냅샷**(기준이 나중에 바뀌어도 배치 판정 불변) |
| `input_weight_kg` | numeric(12,3) null | 투입 중량 |
| `plan_end_at` | timestamptz null | `started_at + target_hours` |
| `completed_at` | timestamptz null | 절임 완료 처리 시각 |
| `final_salinity_pct` | numeric(6,2) null | 완료 시 염도(센서 last 또는 수기) |
| `status` | text not null check in (투입, 진행, 완료) | `bas_code TANK_STATUS` |
| `sensor_equipment_id` | →`bas_equipment` null | 이 배치에 연결된 염도센서(SS-nn) — 매핑 미확정이면 NULL |

인덱스 `(equipment_id, status)`. "같은 절임통에 미완료 배치 1개" 는 부분 유니크 `(equipment_id) where status <> '완료'`.

## 3. `x_kimchi_sanitizer_log` — 소독수 농도 수기 로그 (E4 · 원천 `WSH_SANITIZER_LOG` 의 수기 부분)

| 컬럼 | 형 | 뜻 |
|---|---|---|
| `equipment_id` | →`bas_equipment` not null | 소독수 공급장치(SW-01) |
| `work_order_id` | →`job_work_order` null | |
| `ppm_value` | numeric(8,2) not null | 측정 농도 |
| `contact_min` | numeric(8,2) null | 접촉시간(분) |
| `dosing_rate` | numeric(8,3) null | 투입비율 |
| `source` | text not null check in (manual, collect) | 수기 / (센서 연동 전환기의 수동 적재) |
| `deviated` | char(1) default 'N' | 10ppm 미달 |
| `alarm_id` | →`x_kimchi_env_alarm` null | 만든 알람 |
| `measured_at` | timestamptz not null | |
| `canceled_yn` | char(1) default 'N' | |

센서 시계열 본체는 `eqp_collect(SW-01, sanitizer_ppm)` — 이 표에 복사하지 않는다. 인덱스 `(equipment_id, measured_at desc)`.

## 4. `x_kimchi_taping_log` — 테이핑기 실적 집계 로그 (E4 · 원천 `PKG_TAPING_LOG`)

| 컬럼 | 형 | 뜻 |
|---|---|---|
| `equipment_id` | →`bas_equipment` not null | AP-01 |
| `work_result_id` | →`pop_work_result` null | 진행 중 포장 실적(없으면 NULL + WARN) |
| `work_order_id` | →`job_work_order` null | |
| `pack_qty` | numeric(12,0) not null | 이번 구간 포장 수량(박스) — 증분 |
| `cum_count` | numeric(12,0) null | 설비 카운터 누계 원값(collect 일 때) |
| `run_status` | text null check in (가동, 정지) | |
| `run_minutes` | numeric(8,1) null | 누적 가동(분) |
| `source` | text not null check in (manual, collect) | |
| `raw_id` | →`ifc_collect_raw` null | collect 원문 |
| `logged_at` | timestamptz not null | |

★ `(equipment_id, logged_at, source)`. 작업지시별 누계는 저장하지 않는다(화면 집계).

## 5. `x_kimchi_env_alarm` — 기준 이탈 알람 (E4 · E5 · 원천 `AGE_ENV_ALARM` 일반화)

| 컬럼 | 형 | 뜻 |
|---|---|---|
| `alarm_no` | text ★ | `numbering("ALARM")` |
| `kind` | text not null | `bas_code ALARM_KIND`(소독수 10ppm 미달 · 절임 염도 이탈 · 냉장고 온도 이탈 · 냉장고 습도 이탈 …) |
| `equipment_id` | →`bas_equipment` not null | |
| `tag` | text not null | `collect_tag`(temp_c · humidity_pct · sanitizer_ppm · salinity_pct) |
| `first_value` · `last_value` | numeric(12,3) | 처음 · 마지막 이탈 값 |
| `limit_text` | text | 판정 당시 기준(예 `max 5 ℃` · `9 ± 0.5 %`) — 기준 스냅샷 |
| `count` | int default 1 | 합쳐진 이탈 횟수(D-512) |
| `lot_id` | →`lot` null | 절임통 배치(염도) |
| `work_result_id` | →`pop_work_result` null | |
| `param_id` | →`bas_process_param` null | |
| `status` | text not null check in (발생, 확인, 해제) | |
| `first_at` · `last_at` | timestamptz not null | |
| `acked_at` · `acked_by` | | 확인 |
| `cleared_at` · `cleared_by` · `action_desc` | | 해제 · 조치 |

인덱스 `(equipment_id, tag) where status <> '해제'`(미해제 1건 찾기) · `(first_at desc)`. 검사 · 측정값 이탈(손실률 · 금속 · CCP · 중량)은 여기 **없다** — `qua_issue(source=hook)`(README §7).

## 6. `x_kimchi_lot_ext` — LOT 확장 (E2 집계 · 검색용 · 원천 `AGE_STOCK` + `PKG_COLD_STOCK` 현재 위치) — `lot` 1:1 ext

| 컬럼 | 형 | 뜻 |
|---|---|---|
| `id` | →`lot.id` **PK 겸 FK** cascade | |
| `aging_start_date` | date null | 숙성 투입일(AGING) |
| `aging_due_date` | date null | 완료 예정일 = 시작 + `aging_days`(품목 기준 없으면 21 — D-511) |
| `aging_end_date` | date null | 완료 처리일 |
| `shippable_yn` | char(1) default 'N' | 출하 가능(FIFO 안내 · `validate_shipment` 거부 3) |
| `location_equipment_id` | →`bas_equipment` null | 현재 냉장고(검색 · FIFO 정렬에 쓰므로 `attrs` 가 아니라 ext — D-05) |
| `tank_equipment_id` | →`bas_equipment` null | TANK LOT 의 절임통(역추적 노드 표시용 비정규화 — `x_kimchi_tank` 에서 복사) |

인덱스 `(location_equipment_id)` · `(aging_due_date)`.

## 7. `x_kimchi_cold_move` — 냉장고 입출고 이력 (E4 · 원천 `PKG_COLD_STOCK`)

| 컬럼 | 형 | 뜻 |
|---|---|---|
| `lot_id` | →`lot` not null | PRODUCT · AGING |
| `equipment_id` | →`bas_equipment` not null | 냉장고 |
| `trx_type` | text not null check in (입고, 출고) | |
| `qty` | numeric(12,3) not null | |
| `unit` | text | |
| `device` | text null | web / pop / mobile(TD5 `DEVICE_TYPE`) |
| `moved_at` | timestamptz not null | |
| `canceled_yn` | char(1) default 'N' | |

인덱스 `(lot_id, moved_at)` · `(equipment_id, moved_at desc)`. 냉장고별 잔량은 저장하지 않는다(입고 합 − 출고 합).

## 8. 뷰(팩 · 선택)

- `v_kimchi_tank_board` — 절임통 8 × 현재 배치(X-TANK-01 현황판). `bas_equipment(절임통) left join x_kimchi_tank(status<>완료) join pop_work_result join lot`.
- `v_kimchi_aging_stock` — `lot(kind=AGING)` × `v_lot_state=재고` × `v_lot_stock` × ext.

## 9. 집계

팩 테이블 **7**(1:1 ext 2 · 1:N 5) · 팩 뷰 2 · 코어 테이블 변경 **0** · `pop_measure` 에 시계열 **0**. `check_schema` 기대값 `tables: 7`(`gates.yaml`).

## 10. 쓰기 경계 (R7 기대값)

| 쓰는 곳 | `x_kimchi_*` | 코어(write_scope) |
|---|---|---|
| `routers/cond.py` | item_std | — |
| `routers/wsh.py` | sanitizer_log · env_alarm(`alarm.raise_env`) | — |
| `routers/tank.py` | tank | — |
| `routers/pkg.py` | taping_log | — |
| `routers/age.py` | lot_ext · cold_move | `lot` `lot_genealogy`(`lineage.split` 만) |
| `routers/alm.py` | env_alarm | — |
| `hooks.py` | env_alarm · taping_log | `lot`(`lineage.retag`) · `pop_measure` · `qua_issue` |
