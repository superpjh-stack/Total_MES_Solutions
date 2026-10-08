# printfilm 확장 스키마 — `schema_ext.sql` 의 설계서 (기획자2 · 2026-10-09)

> 규칙은 `pack-contract.md` §3 · §4 R2 · R3: 접두 `x_printfilm_` · 공통 컬럼 5(`id bigserial pk` · `created_at` · `created_by` · `updated_at` · `updated_by`) + `attrs jsonb not null default '{}'` · 코어 테이블 `ALTER` · 트리거 0 · 1:1 ext 는 코어 `id` 가 PK 겸 FK(`on delete cascade`), 그 밖 FK 는 `on delete restrict`.
> 컬럼은 엘컴화인 `contracts/db-schema.md` §4 에서 옮겼다(가설 컬럼 D-18 포함). 규격 **값**은 없다. 아래 표에서 공통 컬럼 5 + `attrs` 는 적지 않는다. `★` 유니크.
> 테이블 **8** = `gates.yaml: tables: 8`.

## 1. 인쇄 기준 (E4 · 엘컴화인 D1 의 4 테이블) — `prt`

### `x_printfilm_plate` ← `plate_spec` 판사양
| 컬럼 | 타입 | NULL | 뜻 (엘컴화인 컬럼) |
|---|---|---|---|
| `plate_code` ★ | text | N | 판 코드 |
| `plate_name` | text | N | 판명 |
| `item_id` → `bas_item` | bigint | Y | 대상 품목(제품) |
| `color_count` | integer | Y | 도수 (가설 D-18 · 값 미확정) |
| `spec_note` | text | Y | 사양 메모 |
| `use_yn` | char(1) | N | 기본 `Y` |

### `x_printfilm_anilox` ← `anilox` 아니록스
| 컬럼 | 타입 | NULL | 뜻 |
|---|---|---|---|
| `anilox_code` ★ | text | N | 아니록스 코드 |
| `anilox_name` | text | N | 명칭 |
| `line_count` | numeric(10,2) | Y | 선수 (가설 · 값 미확정) |
| `cell_volume` | numeric(10,3) | Y | 셀 용적 (가설 · 값 미확정) |
| `note` | text | Y | 비고 |
| `use_yn` | char(1) | N | |

### `x_printfilm_ink_formula` ← `ink_formula` 잉크조성
| 컬럼 | 타입 | NULL | 뜻 |
|---|---|---|---|
| `ink_code` ★ | text | N | 잉크 코드 |
| `ink_name` | text | N | 잉크명 |
| `color_name` | text | Y | 색 이름 |
| `target_l` · `target_a` · `target_b` | numeric(7,2) | Y | 기준 색상값 Lab (가설 — ΔE 가 Lab 차이) |
| `note` | text | Y | |
| `use_yn` | char(1) | N | |

### `x_printfilm_ink_formula_component` ← `ink_formula_component` 조성 행 (1:N)
| 컬럼 | 타입 | NULL | 뜻 |
|---|---|---|---|
| `ink_formula_id` → `x_printfilm_ink_formula` | bigint | N | `on delete cascade`(F-X-PRT-11 이 함께 지운다) |
| `seq_no` | integer | N | 행 순번. `(ink_formula_id, seq_no)` ★ |
| `component_name` | text | N | 성분명 |
| `ratio_pct` | numeric(6,3) | N | 비율 % · CHECK `> 0 and <= 100` |

## 2. 조색 기록 (E4 · 엘컴화인 D4) — `clr`

### `x_printfilm_color_record` ← `color_record`
| 컬럼 | 타입 | NULL | 뜻 |
|---|---|---|---|
| `work_order_id` → `job_work_order` | bigint | N | **Job 참조 필수**(엘컴화인 `job_id`) · `on delete restrict` |
| `ink_formula_id` → `x_printfilm_ink_formula` | bigint | Y | 기준 잉크조성(F-X-PRT-11 삭제 422 의 참조) |
| `color_name` | text | N | 색 이름 |
| `seq_no` | integer | N | 차수. `(work_order_id, color_name, seq_no)` ★ |
| `color_l` · `color_a` · `color_b` | numeric(7,2) | Y | 색상값 Lab (가설) |
| `note` | text | Y | |
| `recorded_at` | timestamptz | N | 기록 일시 · 기본 `now()` |

### `x_printfilm_color_record_mix` ← `color_record_mix` 배합비 행 (1:N)
| 컬럼 | 타입 | NULL | 뜻 |
|---|---|---|---|
| `color_record_id` → `x_printfilm_color_record` | bigint | N | `on delete cascade` |
| `seq_no` | integer | N | `(color_record_id, seq_no)` ★ |
| `component_name` | text | N | 성분명 |
| `ratio_pct` | numeric(6,3) | N | 배합비 % · CHECK `> 0 and <= 100`. 합 = 100 은 라우터(F-X-CLR-02)가 검사 |

## 3. 코어 1:1 확장 (E2 — 검색 · FK 용. `attrs` 는 표시용 D-05)

### `x_printfilm_lot_ext` ← `roll` 의 검색 · FK 컬럼 (코어 `lot` 1:1)
| 컬럼 | 타입 | NULL | 뜻 |
|---|---|---|---|
| `lot_id` → `lot` | bigint | N | **PK 겸 FK** · `on delete cascade`. `lot.kind='ROLL'` 인 행에만 있다 |
| `process_type` | text | N | 공정 구분 `인쇄` · `후가공` · `슬리팅`(CHECK). F-X-RLL-03/05 의 WHERE — 그래서 ext(attrs 아님) |
| `equipment_id` → `bas_equipment` | bigint | Y | 가공 설비(엘컴화인 `roll.equipment_id`). 코어 `lot.equipment_id` 와 중복 — `lineage.split/merge` 가 설비를 받지 못해서(CR-2 · D-514). CR-2 뒤 제거 |
| `slit_seq` | integer | Y | 슬리팅 분할 순번 1..N(슬리팅 롤만) |

- 만드는 곳: `on_result_closed`(인쇄) · F-X-RLL-01/02(후가공) · F-X-RLL-04(슬리팅). 지우는 곳 없음(롤은 지우지 않는다).
- `roll` 의 나머지 컬럼은 코어 `lot` 에: `roll_no → lot_no` · `job_id → work_order_id` · `work_result_id` · `produced_at → made_at` · `produced_by → created_by` · `length_m · width_mm → attrs`(D-502) · `job_lot_id → (CR-1)`.
- 인덱스: `(process_type)`.

### `x_printfilm_job_work_order_ext` ← `job` 의 인쇄 기준 FK 3 (코어 `job_work_order` 1:1)
| 컬럼 | 타입 | NULL | 뜻 |
|---|---|---|---|
| `work_order_id` → `job_work_order` | bigint | N | **PK 겸 FK** · `on delete cascade` |
| `plate_id` → `x_printfilm_plate` | bigint | Y | 판사양 · `on delete restrict`(F-X-PRT-03 삭제 422 의 근거) |
| `anilox_id` → `x_printfilm_anilox` | bigint | Y | 아니록스 · restrict |
| `ink_formula_id` → `x_printfilm_ink_formula` | bigint | Y | 잉크조성 · restrict |

- 만드는 곳: `validate_job_work_order`(수정) · `on_work_order_created`(등록) — `hooks.md` §2 · §3. 입력칸은 `job_work_order.attrs.plate_code` 등(`pack.yaml: attrs`), 저장은 여기 FK — attrs 는 WHERE 에 쓰지 않는다.
- Job 하나에 판사양 · 아니록스 · 잉크조성 각 하나(엘컴화인 db-schema §7 — 다색 인쇄의 색별 지정은 현업 양식 뒤, D-18).

## 4. 두지 않는 것

| 엘컴화인 | 이유 |
|---|---|
| `job_lot` 생산 LOT | 코어 `job_lot` 과 뜻이 다르고 등록 기능이 없다 → CR-1 · D-503. 팩 테이블로 만들면 화면(JOB-02)을 팩에 둘 자리가 없다(모듈 `job` 은 코어) |
| `roll_genealogy` 의 `parent_material_lot_id/parent_roll_id/child_roll_id/child_shipment_id` 4컬럼 | 코어 `lot_genealogy(parent_lot_id, child_lot_id)` 두 컬럼 + `kind` 로 같은 뜻 |
| `shipment.coa_no · coa_issued_at` | 코어 `shp_document` |
| `inspection.delta_e` · `inspection_defect.position` | E3 검사 항목(`qua_insp_item`) · `qua_defect.position` |
| `material_lot.insp_*` | 코어 `qua_inspection(insp_type=입고)` |
| 뷰 `v_roll_state` · `v_material_lot_stock` | 코어 `v_lot_state` · `v_lot_stock` — 팩 뷰를 만들지 않는다 |

## 5. `schema_ext.sql` 작성 메모 (개발2)

- 파일 머리에 `-- @table x_printfilm_plate | PACK | 판사양` 식 태그(코어 `schema.sql` 규약과 같게) — `make contracts` 가 렌더본을 찍는다.
- `create table if not exists` 가 아니라 코어와 같은 `create table`(스키마 재생성은 `make db-schema` 가 한다).
- 코어 테이블에 대한 `alter table` · `create trigger` · `create view` 0 — `check_pack` R2.
- `check_schema` 기대값: `x_printfilm_` 테이블 **8**.
