# progress-dev3 — 개발3 (수주 · 출하 · 조회 · 연계 / `ord` `shp` `trc` `kpi` `ifc` + 이관 배치 4 · `stats` `erp` `migrate`)

검증된 것만 적는다. 형식 `| 항목 | 실측 | 검증 방법 |`. 비밀번호 값은 적지 않는다.

## §1 공표 (R1 · 2026-10-09)

### `app/stats.py` — 집계 SQL 의 유일한 자리 (`interfaces.md` §7 을 코드에 맞춰 고쳤다)

```python
from mescore.app import stats
stats.production(frm, to, *, by="day|item|process|equipment") -> list[dict]   # wo_count plan_qty result_count good_qty defect_qty good_rate achieve_rate (+ day | code name)
stats.quality(frm, to, *, by="day|item|defect") -> list[dict]                 # inspection_count pass_count fail_count cond_count pass_rate / defect: defect_count defect_qty
stats.delivery(frm, to, *, by="day|partner", today=None) -> list[dict]        # due_count shipped_count on_time late pending on_time_rate
stats.equipment(frm, to) -> list[dict]                                       # run/stop/check/fault/logged_seconds run_rate stop_count fault_count mttr_hours current_state
stats.measure_series(param_key, frm, to, *, by="day|work_order|equipment", agg="avg|min|max|sum|count|last") -> list[dict]   # value n deviated_count min_value max_value
stats.totals(kind, rows) -> dict | None                                      # 합계 줄 — 비율은 더한 값으로 다시 나눈다
stats.core_metrics(frm, to, *, today=None) -> dict                           # CORE_METRIC_KEYS 5: production.achieve_rate · production.good_rate · quality.pass_rate · delivery.on_time_rate · equipment.run_rate
stats.kpi_extra(frm, to, by=None) -> list[dict]                              # 팩 훅 kpi_extra(frm, to[, by]) → [{key, label, value, unit}] (D-508). 없으면 []
stats.indicators(frm=None, to=None, *, values=None, today=None) -> list[dict] # kpi_indicator + 현재값 + status(good/warn/critical/None — D-602)
stats.board(today=None) -> dict                                              # KPI-01 — 디자이너3 키 그대로(아래). kpi_snapshot(today) 가 있으면 지표 값은 그것 · source="스냅샷 HH:MM"
stats.snapshot(cur, day) -> int                                              # 배치만: `uv run python -m mescore.app.stats snapshot [YYYY-MM-DD]` → kpi_snapshot 코어 5 + pack:<key>
stats.dashboard(today=None) -> dict                                          # CMN-04: today{date work_orders results inspections_pending shipments_pending} + extra{deviated faults late_orders approvals_pending issues_open labels_today}
stats.summary(kind, frm, to, *, by=None, today=None) -> dict                 # KPI-02 한 탭 분 {kind, by, rows, total}
stats.late_orders(*, today=None, limit=20) · stats.open_work_orders(limit=7) · stats.measure_keys() · stats.period(frm, to) · stats.parse_date() · stats.rate() · stats.status_of(value, target)
```

- 비율은 전부 **퍼센트 float** · 분모 0 → `None` · 행 없음 → `[]`/`None`(화면 `미수집`). 산식은 `stats.py` docstring 에 QA2 대조용으로 한 줄씩 적었다.
- **`board()` 키 확정 (D-602)** — 디자이너3 절의 표 그대로: `today source production{plan_qty actual_qty good_qty defect_qty unit achieve_rate good_rate good_rate_target by_hour[]}
  quality{inspection_count pass_count fail_count pass_rate pass_rate_target top_defects[]} delivery{due_count shipped_count late_count pending_count on_time_rate late_orders[]}
  equipment{run stop check fault items[]} work_orders_count work_orders[] measure{measured_count deviated_count} indicators[]`. 지표 `status` 는 서버 계산(값 ≥ 목표 good · ≥ 목표×95 % warn · 그 밖 critical · 목표 NULL → null).
  `actual_qty` = good + defect · `by_hour` 는 실적이 있는 첫 시간부터 23시까지 · `top_defects.share` = 1위 수량 대비 % · 조건부는 합격에 세지 않는다(D-302).
  → `docs/design/README.md` 디자이너3 §1 을 "확정" 으로 갱신했다.
- `GET /kpi/board` 는 `Accept` 에 `text/html` 이 없으면 **`stats.board()` 그대로**(폴링 — 접근 로그를 남기지 않는다), 브라우저면 `kpi/board.html`(base.html 을 쓰지 않는 벽걸이 전용 · `body.ch-board` · 5초 JSON 폴링 · 실패 시 마지막 값 유지).

### `app/erp.py` — 어댑터 501 + 큐 (D-02 · D-20 · G-C16)

```python
from mescore.app import erp
class erp.ErpAdapter: push(kind, payload) -> ErpResult(ok, message, ref) · pull(kind, since) -> list[dict]   # 기본: raise http.undecided("D-02", "ERP 연계") (501)
erp.adapter() -> ErpAdapter            # pack.yaml: adapters.erp 모듈의 class Adapter(ErpAdapter) 또는 def adapter() · 없으면 기본(501). erp.is_undecided() -> bool
erp.enqueue(cur, kind, payload, *, by=None) -> int   # ifc_outbox `대기` 한 행 — after_commit_* 훅(팩)이 쓴다. 같은 tx 커서
erp.flush(limit=100) -> {processed, sent, failed, undecided, decision, ids}   # 어댑터 501 → 그 행 `미확정` + ifc_erp_link 한 줄. 조용한 폴백 0
erp.retry(outbox_id) -> {id, status, message}        # F-IFC-04 — 어댑터 501 이면 행을 `미확정` 으로 적은 뒤 **501 그대로** 올린다. 없는 ID 404 · 이미 전송 422
erp.outbox(limit, *, status=None) · erp.links(limit)   # IFC-02 읽기
```

- 코어 F-SHP-07 승인은 `http.after_commit(request, "shipment_approved", payload)` 만 한다 — 큐에 넣는 것은 팩의 `after_commit_shipment_approved(payload)` 가 `erp.enqueue` 로(D-20). 코어 단독에서는 큐가 비므로 `seed_dev3` 가 `(예시)` 큐 1행을 넣어 IFC-02 `대기 — 미확정 (D-02)` · F-IFC-04 501 을 재현한다.
- payload: `{shipment_id, shipment_no, partner_code, ship_date, order_no, approved_by, lots[{lot_no, qty, unit}]}`.

### `mescore.migrate` — 이관 배치 4 (개발1 F-SYS-15 가 부른다)

```python
from mescore import migrate
migrate.COMMANDS -> {"basics": (01~09), "orders": (11, 12), "lots": (21, 22), "history": (31~34)}
migrate.run(command, dir, *, dry_run=False, run_by=None) -> MigrateReport     # .ok .exit_code(오류 1건 이상 → 1) .error_count .totals() .text() .as_dict() .files[FileReport(file present read inserted updated skipped errors[RowError(line key reason)])]
migrate.main(argv) -> int                                                    # `uv run python -m mescore.migrate <cmd> --dir <폴더> [--dry-run]`
```

- 모르는 명령 `ValueError` · 없는 폴더 `FileNotFoundError` · DB 연결 실패 `DbUnavailable` — 삼키지 않는다. 폴더에 없는 파일은 "없음" 으로 건너뛴다(오류 아님).
- 멱등: 키 upsert(`xmax = 0` 로 적재/갱신 구분) · 계보는 있으면 `건너뜀`(불변) · 번호는 파일 값 그대로(채번 · `sys_number_seq` 안 올림) · `created_by='migrate'` · `attrs.migrated_from`.
- 계보 22 는 **`lineage.link(cur, parent_id, child_id, relation, by="migrate", qty=)` 로만**. `linked_at` 열은 읽되 쓰지 않는다(§3 요청).
- SHIPMENT 종류 LOT(21)은 `lot.shipment_id` CHECK 때문에 같은 폴더 `34_shipments.csv` 의 헤더(`ship_lot_no` 가 그 LOT)를 먼저 upsert 한다 — **D-301**. 헤더가 없으면 그 줄 오류.
- 예시 세트 `src/mescore/migrate/examples/` 17파일 = 코어 시나리오(원재료 2 · 생산 2 · 합병 1 · 분할 3 · 출하 1 · 계보 10행 · 실적 2 · 측정값 3 · 검사 3 · 출하 헤더 1). 전부 `(예시)` · `-EX-`.

### 라우터 · 훅 자리 (R2)

- 쓰기 순서: 검증 → `packs.hook("validate_<table>")` → tx → `packs.hook("after_save_<table>")`(D-504) → `audit.log_change` → `http.saved`. `ord_order` `ord_order_dtl` `ord_plan` `shp_shipment` `shp_document` `kpi_indicator` 전부.
- F-ORD-01 `on_order_created(cur, order, user)`(order 에 `lines[]` 포함) · F-ORD-02/03 상태가 바뀔 때 `on_order_status_changed(cur, order{before_status}, user)`(D-505) · F-SHP-07 `validate_shipment(cur, shipment, lots, user)` 직전 + `after_commit("shipment_approved", payload)`.
- 개발2 호출: `lineage.ship/unship(cur, shipment_id=, lot_id=, by=, user=)` · `lineage.resolve/search/trace_forward/trace_backward` · `printing.render_print("label_shipment", printing.shipment_label_for(id), screen_id="SHP-02")` · `render_print("document", {"doc", "snapshot", "shipment_no"}, screen_id="SHP-04")` · `collect.CollectMessage.from_payload` → `collect.receive(cur, msg)` → `ReceiveResult`.
- 폼 수정 규약: 빈 폼 값은 "바꾸지 않음"(FastAPI 가 빈 문자열을 None 으로 준다). 연결 해제는 `clear_order=1`(F-SHP-02) · `clear_target=1`(F-KPI-07).
- **개발1 F-JOB-01 상태 전이 확인**: `ord_order_dtl.status` 대기 → 지시(지시 취소로 다른 지시가 없으면 대기 복귀)는 ord 화면과 맞다 — ord 는 `dtl.status` 를 읽기만 하고(F-ORD-02 는 지시가 붙은 상세의 품목 변경을 `job_work_order.order_dtl_id` 로 막고, F-ORD-03 은 대기 · 진행 지시가 있으면 422). `출하` 값은 아무도 쓰지 않는다(출하 수량은 계보에서 계산). `ord_plan.status` 는 **F-ORD-09 만 확정**으로 바꾼다 — F-JOB-01 은 `확정` 계획만 받고 `계획` · `취소` 계획은 422(`확정된 계획만 지시로 이어진다`, function-list F-ORD-09) 로 두는 것이 맞다. 지시 쪽에서 `ord_plan.status` 를 `확정` 으로 올리면 F-ORD-08 의 "확정 후 수량만" 규칙이 사용자 모르게 걸린다.

## §2 실측 (2026-10-09)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 기능 연결 | F-ORD 10 · F-SHP 10 · F-TRC 3 · F-KPI 8 · F-IFC 4 = **35/35** 라우트 연결 · B-MIG **4/4** `COMMANDS` · 테스트 표식 136/136(전체) | `make check-trace` — `기능 132 ↔ 라우트 PASS 132/132` · `이관 배치 4/4 PASS` |
| 고아 라우트 | **1** — `GET /shp/shipments/{id}/label`(D-601 출하 라벨 · 기능 수 밖). `check_trace` 가 D-12 만 제외한다 → §3 요청 | `make check-trace` G-C02 FAIL 1 |
| 화면 | 담당 16 + CMN-04 대시보드 전부 200 · placeholder **0**(남은 1 = 아키텍트 CMN-05 팝업) · RBAC 204건 위반 0 | `make check-routes` |
| 테스트 | 개발3 8파일 **55 passed** · 전체 **241 passed · 0 failed** | `uv run pytest -q` |
| 금지어 | 위반 0 · 템플릿 t() 누락 0 | `make check-terms` G-C23 PASS |
| 코어 해시 | 개발3 파일은 전부 `생김`(새 파일) · 코어 파일 변동 0(바뀐 `home/main.html` · `login.html` 은 개발1 몫) | `uv run python src/mescore/tools/core_hash.py --check` |
| trc · kpi 쓰기 | `grep -iE "insert|update|delete" app/routers/{trc,kpi,dashboard}.py` → trc 0 · dashboard 0 · kpi **2**(kpi_indicator insert/update = F-KPI-06/07) | grep |
| 이관 4종 | `basics` 읽음 15 · `orders` 3 · `lots` 19(계보 10) · `history` 9 — 2회째 적재 0 · 행 수 diff 0 · dry-run 쓰기 0 · 오류 줄 리포트(줄 번호 · 키 · 사유) · 종료 코드 1 · `sys_migration_log` 파일마다 1행 | `tests/test_migrate.py` 5건 · `uv run python -m mescore.migrate <cmd> --dir src/mescore/migrate/examples` |
| 계보 | 예시 세트 적재 뒤 `lot_genealogy` 투입 3 · 합병 2 · 분할 3 · 출하 2 = **10행** · `linked_by=migrate` · P-EX-0006 `재고` | `tests/test_migrate.py::test_lots_and_genealogy_10_rows_via_lineage` |
| 집계 손계산 | 생산(10-01~02 · PRD-EX-01) plan 100 · good 100 · defect 3 · good_rate 100/103·100 · achieve 100 % / 품질(10-02) 합격 2 → 100 % / 납기 O-EX-0001 준수 / 측정값 temp_c avg 26.75 · last 31 · 이탈 1 / 설비 구간 기간 밖 자르기 2h · 기록 없음 → None | `tests/test_stats.py` 10건 |
| 출하 한 바퀴 (API) | 수주 → 계획 확정 → 출하 등록(생산) → LOT 스캔 2(`lineage.ship` · 출하 LOT X… 생성) → 미검사 · 불합격 · 이미 출하 · 원재료 422 → 승인(관리자 · `validate_shipment` 호출 · `after_commit` 이벤트 · HookError 422 되돌림) → 성적서 발행(최신 검사 스냅샷 · 미수집 → 종합 `미확정` · 재발행 새 번호) → 출력(발행 뒤 검사가 생겨도 발행본 불변) → 역추적 X-EX-0001 → 원재료 ①② · 정방향 M-EX-0001 → 출하 + 재고 ③ | `tests/test_shp_api.py` 11건 · `tests/test_trc_api.py` 3건 |
| 현황판 | JSON 키 = 디자이너3 표 · `Cache-Control: no-store` · HTML `data-key` 43 자리 + `data-list` + 5초 폴링 · `?device=pop` 403 | `tests/test_kpi_api.py::test_board_json_keys_and_html_polling_skeleton` |
| ERP | 기본 어댑터 push/pull 501 `D-02` · enqueue → `대기` · flush → `미확정` + `ifc_erp_link` · retry 501 그대로 · F-IFC-04 관리자만 | `tests/test_erp.py` · `tests/test_ifc_api.py` |
| 수집 | 토큰 없음/틀림 401 · 수신 200 `raw_id` · 재전송 `duplicate` · 모르는 설비 422 + 거부 기록 · 모르는 태그 `unknown_tags` | `tests/test_ifc_api.py::test_collect_receive_token_idempotent_unknown_equipment` |
| 모바일 | ORD-03 주 단위 details · SHP-03 · TRC-01/02/03 · KPI-02 카드(`m-card` · `details` · `min-width:0` · `overflow-wrap:anywhere`) · `?device=mobile` HTML 200 | `tests/test_*_api.py` 모바일 단언 4건 |
| 시드 | `seed_dev3` 2회 실행 행 수 같음 — 수주 2 · 상세 2 · 계획 2(확정 1 · 계획 1) · 지표 4(목표 NULL) · ERP 큐 1 | `uv run python -m mescore.db.seed_dev3` ×2 |

## §3 요청

1. **아키텍트 `tools/check_trace.py`** — 고아 라우트 제외에 D-601 `GET /shp/shipments/{}/label` 을 D-12 와 같이 넣어 달라(decisions D-601 "기능 수에 안 센다 — D-12 와 같은 취급"). 지금 G-C02 FAIL 1 의 유일한 원인.
2. **아키텍트 `Makefile`** — `kpi-snapshot` 타깃: `uv run python -m mescore.app.stats snapshot` (+ `erp-flush`: `uv run python -c "from mescore.app import erp; print(erp.flush())"`).
3. **아키텍트 `packs.py: CORE_ROUTER_MODULES`** — `dashboard` 가 13 에 없어 `routers/kpi.py` 가 `routers/dashboard.py` 를 include 한다. 목록에 넣어 주면 kpi 의 include 한 줄을 뺀다.
4. **아키텍트 `function-list.md` B-MIG-03** — 쓰는 테이블에 `shp_shipment` 추가(D-301: SHIPMENT LOT 의 `lot.shipment_id` CHECK 때문에 `lots` 가 34 의 헤더를 먼저 적재한다). 또는 `lot_shipment_chk` 를 완화.
5. **개발2 `lineage.link`** — `at=`(linked_at) 인자. 이관 22 의 `linked_at` 을 지금은 읽기만 한다.
6. **개발2 `collect.counts(frm, to)`** — `frm/to` 가 None 이면 `AmbiguousParameter`(`%(f)s is null` 에 캐스트 없음). IFC-01 은 자체 조회로 우회했다.
7. **개발2 · 아키텍트** — `templates/print/document.html` 은 소유권이 개발3(screen-map §3)이지만 개발2 가 디자이너3 필드로 만들어 두었고 F-SHP-09 스냅샷 모양이 그대로 맞아 그대로 쓴다(수정 0). 소유권 표만 개발2 로 옮기거나 그대로 두어도 된다.
8. **개발1 F-JOB-01** — §1 끝 줄: `ord_plan.status` 는 F-ORD-09 만 바꾸고 지시는 `확정` 계획만 받는 것으로 맞추자. `ord_order_dtl.status` 대기 ↔ 지시 전이는 맞다.
9. **개발2 · 개발1** — 추적 노드 링크(G-C08)를 `QUA-02 ?no=<LOT>` · `MAT-03 ?no=<LOT>` · `JOB-02 ?wo=<지시 번호>`(D-604) 로 걸었다. 그 화면의 쿼리 이름이 다르면 알려 달라(`routers/trc.py: _links`).
