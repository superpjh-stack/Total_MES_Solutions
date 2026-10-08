# printfilm 훅 사양 — `hooks.py` 의 설계서 (기획자2 · 2026-10-09)

> 서명은 `pack-contract.md` §5, 호출 지점은 `contracts/interfaces.md` §9. 전부 **동기 · 코어 트랜잭션 안 · 거부는 `HookError`(422 `hook_rejected`)**, 그 밖 예외는 500(삼키지 않는다). 코어 테이블 쓰기는 `pack.yaml: write_scope.hooks = [lot]` 안에서만(`lineage` 경유). 팩 테이블 `x_printfilm_*` 는 자유.
> 근거: 엘컴화인 `function-list.md`(F-POP-02 · F-JOB-01 · F-SHP-02 · F-SHP-05) · `decisions.md`(D-13 · D-16 · D-17 · D-208 · D-305) · `interfaces.md` §4 · §7.

## 0. 훅 6 한눈에

| 훅 | 코어 시점 | 하는 일 | 쓰는 곳 |
|---|---|---|---|
| `on_result_closed` | F-POP-03 작업 종료, 생산 LOT 생성 **후** | 생산 LOT → `ROLL` kind · ext 행(`process_type=인쇄`) | `lot`(`lineage.retag`) · `x_printfilm_lot_ext` |
| `validate_job_work_order` | F-JOB-01 · 02 저장 직전 | 판사양 · 아니록스 · 잉크조성 코드 검증 · 수주 상세 필수 · ext upsert | `x_printfilm_job_work_order_ext` |
| `on_work_order_created` | F-JOB-01 저장 후 | (ext 는 validate 가 했다) 없음 — 서명만 둔다 | — |
| `on_lot_created` | `make_product_lot` · `split` · `merge` · F-MAT-01 후 | 없음 — 라벨은 응답의 링크로(브라우저 인쇄 · D-04). 서명만 | — |
| `validate_shipment` | F-SHP-07 승인 직전 | 불합격 롤 · 다른 Job 의 롤 · 롤이 아닌 LOT 거부 | 읽기만 |
| `kpi_extra` | `stats.indicators` 조회 시 | 평균 ΔE · 불합격 롤 수 · 재고 롤 수 | 읽기만 |

`validate_lot` · `on_inspection_judged` · `on_collect` · `after_commit_*` 는 두지 않는다 — 엘컴화인에 해당 규칙이 없다(수집 없음 · ERP 501).

---

## 1. `on_result_closed(cur, result, user)` — 인쇄 롤 만들기

- **언제**: 코어 F-POP-03 이 측정값 저장 → `lineage.make_product_lot`(번호 `LOT_PRODUCT` = `R…`, `pop_input` → `투입` 계보) → collect 측정값 채움까지 끝낸 **뒤** 같은 `tx` 에서 부른다. `result["product_lot"]` 에 생산 LOT 행(`id` · `lot_no` · `kind=PRODUCT` · `process_id` · `equipment_id` · `qty` · `attrs`)이 있다.
- **한다**:
  1. `lineage.retag(cur, result["product_lot"]["id"], "ROLL")` — kind 를 `ROLL`(base PRODUCT)로. 번호는 바뀌지 않는다(이미 `R…`).
  2. `insert into x_printfilm_lot_ext (lot_id, process_type, equipment_id, slit_seq) values (…, '인쇄', result["equipment_id"], null)` — 공정 구분 인쇄. `on conflict (lot_id) do update`(재호출 멱등).
  3. `attrs.length_m` · `width_mm` 는 코어가 POP-02 의 `ui.attrs_fields("lot")` 에서 받아 `make_product_lot(attrs=)` 로 이미 넣었다 — 훅이 다시 쓰지 않는다(D-502).
- **거부(HookError)**: 실적의 공정이 `attrs.process_type != '인쇄'` 이면 `t("인쇄 공정의 작업 실적만 롤을 만듭니다")` — 후가공 · 슬리팅은 POP 이 아니라 X-RLL 화면에서 만든다(엘컴화인 P5 = 인쇄 롤만, D-13). 투입 0건은 코어가 이미 422.
- **검증**: `tests/test_hooks.py::test_result_closed_retags_roll` — 종료 뒤 `lot.kind='ROLL'` · `kind_base='PRODUCT'` · ext 1행 · `lot_genealogy(relation=투입)` 행 수 = `pop_input` 수.

## 2. `validate_job_work_order(cur, row, user)` — Job 의 인쇄 기준 · 수주

- **언제**: F-JOB-01 등록 · F-JOB-02 수정 저장 직전. `row` 는 저장될 값(`attrs` 포함 — `plate_code` · `anilox_code` · `ink_code`). 등록 때는 `row["id"]` 가 없고 수정 때는 있다.
- **검증** (전부 `HookError`, `fields=[{name, label: t(…), reason}]`):
  - `row["order_dtl_id"]` 가 비면 `t("수주 상세를 골라야 합니다 — 고객 · 납기는 수주에서 옵니다")` (D-506).
  - `attrs.plate_code` 가 있으면 `x_printfilm_plate(plate_code, use_yn='Y')` 에 있어야 한다. 없으면 `t("없는 판사양 코드")`, 미사용이면 `t("미사용 판사양")`. `anilox_code` · `ink_code` 도 같게. 셋 다 비워도 된다(엘컴화인 F-JOB-01).
  - 품목이 `item_type != '제품'` 이면 거부(엘컴화인 F-JOB-01 "품목은 제품만").
- **쓴다** (CR-5 전까지 — 검증 훅이 팩 테이블을 쓰는 예외, README D-5nn): 수정 때 `row["id"]` 로 `x_printfilm_job_work_order_ext` 를 `upsert`(FK 는 코드로 찾은 id). 등록 때는 id 가 아직 없으므로 `on_work_order_created` 가 한다(§3).
- **검증**: `tests/test_hooks.py::test_job_plate_code_unknown_422` · `test_job_without_order_422`.

## 3. `on_work_order_created(cur, wo, user)`

- F-JOB-01 저장 후. `wo["id"]` · `wo["attrs"]` 로 `x_printfilm_job_work_order_ext(work_order_id, plate_id, anilox_id, ink_formula_id)` 1행 insert(코드 → id 는 §2 가 이미 검증했다). 셋 다 비면 행을 넣지 않는다.
- 다른 일은 없다 — 소요량 · 생산 LOT 생성 없음(CR-1).

## 4. `on_lot_created(cur, lot, user)`

- 아무 일도 하지 않는다. 라벨은 응답의 라벨 링크(F-POP-03 "라벨 출력 안내" · F-X-RLL-01/02/04 응답)로 사용자가 브라우저 인쇄한다(엘컴화인 D-04 · D-206). 프린터 규격이 정해져 `adapters/label_html.py` 가 ZPL 드라이버로 바뀌면 여기서 `PrintAdapter.send` 큐를 넣는다 — 그때는 `after_commit_lot_created` 로 옮긴다(트랜잭션 밖).
- 함수는 두되 본문은 `return`. (`hooks.py` 에 없어도 no-op 이지만 "의도적으로 비웠다" 를 적어 둔다.)

## 5. `validate_shipment(cur, shipment, lots, user)` — 출하 승인 직전

- **언제**: F-SHP-07. `lots` = 이 출하에 스캔된 LOT 행 목록(`id` · `lot_no` · `kind` · `work_order_id` · `insp_status`).
- **거부(HookError)** — 하나라도 걸리면 승인 실패, 메시지에 롤 번호 목록:
  1. `kind != 'ROLL'` 인 LOT 이 있으면 `t("롤이 아닌 LOT 은 출하할 수 없습니다")`.
  2. **최신 검사가 불합격**인 롤(`lot.insp_status = '불합격'`) → `t("불합격 롤이 있어 승인할 수 없습니다")` — 스캔 뒤 불합격 판정이 들어온 경우(엘컴화인 D-305 · S2). 스캔 시점의 불합격 · 미검사는 코어 F-SHP-05 가 이미 422(D-504).
  3. 롤들의 `work_order_id` 가 **서로 다르면** `t("출하 LOT 하나에는 한 Job 의 롤만 담습니다")` (엘컴화인 D-16 — 스캔 때 막는 훅이 없어 승인 때 막는다 · CR-3).
  4. `lots` 가 비면 코어가 이미 422 — 훅은 보지 않는다.
- **쓰지 않는다**. COA 번호 채번도 하지 않는다(발행은 F-SHP-09 · D-505).
- **검증**: `tests/test_scenario_ship.py::test_block_failed_roll`(`gates.yaml` S2) · `test_block_mixed_job`.

## 6. `kpi_extra(frm, to) -> list[dict]` — 인쇄 지표

반환 `[{"key", "label", "value", "unit"}]`. 읽기만. 값이 없으면 `value: None`(화면 `미수집`). 산식은 엘컴화인 D-25 · D-301 을 코어 테이블로 옮긴 것 — QA2 가 자기 SQL 로 대조한다(G-C10).

| key | label | 산식 | unit |
|---|---|---|---|
| `avg_delta_e` | 평균 ΔE (검사) | `qua_insp_item(item_key='delta_e')` 중 `qua_inspection.inspected_at::date` 가 기간 안인 행의 `avg(value_num)`. 검사 행 수 기준(롤별 최신만 세지 않는다 · D-301) | — |
| `fail_roll_count` | 불합격 롤 수 | 기간 안 판정된 검사 중 `judgement='불합격'` 인 **롤**(`lot.kind='ROLL'`) 의 distinct 수 | 개 |
| `stock_roll_count` | 재고 롤 수 | `v_lot_state(state='재고')` ∩ `lot.kind='ROLL'` 의 수(기간 무관 — 현재) | 개 |
| `splice_count` | splice 건수 | 기간 안 `lot_genealogy(relation='splice')` 의 distinct `child_lot_id` 수 | 건 |

- 기간 경계는 코어 `stats` 와 같은 규칙(날짜 양 끝 포함 · DB 세션 시간대).
- 지표 정의(`kpi_indicator.calc_kind='pack:avg_delta_e'` 등)는 **시드로** 넣는다 — 권한 표에서 `kpi` 가 조회 ×4 라 화면 등록은 아무도 못 한다(D-510). 시드 파일: `seed/indicators_example.csv`(개발2 가 만든다 — 열 `indicator_key,name,unit,target_value,calc_kind,visible_yn,seq`, target 은 `(미확정)` 빈칸).

---

## 7. 훅이 **하지 않는** 것 (코어가 한다 · 혼동 방지)

| 규칙 | 누가 |
|---|---|
| 합격 LOT 만 투입 · 소진 · 미검사 LOT 투입 422 | 코어 F-POP-06 · `lineage.assert_usable` |
| 스캔 시점 불합격 · 미검사 · 이미 출하 · 재고 아님 422 | 코어 F-SHP-05 · `lineage.ship` |
| Job 행 잠금(`for share`) · 마감 · 취소 동시성 | 코어 `job` · `pop` |
| 순환 · 자기 참조 · 같은 화살표 중복 | 코어 `lot_genealogy` 트리거 · `lineage.link` |
| 작업지시 → 생산 LOT 번호 | `make_product_lot` 안의 `numbering.next("LOT_PRODUCT")` |
| 검사 판정 → `lot.insp_status` | 코어 F-QUA-05 |
