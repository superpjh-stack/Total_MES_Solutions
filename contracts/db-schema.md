# DB 스키마 계약 (아키텍트 · 2026-10-09 · 초안)

> 원본은 `src/mescore/db/schema.sql`(+ `views.sql`)이다. **§4 는 그 파일과 실제 DB 에서 찍어 낸 렌더본**이 될 자리라 구현 뒤에는 손으로 고치지 않는다 — `schema.sql` 을 고치고 `make db-schema && make contracts`. `make check-schema` 가 이 문서 ↔ 실제 DB 를 컬럼 단위로 대조한다(G-C04).
> 스키마를 고치는 사람은 아키텍트뿐이다. 개발자는 `progress-devN.md` §3 에 요청을 남긴다. 팩은 코어 테이블을 **고치지 못하고** `x_<팩>_*` 만 만든다(`pack-contract.md` §4 R2).
> 테이블 · 컬럼은 근거 사업 셋의 스키마에서 **둘 이상에 대응물이 있는 것**만 넣었다(각 표의 "근거" 열). 하나에만 있던 것은 팩으로 보냈다.

DB `mes_core_db` (PostgreSQL 17) · 테이블 **52** (bas 10 · ord 4 · job 2 · mat 4 · 공용 2 · pop 5 · qua 5 · eqp 4 · shp 2 · kpi 2 · sys 9 · ifc 3) · 뷰 3 · 팩 테이블 `x_<팩>_*`(여기 세지 않는다 — `check_schema` 가 따로 센다).

**공통 컬럼(전 테이블)** — `id bigserial primary key` · `created_at timestamptz not null default now()` · `created_by text` · `updated_at timestamptz` · `updated_by text` · **`attrs jsonb not null default '{}'`**(팩 표시용 속성 E2). 아래 표에는 적지 않는다.
**이름 규칙** — 소문자 snake_case · 모듈 접두어 · 코드 컬럼 `*_code` 유니크 · 번호 컬럼 `*_no` 유니크 · 외래키 `*_id` · 여부 `*_yn char(1)` · 상태 `status text` + CHECK.

## 1. 모듈 → 테이블

| 모듈 | 테이블 | 근거 사업 |
|---|---|---|
| bas | `bas_item` `bas_bom` `bas_bom_dtl` `bas_process` `bas_process_param` `bas_equipment` `bas_partner` `bas_worker` `bas_defect_code` `bas_code` | 임진강 `BAS_*` 10 · 니즈푸드 `BAS_*` 8 · 엘컴화인 `item customer process equipment defect_code` |
| ord | `ord_order` `ord_order_dtl` `ord_order_hist` `ord_plan` | 임진강 `ORD_*` 5 · 니즈푸드 `SAL_ORDER*` `PRD_PLAN` · 엘컴화인 `sales_order` |
| job | `job_work_order` `job_lot` | 임진강 `ORD_WORK_ORDER` · 니즈푸드 `PRD_WORK_ORDER` · 엘컴화인 `job job_lot` |
| mat | `mat_receipt` `mat_stock` `mat_stock_trx` `mat_requirement` | 임진강 `MAT_*` 4 · 니즈푸드 `MAT_*` 4 · 엘컴화인 `material_lot`(→ `lot`) |
| 공용 | **`lot`** **`lot_genealogy`** | 엘컴화인 `material_lot roll shipment roll_genealogy` 일반화 · 임진강 공정 체인 · 니즈푸드 `PRD_BATCH_RESULT` |
| pop | `pop_work_result` `pop_stop` `pop_scrap` `pop_input` `pop_measure` | 엘컴화인 `work_result work_stop work_scrap material_input` · 니즈푸드 `PRD_BATCH_RESULT` · 임진강 공정별 `*_LOG`(→ `pop_measure`) |
| qua | `qua_insp_plan` `qua_inspection` `qua_insp_item` `qua_defect` `qua_issue` | 니즈푸드 `QUA_*` 3 · 임진강 `QUA_*` 4 `*_CCP*` · 엘컴화인 `inspection inspection_defect` |
| eqp | `eqp_run_log` `eqp_check` `eqp_fault` `eqp_collect` | 임진강 `EQP_*` 3 · 니즈푸드 `EQP_*` 4 · 송월 `PRC_EQUIP_STATUS` |
| shp | `shp_shipment` `shp_document` | 엘컴화인 `shipment`(COA 포함) · 니즈푸드 `SAL_SHIP` · 임진강 `PKG_SHIP` |
| kpi | `kpi_indicator` `kpi_snapshot` | 임진강 `KPI_MASTER KPI_RESULT` · 니즈푸드 `KPI_INDICATOR KPI_RESULT` |
| sys | `sys_user` `sys_role` `sys_permission` `sys_session` `sys_access_log` `sys_number_rule` `sys_number_seq` `sys_migration_log` `sys_backup_hist` | 엘컴화인 `sys_*` 7 · 임진강 · 니즈푸드 `SYS_*` 4 |
| ifc | `ifc_collect_raw` `ifc_erp_link` `ifc_outbox` | 송월 `PRC_MONITOR_DATA DAT_IF_LOGS` · 임진강 `IF_SENSOR_RAW IF_ERP_LINK` · 엘컴화인 `erp.py` |

## 2. 쓰기 경계 (G-C05 의 기대값)

| 모듈 | 라우터 | 쓸 수 있는 테이블 | 쓰면 안 되는 대표 사례 |
|---|---|---|---|
| bas | `bas` | `bas_*` 10 | — |
| ord | `ord` | `ord_*` 4 | `job_work_order` |
| job | `job` | `job_work_order` `job_lot` · `ord_order_dtl.status`(연결 상태만) · `ord_plan.status` | LOT 을 미리 만드는 것 · 실적에 쓰기 |
| mat | `mat` | `mat_*` 4 · `lot`(kind=MATERIAL 생성 · `insp_status`) · `qua_inspection` `qua_insp_item`(입고검사 기록) | `job_work_order.status` · `pop_*` |
| pop | `pop` | `pop_*` 5 · `lot`(kind=PRODUCT — `lineage` 경유) · `lot_genealogy`(**`lineage` 경유만**) · `mat_stock` `mat_stock_trx`(투입 소비 — `lineage.consume_material` 경유) | `job_work_order.status` 직접 변경 · `lot_genealogy` 직접 SQL |
| qua | `qua` | `qua_*` 5 · `lot.insp_status` | `lot` 의 다른 컬럼 · `pop_*` |
| eqp | `eqp` | `eqp_run_log` `eqp_check` `eqp_fault` | `eqp_collect`(그건 `collect` 가 쓴다) · `pop_*` |
| shp | `shp` | `shp_*` 2 · `lot`(kind=SHIPMENT — `lineage.ship` 경유) · `lot_genealogy`(`출하` — `lineage` 경유만) | `lot.status` 직접 · `qua_*` |
| **trc** | `trc` | **없음** | 추적 결과 캐시 |
| **kpi** | `kpi` | `kpi_indicator` 만. `kpi_snapshot` 은 배치(`make kpi-snapshot`)만 | 집계 결과 테이블 |
| sys | `sys` · `auth` | `sys_*` 9 | — |
| ifc | `ifc` · `collect` · `erp` | `ifc_*` 3 · `eqp_collect` | 실적 테이블(수집값 → 실적은 팩 훅 `on_collect` 의 일, `write_scope` 필요) |
| 공통 | `templating` · `audit` · `numbering` | `sys_access_log` · `sys_number_seq` | — |
| 배치 | `mescore.migrate` | 그 명령의 대상 테이블 + `sys_migration_log` | — |
| 팩 | `packs/<팩>/routers` · `hooks` | `x_<팩>_*` + `pack.yaml: write_scope` | 선언 밖 · `lot_genealogy` · `sys_number_seq` 직접 |

- `sys_access_log`(조회 로그) · `sys_number_seq`(카운터)는 공통 코드가 쓴다. `trc` · `kpi` 화면을 열면 접근 로그가 한 줄 늘지만 라우터의 쓰기가 아니다 — **G-C05 행 수 대조 대상은 업무 테이블 40개**(sys 9 · ifc 3 제외).
- 저장하지 않고 계산하는 값 셋 — LOT 상태(`v_lot_state`) · 원재료 잔량(`v_lot_stock`) · 작업지시 진행 여부(`v_work_order_progress` — 실적 유무).

## 3. `lot` · `lot_genealogy` — 만들기 전에 종이 위에서 따져 본 것

### 3.1 `lot` 단일 테이블 (D-03)

엘컴화인은 `material_lot` · `roll` · `shipment` 세 테이블이었다. 단일화한 이유 — 계보 FK 가 한 컬럼 쌍(`parent_lot_id` · `child_lot_id`)으로 끝나고, 팩이 LOT 종류(`ROLL` · `BATCH` · `TANK`)를 **행 값**으로 더할 수 있다. 종류별로 꼭 다른 컬럼(공급처 · 출하 거래처)은 NULL 허용 + CHECK 로 묶는다. 출하 자체의 헤더(거래처 · 승인)는 `shp_shipment` 에 있고 출하 LOT 은 그것을 가리킨다.

### 3.2 모양 — 한 행 = 화살표 하나

`(parent_lot_id, child_lot_id, relation)` 유니크 · `parent_lot_id <> child_lot_id` CHECK · 순환은 트리거(`lot_genealogy_no_cycle`: 자식의 후손에 부모가 있으면 거부). `relation` 은 `sys` 가 아니라 **`core.yaml` + 팩 등록 목록**으로 검증한다(`lineage.link` 가 한다 — DB CHECK 로 박으면 팩이 못 더한다).

| 관계 `relation` | `relation_base` | 부모 kind | 자식 kind | 만드는 기능 |
|---|---|---|---|---|
| `투입` | 투입 | MATERIAL(또는 PRODUCT — 반제품 투입) | PRODUCT | F-POP-03 — 그 실적의 `pop_input` 마다 한 줄 |
| `생산` | 생산 | PRODUCT | PRODUCT | 다음 공정 실적이 앞 공정 LOT 을 투입으로 받지 않고 1:1 이어질 때(`make_product_lot(parent=...)`) |
| `분할` | 분할 | PRODUCT | PRODUCT (N) | `lineage.split` |
| `합병` | 합병 | PRODUCT (N) | PRODUCT | `lineage.merge` |
| `출하` | 출하 | PRODUCT | SHIPMENT | F-SHP-05 |
| 팩 (`splice` · `슬리팅` · `혼합` …) | 코어 5 중 하나 | base 대로 | base 대로 | 팩 라우터 → `lineage.split/merge(relation=…)` |

`relation_base` 컬럼을 **저장**한다(팩 relation 의 base 를 매번 매니페스트에서 찾지 않고 추적 SQL 이 바로 쓴다). `lineage.link` 가 채운다.

### 3.3 G-C06 — 코어 시나리오는 정확히 10행인가

| # | 부모 | 자식 | relation |
|---|---|---|---|
| 1 | 원재료 LOT ① | 생산 LOT ① | 투입 |
| 2 | 원재료 LOT ① | 생산 LOT ② | 투입 |
| 3 | 원재료 LOT ② | 생산 LOT ② | 투입 |
| 4 | 생산 LOT ① | 합병 LOT | 합병 |
| 5 | 생산 LOT ② | 합병 LOT | 합병 |
| 6 | 합병 LOT | 분할 LOT ① | 분할 |
| 7 | 합병 LOT | 분할 LOT ② | 분할 |
| 8 | 합병 LOT | 분할 LOT ③ | 분할 |
| 9 | 분할 LOT ① | 출하 LOT | 출하 |
| 10 | 분할 LOT ② | 출하 LOT | 출하 |

투입 3 + 합병 2 + 분할 3 + 출하 2 = **10**. 분할 LOT ③ 은 부모로 나오는 행이 없다 → `v_lot_state = 재고`. `printfilm` 팩은 같은 모양에서 relation 이름만 `splice` · `슬리팅` 이고 kind 가 `ROLL` 이다 — 추적 SQL 은 `relation_base` 만 보므로 **같은 쿼리**가 돈다.

- 행이 더 생기지 않는 이유: 출하 LOT 목록을 따로 담는 테이블이 없고(계보 한 줄이 곧 "실렸다"), 투입 스캔은 `pop_input` 에 있다가 LOT 이 만들어질 때 한 번만 옮겨진다.
- 행이 덜 생기지 않는 이유: 원재료 ① 이 두 생산 LOT 에 들어간 것은 실적 2건의 투입 2건이고, 유니크 키가 `(부모, 자식, relation)` 이라 같은 부모가 다른 자식의 부모가 되는 것은 막지 않는다.
- 추적은 `with recursive` 하나 — 역방향은 `child_lot_id` 에서 `parent_lot_id` 로, 정방향은 반대. 방문 집합으로 중복 제거, `depth` 는 최단.

### 3.4 상태 · 잔량 뷰

- `v_lot_state(lot_id, state)` — SHIPMENT 는 `출하`; PRODUCT 는 자식 쪽에 `출하` 행이 있으면 `출하`, `분할|합병|생산|투입` 의 **부모**로 나오면 `소진`, 아니면 `재고`; MATERIAL 은 잔량 0 이면 `소진`.
- `v_lot_stock(lot_id, qty, consumed_qty, remain_qty)` — MATERIAL: `lot.qty` − Σ`pop_input.qty`(취소 제외). PRODUCT: `lot.qty` − Σ 자식 계보 `qty`.
- `v_work_order_progress(work_order_id, started, closed, result_count, good_qty)`.

## 4. 테이블 — 52

컬럼은 공통 컬럼 5 + `attrs` 를 뺀 것. `PK` 는 전부 `id`. `★` = 유니크.

### `bas_item`
품목. `item_code ★` `item_name` `item_type`(제품/반제품/원재료/부자재 — `bas_code` 그룹 `ITEM_TYPE`) `spec` `unit` `use_yn`. 근거: 셋 다.

### `bas_bom`
BOM 헤더. `item_id →bas_item` `version` `use_yn`. `(item_id, version) ★`. 근거: 임진강 `BAS_BOM` · 니즈푸드 `BAS_RECIPE_BOM`.

### `bas_bom_dtl`
BOM 구성품. `bom_id →bas_bom` `component_item_id →bas_item` `qty` `unit` `loss_rate` `seq`. CHECK `component_item_id <> (select item_id)` 는 라우터가. 근거: 임진강 `BAS_BOM_DTL`.

### `bas_process`
공정. `process_code ★` `process_name` `seq` `use_yn`. 근거: 셋 다.

### `bas_process_param`
**공정 측정값 정의(E3).** `process_id →bas_process` `param_key` `label` `unit` `value_type`(number/text/bool/select) `choices jsonb` `min_value` `max_value` `required_yn` `source`(manual/collect) `collect_tag`(collect 일 때 태그 이름, 기본 `param_key`) `agg`(last/avg/max/min) `seq` `use_yn`. `(process_id, param_key) ★`. 근거: 임진강 `SLT_STD WSH_STD`(기준) + 니즈푸드 `BAS_PROCESS_STD` 의 일반화 — **테이블 폭발을 막는 자리**.

### `bas_equipment`
설비. `equip_code ★` `equip_name` `process_id →bas_process` `collect_yn` `use_yn`. `collect_yn=Y` 면 `collect` 의 `equip_code` 와 1:1. 근거: 셋 다 + 송월 `BAS_EQUIPMENTS`.

### `bas_partner`
거래처. `partner_code ★` `partner_name` `partner_type`(고객/공급/외주) `contact` `use_yn`. 근거: 셋 다.

### `bas_worker`
작업자. `worker_code ★` `worker_name` `process_id →bas_process` `user_id →sys_user`(선택) `use_yn`. 근거: 임진강 · 니즈푸드.

### `bas_defect_code`
불량코드. `defect_code ★` `defect_name` `process_id →bas_process`(선택) `use_yn`. 근거: 엘컴화인 · 임진강 `QUA_DEFECT_TYPE`.

### `bas_code`
공통코드(그룹 + 코드 한 테이블). `group_code` `code` `code_name` `seq` `is_core`(코어 예약) `use_yn`. `(group_code, code) ★`. 코어 그룹: `ITEM_TYPE` `PARTNER_TYPE` `STOP_REASON` `INSP_TYPE` `JUDGEMENT` `EQUIP_STATE` `ISSUE_STATUS` `DEVICE`. 근거: 셋 다.

### `ord_order`
수주 헤더. `order_no ★` `partner_id →bas_partner` `order_date` `due_date` `status`(등록/진행/완료/취소) `note`. 근거: 임진강 `ORD_ORDER` · 니즈푸드 `SAL_ORDER` · 엘컴화인 `sales_order`.

### `ord_order_dtl`
수주 상세. `order_id →ord_order` `line_no` `item_id →bas_item` `qty` `unit` `status`(대기/지시/출하). `(order_id, line_no) ★`.

### `ord_order_hist`
수주 변경 이력. `order_id →ord_order` `changed_at` `changed_by` `field` `before_value` `after_value`. 근거: 임진강 `ORD_ORDER_HIST`.

### `ord_plan`
생산계획. `plan_no ★` `order_dtl_id →ord_order_dtl`(선택) `item_id →bas_item` `plan_date` `plan_qty` `unit` `status`(계획/확정/취소). 근거: 임진강 `ORD_PLAN` · 니즈푸드 `PRD_PLAN`.

### `job_work_order`
작업지시. `work_order_no ★` `item_id →bas_item` `process_id →bas_process` `equipment_id →bas_equipment`(선택) `plan_id →ord_plan`(선택) `order_dtl_id →ord_order_dtl`(선택) `bom_id →bas_bom`(선택) `plan_qty` `unit` `plan_date` `status`(대기/진행/마감/취소) `closed_at` `closed_by` `note`. 근거: 셋 다.

### `job_lot`
지시 ↔ 소요 품목/LOT 매핑. `work_order_id →job_work_order` `item_id →bas_item` `required_qty` `unit` `lot_id →lot`(선택 — 지정 투입). 근거: 엘컴화인 `job_lot`(D-10) · 니즈푸드 소요량.

### `mat_receipt`
입고. `receipt_no ★` `item_id →bas_item` `partner_id →bas_partner` `receipt_date` `qty` `unit` `lot_id →lot`(생성된 원재료 LOT) `note`. 근거: 셋 다.

### `mat_stock`
품목별 현재고. `item_id →bas_item ★` `qty` `unit` `updated_at`. 거래(`mat_stock_trx`)의 합과 같아야 한다(`check_data`). 근거: 임진강 `MAT_STOCK` · 니즈푸드 `MAT_PROD_STOCK`.

### `mat_stock_trx`
재고 거래. `item_id →bas_item` `lot_id →lot`(선택) `trx_type`(입고/투입/조정/출하) `qty`(부호) `unit` `ref_table` `ref_id` `reason` `trx_at`. 근거: 임진강 `MAT_STOCK_TRX` · 니즈푸드 `MAT_STOCK_MOVE`.

### `mat_requirement`
소요량. `period_from` `period_to` `item_id →bas_item` `required_qty` `stock_qty` `shortage_qty` `unit` `source`(calc/hook) `calc_at`. `(period_from, period_to, item_id, source) ★`. 근거: 임진강 `MAT_REQUIRE` · 니즈푸드 소요량.

### `lot`
**추적 단위.** `lot_no ★` `kind`(MATERIAL/PRODUCT/SHIPMENT + 팩 등록) `kind_base`(코어 3 중 하나 — `lineage` 가 채움) `item_id →bas_item`(SHIPMENT 는 NULL) `work_order_id →job_work_order`(선택) `process_id →bas_process`(선택) `equipment_id →bas_equipment`(선택) `work_result_id →pop_work_result`(생성 실적, 선택) `partner_id →bas_partner`(MATERIAL 공급처, 선택) `shipment_id →shp_shipment`(SHIPMENT 만) `qty` `unit` `insp_status`(미검사/합격/불합격/조건부) `made_at` `note`. CHECK `kind_base='SHIPMENT'` ↔ `shipment_id not null`. 근거: 엘컴화인 3테이블 · 니즈푸드 배치 · 임진강 공정 LOT.

### `lot_genealogy`
**화살표 한 줄.** `parent_lot_id →lot` `child_lot_id →lot` `relation` `relation_base`(투입/생산/분할/합병/출하) `qty` `linked_at` `linked_by`. `(parent_lot_id, child_lot_id, relation) ★` · CHECK `parent_lot_id <> child_lot_id` · 트리거 `no_cycle`. **`lineage` 만 쓴다.** 근거: 엘컴화인 `roll_genealogy`.

### `pop_work_result`
실적(작업 1회). `work_order_id →job_work_order` `process_id →bas_process` `equipment_id →bas_equipment`(선택) `worker_id →bas_worker`(선택) `started_at` `ended_at` `good_qty` `defect_qty` `unit` `product_lot_id →lot`(종료 때) `note`. 근거: 셋 다.

### `pop_stop`
정지. `work_result_id →pop_work_result` `reason_code`(`STOP_REASON`) `started_at` `ended_at` `note`. 근거: 엘컴화인 `work_stop` · 니즈푸드 `PRC_DELAY`.

### `pop_scrap`
폐기. `work_result_id →pop_work_result` `defect_code_id →bas_defect_code` `qty` `unit` `scrapped_at`. 근거: 엘컴화인 `work_scrap` · 임진강 불량.

### `pop_input`
투입 스캔. `work_result_id →pop_work_result` `material_lot_id →lot` `qty` `unit` `scanned_at` `canceled_yn`. 종료 때 `투입` 계보로 옮겨진다. 근거: 엘컴화인 `material_input` · 니즈푸드 레시피 투입.

### `pop_measure`
**측정값 기록(E3).** `work_result_id →pop_work_result` `param_id →bas_process_param` `param_key` `value_num` `value_text` `unit` `source`(manual/collect) `deviated`(범위 이탈) `measured_at`. `(work_result_id, param_key) ★`. 근거: 임진강 `SLT_SALINITY_LOG MIX_CCP_RESULT` · 니즈푸드 교반기 값 · 엘컴화인 ΔE 의 일반화.

### `qua_insp_plan`
검사 계획(항목 정의). `insp_type`(입고/공정/최종) `item_id →bas_item`(선택) `process_id →bas_process`(선택) `item_key` `label` `unit` `value_type` `standard` `min_value` `max_value` `seq` `use_yn`. `(insp_type, item_id, process_id, item_key) ★`(NULL 은 빈 문자열로 대체해 유니크). 근거: 니즈푸드 `QUA_INSP_PLAN` · 임진강 `BAS_CCP_STD`.

### `qua_inspection`
검사 1건. `lot_id →lot` `insp_type` `inspected_at` `inspector` `judgement`(NULL/합격/불합격/조건부) `judged_at` `judged_by` `note`. 근거: 셋 다.

### `qua_insp_item`
검사 항목 값. `inspection_id →qua_inspection` `plan_id →qua_insp_plan`(선택) `item_key` `value_num` `value_text` `unit` `item_judgement` `deviated`. `(inspection_id, item_key) ★`. 근거: 임진강 CCP 결과 · 니즈푸드 검식.

### `qua_defect`
불량(검사 판정에 붙는 불량코드별 수량). `inspection_id →qua_inspection` `defect_code_id →bas_defect_code` `qty` `position` `note`. 근거: 엘컴화인 `inspection_defect` · 임진강 `QUA_DEFECT`.

### `qua_issue`
이상 · 시정. `issue_no ★` `occurred_at` `process_id →bas_process`(선택) `lot_id →lot`(선택) `inspection_id →qua_inspection`(선택) `content` `cause` `action` `action_by` `action_at` `status`(발생/조치/종결) `source`(manual/hook). 근거: 니즈푸드 · 임진강 `QUA_ISSUE`.

### `eqp_run_log`
가동 구간. `equipment_id →bas_equipment` `state`(가동/정지/점검/고장 — `EQUIP_STATE`) `started_at` `ended_at` `source`(manual/collect) `note`. 근거: 임진강 `EQP_RUN_LOG` · 니즈푸드 `EQP_STATUS` · 송월 `PRC_EQUIP_STATUS`.

### `eqp_check`
점검. `equipment_id →bas_equipment` `checked_at` `item` `result` `checker` `note`. 근거: 임진강 `EQP_CHECK` · 니즈푸드 `EQP_INSPECT`.

### `eqp_fault`
고장. `equipment_id →bas_equipment` `occurred_at` `symptom` `fixed_at` `fix_action` `fixed_by` `run_log_id →eqp_run_log`. 근거: 임진강 · 니즈푸드 `EQP_FAULT`.

### `eqp_collect`
수집값 정제본(시계열). `equipment_id →bas_equipment` `tag` `ts` `value_num` `value_text` `raw_id →ifc_collect_raw`. `(equipment_id, tag, ts) ★`. 월 단위 파티션 후보(비기능 — 첫 판은 단일 테이블 + 인덱스). 근거: 니즈푸드 `EQP_COLLECT` · 임진강 `IF_SENSOR_RAW` · 송월 `PRC_MONITOR_DATA`.

### `shp_shipment`
출하 헤더. `shipment_no ★` `partner_id →bas_partner` `ship_date` `order_id →ord_order`(선택) `status`(등록/승인/취소) `approved_at` `approved_by` `note`. 출하 LOT 은 `lot(kind=SHIPMENT).shipment_id` 가 가리킨다. 근거: 셋 다.

### `shp_document`
성적서 · 거래명세서 발행본. `document_no ★` `doc_type`(성적서/거래명세서) `shipment_id →shp_shipment` `issued_at` `issued_by` `snapshot jsonb`(발행 시점의 LOT · 검사 값). 근거: 엘컴화인 COA · 평창 거래명세서.

### `kpi_indicator`
지표 정의. `indicator_key ★` `name` `unit` `target_value` `calc_kind`(core:production.good_rate … / pack:<key>) `visible_yn` `seq`. 근거: 임진강 `KPI_MASTER` · 니즈푸드 `KPI_INDICATOR`.

### `kpi_snapshot`
현황판 일 스냅샷(배치만 쓴다). `snap_date` `indicator_key` `value` `calc_at`. `(snap_date, indicator_key) ★`. 근거: 임진강 `KPI_RESULT DSH_METRIC_TS`.

### `sys_user`
사용자. `login_id ★` `user_name` `password_hash` `role_id →sys_role` `worker_id →bas_worker`(선택) `status`(사용/중지/잠금) `fail_count` `last_login_at` `password_changed_at`. 근거: 셋 다.

### `sys_role`
역할. `role_code ★` `role_name` `use_yn`. `ADMIN` 은 시드 필수. 근거: 셋 다.

### `sys_permission`
권한 표 칸. `role_id →sys_role` `menu_code` `level`(없음/조회/입력) `scopes text[]`. `(role_id, menu_code) ★`. 메뉴 수 × 역할 수 = 전 칸 있어야 한다. 근거: 엘컴화인 `sys_permission` · 임진강 `SYS_ROLE_AUTH`.

### `sys_session`
세션. `session_id ★` `user_id →sys_user` `device`(web/pop/mobile/board) `issued_at` `expires_at` `revoked_at` `password_version`. 요청마다 사용자 상태와 함께 확인. 근거: 엘컴화인(D-26 쿠키 → DB).

### `sys_access_log`
접근 로그. `logged_at` `user_id →sys_user`(선택) `login_id` `kind`(login_ok/login_fail/view/change) `screen_id` `fn_id` `target` `detail jsonb` `ip` `device`. 근거: 셋 다 `SYS_LOG`.

### `sys_number_rule`
채번 규칙. `kind ★` `prefix` `date_format` `seq_digits` `use_yn`. 근거: 엘컴화인.

### `sys_number_seq`
채번 카운터. `kind` `seq_scope`(날짜 부분 값) `last_seq`. `(kind, seq_scope) ★`. 행 잠금으로 올린다. 근거: 엘컴화인.

### `sys_migration_log`
이관 로그. `command` `dir` `file` `read_count` `inserted` `updated` `skipped` `errors` `error_detail jsonb` `dry_run` `started_at` `ended_at` `run_by`. 근거: 엘컴화인.

### `sys_backup_hist`
백업 이력. `dump_path` `row_counts jsonb` `started_at` `ended_at` `ok` `verified_at` `verify_ok` `message`. 근거: 임진강 · 니즈푸드 `SYS_BACKUP_HIST`.

### `ifc_collect_raw`
수집 원문. `equip_code` `ts` `source` `payload jsonb` `resend` `received_at` `rejected_reason`. `(equip_code, ts, source) ★`. 모르는 설비도 **거부 사유와 함께 남긴다**. 근거: 송월 `PRC_MONITOR_DATA DAT_COLLECT_LOGS`.

### `ifc_erp_link`
ERP 연계 기록. `kind` `direction`(push/pull) `ref_table` `ref_id` `status`(대기/성공/실패/미확정) `message` `linked_at`. 근거: 임진강 `IF_ERP_LINK` · 송월 `DAT_IF_LOGS`.

### `ifc_outbox`
외부 전송 큐. `event` `payload jsonb` `status`(대기/전송/실패/미확정) `attempts` `last_error` `created_at` `sent_at`. `after_commit_*` 훅이 넣고 `erp.flush` 가 비운다. 근거: 엘컴화인 `erp.py` 일반화 `[가설]`.

## 5. 인덱스 · 제약 요약

- 유니크: 위 `★`. 번호 · 코드 전부.
- FK 전부 `on delete restrict`(삭제 대신 `use_yn=N`), 예외 `x_<팩>_<코어>_ext` 는 `cascade`.
- `lot_genealogy`: `(parent_lot_id)` · `(child_lot_id)` 인덱스 — 재귀 양방향.
- `eqp_collect (equipment_id, tag, ts desc)` · `pop_measure (param_key, measured_at)` · `sys_access_log (logged_at desc)`.
- 공통 `attrs` 에는 인덱스를 두지 않는다(표시용 — D-05).
