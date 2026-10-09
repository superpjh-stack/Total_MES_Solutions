# progress-dev2 — 개발2 (현장 실행 / `mat` `pop` `qua` `eqp` + `lineage` · `printing` · `collect` · `measure`)

검증된 것만 적는다. 형식 `| 항목 | 실측 | 검증 방법 |`. 비밀 값은 적지 않는다.

## §1 공표 — 공용 모듈 시그니처 (R1 · 2026-10-09)

### `app/lineage.py` — 계보 (`lot_genealogy` 에 쓰는 유일한 곳 · 번호는 `numbering` 뿐)

```python
from mescore.app import lineage
# 상수: INPUT PRODUCE SPLIT MERGE SHIP = 투입 생산 분할 합병 출하 · MATERIAL PRODUCT SHIPMENT · IN_STOCK CONSUMED SHIPPED = 재고 소진 출하 · FORWARD BACKWARD
# 쓰기 — 전부 conn.tx() 의 cur. by = login_id · user = rbac.User(훅 validate_lot/after_save_lot/on_lot_created 에 넘김 · 없으면 None). 검증 실패 422
lineage.link(cur, parent_id, child_id, relation, *, by, qty=None, at=None) -> int   # at = linked_at(없으면 now() · 회전 4). 자기참조 · 순환 · 모르는 relation · 중복 (부모,자식,관계) 422. relation_base 저장
lineage.assert_usable(cur, lot_ids) -> None                                         # LOT 잠금(id 오름차순) 뒤 PRODUCT 재고 · MATERIAL 합격/조건부 + 소진 전 · 잔량 > 0 (회전 7). 아니면 422
lineage.remaining(cur, lot_id, for_update=True) -> Decimal | None                     # 회전 7 — 쓰기 경로의 유일한 잔량(= v_lot_stock 문장 · 자식 계보 + 열린 투입). LOT 수량 NULL → None
lineage.lock_lots(cur, lot_ids) -> None                                              # 회전 7 — LOT 행 for update · id 오름차순 한 문장
lineage.merge_parents_of(cur, parent_ids, relation="합병", *, work_result_id=None) -> list[Node]   # 회전 7 — 종료 합병 옵션 부모 검증(잠금 · 자기 투입 LOT 422 · 잔량 > 0 · 투입 중 아님). F-POP-03 이 ended_at 전에 부른다
lineage.make_material_lot(cur, *, item_id, qty, unit, by, partner_id=None, lot_no=None, made_at=None, attrs=None, insp_status="미검사", note=None, kind="MATERIAL", user=None) -> dict
lineage.make_product_lot(cur, *, work_result_id, by, kind="PRODUCT", qty=None, unit=None, attrs=None, parent_id=None, merge_parent_ids=None, merge_relation="합병", user=None) -> dict
#   pop_input(취소 제외) → 투입 N줄 · parent_id → 생산 1:1 · merge_parent_ids(재고 생산 LOT ≥ 1) → 새 LOT 에 base 합병 화살표(별도 합병 LOT 없음 · 회전 4 · F-POP-03 폼 merge_lot_ids)
lineage.split(cur, *, parent_id, count, by, qtys=None, relation="분할", kind=None, process_id=None, equipment_id=None, attrs=None, user=None) -> list[dict]   # D-503 · 코어 분할 N ≥ 2 · 팩 분할 계열 N ≥ 1 · 수량 합 ≤ 잔량 · 자식 insp_status 상속
lineage.merge(cur, *, parent_ids, by, qty=None, relation="합병", kind=None, process_id=None, equipment_id=None, attrs=None, user=None) -> dict            # D-503 · 코어 합병 N ≥ 2 · 팩 합병 계열 N ≥ 1
lineage.ship(cur, *, shipment_id, lot_id, by, user=None) -> int        # 개발3 F-SHP-05. 출하 LOT 없으면 LOT_SHIPMENT 채번. 등록 상태 출하만 · 이미 출하/소진/불합격 · 잔량 ≤ 0 · 투입 중 422 (회전 7 · LOT 잠금 · 화살표 qty = 잔량)
lineage.unship(cur, *, shipment_id, lot_id, by, user=None) -> int      # 개발3 F-SHP-06. 출하 화살표 삭제. 담기지 않은 LOT 422
lineage.consume_material(cur, *, work_result_id, material_lot_id, qty, by, unit=None) -> int   # pop_input + 원재료면 mat_stock_trx(투입 −qty) · mat_stock. 미검사/불합격/소진/잔량 부족/종료 실적 422
lineage.cancel_consume(cur, *, input_id, by) -> int                     # 종료 전만 · 재고 되돌림
lineage.retag(cur, lot_id, kind, *, by=None) -> dict                    # 팩 kind (base 는 등록값)
lineage.inherit_insp(statuses) -> str   # split/merge 자식 — 전부 합격 → 합격 · 불합격 포함 → 불합격 · 미검사 포함 → 미검사 · 그 밖 → 조건부 (회전 4)
lineage.shipment_lot(cur, shipment_id) -> dict | None
# 읽기 — 어떤 테이블에도 쓰지 않는다. 선택 인자 cur 로 같은 트랜잭션 안에서도 읽는다
lineage.resolve(no, cur=None) -> Node | None · search(text, limit=50) · state(lot_id) -> str(404) · node(lot_id) · nodes(ids) · genealogy_rows(ids)
lineage.parents_of(lot_id) / children_of(lot_id) -> list[Edge] · trace_backward(lot_id) / trace_forward(lot_id) -> Trace   # with recursive 한 문장
lineage.relation(name) -> Relation(name, base) · relation_of_base(name, base) · lot_kind(kind) -> LotKind(kind, base, label) · kind_label(kind)
Node(id, no, kind, kind_label, item, state, work_order_no, qty, unit, kind_base, item_id, item_code, insp_status, work_order_id, shipment_id, remain_qty, made_at)
Edge(genealogy_id, parent, child, relation, relation_base, qty, depth)   Trace(start, direction, edges).nodes() .by_kind() .materials() .shipments() .stock() .products()
```
- 분할 · 합병 API: `POST /pop/result/{id}/split`(count · qtys 쉼표 · lot_id 생략 시 그 실적의 생산 LOT · relation) · `POST /pop/result/{id}/merge`(lot_ids 쉼표 — id 또는 LOT 번호 · qty · relation). 권한 F-POP-03 (D-12).
- 상태 · 잔량은 저장하지 않는다(`v_lot_state` · `v_lot_stock`). 코어 관계 5 는 relation = relation_base. 팩 관계는 base 로 동작.

### `app/collect.py` — 수집 (쓰는 테이블 `ifc_collect_raw` · `eqp_collect` 뿐 · 제어 0)

```python
collect.CollectMessage(equip_code, ts, tags, source="gateway", resend=False) · CollectMessage.from_payload(dict)  # 형식 오류 422
collect.receive(cur, msg) -> ReceiveResult(raw_id, duplicate, unknown_tags, saved)   # 멱등 (equip_code, ts, source) · 모르는 설비 = 거부 기록(자동 커밋) + 422 · hook("on_collect")(cur, raw, None)
collect.latest(equip_id) -> {"equipment_id", "ts", "tags": {tag: {"value", "ts"}}} | None
collect.series(equip_id, tag, frm, to) -> [{"ts", "value"}]
collect.aggregate(equip_id, tag, frm, to, agg="last"|"avg"|"max"|"min") -> float | None
collect.known_tags() · collect.counts(frm=None, to=None)   # IFC-01 용 {total rejected resent last_at}
```
- **개발3 `routers/ifc.py` F-IFC-01**: `auth.require_collect_token(request)` → `msg = collect.CollectMessage.from_payload(body)` → `with conn.tx() as cur: r = collect.receive(cur, msg)` → `200 {"ok": true, "raw_id": r.raw_id, "duplicate": r.duplicate, "unknown_tags": list(r.unknown_tags)}`.

### `app/printing.py` — 출력 (라벨 · 바코드는 여기뿐)

```python
printing.barcode_svg(text, *, height=40) -> Markup   # Code128 B/C 자동 · viewBox "0 0 {quiet10+모듈+quiet10} 100" · preserveAspectRatio none · crispEdges · aria-label=값 · A-Z 0-9 - 밖 ValueError · 24자 초과 ValueError
printing.render_print(request, template, data, *, screen_id) -> HTMLResponse|JSON   # templates/print/<template>.html · ctx = data + barcode_svg + printed_at + printed_by
printing.label_for(lot_id, *, size="100x50") -> dict   # {lot_id lot_no kind kind_base kind_label item_code item_name spec qty unit made_at insp_status state work_order_no partner_name attrs[{label value}] size}. 404
printing.shipment_label_for(shipment_id) -> dict       # {shipment_no partner_code partner_name ship_date status approved_at approved_by lot_count total_qty unit order_no shipment_lot_no}
printing.PrintJob(kind, template, data, copies=1, printer=None) · PrintResult(sent, printer, message) · PrintAdapter().send(job) · printing.adapter()   # 팩 adapters.printing 의 adapter()/ADAPTER
```
- 양식 4 (`templates/print/`): `label_lot.html` data `{"labels": [label_for(id)], "size": "100x50"|"50x30", **label}` · `label_shipment.html` data = `shipment_label_for(id)` · `work_order.html` data `wo{work_order_no item_code item_name spec unit process_name equipment_code equipment_name plan_qty plan_date status plan_no order_no partner_name due_date bom_version note created_by}` · `bom_rows[{seq item_code item_name required_qty unit lot_no}]` · `params[{label unit min_value max_value required_yn source}]` · `barcode`(선택 — 없으면 양식이 `barcode_svg(wo.work_order_no)` 로 그린다) · `document.html` data `doc{document_no doc_type issued_at issued_by}` · `snapshot{shipment columns lots summary}`(디자이너3 표 그대로).
- **개발1 F-JOB-07**: 위 `wo` · `bom_rows` · `params` · `barcode` 키와 맞다 — 그대로 `printing.render_print(request, "work_order", data, screen_id="JOB-03")`.

### `app/measure.py` + `templates/home/_measure.html` — 측정값 (G-C24)

```python
measure.params_for(process_id) -> list[dict]   # use_yn=Y · seq. + field("m_<key>") required is_collect tag choices range_text
measure.parse_form(params, form) -> (values{key: {value_num, value_text}}, errs[{name label reason}])   # 필수 누락 · 형식 오류 → errs (라우터 422). collect 칸은 읽지 않는다
measure.record(cur, work_result_id, params, values, *, by) -> list[dict]        # 범위 이탈 저장 + deviated
measure.fill_collect(cur, result_row, params, *, by) -> list[dict]             # 구간(started_at~ended_at · 같은 설비) collect.aggregate(agg). 수신 0 → value NULL 행
measure.values_of(work_result_id) -> {key: pop_measure 행} · measure.deviated(param, v) · measure.plan_fields(qua_insp_plan rows)(i_<key>) · display_value(row)
{% import "home/_measure.html" as mf %}  {{ mf.measure_fields(params, values, latest) }}  {{ mf.measure_table(params, values) }}
```

### 개발2 파일 (소유 목록 밖에 더한 것)
`app/measure.py` · `app/routers/_dev2.py`(라우터 공용 — main 이 include 하지 않는다) · `tests/_dev2_helpers.py`(로그인 클라이언트 · 픽스처 · 개발1 `numbering.py` 가 없을 때만 쓰는 채번 대체 — 지금은 쓰이지 않는다) · `tests/test_pop_scenario.py`.

## §2 실측 (2026-10-09)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| G-C06 계보 10행 (함수) | `lot_genealogy` {투입 3, 합병 2, 분할 3, 출하 2} = **10행** · relation = relation_base · 실적 ↔ 생산 LOT | `uv run pytest -q tests/test_lineage_scenario.py` 7 passed |
| G-C06 계보 10행 (API) | 입고 2 → 입고검사 합격 → 시작 → 투입 스캔 → 종료 ×2 → 합병 → 분할 → `lineage.ship` ×2 = 10행 · 역추적 ①② · 정방향 ③ 재고 · 라벨 4종 렌더 · 바코드 스캔 왕복 | `tests/test_pop_scenario.py` 1 passed |
| G-C07 추적 | 역방향 출하 LOT → 원재료 ①② (9 edges) · 정방향 원재료 ① → 생산 ①② → 합병 → 분할 ①②③ → 출하(③ 재고) · 임의 분기 5단 · **깊이 20 · 분기 100 (edges 2000): 정방향 0.035s · 역방향 0.007s** | `tests/test_lineage_scenario.py -s -k depth_20` |
| 계보 지킴이 | 자기참조 · 순환 · 모르는 relation · 중복 · 소진 LOT 분할 · 재출하 · 1개 합병 · 잔량 초과 분할 · 미검사/불합격/소진 투입 전부 422 | 〃 `test_guards_422` |
| G-C24 측정값 | 선언 3(필수 · 범위 · collect) → 폼 칸 3(collect 는 읽기 전용) · 필수 누락 422 「필수 측정값이 비었습니다」 + fields · 범위 이탈 저장 + deviated · collect 구간 avg 채움(수신 0 → NULL · 422 아님) · 이탈 collect 도 deviated | `tests/test_measure.py` 4 passed |
| 수집 | 멱등(duplicate) · 모르는 설비 422 + 거부 기록 · unknown_tags · latest/series/aggregate(last avg max min) · 수신 0 None | `tests/test_collect.py` 4 passed |
| 출력 | Code128 체크섬 · B/C 전환 · SVG 규격 · 허용 밖 글자 7종 ValueError · 어댑터 기본 sent=False · label_for 404 | `tests/test_printing.py` 9 passed |
| 기능 38 | F-MAT 11 · F-POP 8 · F-QUA 11 · F-EQP 8 전부 라우트 등록 + `@pytest.mark.fn` | `make check-trace` 「기능 132 ↔ 라우트 PASS 132/132」 · 표식 38/38 |
| 화면 17 | MAT-01~05 · POP-01~04 · QUA-01~04 · EQP-01~04 전부 200 · placeholder **0** | `make check-routes` (잔여 1 은 CMN-04 아키텍트) |
| 스캔 422 재렌더 | MAT-02 · POP-01 · POP-03 · POP-04 · QUA-02 — `?no=` 없는 번호 → **그 화면 422** (JSON code=validation_error + screen_id · HTML `data-scan` 1 · `#scan-result`) · 폼 POST 422 → 303 | 각 test_*_api |
| 권한 | 관리자(조회) 쓰기 403 · 품질 입고검사만 · 생산/현장 입력 · EQP-04 pop 채널 403 | 〃 |
| 금지어 | `src/mescore/` 위반 0 · t() 누락 0 | `make check-terms` PASS |
| 코어 해시 | 내 파일 변동 0 (변동은 개발3 `migrate/importer.py` · 개발1 `tools/import_design.py`) | `core_hash.py --check` |
| pytest | **185 passed · 1 failed**(`test_arch_smoke::test_channel_layout_and_channel_rule` — 개발3 KPI-01 현황판 HTML 이 `body.ch-board` 를 안 쓴다 · 내 파일 아님) | `uv run pytest -q` |
| 시드 | `seed_dev2` 2회 → 입고 추가 0 · 수집값 추가 0 (멱등) · ISSUE 채번 규칙 1 · 검사 계획 5 · 원재료 LOT 합격 2(`M-EX-0001/0002`) | `uv run python -m mescore.db.seed_dev2` ×2 |

## §3 요청

- **아키텍트**: ① `core.yaml: numbering` 에 `ISSUE { prefix: Q, date: YYMMDD-, digits: 3, label: 이상 번호 }` 추가(D-202 — 지금은 `seed_dev2` 가 행을 넣는다). ② `_macros.html` 에 `ui.measure_fields` 를 두려면 `{% from "home/_measure.html" import measure_fields %}` 위임 한 줄(D-205 — 서명은 `(params, values, latest)`). ③ `app.js` S-01~S-14 중 미구현분(S-01 둘 이상 콘솔 오류 · S-10 결과 배너 1초 · S-12 503 disabled) — 템플릿은 `#scan-result.err/.ok` · `data-scan` 하나로 맞춰 두었다. ④ `screen-map.md` §3 에 `app/measure.py` · `routers/_dev2.py` · `tests/_dev2_helpers.py` · `tests/test_pop_scenario.py` 를 개발2 로, `print/document.html` 은 내가 디자이너3 필드로 만들었으니 개발3 과 조정. ⑤ `interfaces.md` §4 · §5 · §6 · §2 매크로 줄을 코드대로 고쳤다(D-203 · D-204 · D-205).
- **개발1**: 작업지시서는 `print/work_order.html` 이 `wo · bom_rows · params · barcode` 키 그대로 받는다(위 §1). `pop_work_result.worker_id` 는 `sys_user.worker_id` 를 기본으로 쓴다.
- **개발3**: ① `routers/ifc.py` F-IFC-01 → `collect.CollectMessage.from_payload` + `collect.receive(cur, msg)`(§1 수신 예). ② `routers/shp.py` F-SHP-05/06 → `lineage.ship/unship(cur, shipment_id=, lot_id=, by=, user=)` · 출하 라벨 → `printing.render_print(request, "label_shipment", printing.shipment_label_for(id), screen_id="SHP-02")` · 성적서 → `render_print("document", {"doc": …, "snapshot": …}, screen_id="SHP-04")`. ③ `tests/test_arch_smoke::test_channel_layout_and_channel_rule` — KPI-01 HTML 에 `class="ch-board"` 가 없다.
- **QA2**: 계보 행 수 대조는 `lineage.genealogy_rows(ids)` 또는 SQL. 테스트가 만든 LOT · 실적은 DB 에 남는다(유니크 키는 채번 · `T-…` 코드).

## §3-B 요청 (웨이브 B · printfilm · 2026-10-09) — 코어 변경 요청 (`goal.md` §4.3 · 아키텍트가 `decisions.md` D-5nn 으로)

| # | 어느 확장 지점이 왜 모자란가 | 코어의 어디를 어떻게 — 다른 팩도 쓰는가 | 팩의 임시 처리 |
|---|---|---|---|
| **CR-9 팩 시드** | E1 `seeds[]` 는 `codes* · items* · processes* · equipment* · partners*` 만 받고(`seed_core.seed_pack` 그 밖 SystemExit) `processes*` 의 `attrs.*` 열을 버린다. 팩 테이블(`x_<팩>_*`) · 불량코드 · 지표(`kpi_indicator`) 시드를 넣을 길이 없다. foodservice(`kpi_indicators.csv` · `bom_example.csv`) · kimchi 도 같다 | `seed_core`: ① `seeds[]` 항목을 `{file, table, key}` 로도 받아 `x_<팩>_*` · `kpi_indicator` · `bas_defect_code` 를 멱등 upsert ② 모든 기준정보 파일의 `attrs.<키>` 열을 attrs 로 ③ `process_params · inspection_items` 를 `seeds[]` **뒤에**(지금은 공정이 없으면 `bas_process_param.process_id` NOT NULL 로 실패) ④ `USERS` 를 역할 코드에서 유도(`QA` 고정 → 팩 역할 `QC` 의 계정 없음) | `seed/seed_pack.sql`(`\copy` 로 같은 CSV) 을 **`make db-seed` 앞에** 돌린다 · `qc` 는 F-SYS-01 로 |
| **CR-8 스냅샷 훅** | E5 에 발행 스냅샷을 보강할 자리가 없다(`snapshot_extra`) | `shp.py` F-SHP-09: `packs.hook("snapshot_extra")(cur, snapshot, lots)` 또는 스냅샷에 `lot.attrs` 포함 — kimchi(염도) · foodservice 도 쓴다 | `validate_shp_document` 가 `row["snapshot"]` 을 제자리에서 보강(코어가 같은 객체를 저장) |
| **CR-3 스캔 시점 훅** | `validate_lot_ship(cur, shipment, lot, user)` 없음 | `lineage.ship` 직전 한 자리 — kimchi 금속검출 미통과 스캔 거부도 같은 자리 | 승인 때 `validate_shipment` 로 일괄 |
| **CR-10 G-P03 도구** | `check_trace` 는 `design_source` 가 있으면 `미검증`(import_design 출력 미연동) · `import_design.py` 는 `design.json` 만(설계도 HTML · README §1 매핑표 · `--pack` 없음) | `check_trace --pack` 이 `import_design --mapping packs/<팩>/README.md` 를 부르거나 매핑표 마크다운(§1.1)을 직접 읽어 고아 수를 판정 | README §1.1(32행 · 고아 0 · 밖 1 = JOB-02/CR-1) 수동 |
| **CR-11 R9 범위** | 팩이 선언한 역할(`QC`) · 권한(관리자 `pop` 조회 · `eqp` 숨김) · 필수 attrs · 훅(`on_result_closed` 인쇄 공정만)이 코어 테스트의 전제(`qa` 계정 · 코어 권한 표 · 예시 공정으로 POP 종료)와 어긋난다 → `MES_PACK=printfilm uv run pytest tests/` 57 failed · 6 errors | R9 를 "코어 테스트는 **코어 단독** 전건 + 팩 폴더를 지운 채 전건" 으로 좁히거나, 코어 테스트가 `packs.current()` 의 역할 · 권한 · 시드 공정을 읽게 한다 | 코어 단독 통과만 보장 |
| CR-4 lookup attrs | 그대로(코드 입력 + 훅 검증) | | |
| CR-1 · CR-6 | 1차 범위 밖(D-503) · 이관 단계 | | |
| SYS-04 t() | 접근 로그 화면이 기능명(계약 문구 '작업지시 등록' 등)을 `t()` 없이 찍는다 — G-P05 는 통과(같은 화면에 치환어도 있어서)하지만 엄격한 검사에서는 노출 | 개발1: `t(fn.name)` | 팩 테스트는 SYS-04 를 게이트 규칙으로만 본다 |

## §4 웨이브 B 실측 — printfilm (2026-10-09)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| **S1 계보 10행** | `lot_genealogy` = **투입 3 · splice 2 · 슬리팅 3 · 출하 2 = 10행** · `relation_base` 투입 3 · 합병 2 · 분할 3 · 출하 2 · ROLL 6 · ext 6(인쇄 2 · 후가공 1 · 슬리팅 3 · slit_seq 1,2,3) · 역추적 출하 LOT → M①② (edges 9) · 정방향 M① edges 9 · S③ 재고 · S①② 출하 · R①② F 소진 · 번호 M/J/R 형식 | `MES_PACK=printfilm uv run pytest -q packs/printfilm/tests/test_scenario_lineage.py::test_ten_rows` 1 passed |
| S2 불합격 롤 출하 금지 | 스캔: 불합격 · 미검사 **422 validation_error**(코어) · 승인: 재검사 불합격 → **422 hook_rejected** 메시지에 롤 번호 · `shp_shipment.status=등록` · 출하 계보 1행 그대로 · 다른 Job 의 롤 승인 422 hook_rejected "한 Job 의 롤만" | `test_scenario_ship.py` 3 passed |
| S3 COA | 번호 `C`+YYMMDD-+3 · snapshot.lots 2 각 `{delta_e, judgement, defects, length_m, width_mm, process_type=슬리팅, inspected_at, slit_seq}` · `shipment.shipment_lot_no` · 출력 제목 COA · 바코드 = 출하 LOT 번호 · '성적서' 노출 0 · 미승인 422 · 승인 뒤 새 검사 422 · 재발행 새 번호 · 이전 스냅샷 바이트 동일 | `test_scenario_coa.py` 1 passed |
| 훅 6 | `on_result_closed` ROLL retag + ext · 인쇄 아닌 공정 422 hook_rejected(전체 되돌림) · `validate_job_work_order` 수주 상세 필수 · 제품만 · 없는/미사용 코드 422 · ext upsert 등록 · 수정 · 셋 다 비면 행 없음 · `validate_shipment` · `kpi_extra` 4 키(`pack:*` 지표 4 시드) | `test_hooks.py` 5 passed |
| 기능 24 | F-X-PRT-01~12 · CLR-01~05 · RLL-01~07 전부 엔드포인트 + `@pytest.mark.fn` · `check_trace` 「팩 화면 7/7 · 기능 24/24」 · 고아 라우트 0 | `test_prt_api.py` 12 · `test_clr_api.py` 5 · `test_rll_api.py` 7 passed |
| 팩 pytest | **39 passed** (9 파일) | `MES_PACK=printfilm uv run pytest -q packs/printfilm/tests` |
| 코어 단독 pytest | **239 passed · 2 failed** — `tests/test_job_work_orders.py::{test_list_filters_and_progress_is_computed, test_status_board_today_week_and_drilldown}`(개발1 · 내 파일 아님) | `MES_PACK= uv run pytest -q tests/` (`make gate` 의 G-C21 행과 같다) |
| 팩을 올린 코어 pytest (R9) | 178 passed · 57 failed · 6 errors — 사유 §3-B CR-11 | `MES_PACK=printfilm uv run pytest -q tests/` |
| **G-P01** | `check_pack`: R2·R3 PASS(코어 DDL 0 · 생성 9 · 접두 밖 0) · R4~R6 PASS(모듈 15 · 화면 58 · 역할 4 · 용어 7) · R7 PASS(scope `lot` · 밖 0) · R8 PASS(직접 쓰기 0) · D-05 PASS(집계 0 · WHERE 0) · R10 WARN(덮어쓴 3 = README) · **R1 FAIL — 코어 해시 바뀜 27 · 생김 1**: `src/mescore/` 의 변동은 전부 다른 담당의 **커밋되지 않은 작업 트리**(`app.js` · `mobile.css` · `pop.css` · `templates/*` · `tools/gate.py` …, `git diff --name-only src/mescore` 45 파일). **내가 `src/mescore/**` 에 쓴 파일 0** (`git status packs/printfilm` 만 내 변경) | `MES_PACK=printfilm make check-pack` · `git status` |
| G-P02 | PASS — 화면 7/7 · 기능 24/24 · 테이블 8/8 · 다른 접두 0 · 공통 컬럼 빠짐 0 | `make gate` |
| G-P03 | **미검증** — `design_source` 설계도 HTML · `import_design` 미연동 (CR-10). 매핑표 README §1.1 32행 고아 0 | 〃 |
| G-P04 | **PASS** — 시나리오 3 · 실행 3 · 실패 0 | 〃 |
| G-P05 | **PASS** — 화면 57 · terms 키 7 · 치환 안 된 노출 0 | 〃 · `check_terms --pack` |
| G-P06 | 미검증 (사람 실측) | |
| 팩 DB · 시드 | `mes_printfilm_db` 테이블 60(52 + 8) · 뷰 3 · 권한 칸 60 · 역할 4(ADMIN PROD QC FIELD) · 채번 10(J L M R S C SO + 코어 X N + ISSUE) · 공정 구분 3 · 판사양 2 · 아니록스 2 · 잉크조성 2 · 조성 행 3 · 불량코드 4 · 지표 pack:* 4 · **`seed_pack.sql` → `db-seed` 2회 행 수 diff 0** | `psql -f packs/printfilm/seed/seed_pack.sql && MES_PACK=printfilm make db-seed` ×2 · `conn.table_counts()` diff |
| 화면 캡처 | `outputs/e2e/printfilm/` 14장 — a0 메인(메뉴 순서 실적 현황 → 영업관리 → Job 관리 → 자재 · 입고 → 조색 기록 → 생산 실적 → 후가공 · 슬리팅 롤 이력 → 품질 → 출하 → LOT 추적 → 기준정보 → 인쇄 기준 → 시스템 → 인터페이스 · 설비 없음) · a2 판사양 · a4 Job · a10 조색 · a11 POP Roll · a13 롤 라벨 · a14 후가공 · a15 슬리팅 라벨 3장 · a16 롤 이력 · a21 출하 승인 · a22 COA · a24/a25 역·정방향 추적(모바일 390px) · a28 지표 | 서버 8042 · `MES_PACK=printfilm` |

게이트 원문(`make gate` · printfilm 블록):
```
G-P01  격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0  FAIL  검사 7 · 통과 못한 2 — R1 코어 파일 해시 변동 0: [printfilm] 바뀜 27 · 생김 1 · 없어짐 0 ['src/mescore/app/static/app.js', 'src/mescore/app/static/mobile.css', 'src/mescore/app/static/pop.css'] / R10 코어 템플릿 덮어쓰기 목록 (README.md 에 적는다): [printfilm] 덮어쓴 템플릿 ['print/document.html', 'print/label_lot.html', 'print/work_order.html']
G-P02  규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml                  PASS  검사 2 전부 PASS
G-P03  추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0                          미검증  [printfilm] 추적표: design_source ../lcomFine MES/엘컴화인_MES_설계도 복사본.html · import_design 매핑 판정은 그 도구의 출력으로 (미구현)
G-P04  시나리오 — gates.yaml: scenarios 재현                      PASS  [printfilm] 시나리오 3 · 실행 3 · 실패 0
G-P05  용어 — terms 키 치환 안 된 노출 0                             PASS  [printfilm] 화면 57 · terms 키 7 · 치환 안 된 노출 0
```

미확정으로 둔 값(NULL · 화면 `미확정`): 도수 · 선수 · 셀 용적 · 기준 Lab · ΔE 상한(`inspection_items.csv` standard `(미확정)`) · 인쇄 속도 단위 · 슬리팅 분할 수 상한 · 프린터 규격(브라우저 인쇄) · LOT_SHIPMENT 형식(코어 X · D-501). 결정 후보 D-501~D-514 는 README §6 그대로 아키텍트에게.

## §5 회전 4 (2026-10-09) — 요청 처리 (개발3 §3-5 · 6 · 15 · 16 · 18 · 19 · 디자이너2 이식 요청 4 · 5 · 6) · printfilm 우회 제거

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| `lineage.link(..., at=None)` | `at` → `lot_genealogy.linked_at`(`coalesce(at, now())`) — 이관 22 의 원본 시각 | `tests/test_lineage_scenario.py::test_link_at_keeps_given_time` |
| 팩 관계 N ≥ 1 | `merge` — 코어 `합병` N ≥ 2 · 팩 base 합병 N ≥ 1(기존 확인) · **`split` 도 대칭** — 코어 `분할` N ≥ 2 · 팩 base 분할 N ≥ 1(부분 분할) | `test_pack_relation_merge_and_split_allow_one`(관계 표 monkeypatch) |
| `insp_status` 상속 | `lineage.inherit_insp(statuses)` — 전부 합격 → 합격 · 불합격 하나라도 → 불합격 · 미검사 하나라도 → 미검사 · 그 밖(합격+조건부) → 조건부 · 부모 하나면 그 값. `split` · `merge` 자식에 적용. 불합격을 이은 LOT 출하 422 | `test_inherit_insp_rule`(7) · `test_split_merge_children_inherit_insp_status` |
| `make_product_lot(merge_parent_ids=, merge_relation="합병")` | 재고 생산 LOT 1개 이상 → 새 실적 LOT 에 base 합병 화살표(별도 합병 LOT 없음 · "투입 + 합병 → 한 LOT"). 소진 · 원재료 · 분할 관계 · 중복 422. **F-POP-03 폼 `merge_lot_ids`**(id · LOT 번호 쉼표) · `merge_relation` · 응답 `merged` | `test_make_product_lot_with_merge_parents` · `tests/test_pop_api.py::test_result_end_with_merge_parents_makes_one_lot` |
| 코어 계보 10행 | 그대로 {투입 3 · 합병 2 · 분할 3 · 출하 2} | `test_core_scenario_is_exactly_10_rows` |
| `collect.counts(None, None)` | None · '' 경계는 조건에서 뺀다(파라미터 `is null` 비교 없음) · 정수. 이 환경에서는 재현되지 않았으나(캐스트 있음) 경로 자체를 없앴다 | `tests/test_collect.py::test_counts_with_none_and_bounds` |
| POP-02 | `worker_id_default` = 로그인 사용자 `sys_user.worker_id`(템플릿 `checked`) · `equipment_options` = 지시 공정 설비(`bas_equipment.process_id`) + 지시 지정 설비 | `test_start_screen_defaults_worker_and_filters_equipment_by_process` |
| POP-03 | `last_qty` · `last_unit` = 취소되지 않은 마지막 투입 | `test_input_screen_last_qty_skips_canceled` |
| MAT-01 `?item_code=` | 원재료 · 부자재 품목 → 등록 폼 품목 칸(`item_id_default` · `scan_item`) · 없는 품목(제품 포함) **MAT-01 422 재렌더** · 스캔칸 1 | `tests/test_mat_api.py::test_receipts_scan_entry_by_item_code` |
| EQP-01 `?equip_code=` | 그 설비 카드 맨 앞 + `.card.sel`(`selected_id`) · 없는 설비 **EQP-01 422 재렌더** · 스캔칸 1 · `now` = `"YYYY-MM-DD HH:MM"` 문자열 | `tests/test_eqp_api.py::test_status_scan_entry_by_equip_code` |
| QUA-02 검사 공정 | GET `?process_id=` · POST `process_id` — 기본 LOT 공정 · 고르면 그 공정의 계획 항목(`insp_process_id` · `process_options`) · 없는 공정 422 | `tests/test_qua_api.py::test_inspection_process_choice_defaults_to_lot_process` |
| `interfaces.md` §4 · §6 | `link(at=)` · `split` N 규칙 · `make_product_lot(merge_parent_ids, merge_relation)` · `inherit_insp` · 상속 규칙 문단 · `collect.counts` | `contracts/interfaces.md` |
| printfilm 우회 제거 | ① `screens[].channels` → 기획 코드 `[web]` · `[pop]`(733074f 정규화) ② `terms` `실적: 작업 실적` · `추적: LOT 추적` 복원(겹말 방지) ③ `seeds[]` 기획 10 파일 + `{file, table, key}` 4 + `kpi_indicators_example.csv`(지표 4 를 SQL 에서 CSV 로) · **`seed/seed_pack.sql` 삭제**(6c77eb9 CR-9). `menus.add[].owner` 는 유지(pack-contract §2 서식) | `MES_PACK=printfilm uv run pytest -q packs/printfilm/tests` **39 passed** · `MES_PACK=printfilm make pack-check` OK 용어 9 |
| printfilm 시드 | 빈 스키마 → `MES_PACK=printfilm make db-seed` 한 번에 판사양 2(품목 FK 2) · 조성 행 3 · 지표 pack:* 4 · 공정 구분 3 · 불량 분류 4 · 권한 60 · 계정 4(qc 포함) · **2회 행 수 diff 0** | `conn.table_counts()` 비교 |
| pytest (코어) | **277 passed** (내 새 테스트 18) · 단독 흔들림 1 — `test_trc_api::test_backward_…` 행 수 diff(같은 DB 에 다른 담당이 동시에 씀 · 단독 3 passed) | `uv run pytest -q` |
| 라우트 · 용어 | placeholder 0 · RBAC 위반 0 · G-C03 PASS · G-C23 PASS(위반 0 · t() 누락 0) | `make check-routes` · `make check-terms` |
| G-P01 R1 | FAIL — 코어 해시 바뀜 61(이번 회전 전 담당 미커밋 · 내 `lineage` · `collect` · 라우터 4 포함) → 아키텍트 `make core-hash` | `MES_PACK=printfilm make check-pack` |

### §5-3 요청 (회전 4)

- **아키텍트**: ① `make core-hash` 재기록(내 코어 파일 `app/lineage.py` · `collect.py` · `routers/{pop,mat,qua,eqp}.py` · 템플릿 `pop/{result,inputs}` · `mat/receipts` · `eqp/status` · `qua/inspections`). ② 개발3 §3-17(PRODUCT LOT 부분 투입 — `v_lot_state` 가 자식 계보 하나로 `소진`)은 `views.sql` 몫이다 — 팩 base 분할 N = 1(부분 분할)도 같은 뷰 규칙에 걸린다(부모가 곧바로 `소진`). `remain_qty > 0` 이면 재고로 보는 규칙이면 lineage 는 그대로 맞는다.
- **기획(printfilm)**: `terms` 복원으로 메뉴 rename 이 `t()` 를 한 번 더 거쳐 「생산 작업 실적 (POP)」 · 「작업 실적 현황」 이 된다(겹말은 아님). pack-contract §2 대로 rename 을 최종 이름(`작업 실적 (POP)` 등)으로 쓸지 판단.
- **디자이너2**: MAT-01 · EQP-01 POP 화면에 `ui.scan_box` 한 줄씩 넣었다(요청 4 — S-01 하나 유지) · EQP-01 카드 `.card.sel` · POP-02 종료 폼에 `merge_lot_ids` 칸 한 줄 · QUA-02 검사 공정 GET 폼(`#insp-process-form`) — 모양은 그대로 두었으니 다듬어 달라.
- **개발3**: §3-5 `link(at=)` · §3-6 `counts` · §3-15 팩 분할 N ≥ 1 · §3-16 상속(이제 kimchi `age` 의 `update lot set insp_status` 를 뺄 수 있다) · §3-18 QUA-02 `?process_id=` / 폼 `process_id` · §3-19 F-POP-03 `merge_lot_ids`(+ `merge_relation`) — 전부 반영. §3-9 링크 쿼리 이름(`QUA-02 ?no=` · `MAT-03 ?no=`)은 그대로 맞다.

## §6 회전 5 (2026-10-09) — QA 결함 수정

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| **DEF-QA2-001 중대** 반제품 이중 스캔 | `lineage.consume_material` 이 `_input_available` 로 잔량을 직접 센다(LOT 행 `for update` · 뷰를 거치지 않음): MATERIAL = qty − Σ 취소 아닌 pop_input · PRODUCT 등 = qty − Σ 자식 계보 qty − Σ **열린** pop_input(취소 아님 · 실적 미종료 — 종료 뒤엔 계보 투입 행으로 세므로 두 번 세지 않음). 생산 LOT 20 → E 15(열림) → F 15 **422** · F 5 200 · F 1 422 · E 취소 뒤 다시 15 200 · 둘 다 종료 → v_lot_stock 소비 20 · 잔량 0 · 소진. 아키텍트 `v_lot_stock` 변경과 독립(어느 쪽이든 두 번 빼지 않음) | `tests/test_pop_api.py::test_product_lot_open_inputs_count_against_remain`(수정 전 코드로 FAIL 확인) · QA2 `check_data.py` 「반제품 투입 — 종료 전 이중 스캔」 **PASS** |
| **DEF-QA2-004 경미** 꺼진 선언의 지난 기록 | `measure.params_with_recorded(process_id, values)` — 지금 선언 + `pop_measure` 에만 남은 키(라벨은 param_id 선언 → 같은 공정 · 키 선언 → 키 그대로) · `recorded_only=True`. POP-02 `?id=` 가 이것을 `params` 로 넘긴다(JSON · HTML 표). `_measure.html measure_fields` 는 `recorded_only` 를 건너뛴다(새 입력 칸 없음) | `tests/test_measure.py::test_turned_off_declaration_keeps_past_values_visible` · QA2 `check_data` 참고 행 **PASS** |
| DEF-QA1-004 경로 키 404 | 아키텍트 `main.py` 일괄 처리 확인 — 내 라우트 13(F-MAT-02 · 07 · F-POP-03/04/05/07 · F-QUA-02/05/09/10 · F-EQP-06 · split · merge) `abc` → **404**. 내 라우터 손대지 않음 | TestClient 호출 · printfilm `check_screens` G-C02 156/156 |
| **DEF-QA1-009** printfilm 지표 정의 | `seed/permissions.csv` `kpi,ADMIN,입력,지표` · README §6 D-510 근거(엘컴화인 실적 현황 "조회" 는 집계 · 현황판 — `지표` 범위는 F-KPI-06 · 07 만 연다) · `scenarios.md` 권한 표. `mes_printfilm_db` 의 그 칸 1행을 같은 값으로 갱신(시드는 기존 칸을 덮어쓰지 않는다 — `--reset` 대신 그 칸만) | `packs/printfilm/tests/test_hooks.py::test_kpi_extra_metrics`(admin can_write True · prod False) · check_screens G-C17 60/60 |
| **printfilm G-P05** | `menus.rename` = 최종 이름: `job: Job 관리` · `pop: 작업 실적 (POP)` · `kpi: 작업 실적 현황`(엘컴화인 메뉴명에 terms 적용). 노출 **180 → 2** — 남은 2 는 CMN-02 메인 카드 출처 문구 `stats.TODAY_COUNT_SOURCES`(「오늘 계획 작업지시」 · 「오늘 시작 실적」 · t() 없음 · 개발3/디자이너3). attrs 라벨 노출은 printfilm 에서 0 | `MES_PACK=printfilm uv run python src/mescore/tools/check_screens.py` · `test_terms_and_pack.py` 메뉴 이름 단언 |
| D-37 목록 정렬 | `?sort=` — MAT-01(`date no item partner qty lot`) · MAT-03(`made no item qty remain state insp`) · QUA-02(`at type lot item judgement`) · QUA-04(`at no status process`) · EQP-02(`at equip item result`) · EQP-03(`at equip fixed hours`) · `-` 내림 · 모르는 열 422 · ctx `sort`. 기본 정렬은 그대로 | `tests/test_eqp_api.py::test_list_sort_param_d37` |
| pytest (코어) | **292 passed · 1 failed** — `test_arch_smoke::test_core_has_no_forbidden_terms`(`app/packs.py:583 조리` 아키텍트 작업 중 · `static/app.js:216 splice` 디자이너) · 내 파일 아님 | `uv run pytest -q` |
| 팩 pytest | printfilm **39 passed** | `MES_PACK=printfilm uv run pytest -q packs/printfilm/tests` |
| 계보 10행 | `tests/test_lineage_scenario.py` 18 passed (10행 유지) · QA2 G-C06 PASS | |
| 라우트 · 용어 | check-routes PASS(56/56 · placeholder 0 · RBAC 위반 0) · check-terms G-C23 FAIL 2(위 두 파일 · 내 것 0) · t() 누락 0 | `make check-routes` · `make check-terms` |

### §6-1 요청 (회전 5)
- **개발3 / 디자이너3**: `app/stats.py: TODAY_COUNT_SOURCES` 문구를 화면에 낼 때 `t()` — printfilm G-P05 남은 2(「오늘 계획 작업지시」 · 「오늘 시작 실적」).
- **아키텍트**: ① `make core-hash` 재기록(내 `lineage.py` · `measure.py` · `routers/{mat,pop,qua,eqp}.py` · `home/_measure.html`) ② 팩 attrs 라벨 `t()` — printfilm 은 지금 노출 0 이지만 다른 팩 몫 ③ `v_lot_stock` 열린 투입 규칙은 lineage 와 독립이라 어느 쪽을 택해도 두 번 빼지 않는다 ④ `interfaces.md` §6 에 `measure.params_with_recorded` 한 줄.
- **디자이너2**: POP-02 측정값 표에 `recorded_only` 행(꺼진 선언의 기록)이 섞여 나온다 — 구분 표시가 필요하면 `p.recorded_only` 로. 목록 6 화면에 `?sort=` 가 생겼다(ctx `sort`) — 머리글 링크는 모양 쪽 판단.

## §7 회전 7 (2026-10-09) — 계보 무결성 (QA2 DEF-QA2-007 · 008 · 009 · WARN 2)

규칙 전문은 `contracts/interfaces.md` §4 「잔량 · 잠금 규칙 (회전 7)」. 시그니처 추가 3(`remaining` · `lock_lots` · `merge_parents_of`) — §1 갱신. `_merge_parents` · `_input_available` 은 지웠다(대체).

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| **DEF-QA2-007 중대** 종료 합병 옵션 자기 투입 LOT | `merge_parents_of(work_result_id=)` 가 그 실적의 취소 아닌 pop_input LOT 과 겹치면 **422**(`merge_lot_ids`). F-POP-03 은 `ended_at` 을 쓰기 **전에** 부르고, `make_product_lot` 이 같은 tx 에서 다시 본다. QA2 재현(20 → 15 투입 → 같은 실적 종료 `merge_lot_ids`) → 422 · 종료 되돌림 · 다시 종료 뒤 소비 15 · 잔량 5 | `test_pop_api.py::test_end_merge_option_own_input_lot_is_422_before_end` · `test_lineage_scenario.py::test_end_merge_option_rejects_own_input_lot` · QA2 check_data 행 **PASS** |
| **DEF-QA2-008 중대** 잔량 0 재사용 | 잔량을 `lineage.remaining` 하나로 — `assert_usable` · `consume_material` · `split` · `merge` · `merge_parents_of` · `make_product_lot(parent_id=)` · `ship` 전부 잔량 > 0(수량 시 ≥ 수량) 아니면 422. **수량 없는 투입 = 잔량 전부**(그 값을 pop_input.qty 로 · 잔량 0 이면 422). LOT **통째** 쓰기(합병 · 출하 · 생산 부모 · 종료 합병 · 수량 다 주지 않은 분할)는 열린 투입이 있으면 잔량이 남아도 422. 7경로(투입 수량 없음/1 · 분할 수량 없음/수량 · 합병 · 종료 합병 · 출하) 전부 422 · 잡은 실적 종료 뒤 자식 {투입 1} | `test_lineage_scenario.py::test_open_input_zero_remaining_blocks_every_path[7]` · `test_whole_lot_paths_wait_for_open_input` · `test_qtyless_input_takes_whole_remaining` · `test_pop_api.py::test_open_input_zero_remaining_lot_refused_by_api_paths` · QA2 행 **PASS** |
| **DEF-QA2-009 경미** 동시성 | `lock_lots` — `select id from lot where id = any(…) order by id for update` 를 판정 **전에**: consume_material · split · merge · merge_parents_of/make_product_lot(실적 → LOT → 지시) · ship(출하 헤더 → LOT). 그 뒤 문장으로 상태 · 잔량을 다시 읽는다. 화살표 qty 도 잠근 뒤 잔량 | `test_lineage_scenario.py::test_concurrent_writes_never_go_negative[투입‖분할 · 분할‖분할 · 투입‖출하 · 합병‖투입]` — 두 커넥션 · 스레드 2 · B 는 A 커밋까지 대기 → 422 · 잔량 ≥ 0. QA2 동시성 3쌍 **PASS**(B 가 A 커밋 전 끝남 False 3/3) |
| WARN ① 불합격 → 종료 합병 | `make_product_lot` 새 LOT 은 `미검사`, 합병 · 생산 부모에 `불합격` 이 있으면 **`불합격`**(출하 422) | `test_end_merge_option_inherits_fail` · QA2 참고 행: 200 · insp_status **불합격**(행 판정은 200 이면 WARN 으로 찍는 검사기 기준 그대로 WARN) |
| WARN ② 부분 분할 | 결정: **수량을 모두 준 분할은 남는 양을 부모 잔량으로 둔다**(20 → 5+5 → `remaining` 10). lineage 는 반영. 상태는 `v_lot_state` 몫 — 지금 뷰는 분할 화살표 하나로 `소진` 이라 QA2 참고 행은 아직 WARN(잔량 10 · 소진) | `test_partial_split_keeps_remaining_on_parent` (lineage 잔량만 단언) · 아키텍트 요청 ② |
| QA2 `check_data.py`(코어 · mes_qa2_db 새로) | **행 41 · FAIL 0 · WARN 2** · 37s(회전 6: FAIL 3). G-C04 새 공격 3행 전부 PASS. WARN 2 = 위 참고 ① ② | `uv run python src/mescore/tools/check_data.py` |
| pytest (코어) | **322 passed** · 0 failed | `uv run pytest -q` |
| 팩 pytest | printfilm **39** · foodservice **19** · kimchi **26** passed | `MES_PACK=<팩> uv run pytest -q packs/<팩>/tests` |
| 계보 10행 | `test_core_scenario_is_exactly_10_rows` PASS(10행 유지) · `test_lineage_scenario.py` 35 passed | |
| 라우트 · 용어 | check-routes G-C03 PASS 56/56 · placeholder 0 · RBAC 위반 0 · check-terms G-C23 PASS(위반 0 · t() 누락 0) | `make check-routes` · `make check-terms` |

### §7-1 요청 (회전 7)
- **아키텍트**: ① `make core-hash` 재기록(`app/lineage.py` · `routers/pop.py`) ② **`v_lot_state` 부분 분할** — PRODUCT 의 `분할` 화살표가 **전부 qty 를 가지면** 「투입」 과 같이 잔량으로 판정(잔량 > 0 → 재고). qty NULL 분할 · 합병 · 생산은 지금대로 소진(이 셋은 lineage 가 화살표 qty = 잔량으로 적어 잔량 0 이 된다). D-503 「분할 계보가 생기면 부모는 소진」 문장 대체 · `db-schema.md` §3.4 문장도 ③ `interfaces.md` §1 잠금 순서 줄에 「LOT 행은 id 오름차순 한 문장(`lineage.lock_lots`)」 을 더해 달라(§4 에는 적었다).
- **개발3**: `routers/shp.py: _assert_remaining` 은 이제 `lineage.ship` 이 같은 검사(잠금 뒤 `remaining` ≤ 0 → 422 · 열린 투입 → 422)를 하므로 지워도 된다(주석대로). kimchi S4 는 부분 분할 결정이 뷰에 반영되면 `split(count=1, qtys=[600])` 만으로 K1 잔량 400 재고가 된다(DEF-QA2-010 선택지).
- **QA2**: 참고 ① 행은 응답 200 이면 WARN 으로 찍힌다 — 이제 새 LOT 이 `불합격` 을 잇는 것이 설계다(§4). 판정 기준을 insp_status 로 바꿀지 판단.

