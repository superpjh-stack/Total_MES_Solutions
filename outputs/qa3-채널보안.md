# QA3 — 채널 · 보안 · 팩 격리 · 브라우저 E2E (회전 4 · 2026-10-09)

> QA3 는 **고치지 않는다.** 재고 적는다. 판정 = 아래 명령의 출력. 전용 DB `mes_qa3_db`(빈 DB → `schema.sql` + `views.sql` + `seed_core` 로 시작) · 서버 포트 **8053**(코어) · 8054(`_timing` 팩).
> 비밀번호는 `.env` 에서만 읽는다 — 출력 · 리포트 · 캡처 어디에도 값이 없다(로그인 칸은 가려진 password 입력, 캡처는 로그인 뒤 화면만). 시험 계정 비밀번호는 실행마다 `secrets.token_urlsafe` 난수.
> 기준 커밋 `5d9c581`(HEAD) + 미커밋 `src/mescore/tools/check_security.py`(이 회전 QA3 산출).

## 1. 판정 요약

| 게이트 | 판정 | 실측 (요지) |
|---|---|---|
| G-C13 4채널 | **PASS** | 검사 8 전부 PASS — POP 13 화면 data-scan 0/1 · 포커스 · 없는 번호 422 재렌더 6 화면 · 같은 라벨 2회 = `pop_input` +2 · 모바일 8 화면 390px `scrollWidth == clientWidth` · 현황판 5초 폴링 1배 · 503 stale 유지 · 채널 밖 403 · DB 끊김 503 |
| G-C14 출력물 | **PASS** | 4종 인라인 SVG · 외부 요청 0 · **zxing 이미지 해독값 = 번호** · LOT 라벨(100×50 · 50×30) → POP-03 · POP-04 스캔칸 → 그 LOT · 지시서 → POP-02 · 출하 라벨 → SHP-02 · 성적서 → SHP-04 |
| G-C15 이관 | **PASS** | 4 명령 실제 적재 2회 — 2회째 적재 0 · 대상 20 테이블 diff 0 · dry-run 쓰기 0 · 깨진 파일 → 종료 코드 1 + 리포트 행 + `sys_migration_log.errors/error_detail` |
| G-C16 ERP | **PASS** | push 501 D-02 · `POST /ifc/erp/{id}/retry` HTTP **501** `undecided`(200 위장 0) · 행 `미확정` 유지 · '전송' 0 · 수집 토큰 틀림/없음 401 · 없는 설비 422 + 거부 기록 |
| G-C17 (일부) | **PASS** | 역할 PROD→QA 변경이 재로그인 없이 다음 요청부터(검사 등록 403→200 · 계획 등록 →403). 48칸 전수는 QA1 |
| G-C18 접근 로그 | **PASS** | 시험 계정 login_ok · login_fail · view · change 각 1 → SYS-04 에 보임 · 로그에 틀린 비밀번호 0 · 로그아웃/중지/비밀번호 변경/잠금 뒤 다음 요청 401 |
| G-C19 비밀 | **PASS** | 저장소 대상 504 파일 중 `.env` 비밀 값 든 파일 0 · `.env` · `backups/` gitignore · 하드코딩 비밀 리터럴 0 · 팩 외부 CDN 0(R11) — **단 DEF-QA3-001(개발용 무비밀번호 로그인 기본 켜짐)** |
| G-C20 백업 | **PASS** | backup rc 0 · restore-check rc 0 · 「테이블 52개 전부 복구 · 테이블별 행 수 일치」 |
| G-C22 브라우저 한 바퀴 | **PASS** | 23 단계 전부 화면에서 통과 · 막힌 단계 0 · 캡처 23장 `outputs/e2e/core/` (결함 DEF-QA3-002 는 화면에서 드러났으나 흐름은 막지 않음) |
| G-P01 팩 격리 | **FAIL** | R2 · R4~R8 0 · R11 0 이나 ① R1 해시 — QA 도구 3 파일(아키텍트 재해시 대상, 팩 결함 아님) ② R9 printfilm 팩 올린 채 `test_arch_smoke` 1 FAIL(DEF-QA3-004) ③ 팩 폴더 지운 worktree 코어 `tests/` 274 passed · **1 failed**(DEF-QA3-003 — 팩과 무관, 원본 트리에서도 같음) |
| G-P06 착수 시간 | **PASS** | `outputs/pack-timing.md` — 단계 1~2 실측 약 20초(기계 시간) ≤ 4h |

gate 가 읽는 판정 행:

```
G-C22  브라우저 한 바퀴 — 코어 단독 · 역할 4  PASS  23 단계 전부 통과 · 막힌 단계 0 · 캡처 outputs/e2e/core/01~23 · check_security.py --e2e (mes_qa3_db · 8053)
```

## 2. 명령 (재현)

```
# 전용 DB 초기화 (Makefile db-schema 는 mes_core_db 를 지우므로 쓰지 않는다)
psql -h /tmp -d mes_qa3_db -c 'drop schema public cascade; create schema public;'
psql -h /tmp -d mes_qa3_db -f src/mescore/db/schema.sql && psql -h /tmp -d mes_qa3_db -f src/mescore/db/views.sql
MES_PACK= MES_PG_DSN=postgresql:///mes_qa3_db uv run python -m mescore.db.seed_core

# G-C13~G-C20 (gate 가 부르는 기본 모드 · 약 45초)
MES_PACK= MES_PG_DSN=postgresql:///mes_qa3_db uv run python src/mescore/tools/check_security.py
# + G-C22 E2E · G-P01 팩 격리 (약 1분 50초 — 이 리포트의 수치)
MES_PACK= MES_PG_DSN=postgresql:///mes_qa3_db uv run python src/mescore/tools/check_security.py --e2e --pack-isolation --json <스크래치>/final.json
```

브라우저: `uv run --with playwright --with zxing-cpp --with pillow` 로 같은 파일을 다시 부른다(프로젝트 의존성 변경 0 · 설치된 Chrome 채널 · 헤드리스). 바코드는 스캐너 대신 **화면의 SVG 를 이미지로 떠 zxing 으로 해독**하고, 해독한 글자를 키보드로 스캔칸에 쳐서 Enter — 클릭으로 포커스를 주지 않는다(S-02 · S-05 그대로).

## 3. 실측 원문 (최종 실행 · 09:36 · `mes_qa3_db` 초기화 직후)

```
G-C13  채널 밖 화면 403                                PASS  {'BAS-01?device=pop': 403, 'BAS-01?device=mobile': 403, 'BAS-01?device=board': 403, 'SYS-01?device=pop': 403, 'POP-02?device=board': 403} · 채널 안 KPI-01?device=board 200
G-C13  POP data-scan 하나 · 열자마자 포커스 · 레이아웃         PASS  POP 화면 13 · data-scan 1개 9 · 2개 이상 0 · 포커스 못 받음 0 · ch-pop 아님/200 아님 0
G-C13  없는 번호 스캔 → 그 화면 422 재렌더                    PASS  스캔 진입 GET 6 화면(POP-01 · POP-03 · POP-04 · MAT-02 · QUA-02 · SHP-02) ?no=NOPE-QA3-0000 — 422 · URL 유지 · 오류 배너 · 스캔칸 포커스 어긋남 0
G-C13  바코드 1회 = 1건 (같은 라벨 2회 스캔 = 2행)             PASS  원재료 라벨 해독 M261009-0002 · POP-03 스캔 2회 → pop_input +2
G-C13  모바일 390px 가로 넘침 0 (헤드리스 Chrome)            PASS  모바일 채널 화면 8 · scrollWidth≠clientWidth 또는 200 아님 0
G-C13  현황판 자동 새로고침 · 갱신 시각 · 503 유지               PASS  5초 주기 · 갱신 시각 09:36:11 → 09:36:22 · 11.5초 동안 폴링 2회(1배) · 폴링 503 → data-state=stale · 실패 시각 09:36 · 값 유지 True · 503 중 폴링 2회 · 회복 뒤 state='ok'
G-C13  DB 끊긴 기동 — 503 · 조용한 200 없음                PASS  (로그인 세션 쿠키로 요청) /health 503 · POST /login 503 · 메인 503 「서비스 일시 중단」 · JSON 503 db_unavailable · 접속 문자열 노출 False · 쿠키 없는 JSON 401
G-C13  DB 끊김 — POP 스캔칸 disabled(S-12) · 현황판 오류 화면 새로고침  PASS  POP-01 503 스캔칸 disabled True · 현황판 503 새로고침 표지 True
G-C14  출력물 4종 · 인라인 SVG · 외부 요청 0 · 바코드 해독 = 번호   PASS  작업지시서 200 해독 ['W261009-001'] · LOT 라벨 200 해독 ['P261009-0001'] · 출하 라벨 200 해독 ['S261009-001'] · 성적서 200 해독 ['C261009-001'] · 어긋남 0
G-C14  LOT 라벨 → POP 스캔칸 → 그 LOT (100×50 · 50×30)  PASS  두 크기 모두 해독 P261009-0001 → POP-03 ?no= 200 그 LOT · POP-04 → 그 LOT 라벨 · 스캔칸 포커스 True
G-C14  지시서 → POP-01 · 출하 라벨 → SHP-02 · 성적서 → SHP-04  PASS  지시 W261009-001 → /pop/result?id=2 · 출하 S261009-001 → /shp/scan?no=S261009-001 · 성적서 C261009-001 검색 True
G-C15  이관 4 명령 실제 적재 2회 멱등 · dry-run 쓰기 0         PASS  1회 적재 3·3·17·8 · 2회 적재 합 0 · 2회째 대상 테이블 20 행 수 diff 0 · sys_migration_log +17/+17 · dry-run rc [0,0,0,0] diff 0
G-C15  깨진 파일 → 종료 코드 1 · 오류 리포트 · 로그 행            PASS  rc=1 · 리포트 '01_items.csv 읽음 4 적재 0 갱신 3 건너뜀 0 오류 1' · sys_migration_log +9(파일마다 한 행) · 오류 기록 [{"line": 5, "reason": "item_code: 필수"}]
G-C16  ERP 501 D-02 · 재전송 HTTP 501 · 200 위장 없음       PASS  push → 501 D-02 · POST /ifc/erp/1/retry → 501 undecided D-02 · 그 행 미확정 · '전송' 행 0
G-C16  수집 토큰 틀림/없음 401 · 모르는 설비 422 + 거부 기록       PASS  틀린 토큰 401 · 토큰 없음 401 · 맞는 토큰+없는 설비 422 · 거부 기록 1
G-C17  역할 변경이 다음 요청부터 (시험 계정 PROD→QA)           PASS  품질 검사 등록 403→200 · 생산계획 등록(QA 조회 칸) →403
G-C18  접근 로그 4종 + SYS-04 조회 · 비밀번호 미기록            PASS  login_fail 401 · 조회 200 · 변경 200 → sys_access_log {change 1, login_fail 1, login_ok 1, view 1} · SYS-04 200 계정 행 보임 · 로그에 틀린 비밀번호 0건
G-C18  세션 무효화 — 로그아웃 · 중지 · 비밀번호 변경 뒤 다음 요청 401  PASS  로그아웃 뒤 같은 쿠키 401 · 중지 뒤 다음 요청 401 · 중지 계정 로그인 401 · 비밀번호 변경 전 세션 401
G-C18  잠금 (MES_LOGIN_LOCK_COUNT=3) → 기존 세션 · 바른 비밀번호 모두 401  PASS  틀린 비밀번호 3회 [401,401,401] → 상태 잠금 · 잠기기 전 세션의 다음 요청 401 · 바른 비밀번호 로그인 401
G-C19  비밀 값 grep 0 · .env · backups gitignore           PASS  저장소 대상 파일 504 중 비밀 값 든 파일 0 · gitignore {'.env': True, 'backups/x.dump': True}
G-C19  하드코딩 비밀 패턴 · 팩 외부 CDN 0 (R11)                PASS  password/secret/token = '리터럴' 0 · 팩 외부 CDN 0
G-C20  backup → restore-check 임시 DB · 행 수 일치            PASS  backup rc=0 · restore-check rc=0 · 판정: PASS — 테이블 52개 전부 복구 · 테이블별 행 수 일치 (행 433)
G-P01  [foodservice] check_pack                        FAIL  R1 바뀜 2 · 생김 1 (tools/check_data.py · check_screens.py · check_security.py) · R10 WARN print/work_order.html
G-P01  [kimchi] check_pack                             FAIL  R1 바뀜 2 · 생김 1 (같은 QA 도구 3)
G-P01  [printfilm] check_pack                          FAIL  R1 (같은 QA 도구 3) · R10 WARN 3 · R9 test_arch_smoke::test_admin_opens_every_screen… 1 failed
G-P01  R9 팩 폴더 지운 worktree — 코어 tests/ 전건           FAIL  /tmp/qa3-wt (HEAD 5d9c581) 에서 packs/[foodservice, kimchi, printfilm] 삭제 · passed 274 · failed 1 [tests/test_migrate.py::test_basics_idempotent_and_logged]
G-P01  [foodservice] R9 팩 올린 채 tests/test_arch_*.py    PASS  52 passed, 6 skipped
G-P01  [kimchi] R9 팩 올린 채 tests/test_arch_*.py         PASS  52 passed, 6 skipped
G-P01  [printfilm] R9 팩 올린 채 tests/test_arch_*.py      FAIL  1 failed, 51 passed — test_admin_opens_every_screen_and_placeholders_carry_contract (/eqp/status 403)
```

## 4. G-C22 브라우저 한 바퀴 — 단계 · 역할 · 캡처

코어 단독(`MES_PACK=`) · 헤드리스 Chrome 1366×900 · 역할 4 를 로그아웃 → 로그인으로 바꿔 가며. 데이터는 전부 화면 입력으로 만든다(API 직접 호출 0).

| # | 단계 | 역할 · 채널 | 판정 | 실측 | 캡처 |
|---|---|---|---|---|---|
| 01 | 로그인 → 메인 | 관리자 · Web | PASS | `/` 로 303 | `01_login_admin.png` |
| 02 | 기준정보 — 품목 등록 BAS-01 | 관리자 | PASS | 토스트 「등록했습니다 — 품목 QA3-…」 · 목록에 보임 | `02_bas_item_register.png` |
| 03 | 수주 등록 ORD-01 | 관리자 | PASS | O261009-001 | `03_ord_order_register.png` |
| 04 | 생산계획 등록 · 확정 ORD-04 | 생산 · Web | PASS | N261009-003 → 인라인 확인 → 「확정」 | `04_ord_plan_confirm.png` |
| 05 | 작업지시 등록 JOB-01 (확정 계획 선택) | 생산 | PASS | W261009-002 | `05_job_work_order_register.png` |
| 06 | 작업지시서 출력 | 생산 | PASS | 바코드 해독 W261009-002 · **수주 번호 표시 안 됨 → DEF-QA3-002** | `06_job_print_work_order.png` |
| 07 | 입고 2 MAT-01 | 현장 · POP | PASS | M261009-0003 · 0004 | `07_mat_receipt_x2.png` |
| 08 | 입고검사 MAT-02 (스캔 → 항목 → 합격) | 품질 · POP | PASS | 스캔칸 포커스 True · 2건 합격 | `08_mat_inspection_pass_x2.png` |
| 09 | 지시서 바코드 해독값 → POP-01 스캔 → POP-02 작업 시작 | 현장 · POP | PASS | `/pop/result?wo=5` → 실적 #5 | `09_pop_start_from_wo_barcode.png` |
| 10 | 원재료 라벨 해독 → POP-03 투입 스캔 | 현장 | PASS | 「투입 M261009-0003」 | `10_pop_input_scan_r1.png` |
| 11 | 측정값 입력 → 작업 종료 → 생산 LOT | 현장 | PASS | 중량 50 · 온도 70 저장 → P261009-0002 (이탈 1 = 이관 예시가 더한 `temp_c` 칸 — 아래 §6) | `11_pop_end_measure_r1.png` |
| 12 | 생산 LOT 라벨 해독 → POP-04 스캔 → 같은 LOT | 현장 | PASS | 해독 P261009-0002 = 열린 라벨 | `12_pop_label_scan_roundtrip.png` |
| 13 | 같은 지시 2번째 실적 — 원재료 ①② 투입 · 온도 85 | 현장 | PASS | 범위 이탈 저장 + 화면 「이탈」 | `13_pop_run2_deviation.png` |
| 14 | 합병 2:1 | 현장 | PASS | P261009-0004 | `14_merge_2to1.png` |
| 15 | 분할 1:3 (30·30·30) | 현장 | PASS | P261009-0005 · 0006 · 0007 | `15_split_1to3.png` |
| 16 | 검사 QUA-02 — 분할 ①② 최종 검사 등록 → 판정 합격 | 품질 · Web | PASS | 2건 합격 | `16_qua_inspect_judge_x2.png` |
| 17 | 출하 등록 SHP-01 (수주 선택) | 현장 · POP | PASS | S261009-002 → 스캔 화면으로 | `17_shp_register.png` |
| 18 | 출하 라벨 해독 → SHP-02 → 분할 ①② 라벨 해독 → 스캔 | 현장 | PASS | 2건 「→ S261009-002」 | `18_shp_scan_lots.png` |
| 19 | 출하 승인 | 관리자 · POP (현장은 승인 버튼 disabled 확인) | PASS | 「출하를 승인했습니다」 | `19_shp_approve_admin.png` |
| 20 | 성적서 발행 · 출력 SHP-04 | 생산 · Web | PASS | C261009-002 해독 · 분할 ①② 행 | `20_shp_document_print.png` |
| 21 | 역추적 TRC-02 (출하 LOT) | 생산 | PASS | X261009-0002 → 원재료 ①② 둘 다 | `21_trc_backward.png` |
| 22 | 정방향 TRC-01 (원재료 ①) | 생산 | PASS | 생산 ①② → 합병 → 분할 ①②③ → 출하 · ③ 재고 | `22_trc_forward.png` |
| 23 | 현황판 KPI-01 | 관리자 · 현황판 | PASS | 5초 주기 · 갱신 시각 09:37:03 → 09:37:08 | `23_kpi_board.png` |

막힌 단계: **없음.** 탐색 중 막혔던 것은 전부 검사기 쪽 선택자 문제였다(POP 알림 팝업이 모달이라 Esc 로 닫아야 함 — S-08 그대로 · 상단 탭 「LOT 라벨」 링크와 라벨 링크 혼동 · 관리자 POP 세션은 작업지시서(Web 전용) 403 — 채널 규칙대로).

## 5. 결함

| ID | 등급 | 담당 | 내용 | 증거 |
|---|---|---|---|---|
| DEF-QA3-001 | **중대** | 아키텍트(`settings.py` 기본값) · 개발1(`routers/home.py` `/login/as`) | `MES_ENV` 가 비면 기본값이 **`dev`** → `POST /login/as role=ADMIN` 이 **비밀번호 없이** 관리자 세션을 준다(D-605 는 `가설`). 운영에서 `MES_ENV` 를 빠뜨리면 무인증 관리자 로그인이 열린다. 안전한 쪽 기본값(`prod`)이거나 명시적 `MES_ENV=dev` 일 때만이어야 한다. 이 저장소 `.env` 는 `MES_ENV=dev` 라 지금도 열려 있다 | `MES_ENV=` 로 TestClient: `POST /login/as` 200 `{ok: true, login_id: admin, role_code: ADMIN}` → `/sys/users` 200 |
| DEF-QA3-002 | **중대** | 개발1 (`routers/job.py` F-JOB-01) | 확정 계획(수주 상세에서 만든)으로 작업지시를 만들어도 계획의 `order_dtl_id` · `plan_date` 가 지시로 이어지지 않는다 → `job_work_order.order_dtl_id` NULL · 작업지시서 「수주 -」 「납기 -」 · 수주 상세 상태가 `대기` 그대로(지시로 안 넘어감). 사용자가 계획과 수주 상세를 따로 골라야 하고 서로 다른 것을 골라도 막지 않는다 | E2E 06 캡처 · `select w.order_dtl_id, p.order_dtl_id, d.status …` → `NULL · 9 · 대기` |
| DEF-QA3-003 | **중대** (G-C21 · G-P01 R9) | 개발3 (`tests/test_migrate.py`) | `test_basics_idempotent_and_logged` 가 **방금 시드한 DB 에서 실패** — `bas_bom_dtl … created_by = 'migrate'` 2 를 기대하나 0(시드 `seed_dev1` 이 같은 BOM 상세를 먼저 넣어 이관은 `갱신` 만 한다). 팩과 무관(원본 트리 · 팩 지운 worktree 둘 다 같음) — 데이터 상태에 기대는 테스트 | `MES_PG_DSN=…mes_qa3_db uv run pytest tests/test_migrate.py` → 1 failed (초기화 직후 2회 반복 동일) |
| DEF-QA3-004 | **중대** (G-P01 R9) | 아키텍트 (`tests/test_arch_smoke.py`) | `test_admin_opens_every_screen_and_placeholders_carry_contract` 가 팩이 `menus.hide` 로 숨긴 메뉴의 화면도 200 을 기대한다. printfilm 은 `hide: [eqp]` · `eqp,ADMIN,없음` 이라 `/eqp/status` **403 이 계약대로**인데 테스트가 FAIL — R9(팩 올린 채 코어 테스트 통과)를 막는다. 테스트가 `packs.current()` 의 숨김 메뉴를 빼야 한다 | `MES_PACK=printfilm uv run pytest tests/test_arch_smoke.py -k admin_opens_every_screen` → `assert 403 == 200 /eqp/status` |
| DEF-QA3-005 | 경미 | 아키텍트 (`tests/test_arch_schema.py`) | `test_product_lot_partial_input_stays_in_stock` 가 데이터가 쌓인 DB(E2E · 이관 예시 적재 뒤)에서 `('소진', 60)` 으로 실패하고 빈 DB 에서는 통과 — 데이터 상태에 따라 흔들린다 | `mes_qa3_db`(누적) 실패 → 초기화 뒤 통과 |
| DEF-QA3-006 | 경미 | 개발3 (`templates/trc/*` 트리) | 정방향 트리에서 합병 LOT 노드 수량이 **간선 수량(50)** 으로 보인다(실제 합병 LOT 100 — `lot.qty` 100). 화살표 표의 간선 수량과 노드 수량을 구분해야 한다 | E2E 22 캡처 P261009-0080 「50.000 EA」 · DB `lot.qty` 100 |
| DEF-QA3-007 | 경미 | 아키텍트 (`main.py` `/logout`) | `GET /logout` 이 열려 있어 다른 사이트의 링크 · 이미지로 사용자를 로그아웃시킬 수 있다(쿠키 `SameSite=Lax` 는 최상위 GET 을 보낸다). 쿠키 `Secure` 표시 없음(운영 HTTPS 미확정 — 참고) | `Set-Cookie: path=/; Max-Age=1209600; httponly; samesite=lax` |

참고(결함 아님):
- **G-P01 R1** 의 「바뀜 2 · 생김 1」은 QA 도구(`tools/check_data.py` · `check_screens.py` · `check_security.py`)다 — `core.sha256` 이 QA1·QA2 의 커밋 전 판을 찍었고 `check_security.py` 는 없었다. 아키텍트가 QA 커밋 뒤 `make core-hash` 를 다시 찍으면 사라진다. 팩 결함 아님.
- 분할 30·30·30 은 합병 LOT 100 에서 10 이 어디에도 남지 않는다(합병 LOT 은 `소진`). 코어 시나리오(G-C06) 그대로이므로 수량 정합성 판단은 QA2 에 넘긴다.
- 관리자(생산실적 `조회`)가 POP-03 스캔칸에 Enter 하면 POST 403 오류 화면 — 계약(§2.5)대로. 조회 역할에게 스캔칸을 숨기거나 비활성으로 두는 것은 디자인 판단.
- 이관 예시(`04_process_params.csv`)가 시드 공정 `PRC-EX-01` 에 `temp_c` · `weight_kg` 칸을 더한다 → 이관을 돌린 DB(gate 의 `mes_core_db` 포함)에서 POP-02 종료 폼 칸이 5개가 되고 E2E 11 에서 「이탈 1」(`temp_c` 범위). 앱 결함은 아니나 예시가 시드 공정을 바꾼다는 점은 QA2 · 개발3 참고.

## 6. 조용한 실패 사냥 — 결과

| 시나리오 | 기대 | 실측 | 판정 |
|---|---|---|---|
| DB 끊긴 기동(`MES_PG_DSN` = 없는 DB) + 유효 세션 쿠키 | 503 · 「서비스 일시 중단」 · 접속 문자열 안 보임 | `/health` 503 · `POST /login` 503(401 위장 아님) · 메인 503 · JSON 503 `db_unavailable` · POP 스캔칸 `disabled` · 현황판 503 화면에도 새로고침 표지 · 노출 0 | PASS |
| 현황판 폴링이 503 | 마지막 값 유지 · stale 표시 · 폴링 계속 · 회복 | `data-state=stale` · 실패 시각 · 값 그대로 · 503 동안 폴링 2회 · 해제 뒤 `ok` | PASS |
| 수집 토큰 틀림 · 없음 | 401 | 401 · 401 (토큰 없는 서버 설정이면 전부 401 — 코드 확인) | PASS |
| 수집 — 모르는 설비 | 422 + 버리지 않고 거부 기록 | 422 · `ifc_collect_raw.rejected_reason` 1행 | PASS |
| ERP 재전송 | 501 그대로 · 200 위장 0 | HTTP 501 `undecided` D-02 · 행 `미확정` · `전송` 0 | PASS |
| 이관 깨진 파일 | 종료 코드 1 · 오류 리포트 | rc 1 · 리포트 행 · `error_detail` 줄 번호 + 사유 (같은 파일의 성한 줄 3 은 갱신된다 — 파일 단위 원자성은 계약에 없음) | PASS |
| 로그인 실패 로그 | 비밀번호 미기록 | 틀린 비밀번호 문자열이 `sys_access_log` 에 0건 | PASS |
| 백업 출력 | 비밀 미출력 | backup · restore-check 출력에 `.env` 비밀 0 | PASS |
| `/docs` · `/openapi.json` | 404 · 권한자만 | 404 · 미로그인 401 | PASS |

## 7. G-P01 팩 격리 — 방법

- 팩 3 각각 `MES_PACK=<팩> uv run python src/mescore/tools/check_pack.py`(팩 DB `mes_<팩>_db` · 읽기만).
- R9 (아키텍트 확정 범위): ① `git worktree add --detach /tmp/qa3-wt HEAD` 복사본에서 `packs/{foodservice,kimchi,printfilm}` 를 지우고 `MES_PACK=` 로 코어 `tests/` 전건(`mes_qa3_db`) ② 원본 트리에서 팩을 올린 채 `tests/test_arch_*.py`. **원본 트리의 팩 폴더는 옮기지 않았다.** worktree 는 검사 뒤 `git worktree remove --force` · `prune` 으로 지웠다(`git worktree list` = 원본 하나).
- 결과: 팩을 지워도 코어 테스트 결과는 원본과 같다(실패 1 은 DEF-QA3-003 — 팩 무관). 팩을 올린 채 foodservice · kimchi PASS, printfilm FAIL(DEF-QA3-004 — 테스트가 숨김 메뉴를 모름).

## 8. 하지 않은 것 · 남긴 것

- 실물 스캐너 · 프린터 · 종이 인쇄(barcode_spec §5 의 2 · 10단계) — 범위 밖(§2.8). 대신 브라우저 렌더 이미지를 zxing 으로 해독(Code 128 판독 100% · 100×50 · 50×30 · A4 3종).
- 코드 · 테스트 · 계약 수정 0. 결함은 담당에게.
- `make gate` 전체 실행은 하지 않았다(공유 `mes_core_db` 에 pytest 전건을 또 돌리게 된다). gate 의 파싱은 `gate.per_gate` 로 이 도구의 출력을 읽혀 확인 — G-C13~G-C20 · G-C22 · G-P01 행이 위 판정 그대로 읽힌다.
