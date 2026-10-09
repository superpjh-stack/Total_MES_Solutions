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
stats.dashboard(today=None) -> dict                                          # CMN-04: today{date work_orders results inspections_pending shipments_pending} + extra{deviated faults late_orders approvals_pending issues_open labels_today} + recent[≤5] (회전 4)
stats.recent_activity(limit=5) -> list[dict]                                 # 회전 4 · 최근 변경 — sys_access_log change 최신 순 {logged_at login_id fn_id screen_id target name}
stats.shipment_due(shipment_ids) -> {id: {due_date, due_days, due_state}}    # 회전 4 · SHP-03 행별 납기 대비 — due_days = 출하일 − 수주 납기(양수 = 지남) · due_state 지연/당일/앞섬 · 수주 없음 None
stats.summary(kind, frm, to, *, by=None, today=None) -> dict                 # KPI-02 한 탭 분 {kind, by, rows, total}
stats.today_counts(today=None) -> dict[str, int]                          # 회전 4 · 메인 카드 c.today — 키 = 코어 모듈 코드 12. 출처 home/home.html 머리 주석(아래 §1 표). 값 int(0 도 숫자)
stats.late_orders(*, today=None, limit=20) · stats.open_work_orders(limit=7) · stats.measure_keys() · stats.period(frm, to) · stats.parse_date() · stats.rate() · stats.status_of(value, target)
```

- 비율은 전부 **퍼센트 float** · 분모 0 → `None` · 행 없음 → `[]`/`None`(화면 `미수집`). 산식은 `stats.py` docstring 에 QA2 대조용으로 한 줄씩 적었다.
- **`board()` 키 확정 (D-602)** — 디자이너3 절의 표 그대로: `today source production{plan_qty actual_qty good_qty defect_qty unit achieve_rate good_rate good_rate_target by_hour[]}
  quality{inspection_count pass_count fail_count pass_rate pass_rate_target top_defects[]} delivery{due_count shipped_count late_count pending_count on_time_rate late_orders[]}
  equipment{run stop check fault items[]} work_orders_count work_orders[] measure{measured_count deviated_count} indicators[]`. 지표 `status` 는 서버 계산(값 ≥ 목표 good · ≥ 목표×95 % warn · 그 밖 critical · 목표 NULL → null).
  `actual_qty` = good + defect · `by_hour` 는 실적이 있는 첫 시간부터 23시까지 · `top_defects.share` = 1위 수량 대비 % · 조건부는 합격에 세지 않는다(D-302).
  → `docs/design/README.md` 디자이너3 §1 을 "확정" 으로 갱신했다.
- **`today_counts()` 출처 (회전 4 · `stats.TODAY_COUNT_SOURCES`)** — 디자이너3 `home/main.html` 머리 주석 가설 그대로 + `trc` 는 오늘 계보 연결:
  `bas` 오늘 F-BAS-* 변경(접근 로그 change) · `ord` 납기 = 오늘(취소 제외) · `job` 계획일 = 오늘(취소 제외) · `mat` 입고일 = 오늘 · `pop` 오늘 시작 실적 · `qua` 판정 대기 검사(날짜 무관) ·
  `eqp` 미조치 고장 설비 수 · `shp` 등록(승인 대기) 출하 · `trc` 오늘 `lot_genealogy.linked_at` · `kpi` 오늘 이탈 측정값 · `sys` 오늘 `login_ok` · `ifc` 오늘 수신 거부(`rejected_reason`). 값은 전부 int(0 도 숫자). 개발1 `home.cards_for` 가 `aa9e22a` 에서 붙였다.
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

## §2-R4 실측 (회전 4 · 2026-10-09)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 1. D-29 include 중복 | `routers/kpi.py` 의 `from . import dashboard` · `include_router` 제거 → `/dashboard` 는 `main.py` 코어 15 만 등록 | `make check-routes` 56/56 · `GET /dashboard` 200 |
| 2. `stats.today_counts` | 12 키 int — 실 DB 예 `{bas 1655 · ord 0 · job 1703 · mat 725 · pop 1746 · qua 80 · eqp 79 · shp 404 · trc 1380 · kpi 108 · sys 8102 · ifc 75}`(테스트 잔존 데이터) · `mat` · `ord` 손계산 대조 | `tests/test_stats.py::test_today_counts_modules_and_hand_count` |
| 2. `dashboard.recent[]` | `stats.dashboard()["recent"]` ≤ 5 최신 순 · 라우터가 원형 키 `{at kind text href}` 로(권한 · 채널 밖 화면은 링크 없이 글자 · 기능명은 `t()`) · `dashboard/index.html` 「최근 변경」 박스(원형 `.recent` 모양 · 0건 `미수집`) | `tests/test_kpi_api.py::test_dashboard_recent_five_and_html_block` |
| 2. SHP-03 행별 납기 대비 | `stats.shipment_due(ids)` → 행마다 `due_days` · `due_state` · 템플릿 `due_badge` 가 그 값을 쓴다(템플릿 날짜 계산 제거) | `tests/test_shp_api.py::test_shipment_status_today_week_and_mobile_cards` · `tests/test_stats.py::test_shipment_due_days_per_row` |
| 3. ORD-01 `lines` 전부 | 행마다 `lines[]`(한 쿼리 `_lines_of`) · `orders.html` 모든 수주 아래 `tr.dtl`(실 DB 수주 277 → `tr.dtl` 550) | `tests/test_ord_api.py::test_order_list_filters_and_line_quantities` |
| 3. `total` | ORD-01 · SHP-01 · SHP-03 — `count(*) over ()`(상한 `LIST_LIMIT` 300 앞에서 센 전체 건수) · 템플릿 「전체 N건 · 최근 M건만」 | 같은 테스트 |
| 4. `test_migrate` 흔들림 | 멱등 기준 = 두 번째 `inserted == 0` + **이관 대상 테이블**(function-list B-MIG-0n)에서 이관이 만든 · 갱신한 행(`created_by`/`updated_by = migrate` · `attrs.migrated_from`) 수 diff 0. dry-run 은 대상 테이블 diff 0 + 그 폴더(`dir`)의 로그 +3. 다른 테스트를 같은 DB 에 동시에 돌리며 3회 연속 5 passed | `uv run pytest -q tests/test_migrate.py` × 3 (병행 `test_shp_api` · `test_pop_api`) |
| 5. kimchi 우회 제거 | 아키텍트 `733074f`(packs 채널 코드/라벨 · 겹말 방지) 도착 → `pack.yaml` `screens[]` · `menus.add[]` 채널 **기획대로 코드**(`web/pop/mobile/board`) · `rename.trc` **`로트 추적`** 복원. `rename.qua` 는 `품질` 유지(§3-22). 아키텍트 `6c77eb9`(seed_core 순서 · CR-9) 도착 → **`seed_bootstrap.py` 삭제**(빈 임시 DB `mes_kimchi_r4tmp` 에 스키마 + schema_ext → `seed_core` 2회 행 수 diff 0 · 팩 테스트 26 통과 · DB 삭제) · 개발2 `make_product_lot(merge_parent_ids=)` 미커밋(HEAD 에 없음) → S1 은 10행 유지**(`gates.yaml` 그대로) | `git log -- src/mescore/db/seed_core.py` · `git show HEAD:src/mescore/app/lineage.py \| grep -c merge_parent_ids` → 0 · `MES_PACK=kimchi uv run pytest -q packs/kimchi/tests` **26 passed** · `MES_PACK=kimchi make pack-check` OK WARN [] |
| 7. 검증 | 전체 **274 passed · 1 failed**(`test_arch_smoke::test_core_has_no_forbidden_terms` ← `packs.py:544 조리`(아키텍트) · `routers/qua.py:61 금속검출`(개발2) — 개발3 파일 아님) · `check-routes` PASS 56/56 · placeholder 0 · RBAC 위반 0 · `check-terms` FAIL 2(같은 두 줄) · `grep -iE "insert\|update\|delete" routers/{trc,kpi,dashboard}.py` → 지표 2(`kpi_indicator` insert · update) + `def update_indicator` 이름 + `trc.py:76 base.update(ctx)`(파이썬 dict) — SQL 쓰기 0 | 명령 그대로 |

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

10. **아키텍트 `packs.load`** — `pack.yaml: screens[].channels` · `menus.add[].channels` 의 채널 **코드**(`web/pop/mobile/board`)를 라벨(`관리자 Web …`)로 바꿔 받아 달라. 지금은 `nav.rebuild()` 가 `AssertionError` 로 기동을 거부해 세 팩(kimchi · foodservice · printfilm)의 기획 yaml 이 전부 못 뜬다. kimchi 는 yaml 을 라벨로 고쳐 두었다.
11. **아키텍트 `contracts._validate`(팩)** — 팩 기능의 담당 = `menus.add[].owner` 를 요구하는데 `pack-contract.md` §2 의 `menus.add` 서식(`{code, name, after}`)에는 `owner` 가 없다. 서식에 `owner` · `channels` 를 적거나 팩 기능은 담당 검사를 빼 달라.
12. **아키텍트 `seed_core.seed_pack`** — `seeds[]` 중 `processes*` 를 `process_params` · `inspection_items` **보다 먼저** 넣어 달라. 새 팩 DB 에서 공정이 없어 `bas_process_param.process_id` NOT NULL 로 `make db-seed` 가 멈춘다(세 팩 공통). 또 `equipment*` · `processes*` 시드가 `attrs.*` 열(설비 종류 · 통신 · CCP 여부)을 받지 않는다 — `items*` 처럼 받아 달라. 임시: `packs/kimchi/seed_bootstrap.py`.
13. **아키텍트 `check_trace` G-P03** — `tools/import_design.py` 를 실제로 불러 그 출력 행으로 판정해 달라(지금은 늘 `미검증`). kimchi 는 `MES_PACK=kimchi uv run python src/mescore/tools/import_design.py` → `G-P03  [kimchi] 추적표  PASS  산출물 64 · 매핑 52 · 범위 밖 12 · 고아 0 · N:1 14 · 1:N 15 · 모르는 화면 ID 0`.
14. **개발1 `templates/sys/logs.html`** — 접근 로그 `상세` 칸(`r.detail.name` = `audit.log_change` 가 넣은 **기능명 원문**)에 `|t` 가 없어 팩에서 `출하 LOT` · `작업 종료` 가 날것으로 보인다 → G-P05 FAIL 2 의 유일한 원인(`SYS-04`). 한 줄: `{{ (…)|t }}`.
15. **개발2 `lineage.split`** — 팩 분할 계열 relation 은 **N ≥ 1** 을 허용해 달라(D-503 의 merge 와 대칭). 숙성 투입(포장 LOT 일부 → 숙성 배치, 잔량은 부모 재고)이 1 → 1 부분 분할인데 지금은 N ≥ 2 라 잔량도 새 LOT 이 된다(kimchi 는 `split(count=2)` + 잔량 `retag(PRODUCT)` · 전량은 `retag(AGING)` 로 우회).
16. **개발2 `lineage.split` · `merge`** — 자식 LOT 의 `insp_status` 를 부모에서 잇는 선택 인자(또는 기본). 지금은 늘 `미검사` 라 합격 LOT 을 나눈 숙성 배치가 SHP-02 스캔에서 422(검사 안 함) 가 된다 — kimchi 는 `age` 라우터가 `write_scope` 안에서 `update lot set insp_status` 로 잇는다(직접 SQL 1건 · 없애고 싶다).
17. **개발2 `v_lot_state` · `consume_material`** — PRODUCT LOT 에 자식 계보가 하나라도 생기면 잔량과 무관하게 `소진` 이라 "한 LOT 을 두 절임통에 나눠 담기"(투입 2줄 · 수량 분담)가 첫 실적 종료 뒤에는 422. MATERIAL 처럼 `remain_qty` 로 판정하면 된다. 지금은 두 실적을 종료 전에 모두 스캔해야 한다.
18. **개발2 `routers/qua.py` F-QUA-04/06** — 검사 공정을 고를 수 있게(`plan_for_lot(…, process_id=)` 에 폼 값). 검사 항목이 **LOT 의 공정**으로만 골라져, 혼합 배치(P06 LOT)에 하는 금속검출(P07) 항목이 안 뜬다 — kimchi 는 `inspection_items.csv` 의 P07 행을 공정 공통으로 바꿨다.
19. **개발2 `routers/pop.py` F-POP-03** — 종료 폼에 "합병 부모 LOT" 옵션(기획 `pack.yaml` D-502 가 가정한 것). 지금 합병은 별도 API 가 새 LOT 을 만들어 혼합 배치가 양념 실적 LOT + 절임통 배치 N 의 합병(계보 10행)이 된다. 옵션이 있으면 기획의 9행(투입 + 혼합 한 LOT)이 된다.
20. **아키텍트 `core_hash`** — 작업 폴더에 다른 담당의 미커밋 코어 변경(28 파일 · `static/app.js` · `pop/_layout.html` …)이 있어 G-P01 R1 이 FAIL 로 찍힌다. 개발3 은 `src/` 를 건드리지 않았다(`git diff HEAD -- src` 에 개발3 변경 0 · 커밋은 `packs/kimchi/**` · `progress-dev3.md` 만). 그 변경이 커밋되면 `make core-hash` 를 다시 찍어 달라.
21. **개발1 `tests/test_job_work_orders.py`** — 코어 단독 `MES_PACK= uv run pytest -q tests/` 에서 `test_list_filters_and_progress_is_computed` · `test_status_board_today_week_and_drilldown` 2건이 실패한다(`progress == 진행 and status == 대기` 행 없음). 팩 무관(코어 DB · 팩 미로드) — 개발1 확인 요청.
22. **아키텍트 `packs.translate`** (회전 4) — 겹말 방지는 치환값이 키를 품을 때(`추적` → `로트 추적`)만 막는다. kimchi 기획 `rename.qua: 품질이상` 은 `이상 → 품질 이슈` 로 `품질품질 이슈` 가 된다(붙여 쓴 합성어). **`menus.rename` 값은 팩이 업종어로 쓴 최종 이름이므로 `t()` 를 걸지 않는** 쪽이 맞다(`nav` 가 rename 된 메뉴 이름에 표지를 두고 `base.html` 이 그 이름은 그대로). 그때 kimchi 는 `품질이상` 으로 되돌린다.
23. **아키텍트 · 코어 공통 `?sort=`** (디자이너1 이식 요청 「전 화면 표」) — 서버 정렬 `?sort=<열>&dir=asc|desc` 을 화면마다 따로 만들지 말고 공용 헬퍼(예: `util/http.sort_clause(sort, allowed: dict[str, sql_expr], default)` → 허용 열만 · SQL 주입 0)로 두자. 개발3 은 ORD-01 · SHP-01 · SHP-03 에 `total`(조건 전체 건수)을 먼저 넣었다 — 헬퍼가 생기면 세 목록의 `order by` 를 그것으로 바꾼다.
24. ~~아키텍트 `seed_core.seed_pack` 순서~~ — `6c77eb9` 로 해결 · `seed_bootstrap.py` 지움(§3-12 닫힘). **개발2 `make_product_lot(merge_parent_ids=)`** 가 커밋되면 S1 을 기획 9행(혼합 한 LOT)으로 되돌리고 `gates.yaml` 과 맞춘다(지금 작업 폴더에만 있다).


## §4 웨이브 B — `kimchi` 참조 팩 (2026-10-09)

코어 수정 **0**(`git diff HEAD -- src` 에 개발3 변경 없음 · 커밋 범위 `packs/kimchi/**` · `progress-dev3.md` 뿐) · `ALTER` 0 · `lot_genealogy` · 채번 직접 SQL 0 · `pop_measure` 시계열 0. 구현 메모(기획 문서에서 고친 것 · 기대값과 다른 실측 · 미확정 처리 · G-P03 표)는 `packs/kimchi/README.md` 끝 "구현 메모 (개발3)".

### 게이트 원문 (`MES_PACK= make gate` → `[팩 kimchi · mes_kimchi_db]`)

```
G-P01  격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0  FAIL  검사 7 · 통과 못한 1 — R1 코어 파일 해시 변동 0: [kimchi] 바뀜 28 · 생김 1 · 없어짐 0 ['src/mescore/app/static/app.js', 'src/mescore/app/static/mobile.css', 'src/mescore/app/static/pop.css']
G-P02  규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml                  PASS  검사 2 전부 PASS
G-P03  추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0                          미검증  [kimchi] 추적표: design_source … · import_design 매핑 판정은 그 도구의 출력으로 (미구현)
G-P04  시나리오 — gates.yaml: scenarios 재현                      PASS  [kimchi] 시나리오 4 · 실행 4 · 실패 0
G-P05  용어 — terms 키 치환 안 된 노출 0                             FAIL  팩 용어: [kimchi] 화면 62 · terms 키 25 · 치환 안 된 노출 2 ['SYS-04 `출하 LOT`', 'SYS-04 `작업 종료`']
G-P06  착수 시간 — outputs/pack-timing.md ≤ 4h                  미검증  [kimchi] outputs/pack-timing.md 없음 (사람 · QA3 실측)
```

| 게이트 | 개발3 판정 | 근거 |
|---|---|---|
| G-P01 | 팩 쪽 **PASS**(R2~R10 전부 PASS) · R1 은 **다른 담당의 미커밋 코어 변경** 28+1 파일 때문(§3-20) | `MES_PACK=kimchi make check-pack`: `R4~R6 PASS 모듈 18 · 화면 59 · 역할 6 · 용어 25` · `R2·R3 PASS 코어 DDL 0 · 생성 20 · 접두 밖 0` · `R7 PASS 파일 11 · scope [lot, lot_genealogy, pop_measure, qua_issue] · 밖 0` · `R8 PASS 직접 쓰기 0` · `D-05 PASS 집계 0 · WHERE 0` · `R10 PASS 덮어쓴 템플릿 0`. 팩 폴더를 지워도 코어 테스트는 팩을 안 보므로 그대로(코어 단독 결과 아래) |
| G-P02 | **PASS** | `check_schema`: `x_kimchi_ 7 · gates.yaml 7 · 다른 접두 0 · 공통 컬럼 빠짐 0` · `check_trace`: `화면 8/8 · 기능 24/24` |
| G-P03 | 도구 직접 실행 **PASS** (gate 는 `check_trace` 가 도구를 안 불러 `미검증` — §3-13) | `MES_PACK=kimchi uv run python src/mescore/tools/import_design.py` → `G-P03  [kimchi] 추적표  PASS  산출물 64 · 매핑 52 · 범위 밖 12 · 고아 0 · N:1 14 · 1:N 15 · 모르는 화면 ID 0` (README 끝 표 · D-506) |
| G-P04 | **PASS** 4/4 | 아래 pytest |
| G-P05 | 팩 화면 8 + 코어 화면 노출 0 · **SYS-04 2건은 코어 템플릿**(`sys/logs.html` 의 로그 상세 = 기능명 원문 · §3-14) | `check_terms --pack`: 화면 62 중 SYS-04 만 |
| G-P06 | 미검증 (사람 실측) | — |

### pytest

| 대상 | 결과 | 명령 |
|---|---|---|
| 팩 테스트 (S1~S4 · 기능 24 표식 · 용어 · 스모크) | **26 passed** | `cd packs/kimchi/tests && MES_PACK=kimchi uv run pytest -q` |
| 코어 단독 | **239 passed · 2 failed** — `tests/test_job_work_orders.py` 2건(개발1 · 팩 무관 · §3-21) | `MES_PACK= uv run pytest -q tests/` |
| 코어 라우트 (팩 올린 채) | `[HTTP 200] 64 / 64 (코어 51 + 공통 5 + 팩 8) · placeholder 0 · [RBAC] 236 건 위반 0` | `MES_PACK=kimchi make check-routes` |
| 시드 멱등 | `seed_bootstrap.py` 뒤 `make db-seed` 2회 행 수 diff 0 · 설비 33(`process_id` NULL 0 · `collect_yn` 그대로) · 측정값 19 · 검사 항목 9 · 코드 48 · 공정 9 · 권한 칸 108 · 역할 6 · 채번 10(ALARM · ISSUE 포함) | §4 위 |

시나리오 실측(테스트 원문의 단언):

- **S1** `test_scenario_chain.py::test_s1_chain` — `len(rows) == 10 and got == {"투입": 6, "혼합": 3, "출하": 1}` · `bw["depth"] == 5 and bw["edge_count"] == 10` · 원재료 3(`materials` = M1 M2 M3) · TANK 노드 2 `kind_label == "절임통 배치" and state == "소진"` · `pop_measure salinity_pct` 2행(센서 last 8.9 · 9.1 · source collect) · 손실률 15 이탈 없음 · 출하 `승인`. 기획 기대 9행(혼합 2)과 다른 이유 = 코어 합병이 새 LOT 을 만든다(README 구현 메모 · §3-19).
- **S2** `test_scenario_ship.py::test_s2_block_metal_ng` — NG 판정 → `qua_issue(source=hook)` +1(`CCP 이탈 금속검출 결과[metal_detect] NG / 기준 OK · 불합격 수량 2`) · 포장 K2 → 승인 `r.status_code == 422 and r.json()["code"] == "hook_rejected"` · `shp_shipment.status == "등록"` · 계보 delta 0 · 재검사 OK 뒤 승인 200. 변형 `test_s2_variant_no_metal_inspection_blocks` — 검사 없는 K3 승인 422 `금속검출 합격 기록`.
- **S3** `test_scenario_collect.py::test_s3_alarm` — TC-01 `temp_c 7.2`(픽스처 max 5) → `x_kimchi_env_alarm` +1 `냉장고 온도 이탈 · max 5 ℃ · 발생` · 같은 메시지 `resend` → `duplicate True` · +0 · `7.5` → 행 +0 · `count == 2 · last_value 7.5` · FIELD 해제 403 · QA 확인 → 해제(조치 없음 422 → 조치 입력 200) → `8` → **새 행** +1 · 범위 안 · 미확정(humidity) 알람 0 · 진행 중 TANK 배치(SS-02 · 9 ± 0.5)에서 `10.2` → `절임 염도 이탈 · lot_id = T1(kind TANK)` · 센서 이탈은 `qua_issue` +0. `test_sanitizer_manual_below_10ppm_raises_alarm` — 수기 8 ppm → `소독수 10ppm 미달` · 센서 7 ppm 은 같은 알람에 합침.
- **S4** `test_scenario_aging.py::test_s4_aging` — K1 1000 → 숙성 600 → `A1 kind AGING · kind_base PRODUCT · 600 · 재고 · 합격` · 잔량 LOT 400 재고 · 계보 +2(`숙성` × 2 · base 분할) · 예정 +21(`aging_days_source == "D-511"`) · 첫 승인 422 `숙성 완료 전` · 예정일 전 완료는 사유 필수 → 승인 200 · 계보 +1 · 역추적 AGING 노드 `숙성 배치` · 전량은 `retag` 계보 0행 · 모바일 390 200. `test_cold_moves_in_out_balance` — 입고 100 → 출고 150 422 → 40 → 전량 → 잔량 0 · 위치 NULL.

### 기능 24 ↔ 엔드포인트 ↔ 테스트

`function-list.md` 의 API 열 24 = 라우터 24(`check_trace` 고아 라우트 0 · `G-P02 기능 24/24`). 테스트 표식 `@pytest.mark.fn`: COND-01~04 · WSH-01~03 · TANK-01~05 · PKG-01~02 · AGE-01~07 · ALM-01~03 = 24 (`grep -o "F-X-[A-Z]*-[0-9]*" packs/kimchi/tests/*.py | sort -u | wc -l` → 24).

### 캡처 — `outputs/e2e/kimchi/` 21장 (서버 8043 · `MES_PACK=kimchi` · Playwright headless · gitignore 라 저장소 밖)

`01-login` · `02-main-menu`(팩 메뉴 6 · 임진강 순서) · `03-sys-roles-6` · `04-sys-permissions-108` · `05-cond-item-standards` · `06-tank-operations`(TK-04 진행 · 목표 9 %/48 h · 측정 염도 · 미확정 (D-206) 센서 선택) · `07-tank-salinity` · `08-wsh-sanitizer` · `09-pkg-taping` · `10-age-stock` · `11-age-cold-moves` · `12-alm-alarms`(미해제 4 · 염도 · 온도 · qua_issue 읽기 전용 행) · `13-trc-backward-s1`(S1 출하 로트 X261009-0015 역추적) · `14-qua-issues-hook` · `15-bas-process-params-19` · `16-kpi-indicators` · `17-tank-board-1920` · `18-alm-board-1920` · `19-age-stock-mobile-390`(scrollWidth 390) · `20-age-cold-moves-mobile-390` · `21-tank-operations-pop`. 서버는 8043 에 띄워 두었다.

### 코어 변경 요청 (C-1~8 중 실제로 막힌 것 · 회전 4 아키텍트 판단 근거)

| # | 막혔나 | 1차 처리 | 코어에 있으면 좋았을 것 (다른 팩도 쓰는 모양) |
|---|---|---|---|
| **C-1 알람 (D-501)** | 막힘 — 설비 수집값의 범위 판정 · 발생/확인/해제 이력이 코어에 없다 | `x_kimchi_env_alarm` + `alarm.raise_env`(D-512 합침) + `on_collect` 가 `bas_process_param(설비 공정, collect_tag)` 의 min/max 를 직접 비교 + X-ALM-01 | **구체적으로**: (1) `collect.receive` 가 정제 뒤 `bas_process_param(source=collect)` 의 min/max 와 비교해 `eqp_collect.deviated` 를 찍고, (2) 코어 표 `eqp_alarm(equipment_id, tag, param_id, first_value, last_value, limit_text, count, lot_id, work_result_id, status 발생/확인/해제, first_at, last_at, acked_*, cleared_*, action_desc)` 에 **미해제면 합치고** 아니면 1행, (3) 훅 `on_alarm_raised(cur, alarm, user)` 로 팩이 lot_id · kind 를 보태고, (4) EQP-05 화면(확인 · 해제) + `kpi.board.alarms`. 팩이 더하는 것은 **LOT 연결 규칙**(염도 → 진행 중 절임통 배치)뿐이다. foodservice 냉장 5 ℃ · 냉동 −18 ℃ 가 그대로 같은 표를 쓴다. 테이핑 집계(`x_kimchi_taping_log`)는 코어 `eqp_collect` 증분으로 끝나므로 코어에 필요 없다 |
| **C-2 품목별 범위 (D-509 차단)** | 막힘 | `x_kimchi_item_std` + 훅 비교(세척 키 `deviated` 갱신 · 염도 허용편차) | `bas_process_param.item_id`(선택) + `measure.params_for(process_id, item_id=)` 가 품목 행을 우선. 크기구분 같은 2차 키는 `attrs` 로 |
| **C-3 파생 측정값** | 막히지 않음 | 훅이 `loss_rate_pct` 를 `pop_measure(source=manual)` 에 upsert (D-510) | `source` 에 `hook` 값 하나. `formula` 까지는 필요 없었다 |
| **C-4 화면 단위 권한 (D-502)** | 막힘 — 기능 단위 권한(F-X-WSH-02 · TANK-02 · AGE-02 = PROD · ADMIN)이 메뉴 단위로 넓어진다 | README 명시 · 테스트는 메뉴 단위로 단언 | `sys_permission.screen_id`(선택) 또는 `function-list` 권한 열을 `rbac.can_do` 가 함께 보는 것 |
| **C-5 검사 자동 등록** | 안 씀(1차 수기 · D-509) | — | — |
| **C-6 attrs 집계** | 재현 안 함 | — | — |
| **C-7 보관 위치** | 막히지 않음 | `x_kimchi_lot_ext.location_equipment_id` | `lot.location_id` 가 있으면 ext 1칸이 준다. 급하지 않다 |
| **C-8 kpi_extra 스냅샷** | 막히지 않음(`stats.snapshot` 이 `pack:<key>` 를 찍는다 — R1 구현) | — | — |
| 신규 — 합병 옵션 · split N≥1 · insp_status 상속 · PRODUCT 부분 투입 · 검사 공정 선택 · 채널 코드 · 시드 순서 · G-P03 배선 · SYS-04 `|t` | §3-10~21 | 위 | 위 |

### 미확정 처리

`(미확정)` 값은 전부 NULL 로 두고 판정하지 않는다 — 냉장 온 · 습도 상 · 하한(`bas_process_param`) · 염도 허용편차(`x_kimchi_item_std.tolerance`) · 중량 · CCP 수치(`qua_insp_plan`) · 센서 ↔ 절임통(`SENSOR_TO_TANK = {}` · 화면 `미확정 (D-206)`) · `run_state` 값 형식 · 숙성 품목별 기간(없으면 21 · 응답에 `aging_days_source: D-511`). 테스트는 픽스처가 임시로 넣고 되돌린다(S3). 정본 값(9 %/48 h · 13 %/24 h · 소독수 10 ppm · 목표 700 · 1.30)은 시드에 없다 — X-COND-01 · KPI-03 에서 입력.

## §5 D-501 설비 알람 코어화 — 설계 표 (회전 4 · 개발3 제안 · 코드 0)

근거: `decisions.md` D-501 설계(아키텍트) + kimchi `x_kimchi_env_alarm`/`alarm.py` 실측(D-512 합침 · 발생/확인/해제) + foodservice 냉장 · 냉동 이탈. 테이블 52 → 54 는 사람이 `spec.md` §2.2 · `goal.md` G-C04 를 고친 뒤(아키텍트).

### 테이블 2

| 테이블 | 모듈 · 쓰는 곳 | 컬럼 (공통 6 별도) | 제약 · 인덱스 | kimchi 에서 옮겨 오는 것 |
|---|---|---|---|---|
| `bas_equipment_param` | bas · BAS-05 하위 표(F-BAS-17~20 범위 · 기능 수 불변) | `equipment_id` FK · `tag`(수집 태그 = `eqp_collect.tag`) · `label` · `unit` · `min_value` · `max_value` · `seq` · `use_yn` | uq `(equipment_id, tag)` · min ≤ max CHECK · 범위 둘 다 NULL = 판정 안 함(`미확정`) | 지금 kimchi 는 `bas_process_param(설비 공정, collect_tag)` 의 min/max 를 빌려 쓴다 → 이 표로. 시드는 팩 `seeds[]` `equipment_params*.csv`(값 미확정이면 빈 칸) |
| `eqp_alarm` | eqp · 쓰는 곳 `collect`(발생 · 합침 · 자동 해제) + `eqp`(확인 · 해제 — 기능 추가 시) | `alarm_no`(numbering `ALARM`) · `equipment_id` FK · `tag` · `param_id` FK(`bas_equipment_param`) · `first_value` · `last_value` · `min_value` · `max_value`(발생 당시 복사) · `count`(합친 이탈 수) · `status` 발생/확인/해제 · `first_at` · `last_at` · `acked_at/by` · `cleared_at/by` · `action_desc` · `collect_raw_id` FK(원문) · `lot_id` FK(선택) · `work_result_id` FK(선택) | uq `alarm_no` · **부분 uq `(equipment_id, tag) where status <> '해제'`**(열린 알람 하나) · idx `first_at desc` · status CHECK | `x_kimchi_env_alarm` 거의 그대로(`kind` → `attrs.kind` · `limit_text` → min/max 컬럼). `lot_id` · `work_result_id` 는 코어 컬럼으로 두되 채우는 규칙은 팩 훅 |

### `collect.receive` 판정 (정제 뒤 · 같은 tx · `on_collect` 훅 **앞**)

| 순서 | 동작 | 결과 |
|---|---|---|
| 1 | 정제된 값마다 `bas_equipment_param(equipment_id, tag, use_yn='Y')` 조회 — 없거나 min · max 둘 다 NULL 이면 건너뜀 | 판정 0 (조용한 기본값 없음) |
| 2 | `value < min_value or value > max_value` → 이탈 | — |
| 3 | 이탈 · 열린 알람 없음 → `eqp_alarm` 1행 `발생`(first=last=value · count 1 · 임계값 복사 · `collect_raw_id`) → 훅 `on_alarm_raised` | `ReceiveResult.alarms_raised += 1` |
| 4 | 이탈 · 열린 알람 있음(발생/확인) → **합침**: `last_value` · `last_at` · `count + 1` (D-512 — 새 행 없음) | `alarms_merged += 1` |
| 5 | 정상 · 열린 알람 있음 → 자동 해제 여부는 **설정**(`core.yaml: collect.auto_clear` 기본 false — kimchi 는 사람이 조치 내용 적고 해제). true 면 `해제` + `cleared_by='collect'` | 기본은 그대로 둔다 |
| 6 | 그 다음 기존 `on_collect` 훅 (팩 집계 — 테이핑 등) | 변경 없음 |

`eqp_collect` 에 컬럼을 더하지 않는다(이탈은 조회 때 `eqp_alarm` 과 잇는다 — D-501). 재전송(`resend`) 원문은 판정하지 않는다(멱등 — 같은 `(equip_code, ts, source)` 는 1회).

### 훅 (`interfaces.md` §9 · `pack-contract.md` §5 에 추가)

| 훅 | 서명 | 자리 | 팩이 하는 일 (kimchi 예) |
|---|---|---|---|
| `on_alarm_raised` | `(cur, alarm: dict, user=None) -> dict \| None` | 판정 3 직후 · 같은 tx. 돌려준 dict 의 `lot_id` · `work_result_id` · `attrs` 만 그 행에 반영 | 염도 센서 → 진행 중 절임통 배치의 `lot_id` · `work_result_id` 연결 · `attrs.kind`(ALARM_KIND 6종) |
| `on_alarm_cleared` | `(cur, alarm, user)` | 해제 직후 · 같은 tx | (선택) `qua_issue` 종결 연동 |
| `after_commit_alarm_raised` | `(payload)` | 커밋 뒤(D-20) | 외부 통보(1차 없음) |

### EQP-05 (새 화면 — 기능 ID 는 사람 결정)

| 항목 | 내용 |
|---|---|
| 경로 · 채널 | `GET /eqp/alarms` · web · pop · board (kimchi X-ALM-01 과 같은 채널) |
| 조회(F-EQP-xx) | 설비 · 태그 · 상태 · 기간 · 열린 것만. 행: 알람 번호 · 설비 · 태그 · 첫 값/마지막 값 · 기준(min~max) · 횟수 · 첫/마지막 시각 · 상태 · LOT 링크(TRC) |
| 확인(F-EQP-xx) | `POST /eqp/alarms/{id}/ack` 발생 → 확인 (FIELD · PROD · ADMIN 입력) |
| 해제(F-EQP-xx) | `POST /eqp/alarms/{id}/clear` 조치 내용 필수 · 확인/발생 → 해제 |
| 기능 수 | D-501 은 "1차 ack 없음 · 132 불변" 이었다. kimchi 실측은 **확인 · 해제가 업무에 쓰인다**(S3) — 조회 1 + 확인 1 + 해제 1 = **132 → 135** 안 · 또는 EQP-01 에 열린 알람 표시만(132 불변)하고 확인/해제는 팩에 남기는 안. 사람 결정 |
| 다른 화면 | EQP-01 가동 현황 카드에 열린 알람 수 · 최신 1건 · `stats.board().equipment.alarms_open` · 메인 카드 `today_counts.eqp` 에 열린 알람 더하기는 그때 정의 |

### 팩에 남는 것 (kimchi)

| 남는 것 | 이유 |
|---|---|
| **LOT 연결 규칙**(염도 센서 → 진행 중 절임통 배치 · `SENSOR_TO_TANK` 미확정 D-206) | 업종 규칙 — `on_alarm_raised` 훅 안 |
| 알람 종류 6종(`bas_code ALARM_KIND`) · `tag → kind` 표(`adapters/collect_tags.py`) | 업종어 · 시드 |
| 수기 기록 이탈(F-X-WSH-01 소독수 수기 10 ppm 미달) | 수집이 아닌 수기 — 코어 `collect` 를 안 탄다. 팩이 `eqp_alarm` 에 쓰려면 코어 공개 함수 `alarm.raise_(cur, equipment_id, tag, value, *, source)` 가 필요(팩 write_scope 에 `eqp_alarm` 을 넣지 않는다) |
| 품목별 범위(염도 허용편차 · D-509) | 설비 × 태그 임계값으로는 품목 축이 없다 — `x_kimchi_item_std` 유지 |
| 지우는 것 | `x_kimchi_env_alarm` · `alarm.py` 의 `raise_env/ack/clear` · X-ALM-01 화면(→ EQP-05) · `on_collect` 안 범위 비교 코드 · numbering `ALARM` 팩 종류(코어로) |
