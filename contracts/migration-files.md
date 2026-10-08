# 표준 Import 파일 — 이관 배치 4종 (아키텍트 · 2026-10-09 · 초안)

> 기존 시스템(설치형 MES · 엑셀 · ERP 추출)에서 데이터를 받아 들이는 **유일한 통로**다. 실제 기존 시스템 접속은 범위 밖(`goal.md` §2.8)이고 G-C15 는 이 파일 기준으로 판정한다.
> 실행: `uv run python -m mescore.migrate <명령> --dir <폴더> [--dry-run]` (`api-contract.md` §5). 담당 개발3. 팩은 §5 매핑으로 자기 컬럼을 더한다.

## 1. 공통 규칙

- 파일은 **UTF-8 CSV**(BOM 허용), 첫 줄 헤더. 헤더 이름은 아래 표의 컬럼명과 글자 그대로. 모르는 헤더는 `attrs` 로 들어간다(`attrs.<헤더>`).
- 날짜 `YYYY-MM-DD`, 일시 `YYYY-MM-DD HH:MM:SS`(KST), 숫자는 천 단위 구분 없음, 빈 칸은 NULL.
- **멱등**: 각 파일의 `키` 열로 찾아 있으면 갱신, 없으면 적재. 두 번 돌려도 행 수 diff 0. 같은 파일 안 키 중복은 오류.
- 참조 무결성: 앞 번호 파일이 먼저. 없는 품목 · 공정 · 설비 · 거래처를 가리키면 **그 줄만 오류**로 남기고 계속한다. 오류 1건 이상이면 종료 코드 1.
- 번호(`lot_no` · `work_order_no` · `order_no`)는 **파일의 값을 그대로** 쓴다 — 이관 행은 `numbering` 을 거치지 않고 `sys_number_seq` 도 올리지 않는다. 형식 검사만(영문 대문자 · 숫자 · `-`).
- 모든 적재 행은 `created_by = 'migrate'`, `attrs.migrated_from = <파일명>`. 결과는 `sys_migration_log`(명령 · 파일 · 읽음 · 적재 · 갱신 · 건너뜀 · 오류 · 시작 · 종료).
- 시드 데이터와 섞이지 않게 예시 파일은 `migrate/examples/` 에 두고 값에 `(예시)` 를 붙인다.

## 2. B-MIG-01 기준정보 (`migrate basics`)

| 파일 | 대상 테이블 | 키 | 컬럼 |
|---|---|---|---|
| `01_items.csv` | `bas_item` | `item_code` | `item_code` `item_name` `item_type`(제품/반제품/원재료/부자재) `spec` `unit` `use_yn` |
| `02_partners.csv` | `bas_partner` | `partner_code` | `partner_code` `partner_name` `partner_type`(고객/공급/외주) `contact` `use_yn` |
| `03_processes.csv` | `bas_process` | `process_code` | `process_code` `process_name` `seq` `use_yn` |
| `04_process_params.csv` | `bas_process_param` | `process_code` + `param_key` | `process_code` `param_key` `label` `unit` `value_type`(number/text/bool/select) `min_value` `max_value` `required_yn` `source`(manual/collect) `agg`(last/avg/max/min) `seq` |
| `05_equipment.csv` | `bas_equipment` | `equip_code` | `equip_code` `equip_name` `process_code` `collect_yn` `use_yn` |
| `06_bom.csv` | `bas_bom` + `bas_bom_dtl` | `item_code` + `component_code` | `item_code` `version` `component_code` `qty` `unit` `loss_rate` |
| `07_workers.csv` | `bas_worker` | `worker_code` | `worker_code` `worker_name` `process_code` `use_yn` |
| `08_defect_codes.csv` | `bas_defect_code` | `defect_code` | `defect_code` `defect_name` `process_code` `use_yn` |
| `09_codes.csv` | `bas_code` | `group_code` + `code` | `group_code` `code` `code_name` `seq` `use_yn` |

## 3. B-MIG-02 수주 · 작업지시 (`migrate orders`)

| 파일 | 대상 테이블 | 키 | 컬럼 |
|---|---|---|---|
| `11_orders.csv` | `ord_order` + `ord_order_dtl` | `order_no` + `line_no` | `order_no` `partner_code` `order_date` `due_date` `line_no` `item_code` `qty` `unit` `status` |
| `12_work_orders.csv` | `job_work_order` | `work_order_no` | `work_order_no` `item_code` `process_code` `equip_code` `plan_qty` `unit` `plan_date` `order_no` `line_no` `status`(대기/진행/마감/취소) |

## 4. B-MIG-03 LOT · 계보 (`migrate lots`)

| 파일 | 대상 테이블 | 키 | 컬럼 |
|---|---|---|---|
| `21_lots.csv` | `lot` | `lot_no` | `lot_no` `kind`(MATERIAL/PRODUCT/SHIPMENT 또는 팩 kind) `item_code` `work_order_no` `process_code` `equip_code` `qty` `unit` `insp_status` `made_at` `partner_code`(원재료 공급처) |
| `22_genealogy.csv` | `lot_genealogy` | `parent_lot_no` + `child_lot_no` + `relation` | `parent_lot_no` `child_lot_no` `relation`(코어 5종 또는 팩 등록 관계) `qty` `linked_at` |

- 계보 파일은 **`lineage.link` 를 통해** 적재한다(직접 INSERT 금지 — `check_pack` · G-C05). 순환 · 자기 참조 · 모르는 relation 은 그 줄 오류.
- 모든 LOT 이 있어야 계보를 넣을 수 있으므로 `21` 을 전부 적재한 뒤 `22` 를 돈다.

## 5. B-MIG-04 실적 · 검사 이력 (`migrate history`)

| 파일 | 대상 테이블 | 키 | 컬럼 |
|---|---|---|---|
| `31_work_results.csv` | `pop_work_result` | `work_order_no` + `started_at` | `work_order_no` `process_code` `equip_code` `worker_code` `started_at` `ended_at` `good_qty` `scrap_qty` `unit` `product_lot_no` |
| `32_measures.csv` | `pop_measure` | `work_order_no` + `started_at` + `param_key` | `work_order_no` `started_at` `param_key` `value` `unit` |
| `33_inspections.csv` | `qua_inspection` + `qua_insp_item` | `lot_no` + `inspected_at` + `item_key` | `lot_no` `insp_type`(입고/공정/최종) `inspected_at` `inspector` `judgement`(합격/불합격/조건부) `item_key` `item_value` `item_judgement` |
| `34_shipments.csv` | `shp_shipment` | `shipment_no` | `shipment_no` `partner_code` `ship_date` `order_no` `status` `approved_at` `approved_by` `ship_lot_no`(출하 LOT 번호, `21` 에 있어야 한다) |

- 실적의 `product_lot_no` 는 `21` 에 있어야 한다(없으면 그 줄 오류). 실적 → LOT 의 `투입` 계보는 `22` 에서 온다 — 실적 파일이 계보를 만들지 않는다.
- 검사 결과의 `judgement` 는 `lot.insp_status` 를 갱신한다(최신 검사 기준).

## 6. 팩 매핑 (`packs/<팩>/migrate.yaml`)

```yaml
rename:                       # 기존 시스템 헤더 → 표준 헤더
  품목코드: item_code
  롤번호: lot_no
kinds:                        # 기존 구분값 → lot.kind
  인쇄롤: ROLL
relations:                    # 기존 관계명 → 코어/팩 relation
  분할: 슬리팅
ext:                          # 표준 밖 헤더 → 확장 테이블 컬럼 (attrs 대신)
  lot: { 폭: x_printfilm_lot_ext.width_mm }
```

- 팩 매핑이 없으면 표준 헤더만 읽고 나머지는 `attrs`. 매핑으로 코어 테이블의 **표준 밖 컬럼**에 쓰는 것은 불가(`check_pack`).
- 근거 사업 이관(`spec.md` §13)은 각 사업 DB 에서 이 4종 파일을 **뽑는** 스크립트(`packs/<팩>/migrate_export.py`)를 먼저 만들고, 그 파일을 표준으로 적재해 행 수 · 계보 행 수를 대조하는 순서다.
