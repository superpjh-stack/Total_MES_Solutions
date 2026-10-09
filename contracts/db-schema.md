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
| 공통 | `templating` · `audit` · `numbering` · `auth` · `main`(after_commit) | `sys_access_log` · `sys_number_seq` · `sys_session`(로그인 · 로그아웃) · `ifc_outbox`(`after_commit_*` 훅이 실패했을 때 `status=실패` 한 행 — D-20) | — |
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

- `v_lot_state(lot_id, state)` — SHIPMENT 는 `출하`; PRODUCT 는 자식 쪽에 `출하` 행이 있으면 `출하`, `분할|합병|생산` 의 **부모**로 나오면 `소진`(LOT 통째), 그 밖(투입만 · 열린 투입만 · 아무것도 없음)은 **잔량**(`v_lot_stock` — 계보 + 종료 전 실적의 투입)으로 — 잔량 ≤ 0 · 수량 모르는 투입(계보 qty NULL 또는 열린 `pop_input.qty` NULL) · LOT 수량 NULL 인데 투입이 있으면 `소진`, 아니면 `재고`(부분 투입 · 회전 4). **열린 투입으로 잔량 0 이면 종료 전이라도 `소진`**(회전 7 · D-41 · DEF-QA2-008) — 취소하면 다시 `재고`; MATERIAL 은 잔량 0 이면 `소진`.
- `v_lot_stock(lot_id, qty, consumed_qty, remain_qty)` — MATERIAL: `lot.qty` − Σ`pop_input.qty`(취소 제외). PRODUCT: `lot.qty` − Σ 자식 계보 `qty` − Σ **종료 전 실적**(`pop_work_result.ended_at IS NULL`)의 `pop_input.qty`(취소 제외 — 회전 5 · DEF-QA2-001). 종료되면 그 투입은 계보 `투입` 으로 넘어가 한 번만 센다. `v_lot_state` 는 이 잔량을 그대로 쓴다 — 열린 투입이 잔량을 0 으로 만들면 상태도 `소진`(회전 7 · D-41 · 회전 5 의 「열린 투입은 상태 불변」 문장은 폐기). 쓰기 경로(`lineage.assert_usable` · 잔량 검사)도 같은 상태 · 잔량을 본다.
- `v_work_order_progress(work_order_id, started, closed, result_count, good_qty)`.

## 4. 테이블 — 52 (렌더본 — `make contracts` 가 schema.sql + 실제 DB 에서 찍는다 · D-23)

열: 컬럼 · 타입(`format_type` 그대로) · NULL 허용 · 설명(schema.sql 의 컬럼 주석). **공통 컬럼 6**(`id` · `created_at` · `created_by` · `updated_at` · `updated_by` · `attrs`)은 적지 않는다 — `check_schema` 가 전 테이블에 있는지 따로 센다.
`★` 유니크 · FK · CHECK 는 §5 와 schema.sql 의 `constraint` 이름으로 `check_schema` 가 대조한다. 모듈 `공용` 은 `lot` · `lot_genealogy`.

<!-- BEGIN:generated tables -->
### `bas_process` — bas · 공정
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `process_code` | `text` | N | 공정 코드 (유니크) |
| `process_name` | `text` | N | 공정 이름 |
| `seq` | `integer` | N | 순서 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `bas_item` — bas · 품목
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `item_code` | `text` | N | 품목 코드 (유니크) |
| `item_name` | `text` | N | 품목명 |
| `item_type` | `text` | N | 구분 — 공통코드 ITEM_TYPE (제품/반제품/원재료/부자재) |
| `spec` | `text` | Y | 규격 |
| `unit` | `text` | Y | 단위 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `bas_bom` — bas · BOM 헤더
근거: 임진강 `BAS_BOM` · 니즈푸드 BOM 테이블

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `item_id` | `bigint` | N | 상위 품목 |
| `version` | `text` | N | 버전 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `bas_bom_dtl` — bas · BOM 구성품
근거: 임진강 `BAS_BOM_DTL`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `bom_id` | `bigint` | N | BOM 헤더 |
| `component_item_id` | `bigint` | N | 구성품 품목 (자기 자신 금지는 라우터가) |
| `qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |
| `loss_rate` | `numeric(7,3)` | N |  |
| `seq` | `integer` | N | 순서 |

### `bas_process_param` — bas · 공정 측정값 정의 (E3) — 이 행이 POP 종료 폼을 만든다
근거: 임진강 `SLT_STD WSH_STD`(기준) + 니즈푸드 `BAS_PROCESS_STD` 의 일반화 — **테이블 폭발을 막는 자리**

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `process_id` | `bigint` | N | 공정 |
| `param_key` | `text` | N | 키 (영문 — pop_measure.param_key · collect 태그와 잇는다) |
| `label` | `text` | N | 화면 라벨 |
| `unit` | `text` | Y | 단위 |
| `value_type` | `text` | N | 형식 number/text/bool/select |
| `choices` | `jsonb` | Y | select 일 때 선택지 목록 |
| `min_value` | `numeric(18,4)` | Y |  |
| `max_value` | `numeric(18,4)` | Y |  |
| `required_yn` | `character(1)` | N | 필수 여부 (누락 422) |
| `source` | `text` | N | 수집원 manual/collect |
| `collect_tag` | `text` | Y | collect 일 때 태그 이름 (기본 param_key) |
| `agg` | `text` | N | collect 대표값 last/avg/max/min |
| `seq` | `integer` | N | 순서 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `bas_equipment` — bas · 설비
근거: 셋 다 + 송월 `BAS_EQUIPMENTS`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `equip_code` | `text` | N | 설비 코드 (유니크 · collect 의 equip_code 와 1:1) |
| `equip_name` | `text` | N | 설비 이름 |
| `process_id` | `bigint` | Y | 공정 |
| `collect_yn` | `character(1)` | N | 수집 설비 여부 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `bas_partner` — bas · 거래처
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `partner_code` | `text` | N | 거래처 코드 (유니크) |
| `partner_name` | `text` | N | 거래처명 |
| `partner_type` | `text` | N | 구분 — 공통코드 PARTNER_TYPE (고객/공급/외주) |
| `contact` | `text` | Y | 연락처 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `sys_role` — sys · 역할
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `role_code` | `text` | N | 역할 코드 (유니크 · ADMIN 시드 필수) |
| `role_name` | `text` | N | 역할 이름 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `sys_user` — sys · 사용자
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `login_id` | `text` | N | 로그인 ID (유니크) |
| `user_name` | `text` | N | 이름 |
| `password_hash` | `text` | N | 비밀번호 해시 (PBKDF2) — 평문 없음 |
| `role_id` | `bigint` | N | 역할 |
| `worker_id` | `bigint` | Y | 작업자 연결 (선택 · FK 는 bas_worker 뒤에 붙인다) |
| `status` | `text` | N | 상태 사용/중지/잠금 |
| `fail_count` | `integer` | N | 로그인 실패 횟수 |
| `last_login_at` | `timestamp with time zone` | Y | 마지막 로그인 |
| `password_changed_at` | `timestamp with time zone` | N | 비밀번호 변경 시각 — 바뀌면 그 전 세션이 전부 끊긴다 (D-19) |

### `bas_worker` — bas · 작업자
근거: 임진강 · 니즈푸드

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `worker_code` | `text` | N | 작업자 코드 (유니크) |
| `worker_name` | `text` | N | 이름 |
| `process_id` | `bigint` | Y | 담당 공정 |
| `user_id` | `bigint` | Y | 사용자 계정 (선택) |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `bas_defect_code` — bas · 불량코드
근거: 엘컴화인 · 임진강 `QUA_DEFECT_TYPE`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `defect_code` | `text` | N | 불량 코드 (유니크) |
| `defect_name` | `text` | N | 불량 이름 |
| `process_id` | `bigint` | Y | 공정 (선택) |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `bas_code` — bas · 공통코드 (그룹 + 코드 한 테이블)
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `group_code` | `text` | N | 그룹 (코어 그룹은 core.yaml: code_groups) |
| `code` | `text` | N | 코드 |
| `code_name` | `text` | N | 이름 |
| `seq` | `integer` | N | 순서 |
| `is_core` | `character(1)` | N | 코어 예약 코드 여부 (삭제 422) |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `ord_order` — ord · 수주 헤더
근거: 임진강 `ORD_ORDER` · 니즈푸드 `SAL_ORDER` · 엘컴화인 `sales_order`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `order_no` | `text` | N | 수주 번호 (유니크 · numbering ORDER) |
| `partner_id` | `bigint` | N | 거래처 |
| `order_date` | `date` | N | 수주일 |
| `due_date` | `date` | Y | 납기 |
| `status` | `text` | N | 상태 등록/진행/완료/취소 |
| `note` | `text` | Y | 비고 |

### `ord_order_dtl` — ord · 수주 상세
근거: ord_order 와 같다 (§1: 임진강 `ORD_*` · 니즈푸드 `SAL_ORDER*`)

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `order_id` | `bigint` | N | 수주 헤더 |
| `line_no` | `integer` | N | 줄 번호 |
| `item_id` | `bigint` | N | 품목 |
| `qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |
| `status` | `text` | N | 상태 대기/지시/출하 (job 이 지시 연결 상태만 바꾼다) |

### `ord_order_hist` — ord · 수주 변경 이력
근거: 임진강 `ORD_ORDER_HIST`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `order_id` | `bigint` | N | 수주 헤더 |
| `changed_at` | `timestamp with time zone` | N | 변경 시각 |
| `changed_by` | `text` | Y | 변경자 login_id |
| `field` | `text` | N | 바뀐 항목 |
| `before_value` | `text` | Y | 전 값 |
| `after_value` | `text` | Y | 후 값 |

### `ord_plan` — ord · 생산계획
근거: 임진강 `ORD_PLAN` · 니즈푸드 `PRD_PLAN`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `plan_no` | `text` | N | 계획 번호 (유니크 · numbering PLAN) |
| `order_dtl_id` | `bigint` | Y | 수주 상세 (선택) |
| `item_id` | `bigint` | N | 품목 |
| `plan_date` | `date` | N | 계획일 |
| `plan_qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |
| `status` | `text` | N | 상태 계획/확정/취소 |

### `job_work_order` — job · 작업지시
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `work_order_no` | `text` | N | 지시 번호 (유니크 · numbering WORK_ORDER) |
| `item_id` | `bigint` | N | 품목 |
| `process_id` | `bigint` | N | 공정 |
| `equipment_id` | `bigint` | Y | 설비 (선택) |
| `plan_id` | `bigint` | Y | 생산계획 (선택) |
| `order_dtl_id` | `bigint` | Y | 수주 상세 (선택) |
| `bom_id` | `bigint` | Y | BOM (선택) |
| `plan_qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |
| `plan_date` | `date` | Y | 계획일 |
| `status` | `text` | N | 상태 대기/진행/마감/취소 (진행 여부는 실적 유무로 계산) |
| `closed_at` | `timestamp with time zone` | Y | 마감 시각 |
| `closed_by` | `text` | Y | 마감자 login_id |
| `note` | `text` | Y | 비고 |

### `shp_shipment` — shp · 출하 헤더
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `shipment_no` | `text` | N | 출하 번호 (유니크 · numbering SHIPMENT) |
| `partner_id` | `bigint` | N | 거래처 |
| `ship_date` | `date` | N | 출하일 |
| `order_id` | `bigint` | Y | 수주 (선택) |
| `status` | `text` | N | 상태 등록/승인/취소 |
| `approved_at` | `timestamp with time zone` | Y | 승인 시각 |
| `approved_by` | `text` | Y | 승인자 login_id |
| `note` | `text` | Y | 비고 |

### `lot` — 공용 · 추적 단위 (D-03) — MATERIAL · PRODUCT · SHIPMENT + 팩 등록 kind
근거: 엘컴화인 3테이블 · 니즈푸드 배치 · 임진강 공정 LOT

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `lot_no` | `text` | N | LOT 번호 (유니크 · 바코드 — 영문 대문자 · 숫자 · - 만) |
| `kind` | `text` | N | 종류 MATERIAL/PRODUCT/SHIPMENT + 팩 등록 |
| `kind_base` | `text` | N | 코어 종류 3 중 하나 (lineage 가 채움) |
| `item_id` | `bigint` | Y | 품목 (SHIPMENT 는 NULL) |
| `work_order_id` | `bigint` | Y | 작업지시 (선택) |
| `process_id` | `bigint` | Y | 공정 (선택) |
| `equipment_id` | `bigint` | Y | 설비 (선택) |
| `work_result_id` | `bigint` | Y | 생성 실적 (선택 · FK 는 pop_work_result 뒤에) |
| `partner_id` | `bigint` | Y | MATERIAL 공급처 (선택) |
| `shipment_id` | `bigint` | Y | SHIPMENT 만 |
| `qty` | `numeric(18,3)` | Y |  |
| `unit` | `text` | Y | 단위 |
| `insp_status` | `text` | N | 검사 상태 미검사/합격/불합격/조건부 |
| `made_at` | `timestamp with time zone` | N | 생성 시각 |
| `note` | `text` | Y | 비고 |

### `job_lot` — job · 지시 ↔ 소요 품목/LOT 매핑
근거: 엘컴화인 `job_lot`(D-10) · 니즈푸드 소요량

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `work_order_id` | `bigint` | N | 작업지시 |
| `item_id` | `bigint` | N | 소요 품목 |
| `required_qty` | `numeric(18,3)` | Y |  |
| `unit` | `text` | Y | 단위 |
| `lot_id` | `bigint` | Y | 지정 투입 LOT (선택) |

### `mat_receipt` — mat · 입고
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `receipt_no` | `text` | N | 입고 번호 (유니크) |
| `item_id` | `bigint` | N | 품목 |
| `partner_id` | `bigint` | Y | 공급처 |
| `receipt_date` | `date` | N | 입고일 |
| `qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |
| `lot_id` | `bigint` | Y | 생성된 원재료 LOT |
| `note` | `text` | Y | 비고 |

### `mat_stock` — mat · 품목별 현재고 (거래 합과 같아야 한다)
근거: 임진강 `MAT_STOCK` · 니즈푸드 `MAT_PROD_STOCK`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `item_id` | `bigint` | N | 품목 (유니크) |
| `qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |

### `mat_stock_trx` — mat · 재고 거래
근거: 임진강 `MAT_STOCK_TRX` · 니즈푸드 `MAT_STOCK_MOVE`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `item_id` | `bigint` | N | 품목 |
| `lot_id` | `bigint` | Y | LOT (선택) |
| `trx_type` | `text` | N | 거래 구분 입고/투입/조정/출하 |
| `qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |
| `ref_table` | `text` | Y | 참조 테이블 |
| `ref_id` | `bigint` | Y | 참조 ID |
| `reason` | `text` | Y | 사유 (조정은 필수 — 라우터) |
| `trx_at` | `timestamp with time zone` | N | 거래 시각 |

### `mat_requirement` — mat · 소요량
근거: 임진강 `MAT_REQUIRE` · 니즈푸드 소요량

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `period_from` | `date` | N | 기간 시작 |
| `period_to` | `date` | N | 기간 끝 |
| `item_id` | `bigint` | N | 품목 |
| `required_qty` | `numeric(18,3)` | N |  |
| `stock_qty` | `numeric(18,3)` | N |  |
| `shortage_qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |
| `source` | `text` | N | 출처 calc/hook (훅이 만든 행은 재계산이 덮지 않는다) |
| `calc_at` | `timestamp with time zone` | N | 계산 시각 |

### `pop_work_result` — pop · 실적 (작업 1회)
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `work_order_id` | `bigint` | N | 작업지시 |
| `process_id` | `bigint` | N | 공정 |
| `equipment_id` | `bigint` | Y | 설비 (선택) |
| `worker_id` | `bigint` | Y | 작업자 (선택) |
| `started_at` | `timestamp with time zone` | N | 시작 시각 |
| `ended_at` | `timestamp with time zone` | Y | 종료 시각 (NULL = 진행 중) |
| `good_qty` | `numeric(18,3)` | Y |  |
| `defect_qty` | `numeric(18,3)` | Y |  |
| `unit` | `text` | Y | 단위 |
| `product_lot_id` | `bigint` | Y | 생산 LOT (종료 때 lineage 가 채운다) |
| `note` | `text` | Y | 비고 |

### `lot_genealogy` — 공용 · 계보 — 화살표 한 줄 = 부모 LOT → 자식 LOT. lineage 만 쓴다
근거: 엘컴화인 `roll_genealogy`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `parent_lot_id` | `bigint` | N | 부모 LOT |
| `child_lot_id` | `bigint` | N | 자식 LOT |
| `relation` | `text` | N | 관계 (코어 5 + 팩 등록 — lineage.link 가 검증) |
| `relation_base` | `text` | N | 코어 관계 투입/생산/분할/합병/출하 (추적 SQL 이 본다) |
| `qty` | `numeric(18,3)` | Y |  |
| `linked_at` | `timestamp with time zone` | N | 연결 시각 |
| `linked_by` | `text` | Y | 연결자 login_id |

### `pop_stop` — pop · 정지
근거: 엘컴화인 `work_stop` · 니즈푸드 `PRC_DELAY`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `work_result_id` | `bigint` | N | 실적 |
| `reason_code` | `text` | N | 사유 — 공통코드 STOP_REASON |
| `started_at` | `timestamp with time zone` | N | 정지 시작 |
| `ended_at` | `timestamp with time zone` | Y | 정지 끝 |
| `note` | `text` | Y | 비고 |

### `pop_scrap` — pop · 폐기
근거: 엘컴화인 `work_scrap` · 임진강 불량

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `work_result_id` | `bigint` | N | 실적 |
| `defect_code_id` | `bigint` | Y | 불량코드 |
| `qty` | `numeric(18,3)` | N |  |
| `unit` | `text` | Y | 단위 |
| `scrapped_at` | `timestamp with time zone` | N | 폐기 시각 |

### `pop_input` — pop · 투입 스캔 (종료 때 투입 계보로 옮겨진다)
근거: 엘컴화인 `material_input` · 니즈푸드 BOM 투입

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `work_result_id` | `bigint` | N | 실적 |
| `material_lot_id` | `bigint` | N | 투입한 원재료 LOT |
| `qty` | `numeric(18,3)` | Y |  |
| `unit` | `text` | Y | 단위 |
| `scanned_at` | `timestamp with time zone` | N | 스캔 시각 |
| `canceled_yn` | `character(1)` | N | 취소 여부 |

### `pop_measure` — pop · 측정값 기록 (E3) — 실적 1건당 키당 1행
근거: 임진강 `SLT_SALINITY_LOG MIX_CCP_RESULT` · 니즈푸드 설비 측정값 · 엘컴화인 색차 측정값의 일반화

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `work_result_id` | `bigint` | N | 실적 |
| `param_id` | `bigint` | Y | 측정값 정의 (선택 — 정의가 지워져도 기록은 남는다) |
| `param_key` | `text` | N | 키 |
| `value_num` | `numeric(18,4)` | Y |  |
| `value_text` | `text` | Y | 글자 값 |
| `unit` | `text` | Y | 단위 |
| `source` | `text` | N | 수집원 manual/collect |
| `deviated` | `boolean` | N | 범위 이탈 (저장하고 표시 — 오류 아님) |
| `measured_at` | `timestamp with time zone` | N | 측정 시각 |

### `qua_insp_plan` — qua · 검사 계획 (항목 정의)
근거: 니즈푸드 `QUA_INSP_PLAN` · 임진강 `BAS_CCP_STD`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `insp_type` | `text` | N | 검사 유형 입고/공정/최종 — 공통코드 INSP_TYPE |
| `item_id` | `bigint` | Y | 품목 (선택) |
| `process_id` | `bigint` | Y | 공정 (선택) |
| `item_key` | `text` | N | 항목 키 |
| `label` | `text` | N | 항목 라벨 |
| `unit` | `text` | Y | 단위 |
| `value_type` | `text` | N | 형식 number/text/bool/select |
| `standard` | `text` | Y | 기준 (글자) |
| `min_value` | `numeric(18,4)` | Y |  |
| `max_value` | `numeric(18,4)` | Y |  |
| `seq` | `integer` | N | 순서 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `qua_inspection` — qua · 검사 1건 (최신 검사가 그 LOT 의 판정)
근거: 셋 다

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `lot_id` | `bigint` | N | 검사한 LOT |
| `insp_type` | `text` | N | 검사 유형 입고/공정/최종 |
| `inspected_at` | `timestamp with time zone` | N | 검사 시각 |
| `inspector` | `text` | Y | 검사자 login_id |
| `judgement` | `text` | Y | 판정 NULL/합격/불합격/조건부 |
| `judged_at` | `timestamp with time zone` | Y | 판정 시각 |
| `judged_by` | `text` | Y | 판정자 login_id |
| `note` | `text` | Y | 비고 |

### `qua_insp_item` — qua · 검사 항목 값
근거: 임진강 CCP 결과 · 니즈푸드 검사 항목

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `inspection_id` | `bigint` | N | 검사 |
| `plan_id` | `bigint` | Y | 계획 항목 (선택) |
| `item_key` | `text` | N | 항목 키 |
| `value_num` | `numeric(18,4)` | Y |  |
| `value_text` | `text` | Y | 글자 값 |
| `unit` | `text` | Y | 단위 |
| `item_judgement` | `text` | Y | 항목 판정 |
| `deviated` | `boolean` | N | 기준 이탈 |

### `qua_defect` — qua · 불량 (판정에 붙는 불량코드별 수량)
근거: 엘컴화인 `inspection_defect` · 임진강 `QUA_DEFECT`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `inspection_id` | `bigint` | N | 검사 |
| `defect_code_id` | `bigint` | N | 불량코드 |
| `qty` | `numeric(18,3)` | Y |  |
| `position` | `text` | Y | 위치 |
| `note` | `text` | Y | 비고 |

### `qua_issue` — qua · 이상 · 시정
근거: 니즈푸드 · 임진강 `QUA_ISSUE`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `issue_no` | `text` | N | 이상 번호 (유니크) |
| `occurred_at` | `timestamp with time zone` | N | 발생 시각 |
| `process_id` | `bigint` | Y | 공정 (선택) |
| `lot_id` | `bigint` | Y | LOT (선택) |
| `inspection_id` | `bigint` | Y | 검사 (선택) |
| `content` | `text` | N | 내용 |
| `cause` | `text` | Y | 원인 |
| `action` | `text` | Y | 조치 내용 |
| `action_by` | `text` | Y | 조치 담당 |
| `action_at` | `timestamp with time zone` | Y | 조치 일시 |
| `status` | `text` | N | 상태 발생/조치/종결 — 공통코드 ISSUE_STATUS |
| `source` | `text` | N | 출처 manual/hook |

### `eqp_run_log` — eqp · 가동 구간
근거: 임진강 `EQP_RUN_LOG` · 니즈푸드 `EQP_STATUS` · 송월 `PRC_EQUIP_STATUS`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `equipment_id` | `bigint` | N | 설비 |
| `state` | `text` | N | 상태 가동/정지/점검/고장 — 공통코드 EQUIP_STATE |
| `started_at` | `timestamp with time zone` | N | 구간 시작 |
| `ended_at` | `timestamp with time zone` | Y | 구간 끝 |
| `source` | `text` | N | 출처 manual/collect |
| `note` | `text` | Y | 비고 |

### `eqp_check` — eqp · 점검
근거: 임진강 `EQP_CHECK` · 니즈푸드 `EQP_INSPECT`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `equipment_id` | `bigint` | N | 설비 |
| `checked_at` | `timestamp with time zone` | N | 점검 일시 |
| `item` | `text` | N | 점검 항목 |
| `result` | `text` | Y | 결과 |
| `checker` | `text` | Y | 점검자 |
| `note` | `text` | Y | 비고 |

### `eqp_fault` — eqp · 고장
근거: 임진강 · 니즈푸드 `EQP_FAULT`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `equipment_id` | `bigint` | N | 설비 |
| `occurred_at` | `timestamp with time zone` | N | 발생 시각 |
| `symptom` | `text` | N | 증상 |
| `fixed_at` | `timestamp with time zone` | Y | 복구 시각 |
| `fix_action` | `text` | Y | 조치 내용 |
| `fixed_by` | `text` | Y | 조치자 |
| `run_log_id` | `bigint` | Y | 가동 로그의 고장 구간 |

### `ifc_collect_raw` — ifc · 수집 원문 (모르는 설비도 거부 사유와 함께 남긴다)
근거: 송월 `PRC_MONITOR_DATA DAT_COLLECT_LOGS`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `equip_code` | `text` | N | 설비 코드 (메시지 그대로) |
| `ts` | `timestamp with time zone` | N | 메시지 시각 |
| `source` | `text` | N | 출처 |
| `payload` | `jsonb` | N | 메시지 원문 |
| `resend` | `boolean` | N | 재전송 여부 |
| `received_at` | `timestamp with time zone` | N | 수신 시각 |
| `rejected_reason` | `text` | Y | 거부 사유 (NULL = 정제됨) |

### `eqp_collect` — eqp · 수집값 정제본 (시계열)
근거: 니즈푸드 `EQP_COLLECT` · 임진강 `IF_SENSOR_RAW` · 송월 `PRC_MONITOR_DATA`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `equipment_id` | `bigint` | N | 설비 |
| `tag` | `text` | N | 태그 |
| `ts` | `timestamp with time zone` | N | 시각 |
| `value_num` | `numeric(18,4)` | Y |  |
| `value_text` | `text` | Y | 글자 값 |
| `raw_id` | `bigint` | Y | 원문 |

### `shp_document` — shp · 성적서 · 거래명세서 발행본 (스냅샷 — 발행 뒤 불변)
근거: 엘컴화인 성적서 · 평창 거래명세서

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `document_no` | `text` | N | 문서 번호 (유니크 · numbering DOCUMENT) |
| `doc_type` | `text` | N | 종류 성적서/거래명세서 |
| `shipment_id` | `bigint` | N | 출하 |
| `issued_at` | `timestamp with time zone` | N | 발행 시각 |
| `issued_by` | `text` | Y | 발행자 login_id |
| `snapshot` | `jsonb` | N | 발행 시점의 LOT · 검사 값 |

### `kpi_indicator` — kpi · 지표 정의
근거: 임진강 `KPI_MASTER` · 니즈푸드 `KPI_INDICATOR`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `indicator_key` | `text` | N | 지표 키 (유니크) |
| `name` | `text` | N | 이름 |
| `unit` | `text` | Y | 단위 |
| `target_value` | `numeric(18,4)` | Y |  |
| `calc_kind` | `text` | N | 산식 core:<집계 키> 또는 pack:<kpi_extra 키> |
| `visible_yn` | `character(1)` | N | 현황판 표시 여부 |
| `seq` | `integer` | N | 순서 |

### `kpi_snapshot` — kpi · 현황판 일 스냅샷 (배치만 쓴다)
근거: 임진강 `KPI_RESULT DSH_METRIC_TS`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `snap_date` | `date` | N | 날짜 |
| `indicator_key` | `text` | N | 지표 키 |
| `value` | `numeric(18,4)` | Y |  |
| `calc_at` | `timestamp with time zone` | N | 계산 시각 |

### `sys_permission` — sys · 권한 표 칸 (메뉴 × 역할 전 칸)
근거: 엘컴화인 `sys_permission` · 임진강 `SYS_ROLE_AUTH`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `role_id` | `bigint` | N | 역할 |
| `menu_code` | `text` | N | 메뉴(모듈) 코드 |
| `level` | `text` | N | 없음/조회/입력 |
| `scopes` | `text[]` | N | 입력 범위 (일반 · 입고검사 · 승인 · 지표 · 재전송 …) |

### `sys_session` — sys · 세션 (요청마다 사용자 상태와 함께 확인 · D-19)
근거: 엘컴화인(D-26 쿠키 → DB)

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `session_id` | `text` | N | 세션 ID (유니크 · 쿠키에는 이것만) |
| `user_id` | `bigint` | N | 사용자 |
| `device` | `text` | N | 채널 web/pop/mobile/board |
| `issued_at` | `timestamp with time zone` | N | 발급 시각 |
| `expires_at` | `timestamp with time zone` | N | 만료 시각 |
| `revoked_at` | `timestamp with time zone` | Y | 무효화 시각 (로그아웃 · 중지) |
| `password_version` | `bigint` | N | 로그인 때의 비밀번호 판 (password_changed_at epoch) |

### `sys_access_log` — sys · 접근 로그 (로그인 · 조회 · 변경 · 오류)
근거: 셋 다 `SYS_LOG`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `logged_at` | `timestamp with time zone` | N | 시각 |
| `user_id` | `bigint` | Y | 사용자 (선택) |
| `login_id` | `text` | Y | 로그인 ID |
| `kind` | `text` | N | 종류 login_ok/login_fail/view/change/error |
| `screen_id` | `text` | Y | 화면 ID |
| `fn_id` | `text` | Y | 기능 ID |
| `target` | `text` | Y | 대상 (테이블:번호) |
| `detail` | `jsonb` | N | 상세 (비밀번호 · 세션 ID 없음) |
| `ip` | `text` | Y | 접속 IP |
| `device` | `text` | Y | 채널 |

### `sys_number_rule` — sys · 채번 규칙 (조립식 — prefix + to_char(date_format) + seq)
근거: 엘컴화인

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `kind` | `text` | N | 종류 (유니크 · core.yaml: numbering + 팩) |
| `prefix` | `text` | N | 접두어 |
| `date_format` | `text` | N | 날짜 형식 (to_char · 비면 통산) |
| `seq_digits` | `integer` | N | 일련번호 자릿수 |
| `use_yn` | `character(1)` | N | 사용 여부 |

### `sys_number_seq` — sys · 채번 카운터 (행 잠금으로 올린다 — numbering 만 쓴다)
근거: 엘컴화인

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `kind` | `text` | N | 종류 |
| `seq_scope` | `text` | N | 날짜 부분 값 (카운터 범위) |
| `last_seq` | `integer` | N | 마지막 번호 |

### `sys_migration_log` — sys · 이관 로그
근거: 엘컴화인

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `command` | `text` | N | 명령 basics/orders/lots/history |
| `dir` | `text` | Y | 폴더 |
| `file` | `text` | Y | 파일 |
| `read_count` | `integer` | N | 읽음 |
| `inserted` | `integer` | N | 적재 |
| `updated` | `integer` | N | 갱신 |
| `skipped` | `integer` | N | 건너뜀 |
| `errors` | `integer` | N | 오류 수 |
| `error_detail` | `jsonb` | N | 오류 상세 |
| `dry_run` | `boolean` | N | 시험 실행 여부 |
| `started_at` | `timestamp with time zone` | N | 시작 |
| `ended_at` | `timestamp with time zone` | Y | 끝 |
| `run_by` | `text` | Y | 실행자 |

### `sys_backup_hist` — sys · 백업 이력
근거: 임진강 · 니즈푸드 `SYS_BACKUP_HIST`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `dump_path` | `text` | Y | 덤프 경로 |
| `row_counts` | `jsonb` | N | 테이블별 행 수 |
| `started_at` | `timestamp with time zone` | N | 시작 |
| `ended_at` | `timestamp with time zone` | Y | 끝 |
| `ok` | `boolean` | Y | 성공 여부 |
| `verified_at` | `timestamp with time zone` | Y | 복구 확인 시각 |
| `verify_ok` | `boolean` | Y | 복구 확인 결과 |
| `message` | `text` | Y | 메시지 |

### `ifc_erp_link` — ifc · ERP 연계 기록
근거: 임진강 `IF_ERP_LINK` · 송월 `DAT_IF_LOGS`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `kind` | `text` | N | 연계 종류 |
| `direction` | `text` | N | 방향 push/pull |
| `ref_table` | `text` | Y | 참조 테이블 |
| `ref_id` | `bigint` | Y | 참조 ID |
| `status` | `text` | N | 상태 대기/성공/실패/미확정 |
| `message` | `text` | Y | 메시지 |
| `linked_at` | `timestamp with time zone` | N | 시각 |

### `ifc_outbox` — ifc · 외부 전송 큐 (after_commit_* 훅이 넣고 erp.flush 가 비운다)
근거: 엘컴화인 `erp.py` 일반화 `[가설]`

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `event` | `text` | N | 사건 |
| `payload` | `jsonb` | N | 페이로드 |
| `status` | `text` | N | 상태 대기/전송/실패/미확정 |
| `attempts` | `integer` | N | 시도 횟수 |
| `last_error` | `text` | Y | 마지막 오류 |
| `sent_at` | `timestamp with time zone` | Y | 전송 시각 |
<!-- END:generated tables -->

## 5. 인덱스 · 제약 요약

- 유니크: 위 `★`. 번호 · 코드 전부.
- FK 전부 `on delete restrict`(삭제 대신 `use_yn=N`), 예외 `x_<팩>_<코어>_ext` 는 `cascade`.
- `lot_genealogy`: `(parent_lot_id)` · `(child_lot_id)` 인덱스 — 재귀 양방향.
- `eqp_collect (equipment_id, tag, ts desc)` · `pop_measure (param_key, measured_at)` · `sys_access_log (logged_at desc)`.
- 공통 `attrs` 에는 인덱스를 두지 않는다(표시용 — D-05).
