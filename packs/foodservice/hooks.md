# 훅 사양 — `foodservice/hooks.py` 가 구현할 것 (기획자1 · 2026-10-09 · 초안)

> 코드가 아니라 **사양**이다. 서명은 `contracts/pack-contract.md` §5, 호출 지점은 `contracts/interfaces.md` §9 를 그대로 따른다. 전부 동기 · 코어 트랜잭션 안 · 거부는 `HookError`(422 `hook_rejected`) 뿐, 그 밖 예외는 500(조용히 삼키지 않는다).
> 코어 테이블 쓰기는 `pack.yaml: write_scope.hooks` 안에서만(`mat_requirement` · `qua_issue` · `job_lot` · `lot`(`lineage.retag` 경유)). `x_foodservice_*` 는 자유. `lot_genealogy` · `sys_number_seq` 직접 SQL 금지.
> 문구는 전부 `t()` 를 거친다. 값이 없으면 지어내지 않고 `(미확정)` 을 그대로 둔다.
> 근거: `../NeedsFood MES Platform/src/needsfood/app/routers/{prd,qua,mat}.py` · `app/alarm.py` · `app/kpi.py` · `decisions-dev2.md` D-201~D-206 · TD3 체크 문장.

## 0. 공통 — 보조 조회

| 이름 | 하는 일 | 읽는 곳 |
|---|---|---|
| `_item_ext(cur, item_id)` | `x_foodservice_item_ext` 한 행(없으면 `None`) | ext |
| `_active_bom(cur, item_id)` | `bas_bom.use_yn='Y'` 인 레시피 헤더 1건 + `bas_bom_dtl` + `x_foodservice_bom_ext.batch_serve_qty`. 0건이면 `None`, 2건 이상이면 `RuntimeError`(validate 가 막았어야 한다) | 코어 + ext |
| `_per_serving(dtl, batch_serve_qty)` | **1인량 = `qty` ÷ `batch_serve_qty`** (D-502). `batch_serve_qty` 가 0 · NULL 이면 `HookError` | 순수 계산 |
| `_cook_process_id(cur, item_id)` | `x_foodservice_item_ext.cook_process_id` | ext |

## 1. `validate_bas_bom(cur, row, user)` — F-BAS-05 · 06 저장 직전

| 항목 | 내용 |
|---|---|
| 입력 | `row` = 저장될 `bas_bom` 값(dict: `item_id` `version` `use_yn` `attrs` + 폼의 ext 값 `batch_serve_qty` — 코어 폼에 ext 칸을 어떻게 받는지는 `ui.attrs_fields` 와 같은 자리(가설, 개발1 이 `_template` 를 보고 정한다)) |
| 규칙 R1 | 상위 품목은 `bas_item.item_type='제품'` 이어야 한다 — 아니면 거부 `"레시피는 메뉴에만 등록합니다"` `fields=[item_id]` |
| 규칙 R2 | `batch_serve_qty` 필수 · `> 0` — 아니면 거부 `"배치(솥) 기준인분이 필요합니다"` (TD5 `BATCH_SERVE_QTY NOT NULL`) |
| 규칙 R3 | **메뉴당 활성 버전 1건**: `use_yn='Y'` 로 저장하려는데 같은 `item_id` 의 다른 `bas_bom.use_yn='Y'` 가 있으면 거부 `"메뉴당 활성 레시피는 1건입니다 — 기존 버전을 비활성으로 바꾸세요"` (TD3-002 체크 · TD5 `ACTIVE_YN` "활성 버전 1건만 유지") |
| 규칙 R4 | 구성품에 상위 품목 자신 — 코어 F-BAS-05 가 이미 422(자기 자신 구성품). 훅은 안 본다 |
| 출력 | 없음(통과) 또는 `HookError` |
| 쓰는 테이블 | 없음. ext 행(`x_foodservice_bom_ext`)은 코어가 `attrs` 를 저장한 뒤 **`on_bas_bom_saved` 가 없으므로** 라우터 저장 직후를 잡을 자리가 없다 → ext 행은 `validate_bas_bom` 안에서 `upsert` 한다(같은 트랜잭션 · `row["id"]` 가 있을 때. 신규 등록은 `id` 가 없어 저장 뒤 첫 조회 때 `_active_bom` 이 ext 없음을 `(미확정)` 으로 보인다) — **코어 변경 요청 후보 §A** |

## 2. `validate_job_work_order(cur, row, user)` — F-JOB-01 · 02 저장 직전

| 항목 | 내용 |
|---|---|
| 입력 | `row` = `job_work_order` 값(`item_id` `process_id` `equipment_id` `plan_qty` `unit` `plan_date` `bom_id` `order_dtl_id` …) |
| 규칙 R1 | 품목 `item_type='제품'` 이어야 한다(원재료에 조리 지시 금지) |
| 규칙 R2 | **활성 레시피 필수**: `_active_bom` 이 `None` 이면 거부 `"활성 레시피가 없는 메뉴입니다 — 레시피를 먼저 등록하세요"` `fields=[item_id]` (TD4-017 · 니즈푸드 `prd.create_work_order`) |
| 규칙 R3 | `bom_id` 가 비어 있으면 활성 레시피의 `id` 를 채운다(지시 시점 버전 고정 — TD3-017 체크 "BOM 버전 고정"). 채워져 있는데 그 품목의 레시피가 아니면 거부 |
| 규칙 R4 | `unit` 이 비어 있으면 `'인분'`. 비어 있지 않은데 `'인분'` 이 아니면 거부 `"조리 지시 수량 단위는 인분입니다"` |
| 규칙 R5 | `process_id` 가 비어 있으면 `_cook_process_id` 로 채운다. 둘 다 없으면 거부 `"조리 공정을 지정하세요"` |
| 규칙 R6 | `plan_qty > 0` (코어가 이미 본다 — 중복이면 생략) |
| 규칙 R7 | `attrs.caution_note` 가 비어 있으면 레시피 `attrs.caution_note` 를 복사(POP · 현황판 표시 문구, TD5 `PRD_WORK_ORDER.CAUTION_NOTE`) |
| 출력 | `row` 를 제자리에서 보정(`bom_id` · `process_id` · `unit` · `attrs`) — 코어가 보정된 `row` 를 저장한다는 전제(가설: `validate_*` 가 dict 를 바꾸는 것이 허용되는지 `_template` 주석으로 확인) |
| 쓰는 테이블 | 없음 |

## 3. `on_work_order_created(cur, wo, user)` — F-JOB-01 저장 후 · **G-P04 핵심**

| 항목 | 내용 |
|---|---|
| 입력 | `wo` = 저장된 `job_work_order` 행(`id` `work_order_no` `item_id` `bom_id` `plan_qty`(식수 · 인분) `plan_date`) |
| 계산 | 활성 레시피(`wo.bom_id`) 구성품마다 **소요량 = 식수 × 1인량 × (1 + loss_rate)**, 1인량 = `bas_bom_dtl.qty` ÷ `x_foodservice_bom_ext.batch_serve_qty`(D-502). `loss_rate` NULL 은 0. 소수 3자리 반올림(`numeric(12,3)`) |
| 검산 | 제육볶음 1,200인분 · 돈육 12.000 kg/100인분 → **144.000 kg** · 양파 3.500 → **42.000 kg** = TD3-015 목업 '총 소요량' |
| 쓰기 1 | `mat_requirement` — 키 `(period_from=plan_date, period_to=plan_date, item_id=구성품, source='hook')`. 있으면 `required_qty += 소요량`, 없으면 INSERT. `stock_qty` = `mat_stock.qty`(없으면 0) · `shortage_qty = max(0, required_qty − stock_qty)` · `unit` = 구성품 단위 · `calc_at = now()`. **같은 날 같은 자재의 지시가 N건이면 한 행에 누적**(유니크 제약이 그렇게 되어 있다) |
| 쓰기 2 | `job_lot` — 구성품마다 `(work_order_id, item_id, required_qty, unit, lot_id)` 1행. `lot_id` 는 **FIFO 추천**: `lot.kind='MATERIAL'` · `insp_status in ('합격','조건부')` · `v_lot_stock.remain_qty > 0` · `x_foodservice_lot_ext.expiry_date` 오름차순(NULL 은 뒤) · 같으면 `made_at` 오름차순 — 첫 LOT. 없으면 NULL(TD4-017 기능 3 · 니즈푸드 `prd.fifo_lots`). 코어 F-JOB-01 이 BOM 으로 `job_lot` 줄을 이미 만들었으면 **그 행의 `lot_id` · `required_qty` 만 갱신**(중복 생성 금지 — 개발1 이 코어 `job.py` 가 `job_lot` 을 만드는지 먼저 확인) |
| 거부 | `_active_bom` 없음 → `HookError`(validate 가 먼저 막지만 방어) · `batch_serve_qty` 0 → `HookError "배치 기준인분이 0 입니다"` |
| 되돌림 | 지시 취소(F-JOB-04) 때 되돌릴 훅이 코어에 없다 → `mat_requirement` 행이 남는다. README §7-③ 코어 변경 요청. 그때까지 F-MAT-10 재계산(`source=calc`)과 분리되어 있으니 화면에서 `source` 로 구분된다 |
| 멱등 | 같은 지시로 두 번 불리지 않는다(코어가 등록 후 한 번). 테스트는 지시 2건 등록 후 `mat_requirement` 행 수 = 구성품 수 · `required_qty` = 합 |

## 4. `on_result_closed(cur, result, user)` — F-POP-03 작업 종료 후 (코어가 측정값 · 생산 LOT · collect 값을 채운 **다음**)

| 항목 | 내용 |
|---|---|
| 입력 | `result` = `pop_work_result` 행 + `result["product_lot"]`(코어가 만든 `lot(kind=PRODUCT)`) |
| 쓰기 1 | `lineage.retag(cur, lot_id, "BATCH")` — 완제품 LOT 을 배치(솥)로. 코어 `lot.kind_base` 는 `PRODUCT` 그대로(추적 · 상태 계산은 base) |
| 쓰기 2 | `x_foodservice_lot_ext` upsert — `batch_seq` = 그 지시의 종료된 실적 순번(1부터), `batch_no = f"B-{batch_seq:02d}"`(TD3-017 목업 `B-01`), `work_result_id` |
| 쓰기 3 | `pop_work_result.attrs.input_type` 은 **코어가 폼에서 받은 값**을 둔다. 다만 공정이 `PRC-040`/`PRC-060`(collect 공정)이고 `pop_measure(source='collect')` 행이 1개 이상이면 `'자동(PLC)'` 로 바꾼다(니즈푸드 D-206). 훅이 `pop_work_result` 를 UPDATE 하려면 `write_scope` 에 있어야 하는데 **없다** → 이 보정은 하지 않고 `x_foodservice_lot_ext.input_type` 에 기록한다 |
| 대표값 | 코어 F-POP-03 이 `bas_process_param(source=collect)` 선언대로 `collect.aggregate(equipment_id, tag, started_at, ended_at, agg)` 로 `pop_measure` 를 채운다(RPM avg · STIR_TIME max · TEMP avg). **훅은 다시 계산하지 않는다.** 수집 행이 0건이면 코어가 `pop_measure` 를 비워 두고(필수 아님) 화면은 `미수집` — 훅도 거부하지 않는다(무침 · 조리 공정과 같은 길) |
| 거부 | `result["product_lot"]` 가 없으면 `RuntimeError`(코어 계약 위반 — 500 이 맞다). `good_qty < 0` 등은 코어가 본다. **불량인분 ≤ 생산인분**(TD3-018 체크)은 코어 F-POP-03 이 `defect_qty` 를 따로 받으므로 `defect_qty > good_qty` 면 `HookError "불량 인분이 생산 인분보다 많습니다"` — 종료 직전이 아니라 종료 후 훅이라 롤백으로 처리된다(같은 트랜잭션) |
| 쓰는 테이블 | `lot`(retag · lineage 경유) · `x_foodservice_lot_ext` |

## 5. `on_inspection_judged(cur, insp, user)` — F-QUA-05 · F-MAT-04 판정 후

| 항목 | 내용 |
|---|---|
| 입력 | `insp` = `qua_inspection` 행(`id` `lot_id` `insp_type` `judgement` `inspected_at` `inspector`) |
| 조건 | `judgement='불합격'` 이고 `insp_type in ('공정','최종')`(검식)일 때만. 입고검사 불합격은 코어가 `lot.insp_status` 로 투입을 막으므로 이슈를 만들지 않는다(니즈푸드: 불합격 자재는 가용재고 미반영 — 이슈 아님) |
| 쓰기 | `qua_issue` 1행 — `issue_no = numbering.next("ISSUE", cur=cur)`(코어 종류에 `ISSUE` 가 없으면 `pack.yaml: numbering` 에 추가 — **(미확정)** 니즈푸드 목업 `QI-260812-01`) · `occurred_at = insp.inspected_at` · `lot_id = insp.lot_id` · `inspection_id = insp.id` · `process_id` = 그 LOT 의 `lot.process_id`(**원인 공정 = 조리 공정**, TD3-021 "원인 공정 추적") · `content = t("검식 불합격") + 항목별 이탈 값(이물 발견 Y · 관능점수 등 `qua_insp_item.deviated` 행)` · `status='발생'` · `source='hook'` · `attrs.issue_type` = 이물 발견이면 `'이물'` 아니면 `'품질이상'` |
| 멱등 | 같은 `inspection_id` 로 `qua_issue` 가 이미 있으면 만들지 않는다 |
| 거부 | 없음(판정은 사람이 했다) |
| 쓰는 테이블 | `qua_issue` |

## 6. `validate_shipment(cur, shipment, lots, user)` — F-SHP-07 출하 승인 직전

| 항목 | 내용 |
|---|---|
| 입력 | `shipment` 행 + `lots` = 스캔된 생산 LOT 목록(각 `id` `kind` `item_id` `insp_status` `qty`) |
| 규칙 R1 | **검식(최종) 합격 필수**: `kind='BATCH'` 인 LOT 마다 `qua_inspection(lot_id, insp_type='최종', judgement='합격')` 이 1건 이상 있어야 한다. 없으면 `HookError "검식 합격 전 배치는 출고할 수 없습니다"` `fields=[{name: lot_no, reason: "최종 검식 없음|불합격"}]`(AD2-020 기능 3 "출하 가능 여부") — 코어 F-SHP-05 가 `insp_status` 불합격 · 미검사를 이미 막지만, **샘플링 검식은 LOT 마다 하지 않으므로**(10솥당 1솥) 다음 규칙으로 완화한다 |
| 규칙 R1' | 같은 지시(`work_order_id`)의 배치 중 **하나라도** `최종 합격` 이 있으면 그 지시의 다른 배치도 통과(샘플링 단위 = 지시 = 메뉴 × 생산일). 지시 안에 `불합격` 이 하나라도 있으면 전부 거부. 이 완화는 **가설(D-5nn 후보)** — 영양사 확인 필요. 거부 문구에 `(미확정)` 을 붙이지 않는다(규칙은 확정 행동이다) |
| 규칙 R2 | LOT 0건은 코어가 422. `kind='MATERIAL'` 이 섞여 있으면 거부 `"원료 LOT 은 출고 대상이 아닙니다"` |
| 규칙 R3 | 수주 상세와 품목 불일치: `shipment.order_id` 가 있고 그 수주 상세에 없는 품목의 배치가 있으면 거부 `"수주에 없는 메뉴입니다"`(TD3-035 수주상세 연결) |
| 출력 | 통과 또는 `HookError` |
| 쓰는 테이블 | 없음 |

## 7. `on_collect(cur, raw, user=None)` — `collect.receive` 정제 후

| 항목 | 내용 |
|---|---|
| 입력 | `raw` = `ifc_collect_raw` 행(`equip_code` `ts` `payload.tags{}`) + 코어가 만든 `eqp_collect` 행 목록(가설: `raw["collect_rows"]` — 없으면 `(equip_code, ts)` 로 다시 읽는다) |
| 판정 | 태그 `PV_TEMP`: `x_foodservice_equipment_ext.storage_kind` 가 `냉장` 이면 상한 `temp_limit`(5) · `냉동` 이면 -18(AD2-053). 구분 · 임계가 없으면 **판정하지 않는다**(`(미확정 D-10)` — 기록도 안 한다). 태그 `TEMP` · `HUMI`(온습도센서): `temp_limit`/`humi_limit` 가 있을 때만(AD2-052 "임계치 명시되어 있지 않다" → 보통 없음). 태그 `RPM` · `STIR_TIME` · `TEMP`(교반기): **여기서 판정하지 않는다** — 실적 측정값 범위 이탈은 코어 G-C24(`pop_measure.deviated`)가 종료 때 본다 |
| 쓰기 | 이탈이면 `x_foodservice_env_alarm` 1행(`equipment_id` `tag` `ts` `value` `limit_value` `kind='상한 초과'` `collect_id`). 같은 `(equipment_id, tag, ts)` 는 멱등 |
| 거부 | 없음 — 수집은 거부하지 않는다(코어가 멱등 · 모르는 설비 422 를 이미 한다) |
| 쓰는 테이블 | `x_foodservice_env_alarm` |
| 한계 | 코어 EQP-01 · 04 화면에는 이탈이 보이지 않는다(README §7-①). `kpi_extra` 가 건수를 낸다 |

## 8. `kpi_extra(frm, to) -> list[dict]` — `stats.indicators` · 현황판

반환 각 행 `{"key", "label", "value", "unit"}` + 선택 `{"target", "base", "note"}`. 원천 0건이면 `value: None`(화면 `미수집`) — 0 으로 뭉개지 않는다(니즈푸드 `kpi.py` 규칙). 산식은 니즈푸드 `app/kpi.py` 정본 산식 그대로.

| key | label | 산식 | 원천 | 단위 · 목표 |
|---|---|---|---|---|
| `hourly_output` | 시간당 생산량 | Σ `pop_work_result.good_qty` ÷ Σ (`ended_at − started_at`)(h). `ended_at` NULL · 가동 1분 미만 실적은 분자 · 분모 모두 제외(니즈푸드 D-301 · D-315) | `pop_work_result`(기간 = `ended_at`) | 인분/시간 · 350(기준 300) |
| `defect_rate` | 완제품 불량률 | Σ `defect_qty` ÷ Σ (`good_qty + defect_qty`) × 100. 합 0 이면 None | `pop_work_result` | % · 6.5(기준 7.5) |
| `recipe_std_rate` | 레시피 표준화율 | 활성 레시피(`bas_bom.use_yn='Y'`)가 있는 메뉴 수 ÷ `bas_item(item_type='제품', use_yn='Y')` 수 × 100. 분모 `note: "전체 레시피 모집단 (미확정 D-10)"` | `bas_item` · `bas_bom` | % · 90(기준 0) |
| `insp_pass_rate` | 검식 적합률 (관리지표) | `qua_inspection(insp_type in 공정·최종, judgement='합격')` ÷ 판정된 검식 수 × 100 | `qua_inspection` | % · 목표 없음 |
| `order_ship_gap` | 수주 대비 출고 차이 (관리지표) | Σ 출고 인분(계보 `출하` 의 `lot.qty`, 승인된 출하) − Σ 수주 인분(`ord_order_dtl.qty`, 기간 = 납기) | `lot_genealogy` · `shp_shipment` · `ord_order_dtl` | 인분 · 목표 없음 (TD1 관리지표) |
| `env_alarm_count` | 보관온도 이탈 건수 (관리지표) | `count(x_foodservice_env_alarm)` 기간 내 | ext | 건 |
| `plan_batch_count` | 기간 내 계획 배치(솥)수 | Σ ceil(`ord_plan.plan_qty` ÷ 배치 기준인분). 기준인분 = `x_foodservice_process_ext.batch_std_qty`(그 메뉴 조리 공정) → 없으면 활성 레시피 `batch_serve_qty` → 둘 다 없으면 그 계획은 제외 + `note` 건수(니즈푸드 D-202) | `ord_plan` · ext | 솥 |

`kpi_indicator` 시드(`seed/kpi_indicators.csv`)의 `calc_kind=pack:<key>` 가 위 key 와 맞아야 KPI-03 에 목표 대비가 뜬다.

## 9. `validate_pop_input(cur, row, user)` — F-POP-06 투입 스캔 직전 (경고용 · 거부하지 않는다)

| 항목 | 내용 |
|---|---|
| 입력 | `row` = `pop_input` 값(`work_result_id` `material_lot_id` `qty`) |
| 규칙 | 그 실적의 지시 `job_lot.lot_id`(FIFO 추천)와 다른 LOT 이고, 추천 LOT 의 잔량이 아직 있으면 **거부하지 않고** `row["attrs"]["fifo_warning"] = "추천 LOT {no} 보다 유통기한이 늦습니다"` 를 남긴다(현장이 다른 솥을 쓸 수 있다 — AD2-012 "FIFO 정보를 작업지시 추천에 제공") |
| 거부 | 유통기한 경과 LOT: `x_foodservice_lot_ext.expiry_date < 오늘` 이면 `HookError "유통기한이 지난 원료 LOT 입니다"`(TD3-012 · 니즈푸드 사유코드 '유통기한경과') |
| 쓰는 테이블 | 없음 |

## 10. `validate_mat_receipt(cur, row, user)` — F-MAT-01 입고 등록 직전

| 항목 | 내용 |
|---|---|
| 규칙 R1 | 품목 `attrs.expiry_mng_yn` 이 참이면 폼의 `expiry_date` 필수 — 없으면 `HookError "유통기한관리 대상 자재는 유통기한이 필요합니다"`(TD3-012 제약) |
| 규칙 R2 | `expiry_date < receipt_date` 면 거부 |
| 쓰기 | 통과 후 `x_foodservice_lot_ext(expiry_date)` 는 **LOT 생성 후** 에 써야 한다 → `on_lot_created(cur, lot, user)` 에서 `lot.kind='MATERIAL'` 이고 `lot.attrs.expiry_date`(폼 값을 코어가 `attrs` 로 저장한 것)가 있으면 ext 로 옮긴다. 즉 유통기한은 폼 → `attrs` → 훅이 ext 복사(검색 · 정렬은 ext 만 본다) |
| 쓰는 테이블 | `x_foodservice_lot_ext`(`on_lot_created` 에서) |

## 11. `validate_qua_issue(cur, row, user)` — F-QUA-08 이상 등록 직전

| 규칙 | `attrs.issue_type='클레임'` 이면 `attrs.partner_code` 필수(TD3-021 체크 "클레임은 고객사 필수") · `process_id` 는 9 공정 중 하나(코어 FK) |

## 12. 만들지 않는 훅

`on_order_created`(수주 → 생산계획 자동은 코어 변경 요청 §7-③ 전까지 사람이 ORD-04 에서 등록) · `on_work_order_closed` · `on_result_started` · `after_commit_*`(SCM · 프린터 없음 — ERP 어댑터 null 501).

## A. 이 사양이 드러낸 코어 변경 요청 후보 (README §7 에 합쳐 올린다)

- `validate_<table>` 뒤 **저장 직후 훅**(`on_<table>_saved(cur, row_with_id, user)`)이 없어 ext 행을 같은 트랜잭션에서 신규 행 `id` 로 넣을 수 없다(§1 · §10). 지금은 `on_lot_created` 가 있는 LOT 만 깔끔하고, `bas_bom` · `bas_item` · `bas_process` · `ord_order` · `bas_equipment` 의 ext 는 **코어가 `attrs` 로 받은 값을 다음 조회 · 수정 때 ext 로 옮기는 지연 복사**가 된다. 코어에 범용 `on_saved(cur, table, row, user)` 하나면 세 팩 모두의 E2 ext 가 같은 트랜잭션에서 끝난다.
