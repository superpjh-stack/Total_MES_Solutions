# progress-dev2 — 개발2 (현장 실행 / `mat` `pop` `qua` `eqp` + `lineage` · `printing` · `collect` · `measure`)

검증된 것만 적는다. 형식 `| 항목 | 실측 | 검증 방법 |`. 비밀 값은 적지 않는다.

## §1 공표 — 공용 모듈 시그니처 (R1 · 2026-10-09)

### `app/lineage.py` — 계보 (`lot_genealogy` 에 쓰는 유일한 곳 · 번호는 `numbering` 뿐)

```python
from mescore.app import lineage
# 상수: INPUT PRODUCE SPLIT MERGE SHIP = 투입 생산 분할 합병 출하 · MATERIAL PRODUCT SHIPMENT · IN_STOCK CONSUMED SHIPPED = 재고 소진 출하 · FORWARD BACKWARD
# 쓰기 — 전부 conn.tx() 의 cur. by = login_id · user = rbac.User(훅 validate_lot/after_save_lot/on_lot_created 에 넘김 · 없으면 None). 검증 실패 422
lineage.link(cur, parent_id, child_id, relation, *, by, qty=None) -> int            # 자기참조 · 순환 · 모르는 relation · 중복 (부모,자식,관계) 422. relation_base 저장
lineage.assert_usable(cur, lot_ids) -> None                                         # PRODUCT 재고 · MATERIAL 합격/조건부 + 소진 전. 아니면 422
lineage.make_material_lot(cur, *, item_id, qty, unit, by, partner_id=None, lot_no=None, made_at=None, attrs=None, insp_status="미검사", note=None, kind="MATERIAL", user=None) -> dict
lineage.make_product_lot(cur, *, work_result_id, by, kind="PRODUCT", qty=None, unit=None, attrs=None, parent_id=None, user=None) -> dict   # pop_input(취소 제외) → 투입 N줄 · parent_id → 생산 1:1
lineage.split(cur, *, parent_id, count, by, qtys=None, relation="분할", kind=None, process_id=None, equipment_id=None, attrs=None, user=None) -> list[dict]   # D-503 · N ≥ 2 · 수량 합 ≤ 잔량
lineage.merge(cur, *, parent_ids, by, qty=None, relation="합병", kind=None, process_id=None, equipment_id=None, attrs=None, user=None) -> dict            # D-503 · 코어 합병 N ≥ 2 · 팩 합병 계열 N ≥ 1
lineage.ship(cur, *, shipment_id, lot_id, by, user=None) -> int        # 개발3 F-SHP-05. 출하 LOT 없으면 LOT_SHIPMENT 채번. 등록 상태 출하만 · 이미 출하/소진/불합격 422
lineage.unship(cur, *, shipment_id, lot_id, by, user=None) -> int      # 개발3 F-SHP-06. 출하 화살표 삭제. 담기지 않은 LOT 422
lineage.consume_material(cur, *, work_result_id, material_lot_id, qty, by, unit=None) -> int   # pop_input + 원재료면 mat_stock_trx(투입 −qty) · mat_stock. 미검사/불합격/소진/잔량 부족/종료 실적 422
lineage.cancel_consume(cur, *, input_id, by) -> int                     # 종료 전만 · 재고 되돌림
lineage.retag(cur, lot_id, kind, *, by=None) -> dict                    # 팩 kind (base 는 등록값)
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
