# 결정 대장

> **에이전트는 이 파일을 읽고, 여기 없는 것을 마음대로 정하지 않는다.**
> 정본(`intro.md` · `problem.md` · `spec.md`)에 없는 것을 정해야 하면 추측으로 코드에 박지 말고 여기에 `가설` 로 올리고 `contracts/` 를 고친 뒤 쓴다.
> 사람 확인 없이는 못 가는 것은 `차단` 으로 올리고 화면에 `미확정 (D-nn)` 을 렌더링한 뒤 다음 일로 넘어간다.
> 팩 작업 중 확장 지점 7개 밖의 것이 필요하면 `코어 변경 요청` 으로 올린다(`goal.md` §4.3) — 어느 확장 지점이 왜 모자란지, 코어의 어디를 어떻게 바꾸면 **다른 팩도** 쓸 수 있는지. 아키텍트가 `가설` 로 바꾸고 코어를 고친다.
> 사람이 정하면 상태를 `확정` 으로 바꾸고 근거를 적는다. 확정된 항목은 되돌리지 않는다.

상태: `확정` / `가설`(잠정 채택, 현업 확인 대기) / `차단`(진행 불가) / `코어 변경 요청`(팩이 올린 것 — 아키텍트가 처리)
번호 대역 — D-01~D-12 `goal.md` §7 · 아키텍트 `D-13~D-99` · 개발1 `D-1nn` · 개발2 `D-2nn` · 개발3 `D-3nn` · QA `D-4nn` · 기획 `D-5nn` · 디자인 `D-6nn`
제목 줄 형식은 `## D-nn 제목 · 상태: 가설` 로 고정한다 (`src/mescore/tools/gate.py` 가 `상태: 차단` 을 읽어 게이트 판정에 반영한다).

---

## goal.md §7 「열려 있는 결정」 12건 (옮김 · 2026-10-09)

## D-01 코어 모듈 수 · 경계 (Q1) · 상태: 가설
- 확인 필요: 코어 모듈을 몇 개로, 어디서 자르는가.
- **기본값**: 12. `ord`(수주 · 계획)와 `job`(작업지시)을 분리한다.
- 바뀌면 고칠 곳: `src/mescore/core.yaml` 의 `modules` 표 한 곳.

## D-02 ERP 연계 · 상태: 가설
- 확인 필요: 연계할 데이터와 방식.
- **기본값**: 연계 없음. `app/erp.py` 어댑터 인터페이스만 두고 호출하면 **501 `ERP 연계 미확정 (D-02)`**. 조용한 폴백 0 (G-C16). `ifc_outbox` 재시도 큐.
- 바뀌면 고칠 곳: `app/erp.py`.

## D-03 LOT 단일 테이블 (Q2) · 상태: 가설
- 확인 필요: 원재료 LOT · 생산 LOT · 출하 LOT 을 한 테이블로 둘 것인가.
- **기본값**: `lot` 하나 + `kind`(MATERIAL · PRODUCT · SHIPMENT + 팩 등록) + `kind_base`. 상태 · 잔량은 뷰 `v_lot_state` · `v_lot_stock` 로 계산한다. 근거는 `contracts/db-schema.md` §3.
- 바뀌면 고칠 곳: `db/schema.sql` · `app/lineage.py`.

## D-04 측정값 EAV 범위 (Q3) · 상태: 가설
- 확인 필요: 공정별 측정값을 어디까지 `pop_measure` 한 테이블로 받을 것인가.
- **기본값**: 실적 1건당 키당 1행은 `pop_measure`(`bas_process_param` 선언 → 자동 폼). **시계열**(분 단위 센서 로그)은 `eqp_collect` 또는 팩 테이블.
- 바뀌면 고칠 곳: `spec.md` §3.3 · `ui.measure_fields`.

## D-05 `attrs` 와 확장 테이블 (Q4) · 상태: 가설
- 확인 필요: 팩 속성을 `attrs jsonb` 에 둘지 확장 테이블에 둘지.
- **기본값**: 표시용은 `attrs`, 검색 · 집계 · 제약 · FK 는 `x_<팩>_<코어>_ext`. `attrs` 에 인덱스를 두지 않는다.
- 바뀌면 고칠 곳: `contracts/pack-contract.md` §3.

## D-06 훅 실행 (Q5) · 상태: 가설
- 확인 필요: 팩 훅을 동기로 같은 트랜잭션에서 돌릴 것인가.
- **기본값**: 동기 · 같은 트랜잭션 · `HookError` → 422 `hook_rejected` 전체 롤백 · 외부 전송은 `after_commit_*` 에서만(트랜잭션 밖 — `main.py` 미들웨어가 커밋 뒤 큐를 비운다).
- 바뀌면 고칠 곳: `app/packs.py` · `app/main.py`.

## D-07 용어 사전 범위 (Q6) · 상태: 가설
- 확인 필요: 팩 용어 사전이 어디까지 바꾸는가.
- **기본값**: 템플릿 문구 · 메뉴명 · 메시지 · 출력물 · 바코드 라벨 제목. **코드 식별자 · 테이블명 · URL · 기능 ID 는 불변.** 사전 키는 `core.yaml: terms_keys` 26개뿐.
- 바뀌면 고칠 곳: `app/packs.py: t()` 와 `core.yaml: terms_keys`.

## D-08 기본 역할 4 (Q7) · 상태: 가설
- 확인 필요: 기본 역할의 수와 이름.
- **기본값**: 관리자 `ADMIN` · 생산 `PROD` · 품질 `QA` · 현장 `FIELD`. 시드 계정은 역할 코드 소문자(`admin` `prod` `qa` `field`), 비밀번호는 `MES_SEED_PASSWORD` 로만.
- 바뀌면 고칠 곳: `core.yaml: roles` · 팩 `pack.yaml: roles`.

## D-09 코어 버전 호환 (Q9) · 상태: 가설
- 확인 필요: 코어와 팩의 버전 호환 규칙.
- **기본값**: `core.yaml: core_version 0.1.0` · 팩 `requires_core` 는 semver 범위(`>=0.1,<1.0` 꼴). 밖이면 기동 거부(`PackError`).
- 바뀌면 고칠 곳: `app/packs.py: _requires_ok`.

## D-10 스캐너 · 프린터 · 채번 형식 · 상태: 가설
- 확인 필요: 현장 장치 규격과 번호 규칙.
- **기본값**: 스캐너 = 키보드 입력(스캔칸 + Enter), 라벨 = 브라우저 인쇄(바코드 인라인 SVG), 채번 `접두어 + YYMMDD- + 3자리`(LOT 종류는 4자리). 형식은 코드가 아니라 `sys_number_rule` 행(시드 → `core.yaml: numbering`).
- 바뀌면 고칠 곳: `app/printing.py` · `sys_number_rule` 시드(`core.yaml: numbering`).

## D-11 기능 136줄 전개 · 상태: 가설
- 확인 필요: 화면 51 을 단위 기능으로 어떻게 전개하는가.
- **기본값**: `contracts/function-list.md` 의 전개 전체가 가설. 근거 사업 둘 이상에 있는 기능만 넣었다. 수는 132 + 4.
- 바뀌면 고칠 곳: `contracts/function-list.md`(아키텍트만).

## D-12 분할 · 합병 화면 · 상태: 가설
- 확인 필요: 분할 · 합병에 코어 전용 화면을 둘 것인가.
- **기본값**: 없음. `lineage.split/merge` API(`POST /pop/result/{id}/split` · `/merge`)와 POP-02 의 버튼으로만 열고 기능 수에 세지 않는다. 화면은 팩이 만든다(`printfilm` 후가공 · 슬리팅).
- 바뀌면 고칠 곳: `routers/pop.py`.

---

## 아키텍트 (Phase 0 · 2026-10-09)

## D-13 권한 표 칸 수 — goal.md §6 의 합계 표기가 표와 다르다 · 상태: 가설
- `goal.md` §6 표 그대로 세면 **입력 19 · 조회 22 · 없음 7 = 48** 이다(§6 아래 줄의 "입력 18 · 조회 23" 과 다르다). 괄호 조건도 "3개" 라 적혀 있으나 표에는 4개(입고검사 · 승인 · 지표 정의 · 재전송)다.
- **기본값**: 표(48칸)가 맞다. `core.yaml: permissions` 는 표 그대로, 범위 4개(`입고검사` `승인` `지표` `재전송`)를 `scopes` 에 둔다. `check_trace` 가 세는 기대값은 `core.yaml` 에서 읽는다(19 · 22 · 7). 정본은 고치지 않고 여기 적는다 — 최종 보고에 올린다.
- 괄호 조건의 뜻(엘컴화인 D-14 와 같다): `입력 (승인)` 은 **그 범위 기능만** 쓸 수 있다 — 관리자는 출하 등록 · 수정 · 취소 · 스캔(범위 `일반`)을 하지 못하고 승인만 한다. 그래서 `function-list.md` F-SHP-01~06 의 권한 열에서 `관리자` 를 뺐다(코드 = `rbac.Cell.can_write(scope)` 가 맞다 — 계약을 고쳤다).

## D-14 로그인 실패 횟수와 잠금 · 상태: 가설
- 정본에 잠금 횟수가 없다. **기본값**: 실패 횟수는 `sys_user.fail_count` 에 세되 `MES_LOGIN_LOCK_COUNT` 가 비어 있으면 잠그지 않는다. 값을 주면 그 횟수에서 `status=잠금`. 잠금 해제는 SYS-01(F-SYS-03).
- 바뀌면 고칠 곳: `app/auth.py: login`.

## D-15 정지 사유 코드 · 상태: 가설
- 정본에 정지 사유 목록이 없다. **기본값**: 공통코드 그룹 `STOP_REASON` 에 코어 코드 `ETC 기타 (예시)` 하나만 두고 나머지는 팩 시드(`seed/codes.csv`)가 더한다. 화면은 코드가 하나뿐이어도 `미확정` 로 표시하지 않는다(코드가 있으므로).
- 바뀌면 고칠 곳: `core.yaml: code_groups.STOP_REASON`.

## D-16 채번 접두어 기본값 · 상태: 가설
- D-10 은 형식만 정했고 종류별 접두어는 없다. **기본값**(`core.yaml: numbering`): `WORK_ORDER W` · `LOT_MATERIAL M` · `LOT_PRODUCT P` · `LOT_SHIPMENT X` · `SHIPMENT S` · `DOCUMENT C` · `ORDER O` · `PLAN N`. 날짜 `YYMMDD-`, 자릿수 3(LOT 세 종류는 4). 팩이 `numbering:` 으로 덮어쓴다.
- 다른 모듈은 번호의 첫 글자로 종류를 판정하지 않는다(`interfaces.md` §3).

## D-17 코어 공용 수집 태그 · 상태: 가설
- `api-contract.md` §4 의 "태그 키가 `bas_process_param`/`core.yaml: collect_tags` 에 없으면 `unknown_tags`". 코어가 아는 태그는 설비 공통인 `run_state`(가동 상태) · `count`(생산 수량) 둘뿐. 나머지는 `bas_process_param.collect_tag` 선언이 결정한다.
- 바뀌면 고칠 곳: `core.yaml: collect_tags`.

## D-18 화면 GET 의 JSON 응답 (백엔드 우선) · 상태: 가설
- `spec.md` §7 은 JSON 을 "같은 경로에 `Accept: application/json` 또는 `/api/…` 접두어" 라 했다. **기본값**: 별도 `/api/` 를 두지 않는다. `templating.render` 가 요청 `Accept` 에 `text/html` 이 없으면 템플릿 대신 **`ctx` 를 JSON** 으로 준다(`request` · 설정 · 함수 객체는 뺀다). 테스트 · API 검증은 이 JSON 으로 판정한다. placeholder 는 `{"placeholder": true, "screen_id", "owner", "functions": […]}`.
- 바뀌면 고칠 곳: `app/templating.py: render` · `interfaces.md` §2 · `api-contract.md` §2.

## D-19 세션은 DB(`sys_session`) · 쿠키는 세션 ID 만 · 상태: 가설
- 쿠키(서명)에는 `sid` 하나만 넣고 사용자 · 역할 · 상태는 **요청마다** `sys_session ⋈ sys_user ⋈ sys_role` 로 읽는다. 로그아웃은 `revoked_at`, 중지 · 잠금 · 비밀번호 변경(`password_changed_at` 이 세션의 `password_version` 과 어긋남)은 다음 요청부터 401. 만료 `expires_at` 은 14일(자동 로그아웃 수치는 정본에 없다 — `MES_SESSION_IDLE_MINUTES` 없음, 두지 않는다).
- 바뀌면 고칠 곳: `app/auth.py` · `app/rbac.py`.

## D-20 `after_commit_*` 훅 실패의 처리 · 상태: 가설
- `interfaces.md` §9: "실패해도 응답은 성공, `ifc_outbox` 에 남는다". **기본값**: 쓰기 라우터가 `http.after_commit(request, "<event>", payload)` 로 큐에 넣고, `main.py` 미들웨어가 응답(2xx · 3xx)이 끝난 뒤 `packs.hook("after_commit_<event>")(payload)` 를 부른다. 예외가 나면 서버 로그 + `ifc_outbox(event, payload, status='실패', last_error)` 한 행 — 공통 코드의 쓰기(`db-schema.md` §2 공통 행에 적었다).

## D-21 공통 화면 CMN-04 대시보드 · CMN-05 팝업의 Phase 0 상태 · 상태: 가설
- 둘 다 placeholder(HTTP 200 + 미구현 표식). CMN-05 경로는 `/popup/{kind}` 라 검사 도구는 `kind=item` 으로 연다. `kind ∉ {item, partner, equipment, lot, worker}` 는 404.
- 메인(CMN-02 `/`)은 Phase 0 에서 아키텍트가 모듈 카드(일하는 순서 · 권한 `없음` 숨김)를 그려 두었다 — 개발1 이 `routers/home.py` 에 `/` 를 등록하면 그것이 우선한다(`main.py` 는 라우터에 없는 공통 경로만 자기 것으로 둔다).

## D-22 메뉴(화면 메뉴)라는 말과 금지어 「메뉴(음식 뜻)」 · 상태: 가설
- `spec.md` §12 급식 금지어의 `메뉴` 는 "음식 뜻" 으로 한정돼 있다. 화면 메뉴 · 좌측 메뉴의 `메뉴` 는 코어에 쓴다. `check_terms` 는 `core.yaml: forbidden_terms` 의 글자를 그대로 찾되 이 항목은 `forbidden_terms_notes` 로 옮겨 검사에서 뺀다(게이트를 낮춘 것이 아니라 정본의 단서를 그대로 옮긴 것). 다른 금지어는 **부분 문자열**로 찾는다 — 코어는 `롤` 이 든 낱말(예: 스크롤)도 쓰지 않는다. 영문 금지어(Roll · Job · COA · DTF · splice · ΔE)는 대소문자를 구분한다.

## D-23 `db-schema.md` §4 는 렌더본 · 상태: 가설
- §4 의 표는 `schema.sql` 의 `-- @table 이름 | 모듈 | 설명` 과 컬럼 주석 + 실제 DB 타입에서 `make contracts`(`tools/gen_contracts.py`)가 찍는다. 공통 컬럼 6(`id` · `created_at` · `created_by` · `updated_at` · `updated_by` · `attrs`)은 표에 적지 않고 `check_schema` 가 전 테이블에 있는지 따로 센다. `screen-map.md` §1 · §4 도 같은 방식(`core.yaml` → 렌더본).

## D-24 Phase 0 에서 참조 팩 3 의 `pack.yaml` 뼈대를 만들지 않았다 · 상태: 가설
- `goal.md` §3.1 7 은 "뼈대만" 이라 했으나 기획자 3명이 `packs/kimchi|foodservice|printfilm/` 을 동시에 쓰고 있어 그 폴더를 만들거나 건드리지 않았다. 로더 검증은 `packs/_template` 과 임시 팩(테스트 `tests/test_arch_packs.py`)으로 한다. 기획자가 쓴 `pack.yaml` 은 `MES_PACK=<팩> make pack-check` 로 검증한다. 그래서 Phase 0 종료 조건의 "G-P01 은 팩 3 뼈대로 PASS" 는 이번에 재지 않았다(팩 DB `mes_<팩>_db` 도 아직 없다 → `미검증`).

## D-25 `itsdangerous` 의존성 추가 · 상태: 가설
- 세션 쿠키 서명(`starlette.middleware.sessions.SessionMiddleware`)이 `itsdangerous` 를 요구한다. 지시된 의존 목록(fastapi · uvicorn · jinja2 · psycopg · python-multipart · pyyaml · pytest · httpx)에 하나를 더했다.

## D-26 라우터 파일이 없는 모듈은 오류가 아니다 · 상태: 가설
- `main.py` 는 `app/routers/<모듈>.py` 파일이 **없으면** 건너뛰고(그 화면은 placeholder), 파일이 있는데 임포트가 실패하면 `/health.router_include_errors` 에 모듈과 예외 종류를 적는다. 없는 것과 깨진 것을 구분한다.

## D-27 `tools/backup.py` 는 아키텍트가 이식했다 · 상태: 가설
- G-C20 의 판정은 QA3 몫이지만 `make backup` · `make restore-check` 명령 자체는 CLAUDE.md 「명령」에 있어 엘컴화인 `tools/backup.py` 를 `MES_` · `mes_core_db` 로 바꿔 두었다. 운영 DB 에는 쓰지 않고 임시 DB 에만 복구한다.

---

## 아키텍트 (회전 3 · 웨이브 D-1 · 2026-10-09)

## D-28 `tests/test_permission_matrix_is_data` 의 기대값 = DB 역할 수 × 메뉴 수 · 상태: 가설
- 개발1 요청. SYS-02 로 역할을 더하면(정상 기능) `48` 고정 기대값이 깨진다. 전체 칸 = `len(rbac.roles()) × len(nav.ALL_MENUS)`, **코어 역할 4 의 칸만** goal.md §6 표(입력 19 · 조회 22 · 없음 7)와 대조한다. `check_trace` 의 48 은 매니페스트(core.yaml) 기준이라 그대로.

## D-29 `packs.CORE_ROUTER_MODULES` 15 = 모듈 12 + `home` · `dashboard` · `popup` · 상태: 가설
- 개발3 요청(`routers/kpi.py` 가 `dashboard.router` 를 include 하던 것). 공통 화면 라우터 3 은 모듈이 아니지만 코어가 등록한다. **개발3 은 `kpi.py` 의 include 한 줄을 뺀다**(지금은 `/dashboard` 가 두 번 등록되어 첫 것이 응답 — 동작은 같다).

## D-30 QA 검사기가 없을 때 `gate.py` 는 있는 증거로 PASS/FAIL 을 매긴다 · 상태: 가설
- 회전 2 까지 `gate.py` 는 QA 도구(`check_data` · `check_security` · `check_screens`)만 보고 개발 테스트를 판정에 안 썼다 → 미검증 36. 회전 3 부터 개발 테스트 파일 단독 실행(G-C06 · 07 · 24 · 15 · 10 참고) · 시드 LOT SQL(G-C08) · 양식 4 + `lineage.resolve`(G-C14) · 이관 dry-run 2회 diff(G-C15) · `erp.flush` 501(G-C16) · 접근 로그 4종(G-C18) · 라우터 쓰기 SQL 정적 스캔 + 조회 전후 행 수 diff(G-C05) · 행 0 표 표본(G-C11) · 제어성 경로 grep(G-C12) · `body.ch-*` + `data-scan`(G-C13) · 역할 × 쓰기 기능 전부 403(G-C17) · 저장소 비밀 grep(G-C19) · `backup.py` 실행(G-C20)으로 판정한다. 판정 줄에 **「QA 대조 대기」** 를 붙이고 상태는 PASS/FAIL. QA 도구가 생기면 그 출력이 우선한다(기존 분기 유지). 기대값은 내리지 않았다 — G-C10(QA 가 따로 짠 SQL)은 정의상 QA 없이는 `미검증`, G-C13 의 390px 가로 넘침 · G-C22 는 브라우저 실측이 남는다.

## D-31 `core.yaml: extra_routes` — 기능 수 밖 허용 라우트의 단일 출처 · 상태: 가설
- D-12(`POST /pop/result/{id}/split` · `/merge`) · D-601(`GET /shp/shipments/{id}/label`) 처럼 `function-list.md` 에 없지만 코어가 등록하는 엔드포인트는 `core.yaml: extra_routes` `[{method, path, decision, note}]` 에 적는다. `check_trace` 의 G-C02 고아 판정이 여기서 읽는다(코드에 박힌 D-12 정규식을 뺐다). 새 항목은 D-번호가 있어야 한다. `packs.extra_routes()`.

## D-32 CMN-05 공용 팝업 — `routers/popup.py` · `home/_popup.html` · 상태: 가설
- `GET /popup/{kind}` kind = `core.yaml: common[CMN-05].kinds`(item · partner · equipment · lot · worker · 그 밖 404). `?q=` 코드 · 이름 부분 일치(LOT 은 `lineage.search` — 번호 · 품목 · 지시 번호), `?limit=`(기본 50 · 상한 200). `Accept` 에 `text/html` 이 없으면 ctx JSON(`kind q columns rows count pick`) — D-18. 읽기만(쓰기 0). 행의 `data-pick`(코드 · 번호) · `data-pick-id` 를 부모 화면 입력칸으로 돌려주는 동작은 `static/app.js` 의 몫(디자이너2 · S-목록에 없으면 추가 요청) — 템플릿에 스크립트 0.

## D-33 웨이브 A′ 동안 템플릿 · 정적 파일 소유권은 디자이너에게 · 코어 해시는 아키텍트 회전 끝에 다시 찍는다 · 상태: 가설
- `screen-map.md` §3 갱신 — `base/_error/login.html` · `_macros.html` · `style.css` · `templates/{bas,job,sys,ord}/` 디자이너1 / `app.js` · `pop.css` `mobile.css` · `templates/{pop,mat,qua,eqp,shp}/` 디자이너2 / `templates/{kpi,trc,ifc,dashboard,print}/` · `home/main.html` · `board.css` 디자이너3. 개발은 그동안 `routers/*.py` 만 고친다. `outputs/core.sha256`(G-P01 기준값)은 웨이브 A′ 가 도는 동안 회전마다 어긋난다 — 아키텍트가 회전 끝에 `make core-hash` 로 다시 찍고, 팩 작업의 코어 변동은 `git diff --stat packs/ src/` 로 따로 본다(해시만으로는 디자이너 변경과 팩 작업자 변경을 못 가른다).

## D-34 `core.yaml: numbering` 에 `ISSUE`(Q · YYMMDD- · 3) · 상태: 가설
- D-202 를 코어로 올렸다. `seed_core` 가 `sys_number_rule` 에 넣는다(`seed_dev2` 의 `on conflict do nothing` 행과 같다). 채번 종류 8 → 9 — `interfaces.md` §3 의 8 은 코어 기본 8 + ISSUE 로 읽는다.

## D-35 `Makefile` `kpi-snapshot` · `erp-flush` · `pack-db NAME=` · 상태: 가설
- 개발3 요청. `pack-db` = `createdb` + 코어 스키마(+ `schema_ext.sql`) + `seed_core`(코어 → 팩 → 개발 시드). 팩이 `PackError` 면 팩 시드 단계에서 멈춘다(지어낸 폴백 없음). 회전 3 에 `mes_printfilm_db` 는 아키텍트가 코어 스키마 + 코어 시드만 넣었다(`MES_PACK=` + `MES_PG_DSN` 지정) — 팩 시드는 개발2 가 `MES_PACK=printfilm make db-reset`.


## 아키텍트 (회전 4 · 웨이브 D-2 · 2026-10-09)

## D-36 R9 범위 — 코어 단독 `tests/` 전건 + 팩을 올린 채 `tests/test_arch_*.py` · 상태: 가설
- 세 팩 공통 CR-11(개발1 ⑧ · 개발2 CR-11 · 개발3). 옛 R9 "팩을 올린 채 코어 테스트 전건" 은 E1(역할 대체 · 권한 칸 · 채번 접두) · E3(시드 공정)와 양립하지 않는다 — 코어 업무 테스트는 `prod · qa · field` 계정 · goal.md §6 권한 표 · `M/W` 접두 · `PRC-EX-01` 측정값을 **정의상** 가정한다(팩에서 foodservice 35 · printfilm 57+6 실패). 그 가정을 병합본에서 끌어오게 고치면 테스트가 무엇을 증명하는지 흐려진다.
- **정의**: R9 = ① 코어 단독(`MES_PACK=`)에서 `tests/` 전건(gate G-C21) ② 팩을 올린 채 `tests/test_arch_*.py` 전건(구조 · 병합 · 스키마 · 오류 계약 · 로그인 — 팩이 바꿀 수 없는 것만 단언, 코어 권한 표 · 접두를 보는 단언은 `is_core_only` 일 때만). 팩의 업무 흐름은 G-P04(팩 테스트)가 본다. "팩 폴더를 지운 채" 는 ① 과 같다(코어 단독은 팩을 읽지 않는다).
- 판정: `check_pack` R9 — `MES_PACK=<팩> pytest tests/test_arch_*.py`(G-P01 에 들어간다 · `--no-r9` 로 건너뜀). `tests/test_arch_packs.py` 의 임시 팩 픽스처는 끝나고 **그 실행의 팩**(`MES_PACK`)으로 되돌린다(전엔 코어 단독으로 돌려 같은 실행의 뒤 테스트가 팩 DB 를 코어 병합본으로 보았다).
- 게이트를 낮춘 것이 아니다 — 코어 단독 전건은 그대로이고, 팩에서 무엇을 보는지를 확장 지점과 맞췄다. 바뀌면 고칠 곳: `contracts/pack-contract.md` §4 R9 · `tools/check_pack.py` · `tests/test_arch_*.py`.


## D-37 목록 정렬 `?sort=` 는 공용 헬퍼 `http.sort_clause` 하나로 · 상태: 가설
- 개발3 요청(회전 4). 화면마다 `?sort=` 를 따로 해석하면 SQL 주입 · 열 이름 노출 · 화면마다 다른 문법이 생긴다. `util/http.sort_clause(sort, allowed, default)` — `sort` = `열` · `-열`(내림) · 쉼표로 여럿, `allowed` = {공개 이름: SQL 식}(허용 열만), 비면 `default`(지금 라우터의 order by 그대로), **모르는 열은 422**(조용히 기본 정렬로 바꾸지 않는다). 라우터 적용은 각 담당이 목록 화면에 `sort: str | None = None` 을 더할 때 — 강제하지 않는다(정렬이 필요한 화면부터). `interfaces.md` §8.
- 바뀌면 고칠 곳: `app/util/http.py: sort_clause` · `tests/test_arch_smoke.py::test_sort_clause_allows_only_declared_columns`.

---

## D-38 팩 문구의 용어 치환 범위 — `menus.rename` 값은 그대로 · 속성 라벨은 `t()` · 상태: 가설
- 회전 5 아키텍트(DEF-QA1-003 · G-P05). ① `menus.rename` 값은 **팩이 쓴 최종 이름**(`pack.verbatim`) — `t()` 를 걸지 않는다(회전 4 결정 유지 · 값이 terms 키와 똑같을 때만 치환). 그래서 rename 값은 terms 키를 담지 않게 **최종 꼴로** 쓴다(foodservice `실적 (POP)` → `조리 실적 (POP)` 처럼). `check_terms --pack` 은 rename 값을 노출로 세지 않는다. ② 팩 `attrs` 라벨은 `packs.attrs_of()` 가 **`t()` 를 거친 라벨**을 준다 — 팩은 라벨을 terms 키(중립어)로 쓴다(`공정구분` → `조리 공정구분`). 선택지(`choices`)는 저장 값이라 바꾸지 않는다. ③ 판정 단위는 화면 글 조각(태그 사이 글 · title/placeholder/aria-label) — 표 본문 · 선택지 · 숫자/`(예시)` 가 든 조각(DB 값)은 뺀다(QA1 `check_screens` 와 같은 규칙).
- **회전 7(DEF-QA1-011)**: ① 의 「terms 키를 담지 않는다」 는 **붙여 쓴 합성어도 포함**(`품질이상` ⊃ `이상`) — 예외를 두지 않는다. QA1 `check_screens` G-P05 「menus.rename 값에 치환 안 된 terms 키 0」 행은 그대로 둔다(kimchi 는 기획자3 이 이름을 고친다). `pack-contract.md` §2 `menus.rename` 줄.
- 바뀌면 고칠 곳: `app/packs.py`(`t` · `attrs_of`) · `tools/check_terms.py`.

## D-39 출하 승인 뒤 ERP 큐는 코어 기본 훅이 넣는다 · 상태: 가설
- 회전 5 아키텍트(DEF-QA1-007). F-SHP-07 계약 문장 "after_commit 으로 ERP 큐" 를 맞춘다: `after_commit_shipment_approved` 를 팩이 선언하지 않으면 **코어 기본 구현**(`main.CORE_AFTER_COMMIT` → 자기 트랜잭션에서 `erp.enqueue(cur, "shipment_approved", payload, by=승인자)` — `ifc_outbox` `대기` 1행)이 돈다. 팩이 같은 훅을 두면 팩 것이 대신한다(팩 훅이 큐를 원하면 스스로 `erp.enqueue`). D-20(트랜잭션 밖 · 실패 시 `ifc_outbox` 실패 행)은 그대로.
- 바뀌면 고칠 곳: `app/main.py`(`CORE_AFTER_COMMIT` · `_run_after_commit`) · `contracts/function-list.md` F-SHP-07 · `interfaces.md` §9.

## 개발1 (웨이브 A R1·R2 · 2026-10-09 — `progress-dev1.md` §2 「계약과 달라진 점」 을 아키텍트가 옮겼다 · D-101 은 개발3 의견으로 바꿨다)

## D-101 작업지시 등록(F-JOB-01)과 계획 · 수주 상세 상태 · 상태: 가설 (개발1 안을 **개발3 안으로 바꿈** — 개발1 다음 회전 수정)
- 개발1 R2 는 지시가 붙은 생산계획을 `계획 → 확정` 으로 올리고 수주 상세를 `대기 → 지시`(취소 시 살아 있는 지시가 없으면 `대기`) 로 바꿨다.
- 개발3 §1: `function-list.md` F-ORD-09 「`status=확정`. **확정된 계획만 지시로 이어진다**」 · F-ORD-08 「확정 후에는 수량만」 — 지시 쪽에서 계획을 `확정` 으로 올리면 F-ORD-08 의 규칙이 사용자 모르게 걸린다. **결정: `ord_plan.status` 는 F-ORD-09 만 바꾼다. F-JOB-01 은 `확정` 계획만 받고 `계획` · `취소` 계획은 422(`확정된 계획만 지시로 이어진다`).** `ord_order_dtl.status` 대기 ↔ 지시 전이는 개발1 안 그대로(개발3 이 읽기만 하며 맞다고 확인).
- 바뀌면 고칠 곳: `routers/job.py: create`(계획 상태 검사 · `update ord_plan` 제거) · `tests/test_job_work_orders.py` · `db-schema.md` §2 job 행의 `ord_plan.status` 는 그때 뺀다(회전 4 아키텍트).

## D-102 삭제 422 판정은 FK 카탈로그(`pg_constraint`)로 센다 · 상태: 가설
- F-BAS-03 등 기준정보 삭제는 참조하는 행이 있으면 422 — 참조 목록을 코드에 적지 않고 `pg_constraint` 에서 그 테이블을 가리키는 FK 를 전부 세어 판정한다. 스키마에 참조가 늘어도 라우터를 고치지 않는다. 취소된 작업지시도 BOM 참조다(F-BAS-07).

## D-103 F-SYS-03 은 `중지 ↔ 사용` 토글이고 `잠금 → 사용`(해제)도 같은 버튼 · 상태: 가설
- 잠금 해제 때 `fail_count` 를 0 으로. 중지 · 해제 모두 그 사용자의 세션을 전부 무효(`auth.revoke_user_sessions`) → 다음 요청부터 401. 자기 자신 중지 · ADMIN 중지 422.

## D-104 F-SYS-08 저장 응답의 `changed` 는 실제로 값이 바뀐 칸 수 · 상태: 가설
- 같은 값으로 저장하면 0. 저장 즉시 `rbac.invalidate()` → 다음 요청부터 반영.

## D-105 F-JOB-07 작업지시서의 양식 폴백 순서 · 상태: 가설
- `printing` 모듈 + `templates/print/work_order.html` 이 있으면 `printing.render_print("work_order", {wo, bom_rows, params, printed_at, printed_by})`, 양식만 없으면 `job/print.html` + `printing.barcode_svg`, 모듈도 없으면 바코드 자리 `미확정`. 지금은 셋 다 있어 첫 갈래만 돈다 — 폴백은 조용한 대체가 아니라 화면에 `미확정` 으로 보인다.

## D-106 마스터 화면 8 을 한 벌(`bas.Master` + `register`)로 등록 · 상태: 가설
- 품목 · 공정 · 측정값 정의 · 설비 · 거래처 · 작업자 · 불량코드 · 공통코드. 계약의 메서드 · 경로 · 기능 ID 는 글자 그대로(`check_trace` 132/132). 훅 이름은 `validate_<table>` · `after_save_<table>` 로 테이블마다 따로 등록된다.

---

## 기획 · 디자인 결정 후보 (회전 1 · 오케스트레이터가 옮김 · 2026-10-09)

기획자 3명의 `packs/<팩>/README.md` 끝 "결정 후보 D-5nn" 절과 디자이너 3명의 `docs/design/README.md` 에서 코어에 닿는 것만 옮겼다. 팩 안에서만 유효한 결정은 각 팩 README 가 원본이다.

## D-501 세 팩 공통 — 설비 단위 임계값 · 이탈 알람이 코어에 없다 · 상태: 차단 (사람 승인 대기 — 회전 4 아키텍트가 설계를 확정했다 · 스키마는 바꾸지 않았다)
- foodservice(냉장 5 ℃ · 냉동 −18 ℃ 온도조절기 이탈) 와 kimchi(냉장 온습도 · 염도 센서 이탈) 가 같은 것을 요구한다. E3 는 **공정** 측정값뿐이라 설비 수집값의 범위 판정 · 알람 발생/해제 이력이 코어 EQP 화면에 못 나온다.
- 1차 웨이브 B 는 팩 테이블(`x_<팩>_env_alarm`)로 간다. 회전 4 에서 코어에 들어가면 두 팩의 알람 테이블을 지운다.
- **판단(회전 3 아키텍트)**: 반영한다. 근거 — ① 요구가 업종이 아니라 "수집 설비" 라는 코어 개념(EQP 모듈 · `eqp_collect` · `bas_equipment.collect_yn`)에 붙는다 ② 세 팩 중 둘이 같은 모양을 요구하고 printfilm 도 온습도 설비가 있다 ③ 팩마다 알람 테이블을 두면 EQP-01 가동 현황에 못 올라와 코어 화면이 팩 데이터를 모른다(D-05 attrs 로는 집계 · 이력이 안 된다).
- **설계 (회전 4 아키텍트가 `schema.sql` · `db-schema.md` 에 넣는다 — 이번 회전에는 고치지 않는다. 팩 3개가 지금 그 테이블 없이 구현 중이라 회전 3 에 스키마를 바꾸면 깨진다)**
  - `bas_equipment_param`(bas · 설비별 수집 태그 임계값): `equipment_id` FK · `tag` · `label` · `unit` · `min_value` · `max_value` · `seq` · `use_yn` + 공통 컬럼 6 + `attrs`. 유니크 `(equipment_id, tag)`. 공정 측정값 정의(`bas_process_param`)와 같은 모양이되 축이 설비 · 태그다. BAS-05 설비 화면의 하위 표로 편집(F-BAS-17~20 의 수정 범위 — 기능 ID 추가 없음).
  - `eqp_alarm`(eqp · 발생/해제 이력): `equipment_id` FK · `tag` · `value` · `min_value` · `max_value`(발생 당시 임계값 복사) · `occurred_at` · `cleared_at` · `status`(`발생` · `해제`) · `collect_raw_id`(원문 추적) · `note` + 공통 컬럼 6 + `attrs`. 열린 알람은 설비 · 태그당 하나(부분 유니크 `where status = '발생'`).
  - 동작: `collect.receive` 가 정제 뒤 `bas_equipment_param` 범위를 판정한다 — 범위 밖이면 열린 알람이 없을 때 `eqp_alarm` 1행 `발생`, 범위 안으로 돌아오면 열린 알람을 `해제`(`cleared_at`). `eqp_collect` 에 컬럼을 더하지 않는다(이탈 여부는 조회 때 `eqp_alarm` 과 잇는다). 쓰기 경계 — `collect` 가 `eqp_alarm` 에 쓴다(db-schema.md §2 `ifc` 행에 추가), `bas` 가 `bas_equipment_param` 에 쓴다. 화면 — EQP-01 가동 현황이 열린 알람 수 · 최신 알람을 보여 준다(F-EQP-01 조회 범위 · 기능 수 불변). 팩 훅 `on_alarm(cur, alarm, user=None)` 을 §9 에 더해 팩이 이상(`qua_issue`) 을 만들 수 있게 한다.
  - 미정(사람): 알람 **확인(ack)** 기능은 기능 ID 가 늘어난다(132 → 133) — 1차는 두지 않는다. 테이블 52 → 54 는 `spec.md` §2.2 · `goal.md` G-C04 · `CLAUDE.md` 의 수치라 **사람이 정본을 고친 뒤** 회전 4 아키텍트가 `schema.sql` 을 바꾼다(그 전엔 G-C04 가 FAIL 이 된다).
  - 바뀌면 고칠 곳: `db/schema.sql` · `contracts/db-schema.md` §1 · §2 · §4 · `app/collect.py`(범위 판정) · `routers/bas.py`(BAS-05 하위 표) · `routers/eqp.py`(EQP-01 표시) · `pack-contract.md` §5(`on_alarm`) · `packs/{foodservice,kimchi}` 의 `x_<팩>_env_alarm` 제거.

- **회전 4 정리 (아키텍트 · 사람 승인 대기)** — 회전 3 설계 + 개발3 `progress-dev3.md` §5 설계 표(kimchi `x_kimchi_env_alarm` · `alarm.py` 실측 — 합침 · 확인 · 해제가 업무에 쓰인다)를 합쳐 한 벌로 확정했다. **스키마 · 코드는 바꾸지 않았다**(정본 테이블 수 52 는 사람이 고친다 — 바꾸면 G-C04 FAIL).
  - `bas_equipment_param`(bas): `equipment_id` FK · `tag`(= `eqp_collect.tag`) · `label` · `unit` · `min_value` · `max_value` · `seq` · `use_yn` + 공통 + `attrs`. uq `(equipment_id, tag)` · `min ≤ max` CHECK · 둘 다 NULL = 판정 안 함(`미확정`). 편집은 BAS-05 하위 표(F-BAS-17~20 범위 · 기능 수 불변). 팩 시드는 `seeds[]` `equipment_params*.csv`(D-36 의 이름 규칙에 추가).
  - `eqp_alarm`(eqp): `alarm_no`(채번 `ALARM`) · `equipment_id` FK · `tag` · `param_id` FK · `first_value` · `last_value` · `min_value` · `max_value`(발생 당시 복사) · `count` · `status`(발생 · 확인 · 해제) · `first_at` · `last_at` · `acked_at/by` · `cleared_at/by` · `action_desc` · `collect_raw_id` FK · `lot_id` FK(선택) · `work_result_id` FK(선택) + 공통 + `attrs`. **부분 uq `(equipment_id, tag) where status <> '해제'`**(열린 알람 하나) · idx `first_at desc`. 쓰는 곳 `collect`(발생 · 합침) · `eqp`(확인 · 해제 — 기능이 생기면).
  - `collect.receive` 판정(정제 뒤 · 같은 tx · `on_collect` **앞** · 재전송 원문은 판정 안 함): 값마다 `bas_equipment_param` 조회 → 범위 밖 · 열린 알람 없음 = `eqp_alarm` 1행 `발생` + 훅 `on_alarm_raised` · 범위 밖 · 열린 알람 있음 = **합침**(`last_value` · `last_at` · `count + 1`) · 범위 안 = 그대로(자동 해제는 `core.yaml: collect.auto_clear` 기본 false). `ReceiveResult` 에 `alarms_raised` · `alarms_merged`. `eqp_collect` 에 컬럼 추가 없음.
  - 훅 `on_alarm_raised(cur, alarm, user=None) -> dict | None`(돌려준 `lot_id` · `work_result_id` · `attrs` 만 반영 — 팩의 LOT 연결 규칙 자리) · `on_alarm_cleared(cur, alarm, user)` · `after_commit_alarm_raised(payload)` → `interfaces.md` §9 · `pack-contract.md` §5.
  - EQP-05 `GET /eqp/alarms`(web · pop · board) — 조회 · `POST /eqp/alarms/{id}/ack` 확인 · `POST /eqp/alarms/{id}/clear` 해제(조치 내용 필수). EQP-01 카드에 열린 알람 수 · 최신 1건 · `stats.board().equipment.alarms_open`.
  - **사람이 정할 것 (한 줄)**: 테이블 52 → **54**(`spec.md` §2.2 · `goal.md` G-C04 · `CLAUDE.md`)와 화면 51 → 52(EQP-05) · 기능 132 → **135**(조회 · 확인 · 해제) 를 승인할지 — 아니면 EQP-01 에 열린 알람 표시만(화면 · 기능 수 불변) 두고 확인/해제는 팩 화면에 남길지. 승인되면 회전 5 아키텍트가 `schema.sql` · `db-schema.md` · `core.yaml` · `function-list.md` 를 고치고 개발2 가 `collect` · `eqp`, kimchi · foodservice 가 `x_<팩>_env_alarm` 을 지운다.

## D-502 두 팩 공통 — 화면 단위 권한 예외 · 상태: 코어 변경 요청 (회전 3 아키텍트 판단 — **미룬다**, 회전 5 이후 팩 실측을 보고 다시 본다)
- foodservice(영양사: 메뉴 · 레시피 · 검식기준만 입력) · kimchi(레시피 BOM 열람 통제). 메뉴 × 역할 칸으로는 표현이 안 된다.
- 후보: `sys_permission` 에 `screen_id` 선택 컬럼(NULL = 메뉴 전체, 값 = 그 화면만 덮어씀). `rbac.cell` 이 화면 칸을 먼저 본다. 1차는 메뉴 단위로 넓혀 둔다(각 팩 D-504).
- **판단(회전 3 아키텍트)**: 이번 루프에서는 반영하지 않는다. 근거 — ① 권한 표 "48칸 전부 데이터"(G-C17 · goal.md §6)와 SYS-03 한 화면 · `rbac.cell(role, menu)` 서명 · `check_routes` 의 `없음 → 403 + 메뉴 숨김` 판정이 전부 메뉴 × 역할 모델 위에 있어, 화면 칸을 더하면 7명이 쓰는 접점(`rbac` · SYS-03 · 검사 도구 · 테스트)이 한꺼번에 바뀐다 ② 두 팩의 요구는 1차에서 다른 확장 지점으로 닿는다 — 영양사 역할은 `pack.yaml: permissions` 로 `bas` 입력을 주고 팩 훅 `validate_bas_item`(품목 구분 제한) · 팩 화면(`X-` · `require_fn` 은 팩 기능 ID)으로 범위를 좁힌다, 레시피 BOM 열람 통제는 BOM 을 팩 화면으로 옮기거나 `menus.hide` + 팩 화면으로 ③ 팩이 실제로 메뉴 단위로 풀지 못한 사례가 웨이브 B 실측에 남으면 그때 `screen_id` 컬럼(스키마 변경 0 — `sys_permission` 컬럼 추가는 테이블 수 불변)으로 다시 올린다.
- 바뀌면 고칠 곳: `app/rbac.py: cell/can_open/can_do` · `routers/sys.py` SYS-03 · `tools/check_routes.py` · `db/schema.sql: sys_permission`.

## D-503 `lineage.split/merge` 에 `process_id · equipment_id · attrs` 인자 · 상태: 가설
- printfilm CR-2. `make_product_lot` 은 받는데 둘은 안 받아 후가공 · 슬리팅 롤의 공정 · 설비를 같은 `tx` 에서 따로 `update lot` 해야 했다. **개발2 R1 에서 인자를 넣는다**(`interfaces.md` §4 갱신). 코어 변경이 아니라 R1 구현 범위.
- 회전 8(D-43): `split(qtys=…)` 로 수량을 **모두** 준 분할(팩 분할 계열 N ≥ 1 포함)은 부모에 남는 양을 잔량으로 두고 `v_lot_state` 도 그 잔량으로 판정한다(> 0 → `재고`). 수량을 하나라도 비우면 LOT 통째 분할 → 부모 `소진`.

## D-504 팩 ext 행을 같은 트랜잭션에 쓰는 훅 자리 · 상태: 가설
- foodservice ⑤ · printfilm(on_result_closed 에서 ext). `validate_<table>` 은 저장 전이라 새 행의 `id` 가 없다. **`after_save_<table>(cur, row, user)`** 훅을 추가한다(저장 직후 · 같은 tx · `row["id"]` 있음). `interfaces.md` §9 · `pack-contract.md` §5 에 추가 — 아키텍트 웨이브 D, 개발 R2 라우터는 `packs.hook("after_save_<table>")` 호출 자리를 미리 둔다.

## D-505 `on_order_status_changed` · `on_work_order_canceled` 훅 · 상태: 가설
- foodservice ③. 지시 취소 시 훅이 만든 `mat_requirement(source=hook)` 를 되돌릴 자리가 없다. 개발1 F-JOB-04 · 개발3 F-ORD-02/03 에 호출 자리를 둔다.

## D-506 G-P03 추적표는 N:1 · 1:N 매핑을 허용한다 · 상태: 가설
- foodservice ④(화면 49 중 N:1 1건 · 1:N 4건). `tools/import_design.py` · `check_trace --pack` 은 산출물 ID 하나가 코어/팩 화면 여럿에, 여럿이 하나에 가는 것을 고아로 세지 않는다. 고아 = 어느 화면에도 안 간 ID.

## D-507 코어 `job_lot` 은 BOM 소요 줄이다 — Job-Lot-Roll 매핑 화면은 코어에 없다 · 상태: 가설
- printfilm CR-1. 1차 printfilm 은 Job → Roll 로 간다(생산 LOT 중간 단계 없음). 필요해지면 팩 화면 `X-JOB-01`.

## D-508 `kpi_extra(frm, to, by=None)` · 상태: 가설
- foodservice ⑤ · kimchi C-8. `by` 인자를 받고 `kpi_snapshot` 배치가 `kpi_extra` 결과도 저장한다. 개발3 R1.

## D-509 `bas_process_param.item_id` 선택 컬럼 · 상태: 차단
- kimchi C-2(품목별 세척 · 절임 범위). 스키마 변경이라 아키텍트 웨이드 D 판단. 1차는 공정 단위 범위만.

## D-601 출하 라벨 경로 · 상태: 가설
- 디자이너3. `function-list.md` 에 없다. `GET /shp/shipments/{id}/label`(SHP-02 인쇄 버튼, 기능 수에 안 센다 — D-12 와 같은 취급). 바코드 값 = 출하 번호. LOT 라벨은 `?size=100x50|50x30` 한 요청 한 크기.

## D-602 현황판 `stats.board()` 키 · 지표 상태 · 상태: 가설
- 디자이너3 절(`docs/design/README.md`)의 키 목록이 1차 계약. 지표 `status` 는 서버 계산(값 ≥ 목표 good · ≥ 95 % warn · 그 밖 critical · 목표 NULL → 없음). 개발3 이 확정하고 README 를 갱신한다. 다크 전환 조건 미확정.

## D-603 `static/app.js` 동작 사양 = 디자이너2 절 S-01~S-14 · 상태: 가설
- 스캔칸 포커스 · 알림 중 스캔 · 422 두 갈래 · 503 disabled. 템플릿 이식 때 `data-demo` · `.demo` · `[원형 전용]` 블록은 지운다.

## D-604 Web 에서 실적을 읽는 화면 · 상태: 확정(회전 5 개발1 — DEF-QA2-002)
- 디자이너1. POP-02 는 POP 전용이라 Web 실적 조회 화면 ID 가 없다. JOB-02 지시 현황의 지시 행에서 실적 목록으로 드릴다운(`GET /job/status?wo=`)으로 한다. 기능 수 불변.
- **회전 5 인자 형식 확정**: `?wo=` 는 지시 **id(숫자) 또는 지시 번호**(`W…` · 팩 접두 그대로) 둘 다 받는다 — 숫자만이면 id, 아니면 `work_order_no` 로 찾고 없으면 404. TRC-01/02 노드 링크(개발3 `_links.work_order`)는 번호를 넘긴다. JOB-03 `?id=` 도 같다(`job.wo_of_key`). 경로의 `{id}`(수정 · 종료 · 취소)는 숫자만(api-contract §1).

## D-605 개발용 역할 바로 로그인 버튼 · 상태: 확정(회전 5 아키텍트 — DEF-QA1-001 · QA3-001)
- `MES_ENV=dev` 일 때만 로그인 화면에 역할 4 버튼. 운영 빌드에는 없다.
- **회전 5**: `MES_ENV` 기본값을 `prod` 로(비거나 없으면 prod · `.env.example` 도 prod — `make setup` 이 새로 만드는 `.env` 는 prod). `POST /login/as` 는 `settings.dev_login_allowed(request)` = `MES_ENV=dev` **그리고** 요청 상대 주소가 루프백일 때만 — 아니면 404. `main.py` 미들웨어가 라우터 앞에서 같은 판정으로 404 를 주고, `routers/home.login_as` 도 이 함수로 바꾼다(개발1). 이름(`localhost` · `testclient`)은 루프백으로 치지 않는다 — 주소만. 프록시 뒤 운영은 dev 로 두지 않는다.



## D-107 사용자 ↔ 작업자 연결의 기준은 `sys_user.worker_id` · 상태: 가설
- 개발1 회전 4. F-SYS-01/02 가 `sys_user.worker_id` 를 등록 · 수정 · 해제(빈 값 → NULL)하고 POP-02 기본 작업자는 이것을 읽는다. BAS-07 의 `bas_worker.user_id` 와는 **동기화하지 않는다**(쓰는 테이블 계약 그대로). 시드는 `seed_dev1` 이 `field ↔ WK-EX-02`(양쪽 비었을 때만). 팩 계정은 `seed/users.csv` 의 `worker_code`(D-36 계정 규칙).

## D-108 메인 카드 「오늘 건수」 는 `stats.today_counts()` · 라벨 `home.TODAY_LABELS` · 상태: 가설
- 개발1 · 개발3 회전 4. 키 = 코어 모듈 코드 12 → int(0 도 숫자). 출처 문장 `stats.TODAY_COUNT_SOURCES`(디자이너3 `home/main.html` 머리 주석 가설 그대로). 팩 모듈 · 함수 없는 버전은 `None` → 화면 `미수집`. 라우터 SQL 0(집계는 stats 뿐).

## D-109 이관 실행 폴더(`MES_MIGRATE_DIR`) · 상태: 가설
- 개발1 회전 5 · DEF-QA2-003. 현장 이관 파일을 서버 어느 폴더에 둘지 정본에 없다. **기본값**: 값이 없으면 SYS-06 은 폴더 칸에 `미확정 (D-109)` 을 그리고 F-SYS-15 이관 실행은 422(`dir`). 파일 업로드 경로는 두지 않는다. 사람이 경로를 정하면 `.env` 의 `MES_MIGRATE_DIR` 하나만 채운다.
- 바뀌면 고칠 곳: `.env`(값) — 코드 변경 없음. 표시 문구는 `routers/sys.migrate_dir_label`.

---

## 개발2 (웨이브 A R1·R2 · 2026-10-09)

## D-201 입고 번호 = 그 입고가 만든 원재료 LOT 번호 · 상태: 가설
- `mat_receipt.receipt_no` 는 유니크인데 `core.yaml: numbering` 8종에 입고 번호 종류가 없다. 1 입고 = 원재료 LOT 1 이므로 **`receipt_no = lot.lot_no`**(`LOT_MATERIAL` 채번 한 번). 새 종류를 지어내지 않는다.
- 바뀌면 고칠 곳: `routers/mat.py: receipt_create` · `core.yaml: numbering`(종류 추가 시 아키텍트).

## D-202 이상 번호 채번 종류 `ISSUE` · 상태: 가설
- `qua_issue.issue_no` 유니크 · 채번 종류 없음. `sys_number_rule(ISSUE, prefix Q, YYMMDD-, 3)` 행을 `db/seed_dev2.py` 가 `on conflict do nothing` 으로 넣고 `numbering.next("ISSUE")` 로 발번한다(코드는 종류명만 안다). `core.yaml: numbering` 에 `ISSUE` 를 넣어 `seed_core` 가 품도록 아키텍트에게 요청(`progress-dev2.md` §3).

## D-203 `lineage` 쓰기 함수의 `user` 인자 · 상태: 가설
- 훅 서명은 `(cur, row, user)` 인데 `interfaces.md` §4 의 lineage 쓰기 함수는 `by`(login_id)만 받았다. `validate_lot · after_save_lot · on_lot_created` 에 `rbac.User` 를 넘기려고 **선택 인자 `user=None`** 을 더했다(계약 뒤에 붙는 선택 인자라 기존 호출은 그대로). `by` 는 여전히 login_id.

## D-204 `collect.receive` 의 반환값 · 모르는 설비의 거부 기록 · 상태: 가설
- `api-contract.md` §4 는 재전송에 `duplicate: true` 를 요구하는데 §6 반환은 `int` 였다. **`ReceiveResult(raw_id, duplicate, unknown_tags, saved)`**(`int()` 가 raw_id)로 바꿨다. 모르는 설비의 거부 기록은 호출자의 트랜잭션이 422 로 되돌아가도 남아야 하므로 **자동 커밋(`conn.x`)** 으로 쓴다 — `collect` 가 쓰는 테이블은 변함없이 `ifc_collect_raw` · `eqp_collect` 뿐.

## D-205 측정값 매크로 서명 `mf.measure_fields(params, values, latest)` · 상태: 가설
- 매크로는 DB 를 읽을 수 없어 `process_id` 대신 라우터가 `measure.params_for(process_id)` 로 넘긴 `params` 를 받는다. 파이썬 쪽은 `app/measure.py`(params_for · parse_form · record · fill_collect · values_of · plan_fields). 검사 항목(`qua_insp_plan`)도 `measure.plan_fields` 로 같은 칸 모양.


## D-206 (kimchi) 센서 ↔ 절임통 연결 · 상태: 차단
- 개발3 kimchi 가 화면에 `미확정 (D-206)` 으로 쓴 번호를 대장에 둔다(개발2 대역이지만 이미 화면에 찍혀 있어 그대로). 염도 센서가 어느 절임통 배치에 붙는지(`SENSOR_TO_TANK`)는 현장 값 — 사람이 정할 때까지 알람의 `lot_id` 는 비운다. D-501 이 승인되면 `on_alarm_raised` 훅 안의 규칙이 된다.

## D-207 팩 분할 · 합병 관계는 N ≥ 1 (코어 `분할` · `합병` 은 N ≥ 2) · 상태: 가설
- 개발2 회전 4(개발3 15). 팩 base 분할 1 → 1 은 **부분 분할**(잔량은 부모에 남음). 부모 상태는 `v_lot_state` 규칙대로 — ~~분할 계보가 생기면 부모는 `소진`(통째)~~ **회전 8(D-43 확정)**: 분할 화살표가 전부 수량을 가지면 부모는 잔량으로 판정(잔량 > 0 → `재고` · 0 → `소진`), 수량 없는 분할 화살표가 하나라도 있으면 통째 `소진`. 코어 시나리오 10행 불변. **회전 7**: `lineage.split` 은 수량을 모두 준 분할의 남는 양을 부모 잔량으로 둔다(개발2) — 뷰 반영은 회전 8 에 끝남(D-43).

## D-208 분할 · 합병 자식의 `insp_status` 상속 `lineage.inherit_insp` · 상태: 가설
- 개발2 회전 4(개발3 16). 전부 합격 → 합격 · 불합격 하나라도 → 불합격 · 미검사 하나라도 → 미검사 · 그 밖(합격 + 조건부) → 조건부 · 부모 하나면 그 값. 팩의 `update lot set insp_status` 우회를 없앤다.

## D-209 `make_product_lot(merge_parent_ids=)` · F-POP-03 폼 `merge_lot_ids` — 「투입 + 합병 → 한 LOT」 · 상태: 가설
- 개발2 회전 4(개발3 19). 재고 생산 LOT 1개 이상을 새 실적 LOT 에 base 합병 화살표로 잇는다(별도 합병 LOT 없음). 소진 · 원재료 · 분할 관계 · 중복은 422. 코어 G-C06 시나리오(합병 API → 별도 LOT · 10행)는 그대로.


---

## 개발3 (R1 · R2 · 2026-10-09)

## D-301 이관 `lots` 가 SHIPMENT LOT 의 출하 헤더를 `34_shipments.csv` 에서 먼저 적재한다 · 상태: 가설
- `migration-files.md` §4 는 `21_lots.csv` 에 SHIPMENT 종류 LOT 을 두고 §5 `34_shipments.csv` 의 `ship_lot_no` 가 "21 에 있어야 한다" 고 했다. 그런데 `lot_shipment_chk`(kind_base = SHIPMENT ⇔ shipment_id not null)
  때문에 출하 헤더 없이는 SHIPMENT LOT 행을 넣을 수 없다 — 계약 순서(21 → 34)가 스키마와 맞지 않는다.
- **기본값**: `migrate lots` 가 SHIPMENT 종류 행을 만날 때 같은 폴더 `34_shipments.csv` 에서 `ship_lot_no` 가 그 LOT 인 헤더를 찾아 `shp_shipment` 를 먼저 upsert 하고 `lot.shipment_id` 를 채운다.
  헤더가 없으면 그 줄 오류. `migrate history` 의 34 는 같은 헤더를 다시 upsert(멱등) 하고 `lot.shipment_id` 를 맞춘다. 그래서 B-MIG-03 의 쓰는 테이블에 `shp_shipment` 가 더 들어간다(`function-list.md` 수정 요청 — progress-dev3.md §3).
- 바뀌면 고칠 곳: `src/mescore/migrate/importer.py: load_lots · _shipment_header_rows`.

## D-302 품질 집계의 `조건부` 는 합격에 세지 않는다 · 상태: 가설
- 디자이너3 절 "조건부는 합격에 세지 않는다(미확정 — D-nn)" 의 번호. `stats.quality.pass_rate = 합격 / 전체 × 100`, 조건부는 `cond_count` 로 따로 센다. 성적서 종합 판정은 불합격 1건이면 불합격 · 미수집(검사 없음)이 있으면 `미확정` · 조건부가 있으면 조건부 · 아니면 합격.
- 바뀌면 고칠 곳: `app/stats.py: quality` · `routers/shp.py: _summary`.

## D-303 메인 · 대시보드 · 출하 현황의 집계 함수 (`stats.today_counts` · `recent_activity` · `shipment_due`) · 상태: 가설
- 개발3 회전 4. `shipment_due` 의 `due_days = 출하일 − 수주 납기`(양수 = 지남) · `due_state` 지연/당일/앞섬 · 수주 없음 None. `recent_activity` = `sys_access_log` change 최신 순(≤ 5). 템플릿은 날짜 계산을 하지 않는다.

## D-304 목록 `total` = 조건 전체 건수(`count(*) over ()`) · 상한 앞에서 센다 · 상태: 가설
- 개발3 회전 4(ORD-01 · SHP-01 · SHP-03). 화면은 「전체 N건 · 최근 M건만」. 정렬은 D-37 `http.sort_clause` 로 옮긴다.

## D-305 이관 멱등 판정 = 이관 대상 테이블에서 이관이 만든 · 갱신한 행 수 diff 0 · 상태: 가설
- 개발3 회전 4. 같은 DB 를 여러 사람이 쓰므로 전체 행 수 diff 는 흔들린다 — 두 번째 `inserted == 0` + `created_by/updated_by = migrate` · `attrs.migrated_from` 행만 센다. gate G-C15 도 대상 테이블로 좁혀 둔 것(회전 3)과 같다.

---

## 디자이너 (회전 4 · 2026-10-09 — `docs/design/README.md` 「이식 요청」 에서 결정이 필요한 것)

## D-606 현황판 야간(다크) 전환 조건 · 상태: 차단
- 디자이너3 요청 3. 템플릿은 **가설로 `?theme=dark` → `html[data-theme="dark"]`**(그 밖은 `light` 고정 · `prefers-color-scheme` 무시)를 찍는다 — 이것이 지금 동작이다. 정할 것: 시각 고정(예: 18시~6시) · 설정값(`MES_BOARD_THEME`) · 쿼리만 중 하나. 현장 현황판 위치(조도)를 아는 사람이 정한다. 그때까지 쿼리만.

## D-607 채널 틀은 `base.html` 하나 — POP · 모바일 · Web · 상태: 가설
- 디자이너1 회전 4(디자이너2 요청 1). `base.html` 이 채널 틀 셋을 그린다(ch-pop: 헤더 + 상단 탭 · ch-mobile: `.m-frame` + 하단 탭 4 · 그 밖: Web 3단) — `{% block pop_body %}` · `{% block mobile_body %}`. `{% block body %}` 를 통째로 바꾼 화면(TRC · KPI · 메인 · 대시보드)도 틀 안에 들어간다. `pop/_layout.html` 의 모바일 틀은 base 로 합쳤다. 디자이너2 · 3 은 다음 회전에 `mobile_body` 로 본문을 나눈다.

## D-40 G-P01 R10 — README 에 적힌 템플릿 덮어쓰기는 PASS · 상태: 가설
- `pack-contract.md` §4 R10 은 "코어 템플릿을 덮어쓴 파일 목록을 README.md 에 적는다" 다. 지금까지 `check_pack` 은 전부 적혀 있어도 WARN 을 냈고, `goal.md` §2.8 은 WARN 을 통과로 보지 않아 규칙을 지킨 팩(foodservice 1 · printfilm 3)이 종료 조건에 걸렸다.
- 오케스트레이터(회전 5 판정)가 판정을 고쳤다: 전부 README 에 있으면 PASS(목록은 실측 칸에 남는다) · 하나라도 없으면 FAIL. 덮어쓰기 자체는 `spec.md` §3.4 의 허용된 탈출구라 실패가 아니다.

## D-41 열린 투입으로 잔량 0 인 PRODUCT LOT 은 종료 전이라도 `소진` · 상태: 확정(회전 7 아키텍트 — DEF-QA2-008)
- QA2 회전 6: §3.4 회전 5 문장 「열린 투입은 상태를 바꾸지 않는다」 때문에 LOT 20 을 종료 전 실적에 20 투입하면 잔량 0 인데 `재고` — 화면 · 추적에 거짓 「재고」 가 보이고, `assert_usable`(상태만 봄)이 수량 없는 투입 · 분할 · 합병 · 종료 합병 옵션 · 출하 스캔을 받아 같은 LOT 이 두 경로로 나갔다.
- **결정**: `v_lot_state` PRODUCT 는 출하 → `출하`, `분할|합병|생산` 부모 → `소진`(통째) 다음에 **잔량(`v_lot_stock` — 계보 + 종료 전 실적의 투입) ≤ 0 이면 `소진`** — 종료 전이라도. 열린 `pop_input.qty` NULL(수량 모르는 투입)도 통째로 보아 `소진`, LOT 수량 NULL 인데 투입(계보 · 열린)이 있으면 `소진`. 투입을 취소하면 다시 `재고`(뷰 계산이라 저장 상태 없음). 회전 5 의 「열린 투입은 상태 불변」 문장은 폐기한다.
- 쓰기 경로는 이중으로 막는다 — 뷰가 `소진` 이면 `assert_usable` 이 422 이고, 개발2 는 잔량(열린 투입 포함) ≤ 0 · 잠금(DEF-QA2-009)을 쓰기 함수에서 따로 본다. 둘이 같은 `v_lot_stock` 을 본다.
- 바뀌면 고칠 곳: `db/views.sql`(`v_lot_state`) · `contracts/db-schema.md` §3.4 · `tests/test_arch_schema.py::test_product_lot_open_input_to_zero_is_consumed`.

## D-42 운영 HTTP 사내망에서 세션 쿠키 `Secure` 를 끄는 설정 · 상태: 차단(사람 결정)
- QA3 회전 6 재현: `MES_ENV=prod` 를 HTTP 로 LAN 주소에서 열면 `POST /login` 303 → `/` 303 → `/login` — 서버는 세션을 발급하지만 브라우저가 `Secure` 쿠키를 저장하지 않아 로그인이 안 된다(루프백만 예외). D-605 · DEF-QA3-007 로 운영은 `Secure` 가 기본이다.
- **아키텍트 제안**: ① 기본 — 운영은 TLS 종단(사내 리버스 프록시 · HTTPS) 뒤에 둔다. 코드 변경 없음. 프록시 뒤면 uvicorn `--proxy-headers --forwarded-allow-ips=<프록시 주소>`. ② HTTP 사내망만 쓰기로 정하면 `MES_COOKIE_SECURE=0`(명시 설정 · 기본 1 · `.env.example` 에 설명) 을 `settings` 에 두고 `main.py` `SessionMiddleware(https_only=…)` 가 그 값을 본다. dev 모드로 대신하지 않는다(`/login/as`).
- 사람이 정할 것: HTTPS 로 갈지 · TLS 를 어디서 끊을지(프록시 · 인증서) · HTTP 운영을 허용할지(②를 코드에 넣을지). 결정 전에는 **코드에 넣지 않는다** — 운영 문서(`CLAUDE.md` 환경 절)에 제안만.
- 바뀌면 고칠 곳(② 채택 시): `app/settings.py` · `app/main.py`(`https_only`) · `.env.example` · `tests/test_arch_smoke.py::test_logout_is_post_only_and_cookie_flags`.

## D-43 부분 분할(수량을 모두 준 분할)의 부모 상태를 잔량으로 — `v_lot_state` 반영 · 상태: 확정(회전 8 아키텍트)
- 개발2 회전 7(`3fcc668` · interfaces §4): `lineage.split` 이 수량을 모두 준 분할(20 → 5+5)은 남는 10 을 부모 잔량으로 둔다. 짝이 되는 뷰 규칙 — 「분할 화살표가 전부 수량을 가지면 투입처럼 잔량으로(잔량 > 0 → 재고) · 수량 없는 분할 · 합병 · 생산은 통째 소진」 — 을 회전 7 아키텍트가 `views.sql` 에 넣어 돌려 보았다.
- 결과: 코어 시나리오가 깨진다 — `test_lineage_scenario` 의 합병 100 → 분할 30·30·30 은 합병 LOT 이 잔량 10 `재고` 가 되어 `test_forward_trace_and_states` · `test_guards_422`(소진된 LOT 재분할 422) · `test_pop_scenario::test_core_scenario_through_api_is_10_rows` 4건 FAIL. QA2 `check_data` G-C04 · G-C07 뷰 재구현(「분할 = 통째 소진」)과 kimchi S4 기대값(`k1_state: 소진` · 잔량 400 새 LOT · D-515)도 현행 규칙을 적고 있다. 이번 회전 종료 판정을 깨지 않으려고 **뷰는 현행 유지**(분할 화살표 하나라도 있으면 부모 `소진`).
- 지금 상태: 쓰기 경로는 잔량을 남기지만 뷰는 부모를 `소진` 으로 본다 — 남는 수량은 재고 화면에서 보이지 않고 다시 쓸 수도 없다(QA2 참고 WARN 「부분 분할 — 남는 수량」 그대로). 거짓 「재고」 는 생기지 않는다(안전한 쪽).
- 회전 8 할 일: ① `views.sql` 위 규칙 + `db-schema.md` §3.4 문장 + `test_arch_schema` ② 코어 시나리오 분할 수량을 30·30·40(합 = 합병 100)으로 바꾸거나 기대값을 「합병 잔량 10 재고」 로(개발2 · `db-schema.md` §3.3 표와 맞춤) ③ QA2 `check_data` 재구현 ④ kimchi S4 「잔량 유지」(K1 재고 · 1 LOT — 기획자3 · 개발3). D-207 의 「분할 계보가 생기면 부모는 소진」 문장은 그때 바꾼다.
- 바뀌면 고칠 곳: `db/views.sql` · `contracts/db-schema.md` §3.4 · `contracts/interfaces.md` §4 · `tests/test_lineage_scenario.py` · `tests/test_pop_scenario.py` · `tools/check_data.py` · `packs/kimchi/gates.yaml` S4.
- **회전 8 결정(확정)**: `v_lot_state` PRODUCT — 출하 → `출하` · **합병 · 생산 부모, 또는 수량 없는(qty NULL) 분할 화살표가 하나라도 있는 부모** → `소진`(통째) · 그 밖(투입 · 수량을 모두 준 분할 · 열린 투입 · 아무것도 없음)은 잔량(`v_lot_stock` = `lineage.remaining`)으로 — 잔량 ≤ 0 · 수량 모르는 투입 · LOT 수량 NULL 인데 투입/분할이 있으면 `소진`, 아니면 `재고`. 20 → 5+5 는 부모 잔량 10 `재고`.
- 코어 시나리오: 합병 100 → 분할 **30·30·40**(합 = 합병 수량 · `db-schema.md` §3.3) — 합병 LOT 잔량 0 → `소진` · 10행 · 역/정방향 · 분할 ③ 재고 그대로. 기대값을 낮춘 것이 아니라 시나리오가 합병 LOT 을 다 나누도록 맞춘 것(수량 없는 1:3 이면 통째 소진 규칙으로 같은 결과).
- 고친 곳(회전 8): `db/views.sql` · `db-schema.md` §3.4 · `interfaces.md` §4 · D-207 · D-503 · `tests/test_arch_schema.py`(시나리오 30·30·40 · 새 `test_product_lot_partial_split_keeps_remainder`) · `tests/test_lineage_scenario.py`(30·30·40 · 잔량 초과 25+20 · 팩 N=1 부분 분할 부모 재고) · `tests/test_pop_scenario.py`(30,30,40) · `tools/check_data.py`(뷰 재구현 · 부분 분할 행 기대 PASS) · `tools/check_security.py`(E2E 분할 30,30,40) · kimchi `gates.yaml` S4 · `routers/age.py`(`split(count=1)`) · `tests/test_scenario_aging.py` · `README.md` D-515. 7 DB 에 `create or replace` 재적용.

## D-44 수량 없는 분할 부모의 잔량 표시 (DEF-QA2-011 · 경미) · 상태: 가설
- 수량 없이 분할한 부모는 `v_lot_state = 소진` 인데 `v_lot_stock.remain_qty` 는 LOT 수량 그대로다(분할 화살표 qty NULL). 쓰기 경로는 상태를 먼저 보므로 다시 쓰이지 않는다 — 데이터 무결성 문제가 아니라 표시 문제다(POP-03 배너 · 추적 노드에 「소진 · 잔량 10」).
- 고치려면 `views.sql` `v_lot_stock` · `lineage.remaining` · QA2 `check_data.my_lot_view` 세 곳이 같은 문장을 바꿔야 한다(「통째 소비 부모(합병 · 생산 · 수량 없는 분할)의 잔량은 0」). 종료 판정 직전(회전 8)이라 미루고 다음 작업 회전의 첫 항목으로 둔다(아키텍트 · 개발2 · QA2 동시).
- QA2 참고 WARN: 합병 `qty` 상한 없음(부모 화살표 합 15 에 1000 허용) — 계약 문장대로라 결함 아님. 물량 보존을 강제할지 설계 확인 대상으로 같이 둔다.

## D-45 메인(IA) 하위 메뉴 — 기능표 · 업무 프로세스 · 시스템 이름 Rodem MES Solution · 상태: 확정
- 사용자 요청(2026-10-09). 메인(CMN-02) 아래에 하위 메뉴 3: 「모듈 지도」(`/` 기존) · 「기능표」(`/main/functions` — `function-list.md` 화면 기능 132 + 이관 4 를 모듈별로, 지금 역할의 사용 가능 여부 표시) · 「업무 프로세스」(`/main/processes` — 화면을 엮은 업무 흐름 10 유형, 데이터는 `app/guide.py`).
- 두 화면은 CMN-02 의 하위 탭이다 — 화면 51 · 기능 132 수에 세지 않는다(읽기 전용 안내 · 어떤 테이블에도 쓰지 않는다). 경로가 모듈 접두가 아니어서 고아 라우트 판정 대상이 아니다.
- 업무 프로세스 단계는 화면 ID 로만 잇는다 — 경로 · 권한 · 채널은 nav · rbac 가 판정(권한 없는 단계는 흐림). 문구는 코어 중립어 + `t()` 라 팩을 올리면 업종 말로 보인다.
- 코어 단독 시스템 이름 `core.yaml: system_name` = **Rodem MES Solution**(팩은 팩 이름 그대로).

## D-46 메인 › 도메인별 프로세스 — 업종 카탈로그는 코어 밖 `domains/*.yaml` · 상태: 확정
- 사용자 요청(2026-10-09). 메인 하위 탭 「도메인별 프로세스」(`/main/domains`)에 김치 · 급식 · 인쇄(필름) · 금속 가공 공장의 공정 흐름 · LOT 모델 · 핵심 관리점 · 지표 · 설비 · 확장 지점(E1~E7) · 용어 치환 · 프로세스 유형(도메인마다 5)과 단계별 화면을 보인다.
- 업종 문장은 코어 금지어 규칙(G-C23) 때문에 코어 코드에 두지 않는다 — 저장소 루트 `domains/<도메인>.yaml` 이 원본이고 코어(`app/domains.py` · `home/domains.html`)는 읽어서 그리기만 한다. 파일을 하나 더 두면 도메인이 늘어난다. 업종 문장에는 `t()` 를 걸지 않는다(이미 그 업종 말).
- 단계 화면 = 코어 화면 ID · 그 도메인 팩의 `X-` 화면 · 아직 없는 제안 화면 셋으로 가른다. 팩 화면은 그 팩을 올렸을 때만 링크된다.
- 김치 · 급식 · 인쇄는 참조 팩(packs/kimchi · foodservice · printfilm) 기획 · 구현에서 옮겼다. **금속 가공은 팩이 없는 설계 제안**이다 — 실제 회사 산출물이 오면 그것이 우선하고, 외주 표면처리(M04)는 코어에 외주 모듈이 없어 코어 변경 요청 후보로 적었다.

## D-47 MES AI Agent — 선택 모듈 `mesagent` (코어 밖) · SQL 조회 + 문서 RAG 멀티 에이전트 · 상태: 확정
- 사용자 요청(2026-10-09). 사이드바 맨 끝 「MES AI Agent」 메뉴(`/agent` 질문하기 · `/agent/about` 에이전트 구성)에서 자연어 질문을 MES DB 조회(SQL)와 문서 검색(RAG)으로 답한다.
- 코어(`src/mescore/app/**`)는 AI · 네트워크 라이브러리를 들이지 않는다(G-C12). 그래서 에이전트는 별도 패키지 `src/mesagent` 이고 `.env` 의 `MES_ADDONS=agent` 로만 켜진다 — 코어는 `mes<addon>.router` 의 `router` · `MENU` 를 읽어 붙이기만 한다(`settings.addons` · `main.py` · `templating` · `base.html`). 끄면 메뉴 · 라우트가 모두 사라진다.
- 에이전트 6: ① 라우터(LLM · 구조화 출력 — 의도 data/docs/both · 테이블 선택) ② 스키마 탐색(코드 — information_schema 컬럼 · 외래키 + `db-schema.md` 설명) ③ SQL 작성(LLM · 구조화 출력) ④ SQL 실행(코드 — 실패 시 오류를 ③에 돌려 최대 3회 자기수정) ⑤ 문서 검색(BM25 · 한글 2-gram · 질문 말투 조각 제외) ⑥ 답변(LLM — 조회 결과 · 문서 조각만 근거).
- LLM = Anthropic SDK · 모델 `claude-opus-5-5`(`MES_AGENT_MODEL` 로 바꿈) · 서버 측 대체 모델 허용. 키(`ANTHROPIC_API_KEY`)는 로컬 `.env` 에만 — 없으면 501 「LLM 미구성」 과 문서 검색 결과만, LLM 호출 실패는 502.
- 안전: SELECT/WITH 한 문장만 · 쓰기/관리/파일/네트워크 함수 · 시스템 카탈로그 차단 · 읽기 전용 트랜잭션 · 5초 · 최대 200행 · 항상 롤백. 역할 권한표(`rbac.can_read_menu`)로 읽을 수 있는 모듈의 테이블만, `sys_session` · `sys_user` · `sys_number_seq` 는 어느 역할에도 안 준다. 질문 · SQL · 행 수는 접근 로그(SYS-04 · screen `AGENT`)에 남는다. 대화는 세션별 메모리 10개(저장 테이블 없음).
- 시험: `tests/test_agent.py` — 가짜 Claude 응답기로 네트워크 없이. 실제 API 종단 확인은 키가 생긴 뒤.
- 판정: goal.md · spec.md 는 AI Agent 를 코어 범위 밖(선택 팩 `agent`)으로 둔다. 그래서 `make gate` · `gate-full` 은 `MES_PACK=` 처럼 `MES_ADDONS=` 로 선택 모듈을 끄고 코어를 판정한다. G-C12 의 `ai|agent` 라우트 금지는 그대로이며, 코어에 에이전트가 섞이면 여전히 FAIL 이다. 에이전트 자체의 안전성은 `tests/test_agent.py` 로 확인한다(SQL 관문 · 읽기 전용 · 역할).

## D-48 MES AI Agent — 호출어 「로뎀」 · 음성 질의/답변 · 오케스트레이터 · 정형 지표 · 상태: 확정
- 사용자 요청(2026-10-09). D-47 의 선택 모듈 `mesagent` 안에서만 바꾼다(코어는 `agent/*.html` 템플릿만).
- **호출어**: 질문이 「로뎀」(로뎀아 · 로뎀님 · 앞의 음/저기 허용)으로 시작할 때만 답한다 — 글 · 음성 모두. 부르지 않으면 `ignored` 로 돌려주고 LLM · DB 를 부르지 않는다. 「로뎀」 만 부르면 "네, 말씀하세요". 음성 인식이 받아 적는 변형(로댐 · 노뎀 · 로덤 · 로템 · rodem)도 호출로 본다. `MES_AGENT_WAKE` 로 바꾼다.
- **음성**: 브라우저 내장 음성 인식(ko-KR · 연속 듣기)과 음성 합성만 쓴다 — 서버는 음성을 받지 않고 글만 받는다. 스크립트는 선택 모듈이 `/agent/voice.js` 로 준다(코어 `app.js` 와 따로). 답을 읽는 동안 마이크를 멈추고 다 읽으면 다시 듣는다. 음성 인식은 HTTPS 또는 localhost 에서만 켜지고(브라우저 규칙), Chrome 의 인식은 브라우저 제조사의 인식 서버를 거친다 — 사내망 운영 전에 확인할 것.
- **오케스트레이터**: ① 규칙 — 지표 낱말(재고 · 출하 · 생산 · 입고 · 불량 · 작업지시) + 양/기간 신호가 있고 세부 조건(번호 · 순위 · 비교 · 목록)이 없으면 **정형 지표 SQL** ② 아니면 LLM 라우터가 **DB · SQL 조회 / RAG 문서 조회 / 둘 다 / 일반 대화** 를 고른다 ③ LLM 미구성이면 규칙 대체 — 문서 신호면 RAG 발췌 답(200), 자유 형식 데이터 질문은 501.
- **정형 지표** 6: 재고량(현재) · 생산량 · 출하량 · 입고량 · 불량률 · 작업지시 현황 — 기간 오늘(기본) · 어제 · 그제 · 이번 주 · 지난주 · 이번 달 · 지난달 · 최근 N일. SQL 은 카탈로그(`mesagent/metrics.py`)에 고정하고 같은 SQL 관문 · 읽기 전용 실행 · 역할 테이블 검사를 거친다. 숫자 문장도 코드가 만든다(LLM 이 숫자를 다시 쓰지 않음 · 음성으로 읽어도 같음). 출하 수량은 계보 「출하」 화살표 qty 로 센다(출하 LOT 의 qty 는 비어 있다 · db-schema §3.3).
- **추천 질의 데이터**: `make sample-today`(`scripts/sample_today.py`)가 오늘 날짜 입고 12 · 작업지시/생산실적 10 · 공정 검사 · 출하 6(승인 4)을 실제 API 로 넣는다(`(예시) 오늘 데이터` · 하루 한 번). 날이 바뀌면 다시 돌린다. 테이블은 하나도 만들지 않는다(52 그대로).

## D-49 AI Agent — 현장 역할도 재고량 · 생산량 조회 (품목 테이블 공유) · 상태: 확정
- 사용자 요청(2026-10-10). 현장 역할은 기준정보(bas) 메뉴 권한이 없어 정형 지표의 품목 이름 조인(`bas_item`)에서 막혔다.
- 코어 권한표(goal.md §6 · 48칸 · D-13)는 바꾸지 않는다. 에이전트의 테이블 허용 규칙(`mesagent/schema.py` SHARED)에서만 `bas_item` 을 **품목을 화면에 보여 주는 업무 모듈**(job · pop · mat · qua · shp · trc · ord) 중 하나라도 읽으면 허용한다. 현장 POP 화면이 이미 품목 코드 · 이름을 보여 주므로 새로 드러나는 정보는 없다.
- 결과: 현장 역할이 재고량 · 생산량 · 입고량 · 불량률 · 작업지시 현황을 조회한다. 출하량은 거래처(`bas_partner`)가 필요해 여전히 막힌다. 그 밖의 기준정보(BOM · 공정 측정값 · 거래처) · 시스템 테이블도 그대로 막힌다.

## D-50 Docker 배포 — PostgreSQL 17 + 앱 + Caddy HTTPS · 상태: 확정
- 사용자 요청(2026-10-10). Hostinger VPS Docker Manager 배포용으로 `Dockerfile` · `docker-compose.yml` · `docker/entrypoint.sh` 를 둔다. Caddy 설정은 compose 명령줄이라 서버에 저장소 파일이 없어도 된다(`MES_BUILD_CONTEXT` 로 GitHub 주소에서 빌드).
- D-42 의 두 갈래 중 **TLS 종단(리버스 프록시 · HTTPS)** 을 택했다 — Caddy 가 `MES_DOMAIN` 으로 인증서를 받고 앱은 `MES_ENV=prod`(Secure 쿠키) 그대로. 「Secure 끄기」 설정은 만들지 않았다(사내망 HTTP 운영은 D-42 그대로 결정 대기).
- 앱은 Caddy 고정 주소(10.213.71.10)의 전달 헤더만 믿는다(`--forwarded-allow-ips`). DB 는 내부망에만 있고 포트를 열지 않는다.
- 비밀값은 이미지 · 저장소에 넣지 않는다. 환경변수로 주지 않으면 첫 기동 때 난수로 만들어 볼륨 `/data/secrets.env` 에 두고 시드 비밀번호를 앱 로그에 한 번 찍는다.
- 빈 DB 면 스키마 · 뷰 · 시드(팩 포함)를 만든다. `MES_SAMPLE=1` 이면 샘플(예시)과 오늘 데이터를 넣는다. 샘플 스크립트는 운영 Secure 쿠키 때문에 내부 클라이언트를 https 주소로 쓴다.
- 시간대 Asia/Seoul (앱 · DB) — 「오늘」 지표가 한국 날짜로 잡힌다.
- 로컬 검증(2026-10-10): 새 볼륨 기동 → HTTPS 200 · 비밀값 생성 · 로그인(Secure 쿠키) · AI Agent 지표 답 · 재기동 후 세션 유지 · HTTP → HTTPS 308 · `/login/as` 404.
- Hostinger VPS(srv1934103) 사정: 80 은 다른 앱(afc200)이 쓴다 → `MES_HTTP_PORT` 를 다른 번호로 두고 443 만으로 인증서를 받는다(TLS-ALPN-01).
- compose 내부망은 10.213.71.0/24 (Caddy 10.213.71.10) — 앱이 많은 서버에서 Docker 기본 대역(172.16~31)과 겹치지 않게.
- **배포(2026-10-10)**: Hostinger VPS srv1934103 · Docker Manager 앱 `rodem-mes` · https://srv1934103.hstgr.cloud (Let's Encrypt) · HTTP 8131 → HTTPS 308 · `MES_SAMPLE=1`. Docker Manager 는 build 를 하지 않아 첫 배포가 「이미지 없음」 으로 실패했고, 웹 콘솔에서 `/docker/rodem-mes` 의 `docker compose up -d --build`(GitHub main 에서 빌드)로 올렸다. 확인: /health 200 · 로그인 화면 200 · 로그인 없이 /agent 401 · `/login/as` 404 · DB 5432 닫힘. 시드 계정 비밀번호는 서버 앱 로그(첫 기동 줄)와 볼륨 `/data/secrets.env` 에만 있다.
