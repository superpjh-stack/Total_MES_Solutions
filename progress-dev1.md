# progress-dev1 — 개발1 (기준 · 지시 · 시스템 / `bas` `job` `sys` + 로그인 · 메인)

검증된 것만 적는다. 형식 `| 항목 | 실측 | 검증 방법 |`. 비밀번호 값은 적지 않는다.

## §1 공표 — 채번 (`app/numbering.py` · R1 · 2026-10-09)

**시그니처 (`interfaces.md` §3 그대로)**

```python
from mescore.app import numbering
numbering.next(kind, *, cur=None, at=None) -> str   # 발번 (카운터 +1). cur 를 주면 그 트랜잭션 안 — 되돌리면 번호도 돌아온다
numbering.peek(kind, *, at=None) -> str             # 발번하지 않고 다음 번호
numbering.rule(kind) -> dict | None                 # sys_number_rule 행 (id kind prefix date_format seq_digits use_yn …). 없으면 None → 화면 `미확정 (D-10)`
numbering.kinds() -> list[str]                      # core.yaml: numbering + 팩 numbering 의 키 (표시 · 시드용)
numbering.counter(kind, *, at=None) -> int          # 지금 범위(오늘)의 카운터 값 — SYS-05 표시용
```

**형식 (가설 — D-10 · D-16 · 행은 `core.yaml: numbering` → 시드 `sys_number_rule`)**

`번호 = prefix + to_char(기준 시각, date_format) + 일련번호(seq_digits 자리 0 채움)` — 구분 기호는 `date_format` 끝의 `-` 가 전부.

| kind | prefix | date_format | digits | 예 (2026-10-09) | 쓰는 곳 |
|---|---|---|---|---|---|
| `WORK_ORDER` | `W` | `YYMMDD-` | 3 | `W261009-001` | 개발1 F-JOB-01 |
| `LOT_MATERIAL` | `M` | `YYMMDD-` | 4 | `M261009-0001` | 개발2 F-MAT-01 |
| `LOT_PRODUCT` | `P` | `YYMMDD-` | 4 | `P261009-0001` | 개발2 `lineage.make_product_lot` · split · merge |
| `LOT_SHIPMENT` | `X` | `YYMMDD-` | 4 | `X261009-0001` | 개발2 `lineage.ship` |
| `SHIPMENT` | `S` | `YYMMDD-` | 3 | `S261009-001` | 개발3 F-SHP-01 |
| `DOCUMENT` | `C` | `YYMMDD-` | 3 | `C261009-001` | 개발3 F-SHP-09 |
| `ORDER` | `O` | `YYMMDD-` | 3 | `O261009-001` | 개발3 F-ORD-01 |
| `PLAN` | `N` | `YYMMDD-` | 3 | `N261009-001` | 개발3 F-ORD-08 |

규칙
- 카운터 범위 = 날짜 부분 값(`seq_scope`). 날짜가 바뀌면 1 부터. `date_format` 이 비면 통산.
- 자릿수를 넘으면 자르지 않고 늘린다(`W261009-1000`). 글자는 `^[A-Z0-9-]+$` 만 — 아니면 `RuntimeError`(규칙 오류).
- 형식 행이 없거나 `use_yn=N` 이면 `RuntimeError`(500) — 번호를 지어내지 않는다. 다른 모듈은 **첫 글자로 종류를 판정하지 않는다**.
- 카운터 행 잠금은 `insert … on conflict do update … returning` 한 문장 — 동시 호출은 행 잠금에서 줄을 선다. 한 트랜잭션의 잠금 순서는 `실적/LOT 행 → 지시 행 → 채번 카운터`(interfaces.md §1).
- 팩은 `pack.yaml: numbering` 으로 접두어 · 형식 · 자릿수 · 종류(예 `BATCH`)를 더한다. 시드가 행을 넣는다 — 코드 변경 없음.

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 채번 | 동시 8스레드 × 5 = 40 발번 중복 0 · 되돌림 뒤 `peek` 복귀 · 날짜 바뀌면 001 · 자릿수 초과 비절단 · 규칙 없음 RuntimeError · 금지 글자 RuntimeError | `uv run pytest -q tests/test_numbering.py` 9 passed |

## §2 실측 — R2 라우터 · 템플릿 · 시드 · 도구 (2026-10-09)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 기능 ↔ 라우트 | 개발1 59 (F-BAS 36 · F-JOB 7 · F-SYS 16) **전부 라우트 연결** — `check-trace` "이어진 기능 113/132" 중 개발1 59/59 · 고아 라우트 중 개발1 0 (고아 1 `GET /shp/shipments/{id}/label` 은 개발3 D-601) | `make check-trace` G-C02 |
| 기능 ↔ 테스트 | 59/59 `@pytest.mark.fn` (`tests/test_bas_master.py` 36 · `test_job_work_orders.py` 8 · `test_sys_admin.py` 16) + `test_numbering.py` 9 = **69 passed** · 2회 반복 통과 | `uv run pytest -q tests/test_bas_master.py tests/test_job_work_orders.py tests/test_sys_admin.py tests/test_numbering.py` |
| 화면 | 개발1 담당 18 (BAS 9 · JOB 3 · SYS 6) + 메인 `/` **placeholder 0** · 전부 200 · RBAC 204건 위반 0 (`check-routes` 잔여 placeholder 는 개발2 8 · 아키텍트 1) | `make check-routes` G-C03 |
| 전체 pytest | 166 중 163 passed · 실패 3 은 전부 `tests/test_arch_smoke.py` — `test_core_has_no_forbidden_terms`(개발2 `lineage.py` 356 · 396 `슬리팅` · `후가공`) · `test_channel_layout_and_channel_rule`(개발3 `/kpi/summary` 500) · `test_permission_matrix_is_data`(다른 프로세스의 테스트가 남긴 임시 역할 — 개발1 테스트는 module 끝에 정리) | `uv run pytest -q` |
| 금지어 | 개발1 파일 위반 0 · 템플릿 `t()` 누락 0 (G-C23 FAIL 2건은 `lineage.py` — 개발2) | `make check-terms` |
| 코어 해시 | 아키텍트 파일 바뀜 **2** = `templates/home/main.html` · `templates/login.html` — 둘 다 개발1 소유로 넘어온 파일(screen-map.md §3 · D-21 · D-605). 그 밖 바뀜 0 · 생김 = 개발 3명의 새 파일 | `uv run python src/mescore/tools/core_hash.py --check` |
| 쓰기 흐름 | 모든 등록 · 수정: 검증 → `packs.hook("validate_<table>")` → `tx` → 저장 → `packs.hook("after_save_<table>")`(D-504 자리) → `audit.log_change` → `http.saved`. F-JOB-01 `on_work_order_created` · F-JOB-03 `on_work_order_closed` · F-JOB-04 `on_work_order_canceled`(D-505) | `grep -n 'packs.hook' src/mescore/app/routers/{bas,job,sys}.py` |
| 지시 행 잠금 | `job.lock_work_order` = `select … for update` — 수정 · 마감 · 취소가 잠근 뒤 실적 수를 다시 센다. 채번 카운터는 지시 저장 직전(마지막) | `tests/test_job_work_orders.py` F-JOB-02/03/04 |
| 오류 계약 | 입력값 422(`fields[].name/label/reason`) · 경로 키 없음 404 · 조회 역할 쓰기 403 · 미로그인 401 — 기능마다 테스트 | 위 테스트 |
| BAS-04 (G-C24 출발점) | `bas_process_param` 전 컬럼 편집(키 · 라벨 · 단위 · 형식 · choices · 하한 · 상한 · 필수 · source · collect_tag · agg · seq · use_yn) · (공정, 키) 중복 422 · 키 변경 422 · 상한<하한 422 · select 는 choices 필수 · collect 는 태그 기본 = 키 · 기록(pop_measure) 있으면 삭제 422 | `test_bas_master.py::test_process_param_*` |
| SYS-03 권한 표 | 한 칸(`role_code·menu_code·level·scopes`) · 표 전체(`level__<역할>__<메뉴>`) 두 모양 → 저장 즉시 `rbac.invalidate()` → **다음 요청부터** (PROD×job 조회로 바꾼 뒤 쓰기 403 · 입력으로 되돌리면 200) · ADMIN×sys `입력` 고정 422 · 빈 칸 `미확정` 표시 | `test_sys_admin.py::test_permission_*` |
| SYS-01/02 | 비밀번호 해시(PBKDF2)만 · 응답 · 로그에 값 0 · 역할 변경 다음 요청 반영 · 비밀번호 재설정 · 중지 → 세션 전부 무효 → 다음 요청 401 · 자기 자신 중지 422 · 역할 등록 = 메뉴 12칸 `없음` · ADMIN 중지 422 | `test_sys_admin.py` F-SYS-01~07 |
| SYS-05 | 규칙 저장 → `peek` 미리보기 · 이미 발번된 번호 불변(카운터 유지) · 바코드 금지 글자 · to_char 형식 오류 422 · 규칙 없는 종류 `미확정 (D-10)` | `test_sys_admin.py` F-SYS-11/12 |
| SYS-06 | 백업 = `tools/backup.py.backup()` 호출 → `backups/` 덤프 + 행 수 JSON + `sys_backup_hist` 1행(실패는 ok=false + 422) · 복구 확인 = `restore_check()` 임시 DB → 행 수 일치 PASS · 임시 DB 삭제 확인 · 이관 = `mescore.migrate.run(command, MES_MIGRATE_DIR, dry_run=)` (폴더 미정 422 · 모듈 없으면 ImportError 그대로) | `test_sys_admin.py` F-SYS-13~16 |
| 메인 `/` | `routers/home.py` 가 등록 — 모듈 12 카드 일하는 순서 · `rbac.cell` 로 `없음` 은 흐림 + 링크 0 (FIELD 로 `href="/bas/items"` 없음) · D-605 `POST /login/as`(role) 은 `MES_ENV=dev` 에서만, 아니면 404 | `check-routes` RBAC · 서버 curl |
| 서버 한 바퀴 | 8030 기동 → `/health` 200 (`placeholders: 4`) → 역할 4 로그인 200 · `/` 200 → admin BAS-01 등록 200 → JOB-01 등록 `W261009-082` → `/job/print?id=` 200 + 바코드 `data-barcode="W261009-082"`(개발2 `printing.barcode_svg`) → field 의 `/bas/items` 403 → `POST /login/as` 200 → 취소 · 정리 | `uv run uvicorn … --port 8030` + curl |
| 시드 | `seed_dev1` — 품목 3 · 공정 1 · 측정값 정의 3(**필수 1 `weight` · 범위 1 `temp` 60~80 · collect 1 `count`**) · BOM 3(구성품 5) · 설비 2 · 거래처 1 · 작업자 1 · 불량코드 2 · 2회 실행 행 수 diff **0** · 표시명 `(예시)` · 코드 `-EX-` | `uv run python -m mescore.db.seed_dev1` ×2 + `conn.table_counts()` diff |
| import_design (G-P03 · D-506) | 니즈푸드 `design.json` td3 49 ↔ `packs/foodservice/README.md` §2: **산출물 49 · 매핑 41 · 범위 밖 8 · 고아 0 · N:1 8 · 1:N 6 · 모르는 화면 ID 0 → PASS**. 매핑 파일이 없으면 빈 양식 49행 + 고아 49 FAIL | `MES_PACK= uv run python src/mescore/tools/import_design.py --design "../NeedsFood MES Platform/docs/design/design.json" --mapping packs/foodservice/README.md --pack foodservice --md` |

### 계약과 달라진 점 · 가설 (D-1nn 후보 — decisions.md 에는 아직 올리지 않았다)
- **F-JOB-01 `ord_plan.status`**: 지시가 붙은 생산계획은 `계획 → 확정` 으로 바꾼다(db-schema.md §2 가 허용한 두 컬럼 중 하나 — 값은 가설). 수주 상세는 `대기 → 지시`, 취소 시 다른 살아 있는 지시가 없으면 `대기` 로 되돌린다.
- **F-BAS-03 등 삭제 422 판정**은 FK 카탈로그(`pg_constraint`)로 센다 — 스키마에 참조가 늘어도 라우터를 고치지 않는다. 취소된 작업지시도 BOM 참조다(F-BAS-07).
- **F-SYS-03** 은 `중지 ↔ 사용` 토글이고 `잠금 → 사용`(해제)도 같은 버튼이다. `fail_count` 는 해제 때 0.
- **F-SYS-08** 저장 응답의 `changed` 는 값이 실제로 바뀐 칸 수(같은 값은 0).
- **F-JOB-07**: `printing` 모듈 + `templates/print/work_order.html`(개발2)이 있으면 `printing.render_print("work_order", {wo, bom_rows, params, printed_at, printed_by})`, 양식만 없으면 `job/print.html` + `printing.barcode_svg`, 모듈도 없으면 바코드 자리 `미확정`.
- **D-605** 구현: `POST /login/as`(role=ADMIN|PROD|QA|FIELD) — `MES_ENV=dev` 아니면 404. 비밀번호는 `MES_SEED_PASSWORD` 환경변수만 쓴다.
- 마스터 화면 8(품목 · 공정 · 측정값 · 설비 · 거래처 · 작업자 · 불량코드 · 공통코드)은 한 벌(`bas.Master` + `register`)로 등록했다 — 계약의 메서드 · 경로 · 기능 ID 는 글자 그대로.

## §3 요청

**아키텍트**
1. `outputs/core.sha256` 재기록(`make core-hash`): `templates/home/main.html` · `templates/login.html` 은 screen-map.md §3 대로 개발1 이 고쳤다(메인 IA · D-605). 지금 `--check` 는 이 둘을 `바뀜` 으로 센다.
2. `tests/test_arch_smoke.py::test_permission_matrix_is_data` 는 `rbac.counts()["전체"] == 48` 을 요구한다 — SYS-02 로 역할을 더하면(정상 기능) 깨진다. 기대값을 `len(roles()) × 12` 로 두거나 코어 역할 4 만 세는 것을 제안한다.
3. D-504 `after_save_<table>` · D-505 `on_work_order_canceled` 를 `interfaces.md` §9 · `pack-contract.md` §5 에 올려 달라 — 라우터는 이미 그 자리에서 부른다(없으면 no-op).
4. `decisions.md` 에 D-101~D-106 (위 "계약과 달라진 점") 을 개발1 대역으로 올려도 되는지 — 올리라면 바로 적는다.

**개발2**
1. `print/work_order.html` 의 data 계약(wo · bom_rows · params)에 맞춰 `job.py` 가 넘긴다. `wo` 에는 `equipment_code/name` · `spec` · `due_date`(수주 납기) 별칭을 더했다. 열 이름을 바꾸면 알려 달라.
2. `lineage.py` 356 · 396 의 `슬리팅` · `후가공` 이 G-C23 금지어로 잡힌다(`make check-terms`).
3. BAS-04 의 `bas_process_param` 행이 시드에 3개 있다(PRC-EX-01: `weight` 필수 · `temp` 60~80 · `count` collect/`count`). `ui.measure_fields` 가 이것으로 G-C24 를 재현하면 된다.

**개발3**
1. `mescore.migrate.run(command, dir, *, dry_run)` 을 F-SYS-15 가 그대로 부른다(`MES_MIGRATE_DIR` 없으면 422). 리포트는 `templating.jsonable` 로 JSON 에 싣는다 — dataclass 면 그대로 풀린다.
2. 메인 카드의 "오늘 건수" 자리(`home.cards_for` 의 `today`)는 `stats` 의 공개 함수가 생기면 붙인다 — 지금은 `미수집`.
3. F-JOB-01 이 `ord_plan.status` 를 `확정` 으로, `ord_order_dtl.status` 를 `지시` 로 바꾼다(취소 시 `대기` 복귀). 수주 · 계획 화면의 상태 전이와 맞는지 확인해 달라.

**웨이브 B 코어 변경 요청 (개발1 · foodservice · 2026-10-09)** — 확장 지점 7 밖이거나 코어 버그라 팩에서 우회한 것. 전부 다른 팩(kimchi · printfilm)도 겪는다.

| # | 어느 확장 지점이 왜 모자란가 | 코어 어디를 어떻게 | 팩에서 우회한 방법 |
|---|---|---|---|
| ① **`packs.read_attrs(request, …)` 가 늘 `{}`** | E2 `attrs` 입력 경로. `starlette.Request` 가 `Mapping` 이라 `isinstance(form, Mapping)` 분기에서 폼을 읽지 않고 ASGI scope 에서 `attr_*` 를 찾는다 → `ord.py` · `shp.py` 처럼 `request` 를 넘기는 라우터는 attrs 가 저장되지 않는다(`bas` · `job` · `mat` · `pop` 은 FormData 를 넘겨 정상) | `packs.read_attrs`: `isinstance(form, Request)` 를 먼저 보고 `form.form()` 을 읽는다 | 수주 납기시간 · 급식유형은 API 로 못 받는다 — `after_save_ord_order` 는 `tests/test_hooks_unit.py` 가 dict 로 검증. S1 은 `ord_order.attrs == {}` 를 그대로 적어 두었다 |
| ② **`seed_core.seed_pack()` 순서** | E3. `process_params` · `inspection_items` 를 `seeds[]`(processes.csv) **앞에** 넣어 첫 시드에서 `bas_process_param.process_id` NOT NULL 로 죽는다 | `seeds[]` 중 `processes*` · `items*` 를 먼저, 그 다음 `process_params` · `inspection_items` | `packs/foodservice/seed_pack.py` 가 공정을 F-BAS-09 로 먼저 만든 뒤 `seed_core` 함수들을 부른다 |
| ③ **`seeds[]` 가 받는 파일 5종뿐** | E1. BOM(레시피) · `kpi_indicator` · 역할별 계정 · 설비/거래처 attrs 를 CSV 로 넣을 자리가 없다 | `bom*` · `kpi_indicators*` · `users*` 로더 추가(또는 팩 `seed_pack.py` 를 `make db-seed` 가 부르는 규약) | `seed_pack.py` 가 코어 API(F-BAS-05 · F-KPI-06 · F-SYS-01 · F-BAS-18/22)로 넣는다 — 코어 테이블 SQL 0 |
| ④ **`audit.log_change` 의 `detail.name` 이 중립어 그대로** | E1 `terms`. 기능 이름('작업 종료' · '출하 LOT 스캔')이 로그에 저장되고 SYS-04 가 `t()` 없이 찍어 G-P05 FAIL (kimchi 도 같은 2건) | `sys/logs.html` 의 「상세」 칸에 `\|t`, 또는 `log_change` 가 `fn_id` 만 저장하고 화면이 `t(contracts.function(fn_id).name)` | `templates/sys/logs.html` 덮어쓰기 1줄 (README §6) |
| ⑤ **팩 `menus.rename` 값에 `t()` 가 한 번 더 걸린다** | E1. `rename: pop: 조리 실적 (POP)` → 화면 '조리 조리 실적 (POP)' | 팩이 준 이름은 치환하지 않는다(코어 기본 이름만 `t()`) | `rename` 을 치환 전 꼴(`실적 (POP)` · `추적`)로 |
| ⑥ **핵심 흐름의 훅 자리에서 코어 필수값을 팩이 채울 수 없다** | E5. F-JOB-01 이 `process_id` 를 필수로 받아 `validate_job_work_order` 의 "비어 있으면 조리 공정으로 채움"(hooks.md §2 R5) 이 돌 기회가 없다 · F-QUA-08 · F-QUA-01 · F-POP-03 은 attrs 를 아예 안 읽어 `validate_qua_issue`(클레임 고객사 필수) · `after_save_qua_insp_plan` · `input_type` 폼값이 닿지 않는다 | `validate_*` 를 필수값 검사 **앞**에 두거나, 모든 쓰기 라우터가 `read_attrs` 를 부른다(interfaces.md §9 규약) | 시나리오는 공정을 명시(S1 PRC-060) · 해당 훅은 dict 단위 테스트 |
| ⑦ **`check_trace` G-P03 이 `import_design` 을 부르지 않는다** | 도구. "매핑 판정은 그 도구의 출력으로 (미구현)" → `make gate` 에서 늘 `미검증` | `check_trace.check_pack_scale` 이 `tools/import_design.py --pack` 을 subprocess 로 돌려 `G-P03` 행을 그대로 낸다 | 수동 실행 — `MES_PACK=foodservice uv run python src/mescore/tools/import_design.py` → **PASS** (§4) |
| ⑧ **pack-contract R9 "팩을 올린 채 코어 테스트 전건 통과" 가 E1 역할 대체와 양립하지 않는다** | 코어 테스트가 `prod · qa · field` 계정과 코어 권한표(goal.md §6) · 코어 채번 접두(`M` · `W`) · 공정 측정값 시드 모양을 **가정**한다. 역할 6 · 권한 72칸 · 채번 `L/WO` 로 바꾼 팩에서는 35 건이 403/200 뒤집힘 · 접두 불일치로 실패(§4) | R9 를 "코어 단독(`MES_PACK=`)에서 전건 + 팩에서는 팩 테스트" 로 바꾸거나, 코어 테스트가 기대값을 병합본(`packs.current()`)에서 끌어온다 | `seed_pack.py` 가 `prod/qa/field` 별칭 계정을 팩 역할에 붙여 로그인 실패만 없앴다(110 → 35 실패) |

## §4 웨이브 B — 참조 팩 `foodservice` 실측 (2026-10-09)

DB `mes_foodservice_db` · 포트 8041 · 명령은 전부 `MES_PACK=foodservice MES_PG_DSN=postgresql:///mes_foodservice_db` 접두. 만든 것 · 기획값과 다르게 둔 것 · 가설은 `packs/foodservice/README.md` §10.

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 코어 수정 | **0** — `git status` 에서 내가 바꾼 파일은 `packs/foodservice/**` · `progress-dev1.md` 뿐. `src/mescore/**` 변경은 전부 다른 담당(아키텍트 · 디자이너 · 개발2/3)의 동시 작업분. `check_pack` R1 의 "바뀜 28" 도 그것(기준값 `outputs/core.sha256` 이 R1 시점이라 아키텍트 재기록 대기 — §3 웨이브 A 요청 1 과 같은 사유) | `git status --short \| grep -v packs/foodservice` · `core_hash.py --check` |
| G-P01 격리 | `R4~R6 PASS 모듈 12 · 화면 51 · 역할 6 · 용어 16` · `R2·R3 PASS 코어 DDL 0 · 생성 11 · 접두 밖 0` · `R7 PASS 파일 2 · scope [job_lot lot mat_requirement qua_issue] · 밖 0` · `R8 PASS 직접 쓰기 0` · `D-05 PASS 집계 0 · WHERE 0` · `R10 WARN 덮어쓴 템플릿 ['print/work_order.html', 'sys/logs.html']`(README §6 에 둘 다 적음 — 미기재 0) · **R1 FAIL 은 위 "코어 수정" 행 참조(내 변동 0)** | `make check-pack` |
| G-P02 규모 | `PASS x_foodservice_ 8 · gates.yaml 8 · 다른 접두 0 · 공통 컬럼 빠짐 0` · `PASS 화면 0/0 · 기능 0/0` | `make check-schema` · `make check-trace` |
| G-P03 추적표 | `G-P03  [foodservice] 추적표  PASS  산출물 49 · 매핑 41 · 범위 밖 8 · 고아 0 · N:1 8 · 1:N 6 · 모르는 화면 ID 0` (`make gate` 에서는 `미검증` — §3 ⑦) | `uv run python src/mescore/tools/import_design.py` |
| G-P04 시나리오 | 팩 테스트 **19 passed** ×3 연속 (S1~S8 8 + 단위 5 + 스모크 5 + 보조 1) — S1 실측: 돈육 `144.000 / 재고 120.000 / 부족 24.000` · 양파 `42.000 / 80.000 / 0.000` · job_lot 2 (FIFO = 유통기한 최소 LOT) · 배치 2 `kind=BATCH kind_base=PRODUCT` `B-01 B-02` · 측정값 collect `RPM 73.5 · STIR_TIME 30 · TEMP 161.25` · 2솥째 `미수집` · 검식 합격 · 출고 승인(출고 담당 승인 403 · 관리자 200) · 계보 **6행**(투입 4 + 출하 2) · 역추적 원재료 2 · 불량률 2÷202×100 = **0.990** · hourly_output 값 있음. `make gate` 판정 원문: `G-P04  시나리오 — gates.yaml: scenarios 재현  PASS  [foodservice] 시나리오 8 · 실행 8 · 실패 0` (1회차 `FAIL S1 1 failed` 는 KPI 대조 SQL 의 불량 NULL 처리 — 테스트 쪽 버그 — 고친 뒤 2회차 PASS). 같은 실행의 `G-P02 PASS 검사 2 전부 PASS` · `G-P05 PASS 화면 54 · terms 키 16 · 치환 안 된 노출 0` · `G-P03 미검증`(§3 ⑦) · `G-P01 FAIL`(R1 코어 해시 — 내 변동 0 · R10 WARN 덮어쓰기 2건 README 기재) | `uv run pytest -q packs/foodservice/tests` · `make gate` |
| G-P05 용어 | `G-P05  팩 용어  PASS  [foodservice] 화면 54 · terms 키 16 · 치환 안 된 노출 0` (처음 FAIL 2 = SYS-04 로그 detail — §3 ④ 우회) | `make check-terms`(`--pack`) |
| 시드 멱등 | `seed_pack.py` 2회차 `행 수 변화 0 테이블: 0 (멱등)` · 이어서 `make db-seed` 도 행 수 변화 0 · `gates.yaml: seed_counts` 실측 sys_role 6 · sys_permission 72 · bas_process_param 7 · qua_insp_plan 13 · bas_equipment 14 · kpi_indicator(pack) 3 · bas_code(pack) 65 · bas_item 6 · bas_partner 4 · bom 1/구성품 2 · equipment_ext(임계) 1 | `seed_pack.py` ×2 · `make db-seed` · SQL |
| 코어 테스트 (코어 단독 `MES_PACK=`) | **239 passed · 2 failed** — 실패 2 = `test_job_work_orders.py::test_list_filters_and_progress_is_computed` · `::test_status_board_today_week_and_drilldown`: `mes_core_db` 에 다른 테스트가 남긴 지시 1,493건(계획일 2031 까지)이라 `LIST_LIMIT 500` 안에 테스트 지시가 안 든다 — 데이터 상태 문제(웨이브 A 테스트의 상한 가정 · 팩 무관). 고치려면 `tests/`(지금 동결) | `MES_PACK= uv run pytest -q tests/` |
| 코어 테스트 (팩을 올린 채) | **206 passed · 35 failed** — 전부 §3 ⑧: 코어 권한표 가정(`field` bas 403 기대 ↔ WORKER 조회 200 등 29) · 채번 접두 `M/W` 가정 3 · `process_param` 시드 모양 1 · 기타 2. 팩 규칙(HookError)로 깨진 코어 테스트 **0** — `hooks._pack_item` 으로 코어 예시 데이터를 중립 통과 | `MES_PACK=foodservice uv run pytest -q tests/` |
| 서버 8041 | `/health` `{"system":"급식 MES","pack":"foodservice","menus":12,"screens":51,"placeholders":0}` · 관리자 로그인 → 메인 메뉴 12 가 `기준정보 · 영업 · 수주 · 자재 · 입고 · 조리 지시 · 조리 실적 (POP) · 품질 · 검식 · 설비 · 출고 · 배치 추적 · KPI · 현황판 · 시스템 · 설비 수집` · 역할 6 로그인 전부 200 · 현장 작업자 `/trc/backward` 403 · 외부업체 `/pop/work` 403 · 영양사 QUA-04 200 | 캡처 `outputs/e2e/foodservice/` 21장 |
| 캡처 (S1 한 바퀴) | `01_login` `02_home_admin` `03_bas_items`(메뉴) `04_bas_bom`(레시피) `05_job_work_orders`(WO-261009-0156) `06_mat_requirements`(144/120/24 · hook) `07_job_print`(덮어쓴 조리 지시서 — 레시피 · 기준인분 100 · 1인량 0.1200 · 지정 LOT) `08_qua_inspections`(검식) `09_shp_scan` `10_trc_backward`(출고 LOT → 배치 2 → 원료 2 · 화살표 6) `11_kpi_board` `12_kpi_indicators` `13_sys_logs` `14_sys_permissions`(72칸) `15_pop_home_worker` `16_pop_result_worker`(교반속도 73.5 · 교반시간 30 · 조리온도 161.25 · 배치 P261009-0188) `17_pop_inputs_worker` `18_worker_trc_403` `19_home_vendor` `20_vendor_pop_403` `21_qua_issues_nutritionist` | `ls outputs/e2e/foodservice` |
| 구현한 훅 | **12**(hooks.md) + `on_work_order_canceled` + `after_save_*` 6 + `sync_ext` — `packs/foodservice/hooks.py` | `grep -c "^def " hooks.py` |

### 미확정으로 둔 값
측정값 범위(`process_params.csv` min/max NULL · D-506) · 표준 소요시간 · 배치 기준수량(`process_ext` NULL) · 관능점수 척도(D-505) · 온습도 임계(`humi_limit` NULL · EQ-TC-01~04/06/07 `storage_kind` NULL → `on_collect` 판정 안 함) · 레시피 표준화율 분모(note `(미확정 D-10)`) · 샘플링 빈도(`insp_plan_ext` 0행) · ISSUE 채번(코어 `Q-` 기본) · `input_type` 폼값(채널로 추정 · README §10.3).

## §5 회전 4 (2026-10-09) — 개발1

중단분(`82f525f` — job 목록 · 현황 `w.id desc` · D-101 · SYS-04 `|t` · foodservice `sys/logs.html` 제거)은 다시 하지 않았다.

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 메인 카드 "오늘 건수" | `home.cards_for` 의 `today` = 개발3 `stats.today_counts()`(코어 모듈 12 → int · 0 도 숫자) · `today_label`(짧은 라벨 12 — `home.TODAY_LABELS`) · `today_source`(`stats.TODAY_COUNT_SOURCES` 문장). 팩 모듈 · `today_counts` 없는 버전 → `None` → 화면 `미수집`. 라우터 SQL 0 | `tests/test_sys_home.py::test_main_cards_today_come_from_stats` |
| 로그인 권한 표 요약 | `GET /login` 을 `routers/home.py` 가 등록(D-21 — main 은 라우터에 있는 공통 경로를 자기 것으로 두지 않는다) · ctx = main 과 같은 4키 + `role_summary[{code name channels[{device label}] write_menus[{code name label}] read_count}]` + `n_menus`. DB 권한 표(`rbac.roles/cell`) 그대로 · 비밀번호 · 해시 0 | `test_sys_home.py::test_login_page_has_role_summary_without_secrets` · `check-routes` 56/56 |
| import_design `--pack` (CR-10) | `--pack` 이 `MES_PACK` 보다 먼저 · `gates.yaml: design_source` 가 `.html` 이면 IA 그림(`ia-menu` h4 × li) 중메뉴 = 산출물 · 매핑표(`mapping_table` → `design_mapping` → `design_expect.mapping` → README.md)의 원본 화면 칸 `BAS-01 품목 관리` 와 이름(괄호 · 공백 무시)으로 ID 를 붙인다 · 분류/판정 칸 `밖` = 범위 밖 · `design_expect.screens` ≠ 원본 수면 FAIL | 아래 3줄 · `tests/test_sys_import_design.py` 5 passed(3팩 PASS + 매핑 한 행 지우면 고아 1 FAIL) |
| G-P03 kimchi | `G-P03  [kimchi] 추적표  PASS  산출물 64 · 매핑 52 · 범위 밖 12 · 고아 0 · N:1 14 · 1:N 15 · 모르는 화면 ID 0` | `uv run python src/mescore/tools/import_design.py --pack kimchi` |
| G-P03 foodservice | `G-P03  [foodservice] 추적표  PASS  산출물 49 · 매핑 41 · 범위 밖 8 · 고아 0 · N:1 8 · 1:N 6 · 모르는 화면 ID 0` | `… --pack foodservice` |
| G-P03 printfilm | `G-P03  [printfilm] 추적표  PASS  산출물 32 · 매핑 31 · 범위 밖 1 · 고아 0 · N:1 2 · 1:N 3 · 모르는 화면 ID 0 · 설계 원본에 없는 매핑 3`(README §1.1 `확장` 3행 = 설계도 IA 밖) | `… --pack printfilm` |
| foodservice attrs 우회 제거 | 아키텍트 `733074f`(read_attrs(Request)) 뒤 S1 이 `ord_order.attrs == {due_time 11:30, service_type 위탁급식}` · ext 복사 `11:30:00 · 위탁급식` 을 API 로 단언(분기 우회 삭제). `test_hooks_unit.py` 는 오류 분기만 | `MES_PACK=foodservice uv run pytest -q packs/foodservice/tests` 19 passed |
| foodservice 시드 우회 | **유지** — `seed_core` CR-9(시드 순서 · 로더) 커밋 없음(`git log` 에 `733074f` packs.py 만). 다음 회전 | `git log --oneline -3` |
| 사용자 ↔ 작업자 (F-SYS-01/02) | `sys_user.worker_id` 등록 · 수정 · 해제(빈 값 → NULL) 동작 · POP-02 는 이미 `sys_user.worker_id` 를 기본 작업자로 읽는다(`pop.py` 156). 시드 계정은 연결이 없었다 → `seed_dev1` 이 `field ↔ WK-EX-02`(양쪽 비었을 때만 · `bas_worker.user_id` 도) · 2회 실행 diff 0 | `test_sys_home.py::test_user_worker_link_for_pop_default` · `seed_dev1` ×2 |
| pytest 코어 단독 | **270 passed · 2 failed** — `test_arch_smoke::test_core_has_no_forbidden_terms`(`packs.py:530 조리` — 아키텍트 작업 중) · `test_migrate::test_basics_idempotent_and_logged`(단독 재실행 5 passed — 동시 실행 흔들림). 개발1 파일 78 passed | `MES_PACK= uv run pytest -q` · `… tests/test_{numbering,bas_master,job_work_orders,sys_admin,sys_home,sys_import_design}.py` |
| check-routes · check-trace · check-terms | G-C03 PASS 56/56 · placeholder 0 · RBAC 204 위반 0 (foodservice 도 PASS) · G-C01/02 PASS · G-C23 FAIL 1 = `packs.py:530`(아키텍트) — 개발1 파일 0 | `make check-routes` · `check-trace` · `check-terms` |

### §3 요청 (회전 4)
- **디자이너1 `login.html`**: ctx `role_summary`(역할 × 채널 × 입력 메뉴 · 위 표) · `n_menus` 가 온다 — README 이식 요청 표 "로그인 | 역할 × 채널 × 입력 메뉴 표" 를 이것으로 그려 달라(지금 `역할 4 · 채널 4` 고정 글자와 개발용 역할 버튼 4 도 `role_summary` 로 바꿀 수 있다). 메뉴 이름은 `t()`.
- **디자이너3 `home/main.html`**: 카드 ctx 에 `today_label`(예 `검사 대기` · `고장 중`) · `today_source`(출처 문장)를 더했다 — `t('오늘')` 고정 대신 `t(c.today_label)` · `title=c.today_source` 로.
- **아키텍트 `main._login_page`**: `POST /login` 실패(401) 재렌더는 아직 main 이라 `role_summary` 가 없다 — `from .routers.home import role_summary` 한 줄로 ctx 에 넣거나, `POST /login` 도 home 으로 넘길지 결정. `check_trace` G-P03 은 이제 `import_design.py --pack <팩>` 을 subprocess 로 돌려 마지막 줄을 그대로 쓰면 된다(종료코드 0 PASS · 1 FAIL · 2 미검증). `packs.py:530` 의 `조리` 가 G-C23 에 걸린다. `seed_core` CR-9 가 들어오면 foodservice `seed_pack.py` 우회를 지운다.
- **개발2**: 시드 `field` 계정에 작업자 `WK-EX-02` 가 연결됐다 — POP-02 `worker_id_default`(디자이너2 요청 5) 는 `sys_user.worker_id` 로 채우면 된다. BAS-07 작업자 화면의 `bas_worker.user_id` 와 `sys_user.worker_id` 는 서로 동기화하지 않는다(쓰는 테이블 계약 그대로) — 기준은 `sys_user.worker_id`.
