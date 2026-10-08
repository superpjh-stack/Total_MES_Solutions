# 훅 사양 — `kimchi` 팩 `hooks.py` (기획자3 · 2026-10-09 · 기획 초안)

> 서명은 `contracts/pack-contract.md` §5, 호출 지점은 `contracts/interfaces.md` §9. 전부 **동기 · 코어 트랜잭션 안 · 거부는 `HookError`(422 `hook_rejected`) · 그 밖 예외는 500**(조용히 삼키지 않는다).
> 코어 테이블 쓰기는 `pack.yaml: write_scope.hooks = [lot, pop_measure, qua_issue]` 안에서만. `lot_genealogy` · `sys_number_seq` 직접 SQL 없음.
> 임계값은 **전부 데이터**에서 읽는다 — `bas_process_param.min/max`, `x_kimchi_item_std`, `qua_insp_plan.min/max`. 값이 없으면 판정하지 않고 `미확정` 으로 둔다(지어내지 않는다).

## 0. 공용 — `alarm.raise_env(cur, *, kind, equipment_id, tag, value, limit_text, lot_id=None, work_result_id=None, at)`

팩 내부 함수(훅과 F-X-WSH-01 이 같이 쓴다). `x_kimchi_env_alarm` 에 쓴다.
- 같은 `(equipment_id, tag)` 에 `status <> 해제` 행이 있으면 **새 행을 만들지 않고** `last_value · last_at · count+1` 갱신(D-512).
- 없으면 `alarm_no = numbering.next("ALARM", cur=cur)` 로 1행(`status=발생`).
- 반환: `(alarm_id, created: bool)`.

## 1. `validate_shipment(cur, shipment, lots, user)` — 출하 승인 직전 (F-SHP-07)

| | |
|---|---|
| 입력 | `shipment` 행 · `lots` = 그 출하에 스캔된 LOT 행 목록(`kind_base=PRODUCT` — `PRODUCT` · `TANK` · `AGING` 전부 올 수 있다) |
| 읽는 테이블 | `lot` · `lot_genealogy`(`lineage.trace_backward`) · `qua_inspection` · `qua_insp_item` · `qua_insp_plan` · `x_kimchi_lot_ext` |
| 쓰는 테이블 | **없음**(읽기만) |
| 거부 1 — 금속검출 미통과 | 각 LOT 에 대해 그 LOT **또는 역추적 조상 중** `insp_type=공정 · process=P07` 검사의 최신 `judgement=합격` 이 하나도 없으면 거부. 역추적을 쓰는 이유: 금속검출은 혼합 배치(X1)에서 하고 출하는 포장 LOT(K1) · 숙성 배치(A1)로 하므로 조상에서 찾아야 한다. 메시지 `t("금속검출 합격 기록이 없는 배치가 있습니다") + lot_no 목록`, `fields=["lots"]` |
| 거부 2 — CCP 불합격 | LOT 또는 조상에 `qua_insp_item.item_key in (metal_detect, mix_ccp, pack_weight_kg)` 이고 `item_judgement=불합격` 인 최신 검사가 있고, 그 뒤 재검사 합격이 없으면 거부. 메시지 `t("CCP 불합격 배치는 출하할 수 없습니다")` |
| 거부 3 — 숙성 미완료 | `kind=AGING` 인데 `x_kimchi_lot_ext.shippable_yn <> 'Y'` 이고 `aging_due_date > today` 면 거부 `t("숙성 완료 전입니다")`. 예정일이 지났으면 통과(완료 처리 없이도 출하 가능 — 임진강 032 "출하 가능 시점 안내"는 안내이지 잠금이 아니다) |
| 통과 | 아무것도 하지 않는다. `lot.insp_status=미검사/불합격` 은 코어 F-SHP-05 가 이미 막는다(중복 검사 안 함) |
| 테스트 | S2(gates.yaml): 금속검출 NG LOT 포함 출하 승인 → 422 `hook_rejected` · `shp_shipment.status` 변화 0 · `lot_genealogy` 변화 0 |

## 2. `on_inspection_judged(cur, insp, user)` — 판정 저장 후 (F-QUA-05 · F-MAT-04)

| | |
|---|---|
| 입력 | `insp` = `qua_inspection` 행(`lot_id` · `insp_type` · `judgement`) |
| 읽는 테이블 | `qua_insp_item`(그 검사의 항목 값 · `item_judgement` · `deviated`) · `qua_insp_plan` · `lot` |
| 쓰는 테이블 | `qua_issue`(write_scope) |
| 조건 | `insp_type in (공정, 최종)` 이고 항목 중 `item_key in (metal_detect, mix_ccp, pack_weight_kg)` 이 `item_judgement=불합격` 또는 `deviated=Y` |
| 동작 | 항목마다 `qua_issue` 1행: `issue_no = numbering.next("ISSUE")` · `occurred_at = insp.judged_at` · `process_id` = 검사 공정 · `lot_id` · `inspection_id` · `content = t("CCP 이탈") + " " + label + " " + 값 + " / 기준 " + min~max` · `status=발생` · **`source=hook`**. 같은 `(inspection_id, item_key)` 로 이미 있으면 만들지 않는다(멱등 — 재판정 대비) |
| 입고 검사 | `insp_type=입고` 불합격은 코어가 `lot.insp_status=불합격` 으로 끝낸다. 이 훅은 아무것도 안 한다(임진강 018 은 입고 이력 연결만) |
| 금속검출 NG 추가 동작 | `ng_qty > 0` 이면 `content` 에 불합격 수량 포함. 불량 수량 등록(`qua_defect`)은 코어 F-QUA-05 화면이 받는다 — 훅이 대신 쓰지 않는다 |
| 거부 | 없음(판정을 되돌리지 않는다) |
| 테스트 | 금속검출 NG 판정 → `qua_issue` +1 (`source=hook`) · 같은 검사 재판정 → +0 |

## 3. `on_collect(cur, raw, user=None)` — 수집 메시지 정제 후 (`collect.receive`)

| | |
|---|---|
| 입력 | `raw` = `ifc_collect_raw` 행(`equip_code` · `ts` · `payload.tags{}`) + 코어가 만든 `eqp_collect` 행들(`raw_id` 로 찾는다) |
| 읽는 테이블 | `bas_equipment` · `bas_process_param`(`source=collect` · `collect_tag` = 태그) · `x_kimchi_tank`(진행 중 배치 — 염도 기준용) · `x_kimchi_item_std` · `adapters/collect_tags.SENSOR_TO_TANK`(센서 → 절임통, 미확정이면 빈 표) |
| 쓰는 테이블 | `x_kimchi_env_alarm`(팩) · `x_kimchi_taping_log`(팩). **`qua_issue` 는 쓰지 않는다**(센서 이탈은 환경 알람 — README §7) |
| 판정 A — 범위 이탈 | 태그마다 `bas_process_param(설비 공정, collect_tag)` 의 `min_value/max_value` 와 비교. 둘 다 NULL 이면 판정 안 함. 이탈이면 `alarm.raise_env(kind=태그별 종류, …)`. 종류: `temp_c` → `냉장고 온도 이탈` · `humidity_pct` → `냉장고 습도 이탈` · `sanitizer_ppm`(min 10) → `소독수 10ppm 미달` |
| 판정 B — 염도 | `salinity_pct` 태그: 센서 → 절임통 매핑으로 진행 중 `x_kimchi_tank` 를 찾고 그 `std_id` 의 `std_value ± tolerance` 밖이면 `절임 염도 이탈`(lot_id · work_result_id 포함). 매핑 없음 · `tolerance` NULL → 판정 안 함(미확정) |
| 집계 C — 테이핑 | `pack_count` · `run_state` 태그(`AP-01`): 그 설비의 진행 중 실적(`pop_work_result` 공정 P08 · `ended_at` NULL)을 찾아 `x_kimchi_taping_log` 1행(`source=collect` · `pack_qty` = 이번 값 − 직전 누계(음수면 리셋으로 보고 이번 값) · `run_status`). 진행 중 실적이 없으면 `work_result_id NULL` 로 쌓고 WARN 로그(버리지 않는다) |
| 거부 | 없음 — 수집 메시지는 거부하지 않는다(코어가 `422` 로 모르는 설비만 거른다) |
| 테스트 | S3(gates.yaml): `POST /ifc/collect` `{equip_code: "TH-10"… tags:{temp_c: X}}` 에서 X 가 P08 `temp_c` max 를 넘으면 `x_kimchi_env_alarm` +1. 같은 메시지 재전송 → +0(코어 멱등) · 다음 이탈 메시지 → 행 +0 · `count` +1 |
| 주의 | `temp_c` 는 P01 · P09 둘 다 선언되어 있다 — 설비의 `process_id` 로 고른다. 범위가 미확정(NULL)이면 S3 는 **테스트 픽스처가 범위를 임시로 넣고** 돈다(시드에는 넣지 않는다) |

## 4. `on_result_closed(cur, result, user)` — 측정값 · 생산 LOT 생성 후 (F-POP-03)

| | |
|---|---|
| 입력 | `result` = `pop_work_result` 행(`product_lot_id` 있음 · `process_id` · `equipment_id`) |
| 읽는 테이블 | `bas_process` · `pop_measure` · `x_kimchi_tank` · `x_kimchi_item_std` |
| 쓰는 테이블 | `lot`(`lineage.retag` 경유) · `pop_measure` · `qua_issue` |
| P03 절임(설비가 절임통) | `x_kimchi_tank` 행이 있으면 **`lineage.retag(cur, result.product_lot_id, "TANK")`** → LOT `kind=TANK`(`kind_base` 는 PRODUCT 그대로). 염도 대표값은 코어가 이미 `pop_measure.salinity_pct`(collect · last) 로 채웠다 — 센서 매핑이 없어 비어 있으면 그대로 둔다(`미수집`). `x_kimchi_tank.status` 가 `완료` 가 아니면 `완료` 로 바꾸고 `completed_at` 채움(F-X-TANK-03 생략 시) |
| P02 전처리 — 손실률 | `input_weight_kg` · `output_weight_kg` 가 있으면 `loss_rate_pct = (in − out) / in × 100`(소수 2자리) 을 `pop_measure` 에 **upsert**(`param_key=loss_rate_pct` · `source=manual` D-510 · `deviated = loss > max_value(20)`). 이탈이면 `qua_issue` 1행(`source=hook` · `content = t("손실률 기준 초과") + …`). `in=0` 또는 비어 있으면 아무것도 안 함 |
| P03 세척 — 품목별 기준 대비 | `wash_time_min` `wash_volume_l` `wash_weight_kg` 각각 `x_kimchi_item_std(품목, 키)` 가 있고 범위 밖이면 그 `pop_measure.deviated=Y` 로 **갱신**(코어는 공정 범위만 봤다). `qua_issue` 는 만들지 않는다(임진강 022 는 "판정 표시"까지) |
| 거부 | 없음 |
| 테스트 | S1 단계 3: 절임 실적 종료 → `lot.kind=TANK` · `kind_base=PRODUCT`. 전처리 종료(in 1000 · out 750) → `pop_measure.loss_rate_pct=25 · deviated=Y` · `qua_issue` +1 |

## 5. `kpi_extra(frm, to) -> list[dict]` — 지표 조회 시 (F-KPI-08 · 현황판 카드)

임진강 KPI 2종(TD1 kpi_effects — 산식은 정본 문장) + 메인 카드 1.

| key | label | 산식 | unit | 읽는 테이블 |
|---|---|---|---|---|
| `throughput_kg_per_h` | 시간당 생산량 | 기간 **포장 공정(P08) 실적 양품 수량(kg) 합 ÷ (기간 생산일수 × 일 근무시간)**. 생산일수 = 실적이 있는 날 수. 일 근무시간은 정본 "8시간"(TD1 재계산식 22.33일 × 8h) — `kpi_indicator(throughput_kg_per_h).attrs.work_hours_per_day` 가 있으면 그 값 | kg/h | `pop_work_result` · `bas_process` |
| `fg_defect_rate` | 완제품 불량률 | **불량 수량(kg) ÷ 생산량(kg) × 100**. 불량 = `qua_defect.qty` 중 `bas_defect_code.attrs.kpi_target_yn=true` 인 것 + `pop_scrap`(P08) 합. 생산량 = P08 양품 + 불량 | % | `qua_defect` · `pop_scrap` · `pop_work_result` |
| `aging_stock_kg` | 숙성 재고 | `lot.kind=AGING` × `v_lot_state=재고` 의 `v_lot_stock.remain_qty` 합(기간 무관 — 현재값) | kg | `lot` · 뷰 |

- 단위가 kg 가 아닌 품목(박스 · 봉)은 `bas_item.attrs.capacity_kg` 로 환산, 없으면 **제외하고** `note` 에 제외 품목 수를 적는다(지어내지 않는다 — 임진강 D-101 과 같은 처리).
- 목표값(700 · 1.30)은 `kpi_indicator.target_value` 시드가 아니라 **KPI-03 화면에서 입력**한다(정본 값이지만 참조 팩 시드는 `(예시)` 만 — D-513 과 같은 원칙). 반환 모양 `[{"key","label","value","unit","note"}]`.
- `stats` 가 QA 재계산 대상이므로 산식을 `hooks.py` 안 **함수 하나**에 두고 테스트가 같은 SQL 을 독립 작성해 대조한다(G-C10 과 같은 방식).

## 6. 쓰지 않는 훅

`validate_<table>` 전부 · `on_order_created` · `on_work_order_created` · `on_work_order_closed` · `on_result_started` · `on_lot_created` · `after_commit_*` — 이 팩에 규칙이 없다. 정의하지 않는다(no-op 를 만들어 두지 않는다).
