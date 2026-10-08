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
