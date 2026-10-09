# 진행 상태

검증된 것만 적는다. 여기 없는 숫자는 화면에 지어내지 않는다. 형식: `| 항목 | 실측 | 검증 방법 |`.

## 지금 해야 할 것

1. **웨이브 A R1 (개발 3 병렬)** — 개발1 `app/numbering.py`(채번 형식을 `progress-dev1.md` §1 에 먼저 공표) · 개발2 `app/lineage.py` + `tests/test_lineage_scenario.py`(G-C06 10행) + `ui.measure_fields` · 개발3 `app/stats.py` · `app/erp.py` · `src/mescore/migrate/` · `app/collect.py` 수신. 각자 `app/routers/<모듈>.py` 에 `router = APIRouter()` 를 두면 placeholder 가 빠진다(`main.py` · `packs.py` · `core.yaml` 은 만지지 않는다).
2. 기획자 3명의 `packs/{kimchi,foodservice,printfilm}/pack.yaml` 은 `MES_PACK=<팩> make pack-check` 로 검증한다 — 지금은 셋 다 **선언한 파일이 아직 없어** `PackError`(kimchi: `hooks.py` · `adapters/collect_tags.py`, foodservice: `hooks.py`, printfilm: `hooks.py` · `adapters/label_html.py`). 빈 `hooks.py`(= `_template/hooks.py` 복사)만 두면 통과한다. 팩 DB 는 `MES_PACK=<팩> make setup db-reset`.
3. QA 는 웨이브 C — `src/mescore/tools/check_data.py`(QA2) · `check_security.py`(QA3) · `check_screens.py`(QA1) 가 생기면 `make gate` 가 그 출력으로 G-C05~G-C20 · G-C24 를 판정한다(지금은 `미검증`).

## 2026-10-09 Phase 0 — 아키텍트 (spec → 계약 · 골격)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 정본 수 | 기능 `F-` 132 · 배치 `B-MIG-` 4 · 화면 51 · 테이블 52 · 확장 지점 7 — `goal.md` 표와 같다 | `goal.md` §9 의 grep 5개 |
| 스캐폴딩 | `git init`(로컬) · `pyproject.toml`(mescore · src 레이아웃) · `uv sync` Python 3.12.13 · `.env` 난수 3개(`MES_SESSION_SECRET` `MES_SEED_PASSWORD` `MES_COLLECT_TOKEN`) · DB `mes_core_db` · 포트 8030 | `make setup` · `.venv/bin/python --version` · `psql -h /tmp -l` |
| `core.yaml` | 모듈 12 · 화면 51 · 공통 5 · 역할 4 · 권한 48칸(입력 19 · 조회 22 · 없음 7 · 범위 4) · 채번 8 · 관계 5 · LOT 종류 3 · `terms_keys` 26 · 금지어 44 · 채널 pop 13 · mobile 8 · board 1 · 공통코드 그룹 8 | `make check-trace` G-C01 7/7 PASS |
| 팩 로더 | `packs.load/current/t/hook/attrs_of/read_attrs/template_dirs/router_modules` · R4~R6 위반 13종 `PackError` · `_template` 로드 OK · 코어 단독 OK | `tests/test_arch_packs.py` 20건 |
| 스키마 | 테이블 52 · 뷰 3 · 공통 컬럼 6 전 테이블 · `lot_genealogy` 유니크 + 자기참조 CHECK + 순환 금지 트리거 · 제약 86 · 인덱스 24 · 트리거 2 | `make check-schema` G-C04 8/8 PASS |
| 계보 (스키마) | 코어 시나리오 SQL 직접 10행(투입 3 · 합병 2 · 분할 3 · 출하 2) · 역추적 9행(원재료 ①② 도달) · 정방향 9행 · `v_lot_state` 재고/소진/출하 · 깊이 25 사슬 · 순환 · 자기참조 · 중복 · 불변 거부 | `tests/test_arch_schema.py` 7건 |
| 시드 | 역할 4 · 권한 칸 48 · 계정 4(`admin prod qa field`) · 채번 규칙 8 · 공통코드 25 · (예시) 품목 3 · 공정 2 · 설비 1 · 거래처 2 · 작업자 1 · 불량코드 1 — 2회 실행 행 수 같음 | `uv run python -m mescore.db.seed_core` ×2 |
| 화면 | 코어 51 + 공통 5 전부 200 · placeholder 53(코어 51 + 대시보드 · 팝업) — 개발1 18 · 개발2 17 · 개발3 17 · 아키텍트 1 · RBAC 204건 조회 검사 위반 0 · 미로그인 303/401 | `make check-routes` |
| 백엔드 우선 | 화면 GET 은 `Accept: text/html` 없으면 `ctx` JSON(D-18) · placeholder 는 `placeholder: true` | `tests/test_arch_smoke.py::test_screen_json_and_html_carry_same_data` |
| 금지어 | `src/mescore/` 파일 38 · 금지어 44 · 위반 0 · 템플릿 `t()` 누락 0 | `make check-terms` G-C23 PASS |
| 계약 | `db-schema.md` §4 · `screen-map.md` §1 렌더본 = 코드 · `function-list.md` 권한 열 = `core.yaml` 계산값 · 범위 4종 | `make contracts` · `make check-trace` |
| 테스트 | pytest **50 passed** · 0 failed (`tests/test_arch_{schema,smoke,packs}.py`) · `_template` 팩 스모크 5 passed | `uv run pytest -q` · `MES_PACK=_template uv run pytest -q packs/_template/tests` |
| 기동 | `uvicorn mescore.app.main:app --app-dir src --port 8030` → `/health` 200 `{"status":"ok","pack":"","core_version":"0.1.0","db":{"ok":true},"menus":12,"screens":51,"functions":132,"placeholders":51,"pack_screens":0,"router_include_errors":[]}` · `/login` 200 | curl |
| 백업 | `make backup` → `backups/mes_core_db-<일시>.dump` + 행 수 JSON(테이블 52 · 행 161) · `make restore-check` 임시 DB 복구 행 수 일치 PASS | 명령 출력 |
| 코어 해시 | `outputs/core.sha256` 코어 파일 39개 (R1 기준값) | `make core-hash` · `uv run python src/mescore/tools/core_hash.py --check` |
| 하지 않은 것 | 참조 팩 3 `pack.yaml` 뼈대(기획자 작업 중 · D-24) · 팩 DB 3 · `check_data` · `check_security`(QA) · 공용 모듈 9(개발) | — |

### `make gate` 판정표 (2026-10-09 02:43 · 코어 단독)

```
G-C01  메뉴 — 코어 12 · 공통 5 · nav = core.yaml                    PASS  검사 7 전부 PASS
G-C02  기능 — 132 + 이관 4 · 계약 = API = 테스트 · 고아 0                FAIL  검사 10 · 통과 못한 3 — 기능 132 ↔ 라우트: 이어진 기능 0/132 / 기능 136 ↔ 테스트: 0/136 / 이관 배치 4 ↔ 명령: 0/4 · src/mescore/migrate 없음 (개발3)
G-C03  화면 — 51 + 공통 5 전부 200 · placeholder 0                  FAIL  화면: 200: 56/56 · placeholder 53 (기대 0) — 개발1 18 · 개발2 17 · 개발3 17 · 아키텍트 1
G-C04  스키마 — 테이블 52 · 계약 = 실제 DB · 공통 컬럼                      PASS  검사 8 전부 PASS
G-C05  쓰기 경계 — trc · kpi 쓰기 0 · lot_genealogy 는 lineage 만     미검증  tools/check_data.py 없음 (QA2) · app/lineage.py 없음 (개발2)
G-C06  계보 재현 — 코어 시나리오 lot_genealogy 10행 (API)                FAIL  tests/test_lineage_scenario.py 없음 (개발2 R1)
G-C07  추적 — 역방향 · 정방향 재귀 · 깊이 20 분기 100 2초                    FAIL  app/lineage.py 없음 (개발2)
G-C08  키 연결 — LOT 번호 → 지시 · 실적 · 측정값 · 검사 · 출하 · 채번 한 곳       FAIL  app/numbering.py 없음 (개발1)
G-C09  시드 멱등 — 2회 실행 행 수 diff 0 · (예시) 표기                     미검증  이 실행에서는 시드를 돌리지 않았다 — `make gate-full`
G-C10  집계 — stats = QA 별도 SQL · measure_series                FAIL  app/stats.py 없음 (개발3)
G-C11  빈 화면 — 미수집 / 미확정 (D-nn)                                미검증  tools/check_data.py 없음 (QA2)
G-C12  범위 밖 0 — 설비 제어 · 업종 전용 기능 없음                           미검증  tools/check_data.py 없음 (QA2) · 금지어는 G-C23
G-C13  4채널 — POP 스캔 · 모바일 390px · 현황판 새로고침                    미검증  tools/check_security.py 없음 (QA3) — 채널 레이아웃(body.ch-*) · data-scan · 새로고침 훅은 있다
G-C14  출력물 4종 — 작업지시서 · 라벨 2 · 성적서 · 바코드 SVG                  FAIL  app/printing.py 없음 (개발2)
G-C15  이관 배치 4 — Import 파일 · 멱등 · 리포트                         FAIL  src/mescore/migrate 없음 (개발3)
G-C16  ERP — 어댑터 + 501 명시 · 조용한 폴백 0                          FAIL  app/erp.py 없음 (개발3)
G-C17  RBAC — 48칸 데이터 · 없음 403 · 조회 = 쓰기 403 · scopes         미검증  자체 실측 DB 권한 표 48칸 (입력 19 · 조회 22 · 없음 7) · 없음 칸 403 위반 0 · 쓰기 403 전수는 check_security(QA3)
G-C18  접근 로그 — 로그인 · 조회 · 변경 · SYS-04                         FAIL  sys_access_log login_ok 36 · login_fail 6 · view 754 · change 0 · 로그 화면(SYS-04) placeholder — 조회 불가 (개발1)
G-C19  비밀 — 저장소 · 문서에 비밀 값 없음                                 미검증  자체 실측 저장소 대상 파일 184개 중 비밀 값이 든 파일 0 · .env gitignore 됨 · check_security(QA3) 대기
G-C20  백업 — make backup · restore-check                       미검증  tools/check_security.py 없음 (QA3) — backup.py 는 있다
G-C21  빌드 — pytest 전건 · check-routes · /health 200            FAIL  pytest passed 50 · failed 0 · check-routes FAIL · /health 200
G-C22  브라우저 한 바퀴 — outputs/e2e/core 캡처 · QA3 판정               미검증  outputs/e2e/core 파일 0개 — `outputs/qa3-채널보안.md` 없음 (QA3)
G-C23  용어 중립 — 코어 금지어 0 · t() 누락 0                            PASS  검사 2 전부 PASS
G-C24  측정값 — bas_process_param 선언 → POP 폼 → pop_measure → 집계  FAIL  app/collect.py 없음 (개발2)

[팩 foodservice · kimchi · printfilm] G-P01~G-P06 전부 미검증 — 팩 DB mes_<팩>_db 없음 (`MES_PACK=<팩> make setup db-reset`)

PASS 3 · FAIL 12 · WARN 0 · BLOCKED 0 · 미검증 27 / 전체 42
```

Phase 0 종료 조건(goal.md §3.1) 대조 — G-C01 PASS · G-C04 PASS · G-C23 PASS · G-C02 는 계약 136줄 존재(라우트 · 테스트 · 이관 미연결로 FAIL 이 정상) · G-C03 은 placeholder 로 FAIL(정상) · pytest 전건 통과 · 8030 기동 `/health` 200 · `/login` 200. G-C21 은 `check-routes` 가 placeholder 0 을 요구해 R2 전까지 FAIL 이 정상이다. "G-P01 은 팩 3 뼈대로 PASS" 는 D-24 로 이번에 재지 않았다.

## 2026-10-09 회전 1 — 오케스트레이터 (Phase 0 판정 · 기획 · 디자인 동시 진행)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| Phase 0 종료 조건 | G-C01 · G-C04 · G-C23 PASS · G-C02 계약 136줄(라우트 0/132 FAIL 정상) · G-C03 placeholder 53 FAIL 정상 · PASS 3 · FAIL 12 · 미검증 27 | `make gate`(오케스트레이터 직접 재실행) |
| 테스트 | 50 passed · 0 failed | `uv run pytest -q` |
| 기획 산출물 | `packs/foodservice` 18파일(화면 0 · 테이블 8 · 역할 6 · 권한 72칸) · `packs/printfilm` 20파일(화면 7 · 기능 24 · 테이블 8 · 권한 60칸) · `packs/kimchi` 14파일(화면 8 · 기능 24 · 테이블 7 · 권한 108칸) — 셋 다 `pack-check` 는 선언 파일(`hooks.py` 등) 미작성으로 PackError(웨이브 B 몫) | `ls packs/*/` · `MES_PACK=<팩> make pack-check` |
| 디자인 산출물 | `docs/design/tokens.css` 토큰 97 · `web/` 레이아웃 + 컴포넌트 18 + 화면 14 · `pop/` 13 · `mobile/` 8 · `board/` 2 · `print/` 4 + 바코드 규격 · `home/` 2 · README 3절 보존 | `ls docs/design/*` · `grep -c '^## ' docs/design/README.md` |
| 코어 매핑 결과 | 니즈푸드 49: 1:1 18 · 용어+확장 23 · 팩 0 · 밖 8 / 엘컴화인 기능 100: 1:1 54 · 용어 18 · 팩 24 · 밖 4 / 임진강 64: 1:1 30 · 용어 13 · 팩 8 · 밖 13 — 코어 테이블 신설 요구 0 | 각 `packs/<팩>/README.md` 매핑표 |
| 결정 | D-501~D-509(기획) · D-601~D-605(디자인) 추가 · 코어 변경 요청 2건(D-501 설비 알람 · D-502 화면 권한) · 차단 1(D-509) | `decisions.md` |
| 다음 | 웨이브 A R1·R2 개발 3명 — 백엔드 우선: 공용 모듈 → 모듈별 라우터 + JSON 검증 + 기능별 테스트. 템플릿은 최소(매크로). 프런트 이식은 웨이브 A′ | — |

## 2026-10-09 회전 2 — 오케스트레이터 (웨이브 A 백엔드 판정)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 기능 연결 | 132/132 라우트 · 136/136 테스트 표식 · 이관 배치 4/4 (개발1 59 · 개발2 38 · 개발3 35+4) | `make check-trace` |
| 테스트 | **241 passed · 0 failed** (아키텍트 50 · 개발1 69 · 개발2 67 · 개발3 55) | `uv run pytest -q`(오케스트레이터 직접) |
| 화면 | 56/56 200 · RBAC 204건 위반 0 · placeholder **1**(CMN-05 팝업 · 아키텍트) | `make check-routes` |
| 계보 | API 시나리오 10행 · 역추적 원재료 ①② · 정방향 ③ 재고 · 깊이 20 분기 100 0.04초 | `tests/test_lineage_scenario.py` 7 · `test_pop_scenario.py` 1 |
| 측정값 G-C24 | 선언 3행 → 칸 3 · 필수 422 · 이탈 저장+deviated · collect avg 자동 | `tests/test_measure.py` 4 |
| 게이트 | PASS 3(C01 · C04 · C23) · FAIL 3(C02 고아 라우트 1 = D-601 라벨 · C03 팝업 1 · C21 ← C03) · 미검증 36 — `gate.py` 가 QA 도구만 보고 개발 테스트를 판정에 안 씀(아키텍트 수정 대상) | `make gate` |
| 결정 | 개발 가설 D-101~ · D-201~205 · D-301~302 (각 `progress-devN.md` · `decisions.md`) | — |
| 다음 | 회전 3 병렬: 아키텍트 웨이브 D-1(요청 처리 · gate 판정 보강 · 팝업 · 팩 DB) · 디자이너 3 프런트 이식(웨이브 A′) · 개발 3 참조 팩(웨이브 B). QA 는 프런트가 선 뒤 회전 4 | — |

## 2026-10-09 회전 3 — 아키텍트 (웨이브 D-1: gate 판정 보강 · 요청 처리 · CMN-05 팝업 · 팩 DB · 결정 정리)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| gate 판정 보강 (D-30) | QA 도구 없이도 증거로 PASS/FAIL — 미검증 36 → **9**(C09 시드는 `gate-full` · C10 QA SQL · C22 브라우저 · 팩 G-P03 3 · G-P06 3). 판정 줄에 「QA 대조 대기」 · QA 도구가 생기면 그 출력 우선(분기 유지) · 기대값은 내리지 않음 | `make gate` (아래 원문) |
| 흔들린 테스트 원인 | `tests/test_job_work_orders.py::test_status_board_today_week_and_drilldown` — JOB-02 `status_board` 가 `order by w.plan_date nulls last, w.id limit 500`(오름차순)인데 오늘 계획일 지시가 **663건**(`created_by='test'` 643 — 여러 테스트 파일이 지시를 남긴다)이라 방금 만든 지시(가장 큰 id)가 500 밖으로 밀려 `StopIteration`. **개발1 파일**(`routers/job.py` · 그 테스트) → 개발1 다음 회전: 최신 지시 우선(`w.id desc`) 또는 테스트가 `?wo=` 로 조회. 데이터가 적을 때만 통과하던 테스트 | `uv run pytest -q tests/test_job_work_orders.py` · `select count(*) from job_work_order where plan_date = current_date` → 663 |
| 요청 처리 (개발1) | ① `make core-hash` 재기록 155 파일(바뀜 0) ② `test_permission_matrix_is_data` 기대값 = DB 역할 수 × 메뉴 수 · 코어 역할 4 칸만 goal §6 표 대조(D-28) ③ `interfaces.md` §9 · `pack-contract.md` §5 에 `after_save_<table>` · `on_work_order_canceled` · `on_order_status_changed` · `on_collect` 반환 · `kpi_extra(by=)` ④ D-101~D-106 을 `decisions.md` 에 올림 — **D-101 은 개발3 안으로 바꿈**(지시는 `확정` 계획만 · `ord_plan.status` 는 F-ORD-09 만 → 개발1 다음 회전 `job.py` 수정) | `core_hash.py --check` · `pytest tests/test_arch_smoke.py` · `decisions.md` |
| 요청 처리 (개발2) | ① `core.yaml: numbering` `ISSUE`(Q · YYMMDD- · 3 · D-34) ② `screen-map.md` §3 — `app/measure.py` · `routers/_dev2.py` · `tests/_dev2_helpers.py` · `test_pop_scenario.py` 개발2, `print/document.html` 은 웨이브 A′ 동안 디자이너3 ③ `_macros.html` `measure_fields` 위임 한 줄(D-205)은 **디자이너1 소유로 넘어가 하지 않음** ④ `app.js` S-01~S-14 는 디자이너2 | `core.yaml` · `screen-map.md` |
| 요청 처리 (개발3) | ① `check_trace` 고아 제외를 `core.yaml: extra_routes`(D-12 split/merge · D-601 라벨 · D-31)에서 읽음 → G-C02 PASS ② `Makefile` `kpi-snapshot` `erp-flush` `pack-db NAME=`(D-35) ③ `packs.CORE_ROUTER_MODULES` 15 = 12 + `home dashboard popup`(D-29 — **개발3 은 `kpi.py` 의 `dashboard` include 한 줄을 뺀다**) ④ `function-list.md` B-MIG-03 쓰는 테이블에 `shp_shipment`(D-301) ⑤ `print/document.html` 소유권은 §3 대로 | `make check-trace` · `make -n pack-db NAME=printfilm` |
| 개발2 다음 회전으로 남김 | 개발3 요청 ⑤ `lineage.link(..., at=)`(이관 22 의 `linked_at`) · ⑥ `collect.counts(None, None)` 의 `AmbiguousParameter`(`%(f)s is null` 캐스트) — 개발2 파일이라 아키텍트가 고치지 않음 | `progress-dev3.md` §3 5 · 6 |
| CMN-05 팝업 (D-32) | `routers/popup.py` + `home/_popup.html` — `/popup/{kind}` item · partner · equipment · lot · worker · `?q=` · `?limit=`(≤ 200) · JSON `{kind q columns rows count pick}` · 없는 종류 404 · 쓰기 0 · 스크립트 0(행 `data-pick` → `app.js` 디자이너2) → placeholder **0** · G-C03 PASS | `make check-routes` → `placeholder 0` · 8039 기동 `/health` `placeholders: 0` · `/popup/item` 200 count 6 · `/popup/lot?q=P-EX` 200 count 6 |
| 팩 DB | `mes_foodservice_db` · `mes_kimchi_db` 는 이 회전 중 개발1 · 개발3 이 먼저 만듦(테이블 60 · 59 = 코어 52 + 팩, 역할 6, 팩 시드 포함). **`mes_printfilm_db` 는 아키텍트가 생성** — 코어 스키마 52 + 뷰 3 + 코어 시드(역할 4 · 권한 48 · 계정 4 · 채번 9 · 개발 시드) · 팩 시드는 개발2 가 `MES_PACK=printfilm make db-reset` | `psql -h /tmp -l` · `psql -d mes_printfilm_db -c "select count(*) from sys_permission"` → 48 |
| 결정 | D-501 **반영**(설계 · 회전 4 아키텍트 · 테이블 52 → 54 는 사람이 `spec.md` §2.2 · `goal.md` G-C04 수치를 고친 뒤) · D-502 **미룸**(메뉴 × 역할 모델 유지 · 팩 훅 · 팩 화면으로 1차 해결) · 아키텍트 D-28~D-35 · 개발1 D-101~D-106 | `decisions.md` |
| 코어 해시 | `outputs/core.sha256` 155 파일 재기록 — 디자이너의 미커밋 편집분 포함(웨이브 A′ 동안 회전마다 어긋남 · D-33). 재기록 직후 팩 게이트 R1 이 다시 `바뀜 7`(`app.js` · `main.html` · `pop/_layout.html` 등 — 디자이너 편집 진행 중) | `core_hash.py --check` |
| pytest | **237 passed · 4 failed**(`make gate` 안 실행) — ① `test_arch_smoke::test_core_has_no_forbidden_terms` ← 디자이너1 `style.css:8 조색` · `job/status.html:2 롤`(「스크롤」) ② `test_job_work_orders::test_status_board_…`(위 흔들린 테스트) ③④ `test_measure` 2건 — 디자이너2 가 `templates/pop/` 를 이식 중이라 POP-02 종료 폼 HTML 에 `mf.measure_fields` 칸(`name="m_t_req"`) · `class="deviated"` 가 빠짐(JSON 은 통과) → **G-C24 FAIL 로 드러남**. 아키텍트 수정 대상 아님 | `uv run pytest -q` |
| 금지어 | `make gate`(04:01) 때 G-C23 FAIL 2 — 둘 다 디자이너1 파일(`style.css` `조색` · `job/status.html` `롤`). 04:05 `make check-terms` 재실행 **PASS**(위반 0 · t() 누락 0 — 디자이너1 이 그 사이 고침). 아키텍트 파일 위반 0(`gate.py` 의 「스크롤」 1건은 내가 고침) | `make check-terms` |
| 게이트 | 코어 **PASS 17 · FAIL 4 · 미검증 3** — FAIL: G-C15(이관 대상 테이블 행 수 diff — 같은 DB 에 다른 프로세스가 쓰는 중 · `test_migrate` 는 단독 재실행 통과 · gate.py 를 이관 대상 테이블로 좁힘) · G-C21(pytest 4) · G-C23(디자이너1 2) · G-C24(디자이너2 이식 중). 팩 3: G-P02 PASS 3 · G-P05 PASS 2 · FAIL = R1 해시(디자이너 편집) · R10 덮어쓴 템플릿 README 미기재(foodservice · printfilm) · G-P04 시나리오 테스트 파일 0 · printfilm `function-list.md` 검증 실패 24건 | `make gate` 원문 아래 |
| 커밋 | `52c2f40` gate · `6722fa9` 요청 처리 · `f48f916` 팝업 · `2144634` decisions · `c55367b` core.sha256 · (이 절) progress + gate G-C15 보정 | `git log --oneline` |
| 하지 않은 것 | 디자이너 · 개발 파일 수정(흔들린 테스트 · 금지어 2 · POP-02 측정값 칸 · `kpi.py` include · `job.py` 계획 상태) · `schema.sql` 변경(D-501 은 회전 4) · 팩 시드 · `pack-check`(hooks.py 는 생겼으나 printfilm `function-list.md` 24건은 개발2) | — |

### `make gate` 판정표 원문 (2026-10-09 04:01 · 코어 단독 + 팩 3 · 아키텍트 직접 실행 · `outputs/gate-r3-arch.txt`)

```
게이트 판정 — MES 표준플랫폼 · 2026-10-09 04:01

[코어 단독 MES_PACK=]
G-C01  메뉴 — 코어 12 · 공통 5 · nav = core.yaml                    PASS  검사 7 전부 PASS
G-C02  기능 — 132 + 이관 4 · 계약 = API = 테스트 · 고아 0                PASS  검사 10 전부 PASS
G-C03  화면 — 51 + 공통 5 전부 200 · placeholder 0                  PASS  200: 56/56 · placeholder 0 (기대 0)
G-C04  스키마 — 테이블 52 · 계약 = 실제 DB · 공통 컬럼                      PASS  검사 8 전부 PASS
G-C05  쓰기 경계 — trc · kpi 쓰기 0 · lot_genealogy 는 lineage 만     PASS  라우터 15 정적 스캔 — 경계 밖 쓰기 0 · lot_genealogy 직접 쓰기 0 · trc/kpi/대시보드 7화면 조회 전후 행 수 diff 0 (테이블 50) · QA 대조 대기 (check_data)
G-C06  계보 재현 — 코어 시나리오 lot_genealogy 10행 (API)                PASS  test_lineage_scenario 통과 (7 passed in 0.96s) · test_pop_scenario(API) 통과 (1 passed in 0.79s) · QA 대조 대기 (check_data)
G-C07  추적 — 역방향 · 정방향 재귀 · 깊이 20 분기 100 2초                    PASS  재귀 추적 · 깊이 20 분기 100 — test_lineage_scenario -k trace/depth 통과 (3 passed, 4 deselected in 0.79s) · QA 대조 대기 (check_data)
G-C08  키 연결 — LOT 번호 → 지시 · 실적 · 측정값 · 검사 · 출하 · 채번 한 곳       PASS  LOT P-EX-0001 → 지시 W-EX-0001 · 실적 #13 · 측정값 2 · 검사(자손 포함) 2 · 출하 1 — lineage.resolve + SQL 5 · 채번 카운터(sys_number_seq)를 쓰는 다른 파일 0 · QA 대조 대기 (check_data)
G-C09  시드 멱등 — 2회 실행 행 수 diff 0 · (예시) 표기                     미검증  이 실행에서는 시드를 돌리지 않았다 — `make gate-full`
G-C10  집계 — stats = QA 별도 SQL · measure_series                미검증  tools/check_data.py 없음 (QA2 가 별도 SQL 로 대조) — 개발3 손계산 test_stats 통과 (10 passed in 0.32s)
G-C11  빈 화면 — 미수집 / 미확정 (D-nn)                                PASS  화면 51 중 표 있는 화면 43 · 행 0 인 표를 미수집 표시 없이 둔 화면 0 · (참고) ctx 빈 목록 화면 7 중 본문에 `미수집`/`미확정` 글자 없는 곳 ['JOB-02:results', 'POP-02:results', 'POP-03:rows', 'SHP-01:lots', 'SHP-02:lots'] — 부속 목록은 QA 가 화면으로 대조 · QA 대조 대기 (check_data)
G-C12  범위 밖 0 — 설비 제어 · 업종 전용 기능 없음                           PASS  라우트 148 중 제어 · 명령성 경로 0 · 테이블 52 중 제어성 이름 0 · 금지어는 G-C23 (FAIL) · QA 대조 대기 (check_data)
G-C13  4채널 — POP 스캔 · 모바일 390px · 현황판 새로고침                    PASS  body.ch-pop True · ch-mobile True · ch-board+새로고침 True · 채널 밖(BAS-01?device=pop) 403 · POP 화면 13 중 data-scan 1개 7 · 2개 이상 0 · 390px 가로 넘침 0 은 브라우저 대조 · QA 대조 대기 (check_security)
G-C14  출력물 4종 — 작업지시서 · 라벨 2 · 성적서 · 바코드 SVG                  PASS  작업지시서 200 svg 바코드=T-W-D811FC5DB8 · LOT 라벨 200 svg 바코드=P261009-0892 · 출하 라벨 200 svg 바코드=T-S-68D428C204 · 성적서 200 svg 바코드=C261009-057 · LOT 라벨 바코드 → lineage.resolve 같은 LOT · QA 대조 대기 (check_security)
G-C15  이관 배치 4 — Import 파일 · 멱등 · 리포트                         FAIL  examples dry-run 8회(명령 4 × 2) 오류 0 · 업무 테이블 행 수 diff {'bas_equipment': (165, 166), 'eqp_collect': (145, 147), 'ifc_collect_raw': (126, 128), 'ifc_erp_link': (335, 361), 'ifc_outbox': (33, 34)} · sys_migration_log +34 · test_migrate 실패 (2 failed, 3 passed in 1.07s) · QA 대조 대기 (check_security)
G-C16  ERP — 어댑터 + 501 명시 · 조용한 폴백 0                          PASS  기본 어댑터 push → 501 D-02 · flush processed 34 undecided 34 sent 0 failed 0 · ifc_outbox {'미확정': 34} · QA 대조 대기 (check_security)
G-C17  RBAC — 48칸 데이터 · 없음 403 · 조회 = 쓰기 403 · scopes         PASS  DB 권한 표 48/48칸 (입력 19 · 조회 22 · 없음 7) · 없음 칸 403 위반 0 · 쓰기 기능 79 × 역할 4 중 권한 없는 조합 207 전수 403 위반 0 · 범위 칸 4종 True · QA 대조 대기 (check_security)
G-C18  접근 로그 — 로그인 · 조회 · 변경 · SYS-04                         PASS  sys_access_log login_ok 4188 · login_fail 131 · view 11774 · change 5522 · SYS-04 200 · QA 대조 대기 (check_security)
G-C19  비밀 — 저장소 · 문서에 비밀 값 없음                                 PASS  저장소 대상 파일 359개 중 비밀 값(MES_SEED_PASSWORD · SESSION_SECRET · COLLECT_TOKEN)이 든 파일 0 · .env gitignore 됨 · QA 대조 대기 (check_security)
G-C20  백업 — make backup · restore-check                       PASS  backup rc=0 (다음: `make restore-check` — 이 덤프를 임시 DB 에 복구해 테이블별 행 수를 대조한다) · restore-check rc=0 (판정: PASS — 테이블 52개 전부 복구 · 테이블별 행 수 일치 (행 36,327)) · QA 대조 대기 (check_security)
G-C21  빌드 — pytest 전건 · check-routes · /health 200            FAIL  pytest passed 237 · failed 4 ['tests/test_arch_smoke.py::test_core_has_no_forbidden_terms', 'tests/test_job_work_orders.py::test_status_board_today_week_and_drilldown', 'tests/test_measure.py::test_declaration_makes_three_fields_in_end_form'] · check-routes PASS · /health 200
G-C22  브라우저 한 바퀴 — outputs/e2e/core 캡처 · QA3 판정               미검증  outputs/e2e/core 파일 0개 — `outputs/qa3-채널보안.md` 없음 (QA3)
G-C23  용어 중립 — 코어 금지어 0 · t() 누락 0                            FAIL  검사 2 · 통과 못한 1 — 코어 금지어 0: 파일 155 · 금지어 44개 · 위반 2 — ['src/mescore/app/static/style.css:8 `조색` (인쇄필름)', 'src/mescore/app/templates/job/status.html:2 `롤` (인쇄필름)']
G-C24  측정값 — bas_process_param 선언 → POP 폼 → pop_measure → 집계  FAIL  test_measure 실패 (2 failed, 2 passed in 0.71s) · 시드 키(weight · temp)를 코어 코드가 안다 0 · QA 대조 대기 (check_data)

[팩 foodservice · mes_foodservice_db]
G-P01  격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0  FAIL  검사 7 · 통과 못한 2 — R1 코어 파일 해시 변동 0: [foodservice] 바뀜 7 · 생김 0 · 없어짐 0 ['src/mescore/app/static/app.js', 'src/mescore/app/templates/home/main.html', 'src/mescore/app/templates/pop/_layout.html'] / R10 코어 템플릿 덮어쓰기 목록 (README.md 에 적는다): [foodservice] 덮어쓴 템플릿 ['print/work_order.html']
G-P02  규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml                  PASS  검사 2 전부 PASS
G-P03  추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0                          미검증  [foodservice] 추적표: design_source ../NeedsFood MES Platform/docs/design/design.json · import_design 매핑 판정은 그 도구의 출력으로 (미구현)
G-P04  시나리오 — gates.yaml: scenarios 재현                      FAIL  [foodservice] 시나리오 8 · 실행 0 · 실패 8 ['S1: 테스트 파일 없음', 'S2: 테스트 파일 없음']
G-P05  용어 — terms 키 치환 안 된 노출 0                             PASS  [foodservice] 화면 54 · terms 키 16 · 치환 안 된 노출 0
G-P06  착수 시간 — outputs/pack-timing.md ≤ 4h                  미검증  [foodservice] outputs/pack-timing.md 없음 (사람 · QA3 실측)

[팩 kimchi · mes_kimchi_db]
G-P01  격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0  FAIL  검사 7 · 통과 못한 1 — R1 코어 파일 해시 변동 0: [kimchi] 바뀜 7 · 생김 0 · 없어짐 0 ['src/mescore/app/static/app.js', 'src/mescore/app/templates/home/main.html', 'src/mescore/app/templates/pop/_layout.html']
G-P02  규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml                  PASS  검사 2 전부 PASS
G-P03  추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0                          미검증  [kimchi] 추적표: design_source ../Limjingang Kimchi MES Platform/docs/design/design.json · import_design 매핑 판정은 그 도구의 출력으로 (미구현)
G-P04  시나리오 — gates.yaml: scenarios 재현                      FAIL  [kimchi] 시나리오 4 · 실행 0 · 실패 4 ['S1: 테스트 파일 없음', 'S2: 테스트 파일 없음']
G-P05  용어 — terms 키 치환 안 된 노출 0                             PASS  [kimchi] 화면 62 · terms 키 25 · 치환 안 된 노출 0
G-P06  착수 시간 — outputs/pack-timing.md ≤ 4h                  미검증  [kimchi] outputs/pack-timing.md 없음 (사람 · QA3 실측)

[팩 printfilm · mes_printfilm_db]
G-P01  격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0  FAIL  검사 7 · 통과 못한 2 — R1 코어 파일 해시 변동 0: [printfilm] 바뀜 7 · 생김 0 · 없어짐 0 ['src/mescore/app/static/app.js', 'src/mescore/app/templates/home/main.html', 'src/mescore/app/templates/pop/_layout.html'] / R10 코어 템플릿 덮어쓰기 목록 (README.md 에 적는다): [printfilm] 덮어쓴 템플릿 ['print/document.html', 'print/label_lot.html', 'print/work_order.html']
G-P02  규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml                  PASS  x_printfilm_ 8 · gates.yaml 8 · 다른 접두 0 · 공통 컬럼 빠짐 0
G-P03  추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0                          미검증  [printfilm] check_trace 에 G-P03 행 없음
G-P04  시나리오 — gates.yaml: scenarios 재현                      FAIL  [printfilm] 시나리오 3 · 실행 0 · 실패 3 ['S1: 테스트 파일 없음', 'S2: 테스트 파일 없음']
G-P05  용어 — terms 키 치환 안 된 노출 0                             FAIL  팩 용어: [printfilm] RuntimeError: packs/printfilm/function-list.md 검증 실패 24건:
G-P06  착수 시간 — outputs/pack-timing.md ≤ 4h                  미검증  [printfilm] outputs/pack-timing.md 없음 (사람 · QA3 실측)

PASS 22 · FAIL 11 · WARN 0 · BLOCKED 0 · 미검증 9 / 전체 42
※ WARN · 미검증은 통과가 아니다. 「QA 대조 대기」 가 붙은 PASS 는 아키텍트 증거 판정 — QA 검사기(check_data · check_security)가 생기면 그 출력이 우선한다. BLOCKED 는 decisions.md 에 D-번호와 사유가 있어야 종료 조건(goal.md §4.4)을 만족한다.
```

다음 회전(QA 3 투입)에 막히는 것: ① QA 도구 3(`check_data` · `check_security` · `check_screens`)이 생기면 `gate.py` 가 그 출력을 우선 — 출력 형식은 `interfaces.md` §10 ② 같은 `mes_core_db` 를 7명이 동시에 쓰므로 행 수 diff · 건수 비교 판정(G-C05 · C09 · C15 · C18)은 **단독 실행**에서만 믿을 수 있다 — QA 는 자기 DB(`MES_PG_DSN`)를 쓰거나 `gate-full` 은 한 번에 하나 ③ 테스트 잔존 데이터(오늘 지시 663건 · 설비 165건 · 접근 로그 2만)가 상한 500 화면을 밀어낸다 — QA2 `check_data` 는 `make db-reset` 뒤 빈 DB 에서 시작해야 한다 ④ 웨이브 A′ 가 도는 동안 템플릿 HTML 단언(test_measure · check_terms)이 흔들린다 — 디자이너 3명이 끝낸 뒤 회전 4 아키텍트가 `core-hash` 를 다시 찍고 G-P01 R1 을 재판정 ⑤ G-C22 · G-P06 은 브라우저 · 사람 실측.

## 2026-10-09 회전 3 — 오케스트레이터 (웨이브 A′ 프런트 · 웨이브 B 팩 3 · 아키텍트 D-1 판정)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 코어 게이트 | **PASS 21 · FAIL 1(G-C21 ← job 테스트 2) · 미검증 3**(C09 gate-full · C10 QA SQL · C22 브라우저) | `make gate`(오케스트레이터 직접) |
| 팩 게이트 | 3팩 모두 G-P02 · G-P04 PASS · G-P05 foodservice/printfilm PASS(kimchi FAIL = SYS-04 `|t` 코어 한 줄) · G-P01 FAIL 3(코어 해시 기준값이 A′ 이전) · G-P03 미검증(check_trace ↔ import_design 미배선 · 도구 직접 실행은 3팩 고아 0) | 〃 |
| 테스트 | 239 passed · 2 failed(`test_job_work_orders` — 잔존 지시 1,493건 > LIST_LIMIT 500 · 정렬) · 팩 테스트 foodservice 19 · printfilm 39 · kimchi 26 | `uv run pytest -q` · `MES_PACK=<팩> uv run pytest -q packs/<팩>/tests` |
| 프런트 | 토큰 `tokens.css` 분리 · base/매크로(서명 변경 0) · Web 18 · POP 13 · 모바일 · 현황판 폴링 1배 · 출력물 4 · 메인 · 대시보드 · 추적 — placeholder 0 · 금지어 0 · 캡처 `outputs/design/` 100장+ | `make check-routes` · `check-terms` · `ls outputs/design` |
| 팩 재현 | printfilm S1 `lot_genealogy` 10행(투입 3 · splice 2 · 슬리팅 3 · 출하 2) · foodservice 소요량 144/120/24 · 배치 측정값 collect · kimchi S1 10행(기획 9 — 합병 API 가 별도 LOT) · S2 422 hook_rejected · S3 알람 합침 · S4 숙성 | 각 팩 `tests/` · `outputs/e2e/<팩>/` |
| 코어 변경 요청 | 세 팩 공통: 설비 알람(D-501 반영 결정 · 테이블 52→54 는 정본 수정 필요 → **사람 결정**) · 팩 시드 적재 범위(CR-9) · check_trace↔import_design(CR-10) · R9 범위(CR-11) · `read_attrs(Request)` 버그 · `menus.rename` 이중 치환 · 채널 코드 정규화 · 시드 순서 · `audit` 기능명 `t()` | `progress-dev{1,2,3}.md` §3 |
| 다음 | 회전 4: 아키텍트 D-2(요청 처리 · core-hash · R9 정의) · 개발 3 수정 · QA 3(`mes_qa_db` 전용 · check_screens/data/security · E2E) · 디자이너1 채널 틀 통합 | — |

## 2026-10-09 회전 4 — 아키텍트 (웨이브 D-2: 요청 처리 · CR-9/10/11 · 422 입력값 · R9 정의 · D-501 정리 · core-hash)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 1 packs (`733074f` · `649c2d6`) | ① `read_attrs(Request)` — starlette `Request` 는 Mapping 이라 폼을 안 읽던 것(개발1 ①) → `HTTPConnection` 이면 `request.form()` · 폼 이름 `attr_<key>` · `attrs.<key>` 둘 다 ② `t()` 한 번 훑기 · 같은 자리 긴 키 먼저 · 치환 결과 재치환 없음 · 겹말 방지(`추적: LOT 추적` 에서 `LOT 추적` → 그대로) ③ **`menus.rename` 값은 `t()` 를 걸지 않는다**(코디네이터 · 개발3 22 — 합성어 `품질이상` 까지) · 단 값이 terms 키와 똑같으면(`출하`) 치환 · `check_terms` G-P05 는 rename 값을 노출로 세지 않음 ④ 채널 코드 `web/pop/mobile/board` · 라벨 둘 다(`screens[]` · `menus.add[]` · `channels` 키) → 병합본은 라벨/코드 키로 정규화 · 모르는 값 `PackError` · `pack-contract.md` §2 | `tests/test_arch_packs.py` 26 passed(새 5) · 3팩 `packs.load` OK |
| 2 팩 시드 CR-9 (`6c77eb9`) | 순서 **seeds[] 공정 → 품목 → 설비 → process_params → inspection_items → 나머지 seeds[] 선언 순서 → 계정** · `seeds[]` 항목 = 문자열(이름 접두 `processes items equipment partners workers defect_codes codes kpi_indicators users`) 또는 `{file, table, key}`(`x_<팩>_*` · 허용 코어 기준정보 8 — 그 밖 `PackError`) · 모든 파일 `attrs.<키>` → attrs 합침 · 열이 아닌 `<x>_code` 는 FK 로 풀기(없는 값 오류 · `ink_code → ink_formula_id`) · 문자열 항목의 모르는 열은 경고(stderr) · `{…}` 항목은 오류 · 계정 = 팩 역할마다 1(로그인 ID 역할 코드 소문자 · 코어 4 는 `admin prod qa field`) + `seed/users.csv`(비밀번호 열 없음 — `MES_SEED_PASSWORD`) | **빈 임시 DB**(스키마 + schema_ext) 3팩 각각 `seed_core` 2회 diff 0 · 우회 없이 첫 시드 성공 · 실 팩 DB `MES_PACK=<팩> make db-seed` ×3 2→3회 diff 0 · printfilm `{file,table,key}` 4 + defect_codes 로 `seed_pack.sql` 결과와 같은 수(판사양 2 · 아니록스 2 · 잉크 2 · 조성 3 · 불량 attrs 4 · 공정 구분 3) 2회 diff 0 · 엄격 모드 모르는 열 · 없는 FK 값 SystemExit |
| 3 audit (`3e86ba4`) | 저장 = function-list 중립어 원문 · 표시 = SYS-04 `|t`(개발1 82f525f) · `interfaces.md` §2 · audit docstring | 문서 |
| 4 422 입력값 · 정적 버전 (`2d908b2`) | `http.validation_error(..., values=)` · `http.FormEcho`(urlencoded POST 본문 복사 · 64KB · 소비 안 함) → `_back_with_flash` 가 `flash.values`(비밀 칸 password/token/secret/csrf 제외 · 칸 2000자) · 훅 거부 · DB 제약 422 도 같다 · JSON 422 에는 values 없음 · `asset_version()` = `static/` 전체 rglob 최신 mtime · `api-contract.md` §2 · `interfaces.md` §8. 디자이너1 매크로(47bbbdc)와 이어 **BAS-01 중복 코드 POST → 303 → 다시 그린 화면에 `item_code="PRD-EX-01"` · `item_name="값유지확인-예시"` 값이 남음** | `tests/test_arch_smoke.py::test_422_form_post_keeps_values_in_flash_and_asset_version_tracks_static` · TestClient HTML 실측 |
| 요청 (`40cca8a`) | `POST /login` 실패 401 재렌더도 `role_summary` · `n_menus`(GET 은 개발1 home · POST 는 인증이라 main 에 둠) | `test_login_401_then_ok_and_logout_revokes` |
| 요청 (`7581e2d`) | `http.sort_clause(sort, allowed, default)` — `열` · `-열` · 쉼표 · 허용 열만 · 모르는 열 422 (D-37). 라우터 적용은 각 담당 | `test_sort_clause_allows_only_declared_columns` |
| 5 G-P03 (`f1e0974`) | `check_trace` 가 `import_design.py --pack <팩>` 출력 마지막 `G-P03 … PASS|FAIL|미검증` 줄 + 종료코드(0/1/2) 로 판정 · 어긋나면 FAIL · `--pack` 없는 도구면 `MES_PACK` 로 다시 | 3팩 G-P03 **PASS**(아래 원문) |
| 6 R9 (`904b12c` · D-36) | R9 = 코어 단독 `tests/` 전건(G-C21) + 팩 올린 채 `tests/test_arch_*.py`(check_pack R9 → G-P01). `test_arch_packs` 임시 팩 픽스처가 끝나고 **실행 팩**으로 복귀(전엔 코어 단독으로 돌려 뒤 테스트가 팩 DB 를 코어 병합본으로 봤다) | kimchi · foodservice `test_arch_*` 50 passed · 6 skipped(구조 · 병합만 · 코어 권한 표 단언은 `is_core_only`) |
| 7 `v_lot_state` (`3d2bdf3`) | PRODUCT: 출하 계보 → 출하 · 분할/합병/생산 → 소진(통째) · **투입만 → 잔량**(≤0 · qty NULL 투입 · LOT 수량 NULL → 소진). `create or replace view` 로 `mes_core_db` · 팩 DB 3 에 다시 적용 | `test_arch_schema::test_product_lot_partial_input_stays_in_stock` · 계보 · POP · 출하 · 이관 테스트 60 passed |
| 8 D-501 (`969b63f`) | 상태 **차단(사람 승인 대기)** — `bas_equipment_param` · `eqp_alarm`(열린 알람 하나 부분 uq · 합침 count) · `collect.receive` 판정(정제 뒤 · `on_collect` 앞 · 자동 해제 기본 off) · `on_alarm_raised` · EQP-05 를 한 벌로 정리. **스키마 · 코드 변경 0** | `decisions.md` D-501 |
| 9 결정 등재 (`969b63f`) | 개발 D-107 · D-108 · D-206~D-209 · D-303~D-305 · 디자이너 D-606(현황판 다크 `?theme=dark` — 차단) · D-607(채널 틀 base 통합) · 아키텍트 D-36 · D-37 | `decisions.md` |
| 10 core-hash (`3decfe9`) | `outputs/core.sha256` 158 파일 — 회전 4 개발1·2·3 · 디자이너1 커밋분 + **QA 미커밋 `tools/check_data.py` · `check_screens.py`**(작업 중이라 다음 편집에서 R1 이 다시 어긋난다 — D-33) | `make core-hash` |
| pytest (코어 단독) | **278 passed · 1 failed** — `test_arch_smoke::test_core_has_no_forbidden_terms` ← QA `tools/check_data.py:1528 · 1532` 의 `슬리팅` · `splice`(미커밋 QA 파일). 아키텍트 파일 위반 0 | `uv run pytest -q -p no:cacheprovider` |
| check-routes · check-terms | G-C03 라우트 PASS 56/56 · placeholder 0 · RBAC 204 위반 0 · G-C23 FAIL 3(전부 QA `check_data.py`) · t() 누락 0 | `make check-routes` · `make check-terms` |
| 게이트 | **PASS 27 · FAIL 9 · 미검증 6 / 42** — QA 검사기(check_screens · check_data)가 이번 회전 처음 판정에 들어왔다(`mes_qa_db`) | `make gate`(09:21) → `outputs/gate-r4-arch.txt` |

### FAIL 9 — 누구 몫인가

| 게이트 | 원인 | 담당 |
|---|---|---|
| G-C02 | QA check_screens 계약 호출 FAIL 21(F-ORD-02/03/08/09 · F-MAT-02/07 · F-POP-03/04/05/07 · F-QUA-02/05 …) — 정상 + 오류 계약 호출 판정 | QA 대조 → 개발2 · 개발3 (`outputs/qa*`) |
| G-C03 | `POST /login/as`(D-605 개발용 로그인) — 인증 없이 열리는 경로 · 비밀번호 없는 로그인(`MES_ENV=dev`). D-605 는 dev 만이라 의도된 것이나 QA 기준은 계약 5종 | 개발1 · 사람(D-605 를 gate 환경에서 끌지) |
| G-C08 | TRC-02 지시 링크 `/job/status?wo=W261009-001` → 404 | 개발3 `trc._links` ↔ 개발1 JOB-02 `?wo=` |
| G-C11 | `미확정` 뒤 `(D-nn)` 없음 — KPI-01「% 목표 미확정」 · SYS-06「실행 폴더 미확정 (MES_MIGRAT…」 | 디자이너3/개발3(KPI-01) · 개발1(SYS-06) |
| G-C21 · G-C23 | QA `check_data.py` 금지어 3(`슬리팅` · `splice`) | QA2 |
| G-P01 ×3 | R1 = QA 미커밋 2 파일(해시 뒤 편집) · R9 = 같은 금지어 테스트 1건 · R10 WARN(foodservice 1 · printfilm 3 — README 기재) | QA2 · (해시는 QA 커밋 뒤 아키텍트 재기록) |

미검증 6: G-C10 · G-C12(check_data rc=1 — 판정 행 없음 · QA2 작업 중) · G-C22(QA3 판정 문서 없음 · e2e 캡처 25) · G-P06 ×3(사람 실측).

### `make gate` 판정표 원문 (2026-10-09 09:21 · 줄마다 앞 400자 · 전문 `outputs/gate-r4-arch.txt`)

```
게이트 판정 — MES 표준플랫폼 · 2026-10-09 09:21
[코어 단독 MES_PACK=]
G-C01  메뉴 — 코어 12 · 공통 5 · nav = core.yaml                    PASS  검사 7 전부 PASS
G-C02  기능 — 132 + 이관 4 · 계약 = API = 테스트 · 고아 0                FAIL  기능 136 계약 호출 (정상 + 오류 계약): PASS 115/136 · FAIL 21 ['F-ORD-02', 'F-ORD-03', 'F-ORD-08', 'F-ORD-09', 'F-MAT-02', 'F-MAT-07', 'F-POP-03', 'F-POP-04', 'F-POP-05', 'F-POP-07', 'F-QUA-02', 'F-QUA-05'] · 미검증 0 [] · 검사 676건 · DB mes_qa_db
G-C03  화면 — 51 + 공통 5 전부 200 · placeholder 0                  FAIL  검사 2 · 통과 못한 1 — 응답 모양 · 인증 없는 경로 · 503 (api-contract §2): 검사 31 · 통과 못한 2 ["인증 없이 열리는 경로 = 계약 5종뿐 (라우트 139 전수 401): ['POST /login/as → 422']", '비밀번호 없는 로그인 경로 0 (POST /login/as role=ADMIN): /login/as 200 → 그 세션 /sys/users 200 · MES_ENV=dev']
G-C04  스키마 — 테이블 52 · 계약 = 실제 DB · 공통 컬럼                      PASS  검사 8 전부 PASS
G-C05  쓰기 경계 — trc · kpi 쓰기 0 · lot_genealogy 는 lineage 만     PASS  GET 132회(화면 · 추적 · 라벨 · 인쇄 · 팝업 · 집계 — JSON+HTML) 응답 {2: 132} · 행 수 · 최종 수정 시각 바뀐 테이블 0
G-C06  계보 재현 — 코어 시나리오 lot_genealogy 10행 (API)                PASS  검사 2 전부 PASS
G-C07  추적 — 역방향 · 정방향 재귀 · 깊이 20 분기 100 2초                    PASS  검사 7 전부 PASS
G-C08  키 연결 — LOT 번호 → 지시 · 실적 · 측정값 · 검사 · 출하 · 채번 한 곳       FAIL  검사 3 · 통과 못한 1 — LOT 번호 → 화면 링크 따라가기 (API): TRC-02 start_links ['backward', 'forward', 'inspection', 'lot', 'work_order'] → 지시 · POP-02 측정값 · QUA-02 검사 · SHP-02 출하 — 불일치 ['지시 링크 /job/status?wo=W261009-001 → 404']
G-C09  시드 멱등 — 2회 실행 행 수 diff 0 · (예시) 표기                     PASS  검사 2 전부 PASS
G-C10  집계 — stats = QA 별도 SQL · measure_series                미검증  check_data 출력에 G-C10 판정 행 없음 (rc=1)
G-C11  빈 화면 — 미수집 / 미확정 (D-nn)                                FAIL  검사 2 · 통과 못한 1 — 미확정 표기 — (D-nn) 동반: 화면 본문의 `미확정` 중 `(D-nn)` 이 바로 붙지 않은 곳 ['KPI-01:「% 목표 미확정 % 불량 미수집 시간」', 'SYS-06:「실행 폴더 미확정 (MES_MIGRAT」'] (goal.md G-C11: 미정이면 `미확정 (D-nn)`)
G-C12  범위 밖 0 — 설비 제어 · 업종 전용 기능 없음                           미검증  check_data 출력에 G-C12 판정 행 없음 (rc=1)
G-C13  4채널 — POP 스캔 · 모바일 390px · 현황판 새로고침                    PASS  body.ch-pop True · ch-mobile True · ch-board+새로고침 True · 채널 밖(BAS-01?device=pop) 403 · POP 화면 13 중 data-scan 1개 9 · 2개 이상 0 · 390px 가로 넘침 0 은 브라우저 대조 · QA 대조 대기 (check_security)
G-C14  출력물 4종 — 작업지시서 · 라벨 2 · 성적서 · 바코드 SVG                  PASS  작업지시서 200 svg 바코드=T-W-E373FE6378 · LOT 라벨 200 svg 바코드=P261009-2349 · 출하 라벨 200 svg 바코드=T-S-2762A3FE93 · 성적서 200 svg 바코드=C261009-159 · LOT 라벨 바코드 → lineage.resolve 같은 LOT · QA 대조 대기 (check_security)
G-C15  이관 배치 4 — Import 파일 · 멱등 · 리포트                         PASS  examples dry-run 8회(명령 4 × 2) 오류 0 · 이관 대상 테이블 20 행 수 diff 0 · sys_migration_log +34 · test_migrate 통과 (5 passed in 0.38s) · QA 대조 대기 (check_security)
G-C16  ERP — 어댑터 + 501 명시 · 조용한 폴백 0                          PASS  기본 어댑터 push → 501 D-02 · flush processed 89 undecided 89 sent 0 failed 0 · ifc_outbox {'미확정': 89} · QA 대조 대기 (check_security)
G-C17  RBAC — 48칸 데이터 · 없음 403 · 조회 = 쓰기 403 · scopes         PASS  검사 4 전부 PASS
G-C18  접근 로그 — 로그인 · 조회 · 변경 · SYS-04                         PASS  sys_access_log login_ok 10551 · login_fail 299 · view 25701 · change 13991 · SYS-04 200 · QA 대조 대기 (check_security)
G-C19  비밀 — 저장소 · 문서에 비밀 값 없음                                 PASS  저장소 대상 파일 501개 중 비밀 값(MES_SEED_PASSWORD · SESSION_SECRET · COLLECT_TOKEN)이 든 파일 0 · .env gitignore 됨 · QA 대조 대기 (check_security)
G-C20  백업 — make backup · restore-check                       PASS  backup rc=0 (다음: `make restore-check` — 이 덤프를 임시 DB 에 복구해 테이블별 행 수를 대조한다) · restore-check rc=0 (판정: PASS — 테이블 52개 전부 복구 · 테이블별 행 수 일치 (행 90,078)) · QA 대조 대기 (check_security)
G-C21  빌드 — pytest 전건 · check-routes · /health 200            FAIL  pytest passed 278 · failed 1 ['tests/test_arch_smoke.py::test_core_has_no_forbidden_terms'] · check-routes PASS · /health 200
G-C22  브라우저 한 바퀴 — outputs/e2e/core 캡처 · QA3 판정               미검증  outputs/e2e/core 파일 25개 — `outputs/qa3-채널보안.md` 없음 (QA3)
G-C23  용어 중립 — 코어 금지어 0 · t() 누락 0                            FAIL  검사 2 · 통과 못한 1 — 코어 금지어 0: 파일 158 · 금지어 44개 · 위반 3 — ['src/mescore/tools/check_data.py:1528 `슬리팅` (인쇄필름)', 'src/mescore/tools/check_data.py:1528 `splice` (인쇄필름)', 'src/mescore/tools/check_data.py:1532 `슬리팅` (인쇄필름)']
G-C24  측정값 — bas_process_param 선언 → POP 폼 → pop_measure → 집계  PASS  폼 칸 ['m_qa2_req', 'm_qa2_rng', 'm_qa2_col'] · HTML 입력 ['m_qa2_req', 'm_qa2_rng'] · 수집 칸 라벨 있음 · 필수 누락 422 · 저장 측정값 0 · LOT None · 범위 이탈 25 → 200 · deviated True · 화면 '이탈' 있음 · collect 수신 [200, 200, 200] → 대표값(avg) 3.0 (기대 3 — 구간 밖 9 제외) · 수신 0 실적 종료 200 · collect 값 None · 화면 미수집 있음 · 선언 변경 뒤 새 실적 폼 ['m_qa2_req', 'm_qa2_rng', 'm_qa
[팩 foodservice · mes_foodservice_db]
G-P01  격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0  FAIL  검사 8 · 통과 못한 3 — R1 코어 파일 해시 변동 0: [foodservice] 바뀜 2 · 생김 0 · 없어짐 0 ['src/mescore/tools/check_data.py', 'src/mescore/tools/check_screens.py'] / R10 코어 템플릿 덮어쓰기 목록 (README.md 에 적는다): [foodservice] 덮어쓴 템플릿 ['print/work_order.html'] / R9 팩을 올린 채 tests/test_arch_*.py 통과 (코어 단독 tests/ 전건은 G-C21): [foodservice] 파일 3 · 1 failed, 51 passed
G-P02  규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml                  PASS  검사 2 전부 PASS
G-P03  추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0                          PASS  산출물 49 · 매핑 41 · 범위 밖 8 · 고아 0 · N:1 8 · 1:N 6 · 모르는 화면 ID 0 (import_design --pack)
G-P04  시나리오 — gates.yaml: scenarios 재현                      PASS  [foodservice] 시나리오 8 · 실행 8 · 실패 0
G-P05  용어 — terms 키 치환 안 된 노출 0                             PASS  [foodservice] 화면 54 · terms 키 16 · 치환 안 된 노출 0
G-P06  착수 시간 — outputs/pack-timing.md ≤ 4h                  미검증  [foodservice] outputs/pack-timing.md 없음 (사람 · QA3 실측)
[팩 kimchi · mes_kimchi_db]
G-P01  격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0  FAIL  검사 8 · 통과 못한 2 — R1 코어 파일 해시 변동 0: [kimchi] 바뀜 2 · 생김 0 · 없어짐 0 ['src/mescore/tools/check_data.py', 'src/mescore/tools/check_screens.py'] / R9 팩을 올린 채 tests/test_arch_*.py 통과 (코어 단독 tests/ 전건은 G-C21): [kimchi] 파일 3 · 1 failed, 51 passed, 6 skipped in 3.28s ['tests/test_arch_smoke.py::test_core_has_no_forbidden_terms']
G-P02  규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml                  PASS  검사 2 전부 PASS
G-P03  추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0                          PASS  산출물 64 · 매핑 52 · 범위 밖 12 · 고아 0 · N:1 14 · 1:N 15 · 모르는 화면 ID 0 (import_design --pack)
G-P04  시나리오 — gates.yaml: scenarios 재현                      PASS  [kimchi] 시나리오 4 · 실행 4 · 실패 0
G-P05  용어 — terms 키 치환 안 된 노출 0                             PASS  [kimchi] 화면 62 · terms 키 25 · 치환 안 된 노출 0
G-P06  착수 시간 — outputs/pack-timing.md ≤ 4h                  미검증  [kimchi] outputs/pack-timing.md 없음 (사람 · QA3 실측)
[팩 printfilm · mes_printfilm_db]
G-P01  격리 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0  FAIL  검사 8 · 통과 못한 3 — R1 코어 파일 해시 변동 0: [printfilm] 바뀜 2 · 생김 0 · 없어짐 0 ['src/mescore/tools/check_data.py', 'src/mescore/tools/check_screens.py'] / R10 코어 템플릿 덮어쓰기 목록 (README.md 에 적는다): [printfilm] 덮어쓴 템플릿 ['print/document.html', 'print/label_lot.html', 'print/work_order.html'] / R9 팩을 올린 채 tests/test_arch_*.py 통과 (코어 단독 tests/ 전건은 G-C21
G-P02  규모 — 팩 화면 · 테이블 · 기능 수 = gates.yaml                  PASS  검사 2 전부 PASS
G-P03  추적표 — 산출물 ID ↔ 화면 매핑 · 고아 0                          PASS  산출물 32 · 매핑 31 · 범위 밖 1 · 고아 0 · N:1 2 · 1:N 3 · 모르는 화면 ID 0 · 설계 원본에 없는 매핑 3 (import_design --pack)
G-P04  시나리오 — gates.yaml: scenarios 재현                      PASS  [printfilm] 시나리오 3 · 실행 3 · 실패 0
G-P05  용어 — terms 키 치환 안 된 노출 0                             PASS  [printfilm] 화면 57 · terms 키 9 · 치환 안 된 노출 0
G-P06  착수 시간 — outputs/pack-timing.md ≤ 4h                  미검증  [printfilm] outputs/pack-timing.md 없음 (사람 · QA3 실측)
PASS 27 · FAIL 9 · WARN 0 · BLOCKED 0 · 미검증 6 / 전체 42
※ WARN · 미검증은 통과가 아니다. 「QA 대조 대기」 가 붙은 PASS 는 아키텍트 증거 판정 — QA 검사기(check_data · check_security)가 생기면 그 출력이 우선한다. BLOCKED 는 decisions.md 에 D-번호와 사유가 있어야 종료 조건(goal.md §4.4)을 만족한다.
```

명령: `make core-hash` → `uv run pytest -q -p no:cacheprovider` → `make check-routes` → `make check-terms` → `make gate > outputs/gate-r4-arch.txt` · 팩 시드 `MES_PACK=<팩> make db-seed` ×3 · 빈 DB `createdb mes_r4arch_<팩>_tmp_db` + schema/views/schema_ext + `MES_PACK=<팩> MES_PG_DSN=postgresql:///mes_r4arch_<팩>_tmp_db uv run python -m mescore.db.seed_core` ×2.

**넘긴 것 (각 담당)** — ① 개발1 foodservice: `seed_pack.py` 우회 제거 가능(CR-9) · `menus.rename.pop` 을 최종 이름 `조리 실적 (POP)` 으로(지금 `실적 (POP)` 이 그대로 보인다 — rename 은 t() 없음) · `kpi_indicators.csv` 의 `base_value` · `formula` 는 `attrs.` 접두로 ② 개발2 printfilm: rename 값이 그대로 나온다(`생산 실적 (POP)` 등 — 최종 이름 확인) ③ 개발3 kimchi: `rename.qua: 품질이상` 으로 되돌려도 된다 · `equipment_example.csv` 의 `equip_type` · `comm_type` · `collect_tags` 는 `attrs.` 접두로 넣으면 attrs 에 들어간다 ④ 디자이너1: `flash.values` 키 확정(같은 이름 여러 값은 목록) ⑤ QA2: `check_data.py` 금지어 3 · G-C10/12 판정 행 ⑥ 각 목록 화면 정렬은 D-37 `http.sort_clause` 로 ⑦ **사람: D-501**(테이블 52→54 · 화면 51→52 · 기능 132→135 승인 여부) · D-606(현황판 다크 조건) · D-605(gate 환경 dev 로그인).

## 2026-10-09 회전 4 — 오케스트레이터 (아키텍트 D-2 · 개발 3 · 디자이너1 · QA 3 첫 투입)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 게이트(아키텍트 09:21) | PASS 27 · FAIL 9 · 미검증 6 / 42 — QA 검사기 첫 투입. 3팩 G-P02 · P03 · P04 PASS | `make gate` · `outputs/gate-r4-arch.txt` |
| QA1 | 기능 136: PASS 115 · FAIL 21(숫자 아닌 경로 키 422 → 404 계약) · 권한 48칸 · 역할×기능 522호출 위반 0 · 채널 155호출 위반 0 · 결함 10(중대 5) | `check_screens.py` · `outputs/qa1-기능계약.md` |
| QA2 | G-C05 · 06 · 07 · 09 · 10 · 12 · 24 PASS(독립 SQL 재계산 일치) · C08 · C11 FAIL · 팩 printfilm · foodservice PASS · kimchi 행 수 차이 · 결함 6(중대 2) | `check_data.py` · `outputs/qa2-계보데이터.md` |
| QA3 | G-C13~C20 · C22(브라우저 23단계) · G-P06(약 20초) PASS · G-P01 FAIL(R1 해시 · R9 테스트 2건) · 조용한 실패 0 · 결함 7(중대 4) | `check_security.py` · `outputs/qa3-채널보안.md` · `outputs/e2e/core/` |
| 최우선 결함 | ① `MES_ENV` 기본 `dev` → 비밀번호 없는 관리자 로그인(QA1-001 · QA3-001) ② `make db-schema` 가 `MES_PG_DSN` 무시 → 코어 DB 삭제 위험(QA1-008) | — |
| 사람 결정 대기 | D-501 설비 알람: 테이블 52→54 · 화면 51→52 · 기능 132→135 승인 vs EQP-01 표시만(수치 불변) | `decisions.md` D-501 |
| 다음 | 회전 5 웨이브 D: 결함 23건을 담당별로 수정 → 회전 6 QA 재판정 | — |

## 2026-10-09 회전 5 — 아키텍트 (웨이브 D: QA 결함 수정)

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 1 보안 QA1-001 · QA3-001 (`de9feba` · `02d6d16`) | `MES_ENV` 기본 **prod**(비거나 없으면) · `.env.example` `MES_ENV=prod`(로컬 `.env` 의 dev 는 그대로 · `make setup` 새 `.env` 는 prod) · `settings.dev_login_allowed(request)` = dev **그리고** 상대 주소 루프백(127/8 · ::1 — 이름 `testclient`/`localhost` 는 아님) · `main.py` 미들웨어가 라우터 앞에서 404 · 개발1 `home.login_as` 도 같은 함수 · `login.html` 역할 버튼은 ctx `dev_login` · D-605 **확정** · api-contract §2 | `test_dev_login_only_dev_and_loopback` — (빈값 · prod · dev+10.0.0.5 · dev+testclient) 404 · (dev+127.0.0.1 · dev+::1) 200 |
| 2 Makefile QA1-008 (`14bd28f`) | `db-create` · `db-schema` · `db-reset` 대상 = `MES_PG_DSN`(셸 · `.env`) 을 앱과 같은 규칙으로 푼 DB(`tools/db_target.py name|dsn|admin`) · `pack-db` 는 `mes_<팩>_db` 고정 · `restore-check` 는 그 DB 의 덤프(`<DB>-<일시>.dump`)만 | `MES_PG_DSN=postgresql:///mes_qa_db make -n db-schema` → `psql -d "dbname=mes_qa_db host=/tmp" … drop schema` · `MES_PACK=kimchi make -n db-reset` → mes_kimchi_db · `make -n db-create` → mes_core_db |
| 3 check_terms · gate QA1-002 · 010 (`b2761d4`) | `check_terms --pack`: 덮어쓰기 버그 제거 · 화면 글 조각(태그 사이 · title/placeholder/aria-label · 표 본문/선택지/코드 제외 · 숫자/(예시) 조각 제외) 마다 **키별** 판정 · rename 값 · 치환 값 먼저 지움 · /login · /error 포함. gate: `check_screens` 의 G-C02 · C03 · **C13 · C17 · C23** 을 앞 판정과 합침(나쁜 쪽 우선 · 실측 둘 다) · 팩 G-P05 = check_terms + check_screens(팩 DB 읽기만) | `make gate` 원문의 `‖ check_screens:` |
| 4 G-P05 QA1-003 (`9dda6ac`) | `packs.attrs_of()` 가 **t() 거친 라벨**(choices 는 그대로) · rename 값은 그대로(D-38) · pack-contract `attrs` 줄. 3팩 재측정(10:07 gate): **kimchi 0 · foodservice 0 · printfilm 0** — check_terms · check_screens 둘 다 PASS | `test_attr_labels_pass_through_terms` · `make gate` |
| 5 경로 키 404 QA1-004 (`e484766`) | `RequestValidationError` 중 loc[0]=path 가 있으면 404 `not_found` · 본문/쿼리만이면 422 그대로 · 미로그인은 여전히 401 먼저 | `test_non_numeric_path_key_is_404_but_bad_body_is_422` · `POST /ord/orders/abc` · `GET /mat/lots/abc/label` · `GET /shp/documents/abc/print` → 404 · QA1 기능 **136/136 PASS** |
| 6 채널명 t() QA1-005 (`d7f91b6` · `02d6d16` · `9de6316`) | `base.html` 헤더 채널 · 사이드바 배지 · 계약 패널 · `login.html` 채널 표 · 선택 라벨 · 역할 요약 채널. 표지 치환 뒤 `/login` 날것 `현황판` 0 | TestClient 표지(§B§) 치환 |
| 7 ERP 큐 QA1-007 (`2d051e5`) | 계약 문장이 맞다(D-39) — 팩이 `after_commit_shipment_approved` 를 안 두면 `main.CORE_AFTER_COMMIT` 이 자기 트랜잭션에서 `erp.enqueue` → `ifc_outbox` `대기` 1행(created_by=승인자). 팩 훅이 있으면 팩 것만. function-list F-SHP-07 · interfaces §9 | `test_shipment_approved_after_commit_enqueues_erp_by_default` |
| 8 `v_lot_stock` QA2-001 (`6704c24`) | PRODUCT 소비 = Σ 자식 계보 + Σ **종료 전 실적**의 `pop_input`(취소 제외) · 종료 뒤엔 계보로만(한 번만 셈) · `v_lot_state` 불변 · db-schema §3.4. `create or replace` 로 mes_core_db · 팩 DB 3 재적용 | `test_product_lot_open_input_counts_in_stock` (20 − 열린 15 = 5 · 취소 무시 · 종료+계보 뒤 5/15) |
| 9 테스트 QA3-004 · 005 (`3365cf9` · `b232c80`) | `test_admin_opens_every_screen…` 이 `packs.current().hidden` 메뉴 화면을 403 으로 기대 · 부분 투입 테스트는 고유 번호 + 트랜잭션 안 `views.sql` 재적용(오래된 뷰가 남은 DB 에서도 코드 정의 판정 · QA3 실패 원인은 예전 v_lot_state 로 추정) | `MES_PACK=printfilm·kimchi·foodservice uv run pytest tests/test_arch_smoke.py` 21 passed 6 skipped · `MES_PG_DSN=…/mes_qa3_db` 통과 |
| 10 로그아웃 · 쿠키 QA3-007 (`da90231`) | `GET /logout` 405(세션 유지) · `POST /logout` 만 · 템플릿 로그아웃은 이미 폼 3곳 · 쿠키 `httponly` · `samesite=lax` · **dev 아니면 `secure`** | `test_logout_is_post_only_and_cookie_flags` |
| 덤 | 디자이너1 몫(`fffde65`): 모바일 `.m-top` 번호 검색 — TRC-01/02 에서는 그 화면 `?no=` · 현황판 채널 오류/503 `err-msg` 48px+ · `err-code` 64px+. interfaces §6 `measure.params_with_recorded` 한 줄 · `packs.py` 주석 업종어 제거 | 화면 HTML 실측 |
| QA1 도구 수정(아키텍트 · 회전 5) — **QA1 다음 회전 검토** (`0fdfde7` · `e3819c5`) | `check_screens.py` ① 팩 G-P05 가 `menus.rename` 값(팩 최종 이름 · D-38)을 노출로 세지 않음(check_terms 와 같은 규칙) ② G-C03 「인증 없이 열리는 경로」 에서 `POST /login/as → 404` 는 위반 아님(D-605 확정 — 경로 없음). 「비밀번호 없는 로그인 0」 검사는 그대로 | 코디네이터 · 개발1 · 개발3 요청 |
| core-hash (`ceba02e`) | `outputs/core.sha256` 160 파일 — 회전 5 개발1 · 2 · 3 · 디자이너 커밋분 포함 | `make core-hash` |
| pytest (코어 단독) | **301 passed · 0 failed** | `uv run pytest -q -p no:cacheprovider` |
| check-routes · check-terms | G-C03 PASS 56/56 · placeholder 0 · RBAC 204 위반 0 · G-C23 금지어 0 · t() 누락 0 | `make check-routes` · `make check-terms` |
| 게이트 | **PASS 39 · FAIL 1 · WARN 2 · 미검증 0 / 42** (회전 4: 27 · 9 · 미검증 6) | `make gate`(10:07) → `outputs/gate-r5-arch.txt` |

### 남은 FAIL 1 · WARN 2 — 누구 몫인가

| 게이트 | 원인 | 담당 |
|---|---|---|
| G-C23 FAIL | QA1 표지 치환 — ① CMN-01 `/login` 채널 선택 라벨 `현황판` → **gate 뒤 고침**(`9de6316` · 표지 뒤 0) ② CMN-02 메인 `· 관리자 Web · 현황판 · 모바일` — `home/main.html:53` `c.menu.channels|reject(…)|join` 에 `map('t')` · `:67` `{{ channel }}` → `t(channel)` · `:51` `title="{{ c.today_source }}"` → `t(…)`(G-P05 화면 글 · 지금은 check_screens 판정 밖) | 디자이너3 (`home/main.html`) |
| G-P01 WARN ×2 | R10 코어 템플릿 덮어쓰기 — foodservice `print/work_order.html` · printfilm `print/document.html · label_lot.html · work_order.html` 을 README 에 적기 | 개발1(foodservice) · 개발2(printfilm) |

### 회전 5 요청 · 다음 회전 후보

- **개발1**: `home.login_as` · `GET /login` ctx `dev_login` 은 반영됨(개발1 회전 5). foodservice `attrs` 라벨이 t() 를 거치면 어색해진다 — `조리공정구분` → 「조리조리 공정구분」 · `연결 설비이상` → 「연결 설비품질 이슈」 · `이상유형` → 「품질 이슈유형」. 라벨을 중립어로(`공정구분`) 쓰거나 terms 키와 겹치지 않는 낱말(`고장 유형` 등)로 바꾼다(D-38). (지금 gate G-P05 는 표 본문 · 숫자 조각 규칙 때문에 잡지 않는다 — 화면에서 확인.)
- **디자이너3**: 위 `home/main.html` 3곳.
- **QA1(다음 회전)**: `check_screens.py` 아키텍트 수정 2건 검토 · `/login/as` 는 `MES_ENV=dev`+루프백이 아니면 404 가 PASS. `OPEN_PATHS` 의 `("GET","/logout")` 은 이제 라우트가 없다(405).
- **QA3(다음 회전)**: `MES_ENV` 가 비면 prod → 쿠키 `Secure`. **운영을 HTTP 로 띄우면 브라우저가 세션 쿠키를 보내지 않아 로그인이 안 된다**(localhost 는 예외) — 운영 HTTPS 여부는 사람 결정(미확정). 검사 서버를 루프백 밖 주소로 띄우면 `/login/as` 는 404.
- **아키텍트 다음 회전 후보**(개발1 요청): `seed_core` 에 `bom*` 로더(헤더 + 구성품 · attrs · 훅) · `seeds[]` 행에 팩 `after_save_*` 훅 실행 옵션.
- **D-501 은 사람 결정 대기 — 손대지 않았다.**
