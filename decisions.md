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

## 기획 · 디자인 결정 후보 (회전 1 · 오케스트레이터가 옮김 · 2026-10-09)

기획자 3명의 `packs/<팩>/README.md` 끝 "결정 후보 D-5nn" 절과 디자이너 3명의 `docs/design/README.md` 에서 코어에 닿는 것만 옮겼다. 팩 안에서만 유효한 결정은 각 팩 README 가 원본이다.

## D-501 세 팩 공통 — 설비 단위 임계값 · 이탈 알람이 코어에 없다 · 상태: 코어 변경 요청
- foodservice(냉장 5 ℃ · 냉동 −18 ℃ 온도조절기 이탈) 와 kimchi(냉장 온습도 · 염도 센서 이탈) 가 같은 것을 요구한다. E3 는 **공정** 측정값뿐이라 설비 수집값의 범위 판정 · 알람 발생/해제 이력이 코어 EQP 화면에 못 나온다.
- 후보: `bas_equipment_param`(설비 · 태그 · 하한 · 상한) + `collect.receive` 가 범위 판정해 `eqp_collect.deviated` 표시 + `eqp_alarm`(발생 · 확인 · 해제). 테이블 52 → 54 가 된다.
- 1차 웨이브 B 는 팩 테이블(`x_<팩>_env_alarm`)로 가고, 웨이브 D 에서 아키텍트가 코어 반영 여부를 정한다. 반영하면 두 팩의 알람 테이블을 지운다.

## D-502 두 팩 공통 — 화면 단위 권한 예외 · 상태: 코어 변경 요청
- foodservice(영양사: 메뉴 · 레시피 · 검식기준만 입력) · kimchi(레시피 BOM 열람 통제). 메뉴 × 역할 칸으로는 표현이 안 된다.
- 후보: `sys_permission` 에 `screen_id` 선택 컬럼(NULL = 메뉴 전체, 값 = 그 화면만 덮어씀). `rbac.cell` 이 화면 칸을 먼저 본다. 1차는 메뉴 단위로 넓혀 둔다(각 팩 D-504).

## D-503 `lineage.split/merge` 에 `process_id · equipment_id · attrs` 인자 · 상태: 가설
- printfilm CR-2. `make_product_lot` 은 받는데 둘은 안 받아 후가공 · 슬리팅 롤의 공정 · 설비를 같은 `tx` 에서 따로 `update lot` 해야 했다. **개발2 R1 에서 인자를 넣는다**(`interfaces.md` §4 갱신). 코어 변경이 아니라 R1 구현 범위.

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

## D-604 Web 에서 실적을 읽는 화면 · 상태: 가설
- 디자이너1. POP-02 는 POP 전용이라 Web 실적 조회 화면 ID 가 없다. JOB-02 지시 현황의 지시 행에서 실적 목록으로 드릴다운(`GET /job/status?wo=`)으로 한다. 기능 수 불변.

## D-605 개발용 역할 바로 로그인 버튼 · 상태: 가설
- `MES_ENV=dev` 일 때만 로그인 화면에 역할 4 버튼. 운영 빌드에는 없다.
