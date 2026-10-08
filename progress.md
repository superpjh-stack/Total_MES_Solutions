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
