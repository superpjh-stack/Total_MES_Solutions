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
