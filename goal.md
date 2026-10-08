# /goal — MES 표준플랫폼 구축 (코어 12모듈 · 화면 51 · 기능 132 + 이관 4 · 테이블 52 · 참조 팩 3)

> **이 문서가 메타프롬프트다.** `/loop` 가 매 회전마다 이 문서를 판정 기준으로 읽는다. 투입되는 에이전트(아키텍트 1 · 개발 3 · QA 3)도
> 작업 전에 이 문서와 `CLAUDE.md` · `contracts/` · `decisions.md` · `progress.md` 를 먼저 읽는다.
> 여기 적힌 수치는 `spec.md` 에서 센 값이다. 세는 방법은 §9 에 있으므로 의심되면 다시 센다.

| 항목 | 값 | 출처 |
|---|---|---|
| 시스템 | MES 표준플랫폼 — 코어 한 벌(`src/mescore`) + 업종 팩(`packs/<팩>`). 한 배포 = 코어 + 팩 하나 | `intro.md` §4 · `spec.md` §1 |
| 정본 | `intro.md` · `problem.md` · `spec.md` (이 폴더 루트, **사람만 고친다**) | — |
| 근거 사업 | `../Limjingang Kimchi MES Platform` · `../NeedsFood MES Platform` · `../lcomFine MES` · `../Songwol Data Gateway` (**읽기 전용**) | `intro.md` §3 |
| 규모 | **코어 모듈 12 · 코어 화면 51 + 공통 5 · 기능 132 + 이관 배치 4 · 테이블 52 · 공용 모듈 9 · 검증 도구 7** | `spec.md` §2 · §6 · §10 |
| 확장 지점 | **7** (E1 설정 · E2 속성 · E3 공정 측정값 · E4 모듈 · E5 훅 · E6 계보 · E7 어댑터). 팩이 할 수 있는 일의 전부 | `spec.md` §3 |
| 참조 팩 | `kimchi` · `foodservice` · `printfilm` + `_template` | `spec.md` §8.3 |
| 핵심 | **`lot` + `lot_genealogy` 재귀 계보** 와 **`bas_process_param` → `pop_measure` 측정값**. 업종이 바뀌어도 이 둘은 선언만 바뀐다 | `spec.md` §2.4 · §3.3 |
| 역할 | 기본 4 (관리자 · 생산 · 품질 · 현장) · 권한 표 12 × 4 = 48칸은 DB 데이터 | `spec.md` §3.1 |
| 채널 | 관리자 Web · 현장 POP · 모바일 · 현황판 = 4 | `spec.md` §6.2 |
| 범위 밖 | 설비 제어 · 실 ERP/프린터/Gateway 연결 · AI Agent · 운영 DB 실이관 · 멀티테넌트 · 다국어 | `problem.md` §5 |
| 완료 기준 | **코어만으로 입고 → 출하 → 역추적이 돌고, 참조 팩 3개가 코어 수정 0 으로 각 사업의 핵심 시나리오를 재현한다** | `problem.md` §4.1 G1 · G5 · G6 |
| 코드 위치 | `/Users/gerardo92/Desktop/AI Coding/Standard MES Platform` (이 폴더) | — |

---

## 0. 이 문서를 어떻게 쓰는가

### 0.1 루프 기동 — 이 한 줄을 붙여 넣는다

```
/loop goal.md 를 판정 기준으로 MES 표준플랫폼을 만든다. §4.2 한 회전 절차를 그대로 따른다 —
progress.md·decisions.md 를 읽고(없으면 §3.1 Phase 0 부터), `make gate` 로 §2 게이트 G-C01~G-C24 · G-P01~G-P06 을 실측하고,
FAIL 중 가장 앞선 웨이브의 항목 하나를 골라 §5 프롬프트로 담당 에이전트를 기동하고(병렬 가능한 것은 한 번에),
보고를 믿지 말고 게이트 명령을 직접 다시 돌려 확인한 뒤 실측값과 검증 명령을 progress.md 에 적고 커밋한다.
막히면 decisions.md 에 D-번호로 `차단`을 올리고 다음 항목으로 넘어간다 — 사람을 기다리며 멈추지 않는다.
게이트를 낮추거나 테스트를 건너뛰지 않는다. §4.4 종료 조건을 만족하면 최종 보고를 쓰고 루프를 멈춘다.
```

중단 후 재개는 `/re-begin` 또는 위 한 줄을 다시 붙여 넣는다. 상태는 전부 파일에 있다(§4.5).

### 0.2 이 프로젝트가 직전 사업(엘컴화인 · 니즈푸드 · 임진강)과 다른 점 — 먼저 알고 시작한다

직전 사업은 **한 회사**의 산출물(설계도 · design.json)이 정본이었고 그 회사 용어로 화면을 만들었다. **여기는 회사가 없다.** 정본은 `spec.md` 이고, 화면은 **중립어**로 만든다.

- **코어에는 업종어가 한 글자도 들어가지 않는다.** `spec.md` §12 금지어 목록을 `tools/check_terms.py` 가 코어에서 찾으면 FAIL 이다(G-C23). 골격을 가져온 근거 사업의 솥 · 절임 · Roll · DTF 는 전부 팩으로 간다.
- **"팩이 할 수 있는 일" 은 확장 지점 7개뿐이다.** 참조 팩을 쓰다가 7개 밖의 것이 필요하면 코어를 고치는 게 아니라 `decisions.md` 에 **코어 변경 요청** 을 올린다(§4.3).
- **근거 사업의 구현을 복사하지 않고 일반화한다.** `../lcomFine MES/src/lcomfine/app/{numbering,lineage,printing,rbac,...}.py` 는 가장 가까운 출발점이지만 `roll` → `lot`, `LCOMFINE_` → `MES_`, 회사 고정값 → `pack.yaml` 로 바꿔야 한다.
- **참조 팩 3개가 곧 테스트다.** 코어가 맞게 일반화됐는지는 팩 3개가 코어 수정 0 으로 재현되는지로 판정한다(G-P01 · G-P04). 코어만 완성하고 팩을 미루면 끝난 것이 아니다.
- **실데이터는 없다.** 코어 시드는 `(예시)`, 참조 팩 시드는 근거 사업의 시드 중 `(예시)` 가 붙은 것만 가져온다. 고객명 · 규격값은 지어내지 않는다.

---

## 1. 목표

**코어 12모듈 · 51화면을 PostgreSQL 52테이블 + FastAPI 실 API 에 연동해 팩 없이 입고 → 출하 → 역추적이 돌게 하고, 참조 팩 3개를 코어 수정 0 으로 올려 각 사업의 핵심 시나리오를 재현한다.**

끝났다고 말할 수 있는 상태는 이것뿐이다.

1. 코어 화면 51 + 공통 5 가 전부 HTTP 200 이고 `_placeholder` 가 **0건**이다(`MES_PACK=` 코어 단독).
2. 기능 132 + 이관 배치 4 가 `contracts/function-list.md` 에 한 줄씩 있고 화면(또는 배치) · API · 테스트와 **1:1** 로 이어진다.
3. 코어 계보 시나리오(§2.2 G-C06, 10행)를 **화면 조작만으로** 만들 수 있고 출하 LOT 에서 원재료 LOT ①② 까지 역추적된다.
4. `bas_process_param` 에 행을 넣는 것만으로 POP 종료 화면에 입력칸이 생기고 `pop_measure` 에 기록되고 집계된다(G-C24).
5. 권한 표 48칸이 데이터로 동작하고, 4채널로 열리고, 코어에 금지어가 0건이다.
6. `MES_PACK=kimchi` · `foodservice` · `printfilm` 각각에서 **코어 파일 해시 변동 0** · 팩 게이트 G-P01~G-P05 PASS. `printfilm` 은 엘컴화인 설계도 §3 예시가 `lot_genealogy` 10행으로 재현된다.
7. QA 3명의 리포트 3종이 `outputs/` 에 있고 치명 결함이 0이다.

### 재사용 자산 — 새로 짓기 전에 먼저 본다

| 자산 | 위치 | 쓰임 |
|---|---|---|
| 정본 | `intro.md` · `problem.md` · `spec.md` | 모듈 · 테이블 · 확장 지점 · 게이트의 출처. 수치가 다르면 `spec.md` 가 맞다 |
| 공용 모듈 원형 | `../lcomFine MES/src/lcomfine/app/{numbering,lineage,printing,erp,stats,rbac,auth,templating,audit}.py` · `util/` · `db/conn.py` | **구조와 작성법을 이식**한다. `roll`/`material_lot`/`shipment` 를 `lot` 으로, 회사 고정값을 `pack.yaml` 로 |
| 템플릿 · 매크로 · JS | `../lcomFine MES/src/lcomfine/app/templates/{base.html,home/_macros.html}` · `static/app.js` | 스캔칸 · 알림 · 채널 레이아웃. 용어는 `{{ t(...) }}` 로 바꾼다 |
| 게이트 도구 | `../lcomFine MES/tools/{gate,check_routes,check_schema,check_data,check_security,check_trace}.py` · `Makefile` | 출력 형식 `G-nn  항목  PASS|FAIL|WARN|BLOCKED|미검증  실측` 그대로. 기대값 출처를 설계도 → `core.yaml` + 팩 `gates.yaml` 로 |
| 정본 로더 | `../NeedsFood MES Platform/src/needsfood/app/design.py` | `tools/import_design.py` 의 `design.json` 파서 원형 |
| 수집 메시지 | `../Songwol Data Gateway/spec.md` §5.2 · `PRC_MONITOR_DATA` | `collect.CollectMessage` · `ifc_collect_raw` 모양 |
| 참조 팩 재료 | 각 근거 사업의 `nav.py` · `schema.sql` · `seed_*.py` · `contracts/` | 팩의 용어 · 화면 · 확장 테이블 · 시나리오 기대값 |
| 방법론 | `../06 Coding Agent/README.md` · `../lcomFine MES/goal.md` | 팀 편성 · 웨이브 · 루프 원본 |

**용어 오염 주의.** 공용 모듈 원형은 인쇄 회사에서 온다. Roll · Job · splice · 슬리팅 · COA · ΔE 는 코어에 없다. 코어 용어는 품목 · LOT · 작업지시 · 실적 · 측정값 · 검사 · 출하 · 추적 · 분할 · 합병이다.

---

## 2. 수용 게이트

**루프는 매 회전마다 이 표를 실행한다.** 판정은 명령의 출력으로만 한다 (`make gate` — 코어 단독 + 팩 3 을 차례로 돈다).

### 2.1 구조 게이트 (코어 단독 `MES_PACK=`)

| # | 항목 | 게이트 | 검증 |
|---|---|---|---|
| G-C01 | 메뉴 | 코어 메뉴 **12** · 공통 5. `nav` 단일 소스 = `src/mescore/core.yaml` | `tools/check_trace.py` — `core.yaml` ↔ `nav` |
| G-C02 | 기능 | 기능 **132** + 이관 배치 **4** (모듈별 36·10·7·11·8·11·8·10·3·8·16·4). 한 기능 = 계약 한 줄 = 화면/API 하나 = 테스트 하나 이상, 고아 0 | `tools/check_trace.py` — `function-list.md` ↔ 라우트 ↔ 테스트 ID |
| G-C03 | 화면 | 코어 51 + 공통 5 전부 HTTP 200 · `_placeholder` 0건 | `make check-routes` |
| G-C04 | 스키마 | 테이블 **52** (`spec.md` §2.2 표와 이름 · 수가 같다). 계약 = 실제 DB 컬럼 단위. 모든 테이블에 공통 컬럼 5 + `attrs` | `tools/check_schema.py` |
| G-C05 | 쓰기 경계 | 모듈은 `db-schema.md` §2 의 테이블에만 쓴다. **`trc` · `kpi`(스냅샷 배치 제외)는 어떤 테이블에도 쓰지 않는다.** `lot_genealogy` 에 쓰는 곳은 `lineage` 뿐 | `tools/check_data.py` — 라우터별 쓰기 SQL 정적 스캔 + 조회 전후 행 수 diff 0 |

### 2.2 계보 · 측정값 게이트 — 이 프로젝트의 본체

| # | 항목 | 게이트 | 검증 |
|---|---|---|---|
| G-C06 | 계보 재현 | 코어 시나리오를 **API(화면이 부르는 것과 같은)** 로 만든다: 원재료 LOT 2 → 생산 LOT 2(같은 작업지시, LOT①은 두 생산 LOT 에 투입) → 합병 1(2:1) → 분할 3(1:3) → 출하 LOT 1(분할 ①② 출하, ③ 재고). 결과 `lot_genealogy` **10행**(투입 3 + 합병 2 + 분할 3 + 출하 2) | `tests/test_lineage_scenario.py` · `tools/check_data.py` |
| G-C07 | 추적 | 역방향: 출하 LOT → 원재료 LOT ①② 둘 다. 정방향: 원재료 ① → 생산 ①② → 합병 → 분할 ①②③ → 출하(③은 재고). 재귀 조회 하나(`lineage.py`), 경로 저장 0, 깊이 20 · 분기 100 에서 2초 이내 | 〃 + 임의 생성 케이스 |
| G-C08 | 키 연결 | LOT 번호 하나로 작업지시 · 실적 · 측정값 · 검사 · 출하가 조회된다. 채번은 `numbering.py` 한 곳, 형식은 `sys_number_rule` | `tools/check_data.py` |
| G-C09 | 시드 멱등 | 두 번 돌려도 행 수 diff 0. 시드 값은 `(예시)` 표기 | `make db-seed` ×2 (`make gate-full`) |
| G-C10 | 집계 | `stats` 의 생산 · 품질 · 납기 · 설비 값이 **QA 가 따로 짠 SQL** 과 일치. `measure_series` 도 같다 | `tools/check_data.py` |
| G-C11 | 빈 화면 | 데이터 없으면 `미수집`, 미정이면 `미확정 (D-nn)`. 빈 표만 두지 않는다 | `tools/check_data.py` |
| G-C12 | 범위 밖 0 | 설비 제어 · 업종 전용 기능(§12 금지어가 가리키는 것)이 코어 메뉴 · 엔드포인트 · 테이블에 없다 | `tools/check_data.py` · `check_terms.py` |
| G-C24 | 측정값 | `bas_process_param` 에 행 3개(필수 1 · 범위 1 · 수집원 collect 1)를 넣으면 **코어 수정 없이** POP 종료 화면에 입력칸 3 · 필수 누락 422 · 범위 이탈 저장 + `이탈` 표시 · collect 값은 `on_result_closed` 가 채움 · `stats.measure_series` 집계 | `tests/test_measure.py` · `tools/check_data.py` |

### 2.3 채널 · 출력 게이트

| # | 항목 | 게이트 |
|---|---|---|
| G-C13 | 4채널 | 같은 앱 · 같은 DB. POP: 확대 · `data-scan` 하나 · 바코드 1회 = 1건 · 없는 번호는 그 화면 422 재렌더. 모바일: 390px 가로 스크롤 0. 현황판: 자동 새로고침 + 갱신 시각. 채널별 대상 화면은 `core.yaml: channels` |
| G-C14 | 출력물 | 작업지시서 · LOT 라벨 · 출하 라벨 · 성적서 **4종** 인쇄용 화면. 바코드 인라인 SVG(외부 CDN 0). 라벨 바코드를 POP 스캔칸에 넣으면 그 LOT 이 열린다. 프린터는 `printing` 어댑터 뒤 |
| G-C15 | 이관 배치 | `migration-files.md` 표준 Import 파일 4종을 멱등 적재 · 건수 · 오류 리포트 · `sys_migration_log` |
| G-C16 | ERP | `erp.py` 어댑터 인터페이스 + 호출 시 **501 `ERP 연계 미확정 (D-02)`**. 조용한 폴백 0. `ifc_outbox` 재시도 큐 |

### 2.4 보안 · 운영 · 용어 게이트

| # | 항목 | 게이트 |
|---|---|---|
| G-C17 | RBAC | 권한 표 **48칸 전부** 데이터(`sys_permission`). 없음 = 메뉴 숨김 + 403, 조회 = 쓰기 403, 범위 조건(`scopes`) 동작. 팩이 역할을 늘려도 코드 변경 0 |
| G-C18 | 접근 로그 | 로그인 성공 · 실패 · 화면 조회 · 데이터 변경이 `sys_access_log` 에 남고 SYS-04 에서 조회 |
| G-C19 | 비밀 | 비밀번호 · 세션 비밀이 저장소 · 문서에 없다. 시드 비밀번호는 `MES_SEED_PASSWORD` 로만 |
| G-C20 | 백업 | `make backup` → 덤프, `make restore-check` → 임시 DB 복구 · 행 수 일치 |
| G-C23 | 용어 중립 | `src/mescore/` 전체(코드 · 템플릿 · 시드 · `core.yaml`)에 `spec.md` §12 금지어 **0건**. `terms_keys` 밖의 중립어를 템플릿에 날것으로 쓴 곳 0(`t()` 누락) |

### 2.5 오류 계약 — QA1 이 그대로 테스트 케이스로 쓴다

| 상황 | HTTP | 화면 |
|---|---|---|
| 필수값 누락 · 코드 중복 · 없는 LOT 스캔 · 이미 출하된 LOT · 자기 자신 계보 · 훅 거부(`HookError`) · 측정값 필수 누락 | **422** | 메시지 (POP 은 큰 글씨, 다음 스캔을 막지 않는다) |
| 인증 실패 | **401** | 브라우저 GET 은 `/login` 303 |
| 권한 없음 · 팩이 숨긴 메뉴 | **403** | `접근 권한이 없습니다` |
| DB 연결 실패 | **503** | `서비스 일시 중단` |
| ERP · 미확정 연계 · 미구현 어댑터 | **501** | `미확정 (D-nn)` 명시. 조용한 폴백 금지 |
| 처리되지 않은 예외 | **500** | `예상하지 못한 오류` + 로그 |

상세는 `contracts/api-contract.md`.

### 2.6 빌드 · E2E 게이트

- G-C21: `uv run pytest -q` 전건 통과 · `make check-routes` PASS · 서버 기동 후 `/health` 200.
- G-C22: **브라우저 한 바퀴** — 코어 단독으로 역할을 바꿔 로그인하며 기준정보 → 수주 → 작업지시 → 입고 · 입고검사 → POP 시작 · 투입 스캔 · 측정값 · 종료 → 합병 → 분할 → 검사 → 출하 · 승인 → 성적서 → 역추적까지 조작하고 캡처를 `outputs/e2e/core/` 에 남긴다. 테스트가 통과해도 화면에서 안 되면 FAIL.

### 2.7 팩 게이트 (`MES_PACK=kimchi` · `foodservice` · `printfilm` 각각)

| # | 항목 | 게이트 | 검증 |
|---|---|---|---|
| G-P01 | 격리 | `tools/check_pack.py` 전 항목 0: 코어 파일 해시 변동 · 코어 테이블 `ALTER` · 코어 경로 재정의 · `write_scope` 밖 쓰기 · `lot_genealogy` 직접 INSERT. 팩 폴더를 지워도 `tests/` 전건 통과 | `make check-pack` · `make test` |
| G-P02 | 규모 | 팩 화면 · 테이블 · 기능 수 = `packs/<팩>/gates.yaml` | `make check-schema` · `check-trace` |
| G-P03 | 추적표 | 근거 사업 산출물 ID(있으면) ↔ 코어/팩 화면 매핑 · 고아 0. `foodservice` 는 `design.json` 49화면 | `tools/import_design.py` · `check_trace.py` |
| G-P04 | 시나리오 | `gates.yaml: scenarios` 를 API 로 재현. **printfilm**: 설계도 §3 = `lot_genealogy` 10행(투입 3 + splice 2 + 슬리팅 3 + 출하 2) · 역추적 LOT ①②. **kimchi**: 절임통 투입(염도) → 혼합 → 금속검출 합격 → 출하, 미통과 출하 422. **foodservice**: 수주(식수) → 조리 지시 → `mat_requirement` 자동 → 배치 실적(RPM·온도) → 검식 → 출하 | `packs/<팩>/tests/` |
| G-P05 | 용어 | 화면 · 메뉴 · 라벨에 `terms` 의 키가 치환되지 않은 채 노출 0 | `tools/check_terms.py --pack` |
| G-P06 | 착수 시간 | 더미 팩 `_timing` 으로 `spec.md` §8.1 단계 1~2 실측 ≤ 4h — `outputs/pack-timing.md` | 사람 또는 QA3 실측 |

### 2.8 범위 밖 — 실패로 보지 않는다

실 ERP · 실 프린터 · 실 Data Gateway(MQTT) 연결 · AI Agent 팩 · 기존 운영 DB 실이관 · 운영 서버 배포 · 멀티테넌트 · 다국어 · 참조 팩의 **전체 화면 1:1 재현**(핵심 시나리오까지가 루프의 몫, 나머지는 `spec.md` §13 이관 단계).

---

## 3. 팀 편성과 웨이브

```
Phase 0  코어 매니페스트·팩 로더·스캐폴딩·스키마 52·공통 시드·게이트 도구·_template 팩 (아키텍트 단독)
   ↓
웨이브 A  개발 3 (병렬)   R1 공용 모듈 → R2 담당 코어 화면 연동          → G-C01~G-C24
   ↓
웨이브 B  개발 3 (병렬)   참조 팩 1개씩 — 개발1 foodservice · 개발2 printfilm · 개발3 kimchi → G-P01~G-P05
   ↓
웨이브 C  QA 3 (병렬)     기능·계약·용어 / 계보·측정값·데이터 / 채널·보안·팩 격리·E2E
   ↓
웨이브 D  결함 수정 (담당 개발 + 아키텍트) — 코어 변경 요청은 아키텍트만 처리
   └──── 게이트 전건 PASS 까지 C→D 반복
```

### 3.1 Phase 0 — 아키텍트 (spec → 계약 · 골격). 여기가 가장 중요하다

1. `git init`(로컬만) · `.gitignore` · `uv`(Python 3.12) · DB `mes_core_db` 생성 · `.env.example`(접두 `MES_`) · 포트 **8030**(8000 니즈푸드 · 8020 엘컴화인을 피한다).
2. `decisions.md` — §7 의 D-01~D-10 을 옮겨 적는다.
3. `src/mescore/core.yaml` — 모듈 12 · 화면 51 · 공통 5 · 역할 4 · 권한 48칸 · 채번 종류 · 관계 5 · LOT 종류 3 · `terms_keys` · 금지어 · 채널별 화면. **`nav` · `rbac` · `numbering` · `terms` 의 유일한 출처.**
4. `app/packs.py` — `core.yaml` + `packs/<팩>/pack.yaml` 병합 · §4.3 병합 규칙 검사 · `t()` · `hook()` · 라우터 · 템플릿 검색 경로. `pack-contract.md` 가 계약.
5. `contracts/function-list.md` 136줄 · `db-schema.md` + `db/schema.sql`(52) · `screen-map.md` · `interfaces.md` · `api-contract.md` · `pack-contract.md` · `migration-files.md` — 이 폴더에 초안이 있다. 코드와 맞춰 확정한다.
6. 골격 이식 — `main` `settings` `nav` `rbac` `auth` `templating` `audit` `util/` `templates/base.html` `home/_macros.html` `static/app.js` · 공통 시드(역할 4 · 권한 48칸 · 계정 4 · 채번 규칙 · 공통코드) · 화면 51 전부 `_placeholder`(HTTP 200 + "미구현 — 담당 개발N" + 계약 문장).
7. `packs/_template/` 전체(`spec.md` §8.2) · `packs/kimchi|foodservice|printfilm/pack.yaml` 의 **뼈대만**(pack · name · terms 몇 줄) — 로더 검증용.
8. `tools/{gate,check_routes,check_trace,check_schema,check_terms,check_pack}.py` · `Makefile` · `CLAUDE.md` 확정 · `progress.md` 첫 섹션. `make gate` 가 판정표를 낸다.

Phase 0 끝 = G-C01 · G-C04 · G-C23 PASS, G-C02 는 계약 136줄 존재, G-C03 은 placeholder 51 로 FAIL(정상), G-P01 은 팩 3 뼈대로 PASS.

### 3.2 개발 3명 — 모듈 12 를 3분할 (한 파일은 한 사람만 만진다)

| 담당 | 모듈 (기능 수) | 합 | 공용 모듈 | 웨이브 B 참조 팩 |
|---|---|---|---|---|
| **개발1** 기준 · 지시 · 시스템 | 기준정보 `bas`(36) · 작업지시 `job`(7) · 시스템 `sys`(16) + 공통(로그인 · 메인) | **59** | `numbering.py` (**R1 에서 가장 먼저 공표**) | `foodservice` — 용어(품목→메뉴 · BOM→레시피 · 생산 LOT→배치) · `on_work_order_created` 식수 소요량 · 배치 측정값 |
| **개발2** 현장 실행 | 자재 `mat`(11) · 생산실적 `pop`(8) · 품질 `qua`(11) · 설비 `eqp`(8) | **38** | `lineage.py` · `printing.py` · `collect.py` · 측정값 자동 폼(`ui.measure_fields`) | `printfilm` — `ROLL` · `splice` · `슬리팅` · 조색/판사양 모듈 · ΔE · 계보 10행 |
| **개발3** 수주 · 출하 · 조회 · 연계 | 수주 `ord`(10) · 출하 `shp`(10) · 추적 `trc`(3) · 현황 `kpi`(8) · 인터페이스 `ifc`(4) + 이관 배치(4) | **35 + 4** | `stats.py` · `erp.py` · `migrate/` | `kimchi` — 절임통 모듈 · 염도/온습도 collect · CCP 검사 항목 · `validate_shipment` 금속검출 |

합계 **59 + 38 + 35 = 132**.

- **R1 (기반)** — 개발1: 채번 · 기준정보 시드 · 공정 측정값 정의 화면(BAS-04) · 작업지시 / 개발2: `lineage.py`(투입 · 생산 · 분할 · 합병 쓰기 + 재귀 조회) 와 G-C06 시나리오 테스트 · `pop_measure` 자동 폼 / 개발3: 추적 화면 뼈대(개발2 시그니처에 맞춤) · `stats.py` · 이관 파일 리더 · `collect` 수신 엔드포인트와 `ifc_collect_raw`.
- **R2 (화면)** — 각자 담당 화면을 `screen-map.md` 대로 실 데이터에 연결.
- 공용 함수 · 채번 형식은 **먼저 정한 사람이 `progress-devN.md` §1 에 공표**하고 나머지가 그대로 쓴다.
- 화면 간 흐름(계약): 수주 → 생산계획 → 작업지시 → 입고 · 입고검사(합격 LOT 만 투입) → POP 시작 → 투입 스캔 → 측정값 → 종료(생산 LOT + 라벨) → 분할/합병 → 검사(LOT 참조) → 출하 등록 → LOT 스캔 → 승인 → 성적서 → 추적 · 현황.
- **웨이브 B 규칙**: 팩을 쓰다 코어가 모자라면 코어를 고치지 않는다. `decisions.md` 에 `코어 변경 요청` 으로 올리고(§4.3) 아키텍트가 웨이브 D 에서 처리한다. 그동안 팩은 `미확정 (D-nn)` 으로 둔다.

### 3.3 QA 3명 — 서로 다른 관점으로 교차 검증

| 담당 | 범위 | 산출 |
|---|---|---|
| **QA1** 기능 · 계약 · 용어 | G-C01~G-C03 · 기능 136 의 1:1 · §2.5 오류 계약 · G-C17 48칸 전수 · **G-C23 금지어 전수** · G-P05 | `outputs/qa1-기능계약.md` · `tools/check_screens.py` |
| **QA2** 계보 · 측정값 · 데이터 | G-C04~G-C12 · **G-C24** — 스키마 대조 · 쓰기 경계 · 계보 10행 · 임의 계보 · 측정값 선언 → 폼 → 기록 → 집계 · 집계 재계산 · 시드 멱등 · **G-P04 팩 3 시나리오를 자기 SQL 로 대조** | `outputs/qa2-계보데이터.md` · `tools/{check_schema,check_data}.py` |
| **QA3** 채널 · 보안 · 팩 격리 · E2E | G-C13~G-C16 · G-C18~G-C20 · **G-C22** · **G-P01 팩을 지우고 코어 테스트** · G-P06 착수 시간 실측 · 조용한 실패 사냥 | `outputs/qa3-채널보안.md` · `outputs/e2e/` · `outputs/pack-timing.md` · `tools/check_security.py` |

결함 ID 는 `DEF-QA{n}-nnn`, 등급은 치명/중대/경미. **QA 는 고치지 않는다.**

---

## 4. 루프 엔지니어링 프로토콜

### 4.1 상태 파일

| 파일 | 역할 | 쓰는 사람 |
|---|---|---|
| `goal.md` | 목표 · 게이트 (이 문서). **판정 기준** | 사람만 |
| `intro.md` · `problem.md` · `spec.md` | 정본. 수치의 출처 | 사람만 |
| `progress.md` | **검증된 현황의 유일한 진실.** `\| 항목 \| 실측 \| 검증 방법 \|` 3열 + 맨 위 "지금 해야 할 것" | 루프 오케스트레이터 |
| `decisions.md` | 결정 대장 `D-nn` — `확정` / `가설` / `차단` / **`코어 변경 요청`** | 전원 |
| `progress-dev{1,2,3}.md` | 개발자별 진행 · 공표(§1) · 요청(§3) | 각 개발자 |
| `outputs/qa{1,2,3}-*.md` | QA 리포트 | 각 QA |
| `contracts/*.md` | 코드 계약. 코드와 다르면 코드가 맞다 — 발견자가 계약을 고친다 | 아키텍트(`schema.sql` · `core.yaml` · `function-list.md` · `pack-contract.md` 는 아키텍트만) |

### 4.2 한 회전에서 하는 일 (순서를 바꾸지 않는다)

1. **읽기** — `progress.md` 최신 섹션 · `decisions.md` 미결 · 직전 QA 리포트. `progress.md` 가 없으면 Phase 0.
2. **판정** — `make gate` (코어 단독 → 팩 3 순). FAIL 목록.
3. **선택** — FAIL 중 **가장 앞선 웨이브의 항목 1개**. 웨이브를 건너뛰지 않는다. 코어 게이트가 FAIL 인 채로 팩 게이트를 고치지 않는다.
4. **기동** — §5 프롬프트로 담당 에이전트를 띄운다. 병렬 가능한 것은 한 번에. 작은 수정은 직접.
5. **검증** — 보고를 믿지 않는다. 게이트 명령을 **직접 다시 실행**한다. 팩 작업 뒤에는 반드시 `make check-pack` 과 코어 테스트를 다시 돈다.
6. **기록 · 커밋** — `progress.md` 에 실측과 명령, 새 결정은 `decisions.md`. `git add -A && git commit -m "<G-nn|웨이브>: <한 줄>"` (로컬만).
7. **다음 회전** — FAIL 이 남았으면 예약. 에이전트가 돌고 있으면 긴 대기(20분 이상).

### 4.3 멈추지 않기 위한 규칙

- **막히면 우회한다.** 사람 확인이 필요한 값은 `차단`, 화면에는 `미확정 (D-nn)`.
- **코어 변경 요청.** 팩 작업 중 확장 지점 7개 밖의 것이 필요하면 `decisions.md` 에 `## D-nnn <제목> · 상태: 코어 변경 요청` 으로 올린다 — 어느 확장 지점이 왜 모자란지, 코어의 어디를 어떻게 바꾸면 **다른 팩도** 쓸 수 있는지. 아키텍트가 `가설` 로 바꾸고 코어를 고친 뒤 `spec.md` §3 과 `pack-contract.md` 에 반영한다. 팩 작성자가 코어를 직접 고치면 G-P01 FAIL.
- **같은 실패를 2회 넘게 반복하지 않는다.** 3회째면 접근을 바꾸고, 그래도 안 되면 `차단`.
- **게이트를 낮추지 않는다.** 금지어 목록에서 단어를 빼거나 `write_scope` 를 넓혀 통과시키는 것도 낮추는 것이다.
- **한 파일은 한 사람만.** 팩 폴더는 그 팩 담당만.
- **동시에 3명 이하.** 시드 · 스키마 재생성은 한 번에 하나. 팩 3개는 **같은 DB 를 쓰지 않는다** — `mes_core_db` · `mes_kimchi_db` · `mes_foodservice_db` · `mes_printfilm_db`.
- **이 폴더 밖은 읽기만 한다.** 근거 사업 폴더와 그 DB 를 고치지 않는다. 포트 8000 · 8020 을 피한다.
- **밖으로 내보내지 않는다.** push · 배포 · 외부 전송 없음.

### 4.4 종료 조건 (EXIT) — 셋을 동시에 만족하면 멈춘다

1. G-C01~G-C24 **전건 PASS**(코어 단독) **그리고** G-P01~G-P05 가 팩 3개 모두 PASS (`차단` 은 D-번호와 사유가 있을 것. G-P06 은 사람 실측이 없으면 `미검증` 허용)
2. QA 리포트 3종이 있고 **치명 결함 0**
3. **연속 2회전 동안 `progress.md` 에 새 실측 변화가 없음**

멈출 때 `progress.md` 맨 위에 최종 보고 — 게이트 판정표(코어 + 팩 3), 사람이 정해야 할 D-목록, 미처리 코어 변경 요청, `spec.md` §13 이관 착수 절차.

### 4.5 중단 · 재개

세션이 끊기면 `progress.md` 최신 섹션 + `decisions.md` 미결만 읽고 **4.2 의 1번부터**. 대화 기록에 의존하지 않는다.

---

## 5. 에이전트 기동 프롬프트 (그대로 복사해 쓴다)

모든 프롬프트는 아래 **공통 서두**로 시작한다.

> 너는 MES 표준플랫폼 개발팀의 [역할]이다. 작업 폴더는 `/Users/gerardo92/Desktop/AI Coding/Standard MES Platform`.
> 작업 전에 `CLAUDE.md` · `goal.md` · `contracts/` · `decisions.md` · `progress.md` 를 읽는다. 정본은 `intro.md` · `problem.md` · `spec.md` 이며 읽기만 한다.
> 이 시스템은 **코어 한 벌 + 업종 팩**이다. 코어에는 업종어가 한 글자도 없고(`spec.md` §12 금지어), 업종 차이는 확장 지점 7개(`spec.md` §3)로만 표현한다.
> 본체는 **`lot` + `lot_genealogy` 재귀 계보**와 **`bas_process_param` → `pop_measure` 측정값**이다. 계보에 쓰는 곳은 `lineage` 뿐, 번호는 `numbering` 뿐, 집계는 `stats` 뿐.
> **계약에 없는 것을 혼자 정하지 않는다** — 컬럼 · 경로 · 시그니처는 `contracts/` 가 출처다. 모자라면 `decisions.md` 에 `가설` 로 올리고 계약을 고친 뒤 쓴다.
> **실데이터를 지어내지 않는다** — 시드는 `(예시)`. **조용한 실패 금지** — 실패는 사용자에게 보인다. **범위 밖 금지** — 설비 제어 · AI · 실 연계는 만들지 않는다.
> 담당 밖 파일과 이 폴더 밖은 고치지 않는다. 끝나면 실측값과 검증 명령을 [본인 진행 파일]에 적는다. 비밀번호 값은 문서에 적지 않는다.
> 환경: PostgreSQL 17 (unix socket `/tmp`) DB `mes_core_db`(팩은 `mes_<팩>_db`) · 포트 8030 · `uv` / Python 3.12 · 명령은 `uv run …` · 환경변수 접두 `MES_` · 팩 선택 `MES_PACK`.

**아키텍트 (Phase 0)**
> §3.1 의 1~8 을 순서대로 한다. `spec.md` §2 · §6 에서 모듈 12 · 화면 51 · 테이블 52 을 직접 세고 `contracts/` 초안의 수와 맞는지 확인해 `progress.md` 에 실측으로 적는다.
> 가장 공들일 것은 `core.yaml` · `packs.py` · `db-schema.md` 다 — `nav` · `rbac` · `numbering` · `terms` 가 전부 `core.yaml` 하나에서 나와야 팩이 선언만으로 바꿀 수 있다. `lot` 단일 테이블(Q2)과 `lot_genealogy` 제약(순환 금지 · `(parent, child, relation)` 유니크 · base 관계 매핑)은 종이 위에서 G-C06 10행을 먼저 따져 본 뒤 정한다.
> 골격은 `../lcomFine MES/src/lcomfine/app/` 에서 이식하되 패키지명 `mescore`, 인쇄 용어 · 테이블은 가져오지 않는다. `tools/check_terms.py` 를 가장 먼저 만들어 이식 결과를 돌려 본다. 끝나면 `make gate` 판정표를 `progress.md` 에 붙인다.

**개발1 (기준 · 지시 · 시스템 / 기능 59 → 팩 foodservice)**
> 담당: `bas`(품목 · BOM · 공정 · **공정 측정값 정의** · 설비 · 거래처 · 작업자 · 불량코드 · 공통코드) · `job`(작업지시 · 현황 · 작업지시서) · `sys`(사용자 · 역할 · 권한 표 · 로그 · 채번 규칙 · 백업/이관) + 로그인 · 메인.
> R1: `app/numbering.py` — 조립식(`sys_number_rule` 접두 · 날짜 형식 · 자릿수, 카운터 잠금, `cur=` 동반 롤백). 종류는 `core.yaml: numbering` 의 것. 형식을 `progress-dev1.md` §1 에 **가장 먼저** 공표. BAS-04 공정 측정값 정의가 `bas_process_param` 을 쓰고 개발2 의 자동 폼이 그것을 읽는다 — 컬럼은 `db-schema.md` 그대로.
> R2: 담당 화면 18. 권한 표(SYS-03)는 48칸 편집 → `rbac.invalidate()` 즉시 반영. 채번 규칙(SYS-05)은 `numbering.rule` 이 읽는 행을 편집.
> 웨이브 B: `packs/foodservice` — `pack.yaml`(terms · 역할 · 채번 · `BATCH` kind) · `seed/process_params.csv`(RPM · 교반시간 · 온도 collect) · `x_foodservice_item_ext`(식수 · 1인량) · `hooks.on_work_order_created`(식수 × 1인량 → `mat_requirement`) · `gates.yaml` 시나리오. 니즈푸드 `design.json` 을 `tools/import_design.py` 로 돌려 G-P03 매핑표.

**개발2 (현장 실행 / 기능 38 → 팩 printfilm)**
> 담당: `mat`(입고 · 입고검사 · 원재료 LOT · 재고 · 소요량) · `pop`(작업 목록 · 시작/종료 · 투입 스캔 · LOT 라벨) · `qua`(검사 계획 · 결과 · 불량 집계 · 이상/시정) · `eqp`(가동 · 점검 · 고장 · 수집값).
> R1: `app/lineage.py` — `link assert_usable make_product_lot split merge ship unship`(전부 `cur`) + `resolve search state parents_of children_of trace_backward trace_forward`. 관계는 `core.yaml` 5종 + 팩 등록(base 매핑). 시그니처를 `progress-dev2.md` §1 에 공표. `tests/test_lineage_scenario.py` 로 G-C06 10행을 먼저 통과. `ui.measure_fields` — `bas_process_param` 을 읽어 POP 종료 폼을 자동 생성, `pop_measure` 기록, 범위 이탈 표시(G-C24). `app/collect.py` 수신 → `ifc_collect_raw` → `eqp_collect`.
> R2: POP 은 터치 · 스캔 전제. 종료 시 생산 LOT + 라벨. `app/printing.py` 라벨 · 바코드 SVG · `PrintAdapter`.
> 웨이브 B: `packs/printfilm` — `ROLL` kind · `splice`(base 합병) · `슬리팅`(base 분할) · 용어(작업지시→Job · 생산 LOT→Roll · 성적서→COA) · `x_printfilm_{plate,anilox,ink_formula,color_record}` 모듈 · ΔE 측정값 · `on_result_closed` Roll 생성 · `gates.yaml` 에 엘컴화인 설계도 §3 10행 시나리오. `../lcomFine MES/contracts/db-schema.md` §3 이 기대값.

**개발3 (수주 · 출하 · 조회 · 연계 / 기능 35 + 배치 4 → 팩 kimchi)**
> 담당: `ord`(수주 · 이력 · 납기 달력 · 생산계획) · `shp`(출하 등록 · LOT 스캔/승인 · 현황 · 성적서) · `trc`(정방향 · 역방향 · 검색) · `kpi`(현황판 · 집계 · 지표 정의) · `ifc`(수집 현황 · ERP 로그) + 이관 배치 4 + `app/erp.py`.
> R1: 추적은 개발2 `lineage` 조회만 — **아무 테이블에도 쓰지 않는다**(G-C05). `app/stats.py` 한 곳에 집계 SQL + `measure_series` + `kpi_extra` 훅 병합. `migrate/` 표준 Import 파일 4종 리더(`migration-files.md`). `erp.py` 501 + `ifc_outbox`.
> R2: 출하는 LOT 스캔 → 등록 → 승인(`validate_shipment` 훅 호출) → 성적서. 현황판 `?device=board`, 모바일 390px.
> 웨이브 B: `packs/kimchi` — `TANK` · `AGING` kind · 용어 · `x_kimchi_tank`(절임통 운영) 모듈 · 염도/절임시간 측정값 · 온습도 collect 시드 · CCP 검사 항목 · `validate_shipment`(금속검출 미통과 422) · `on_inspection_judged`(CCP 이탈 → `qua_issue`) · `gates.yaml`.

**QA1 / QA2 / QA3 (웨이브 C, 병렬)**
> §3.3 의 담당 범위를 §2 게이트와 `api-contract.md` 로 검증한다. **고치지 않는다.** 결함은 `DEF-QA{n}-nnn` 으로 재현 절차 · 실측 · 기대값 · 담당을 `outputs/qa{n}-*.md` 에, 통과 항목도 실측과 명령을 함께.
> 검사기 출력은 `G-nn  항목  PASS|FAIL|WARN|BLOCKED|미검증  실측` 행. 기대값은 개발 코드가 아니라 `spec.md` · `core.yaml` · 팩 `gates.yaml` 에서 끌어온다. QA2 는 계보 10행 · 측정값 · 집계를 자기 SQL 로, QA3 는 실제 브라우저로 G-C22 를, 그리고 **팩 폴더를 지운 채** 코어 테스트를 돈다.

---

## 6. 권한 표 기본값 (`core.yaml: permissions` — G-C17 의 기대값 · 팩이 덮어쓸 수 있다)

| 모듈 | 관리자 | 생산 | 품질 | 현장 | 주로 쓰는 채널 |
|---|---|---|---|---|---|
| 기준정보 `bas` | 입력 | 조회 | 조회 | 없음 | 관리자 Web |
| 수주 · 계획 `ord` | 입력 | 입력 | 조회 | 조회 | 관리자 Web |
| 작업지시 `job` | 입력 | 입력 | 조회 | 조회 | 관리자 Web |
| 자재 `mat` | 조회 | 입력 | 입력 (입고검사) | 입력 | 현장 POP, 관리자 Web |
| 생산실적 `pop` | 조회 | 입력 | 조회 | 입력 | 현장 POP |
| 품질 `qua` | 조회 | 조회 | 입력 | 조회 | 관리자 Web, 현장 POP |
| 설비 `eqp` | 조회 | 입력 | 조회 | 입력 | 현장 POP, 관리자 Web |
| 출하 `shp` | 입력 (승인) | 입력 | 조회 | 입력 | 현장 POP, 관리자 Web |
| LOT 추적 `trc` | 조회 | 조회 | 조회 | 없음 | 관리자 Web, 모바일 |
| 현황 · KPI `kpi` | 입력 (지표 정의) | 조회 | 조회 | 조회 | 관리자 Web, 현황판, 모바일 |
| 시스템 `sys` | 입력 | 없음 | 없음 | 없음 | 관리자 Web |
| 인터페이스 `ifc` | 입력 (재전송) | 조회 | 없음 | 없음 | 관리자 Web |

입력 18 · 조회 23 · 없음 7 = 48. 괄호 조건 3개는 `scopes`(입고검사 · 승인 · 지표 정의 · 재전송).

---

## 7. 열려 있는 결정 — Phase 0 에서 `decisions.md` 로 옮긴다

`problem.md` §8 Q1~Q10 을 D-01~D-10 으로. 사람이 답하기 전까지 루프는 **기본값(가설)** 으로 간다.

| # | 확인 필요 | 기본값 (가설) | 바뀌어도 한 곳만 고치게 |
|---|---|---|---|
| D-01 | 코어 모듈 수 · 경계 (Q1) | 12. `ord` 와 `job` 분리 | `core.yaml` 모듈 표 |
| D-02 | ERP 연계 | 없음. 어댑터 + 501 | `app/erp.py` |
| D-03 | LOT 단일 테이블 (Q2) | `lot` 하나 + `kind`. 뷰 `v_lot_state` · `v_lot_stock` | `schema.sql` · `lineage.py` |
| D-04 | 측정값 EAV 범위 (Q3) | 실적당 키당 1행은 `pop_measure`, 시계열은 `eqp_collect` 또는 팩 테이블 | `spec.md` §3.3 · `ui.measure_fields` |
| D-05 | `attrs` 와 확장 테이블 (Q4) | 표시용 `attrs`, 집계 · 검색 · 제약은 ext 테이블 | `pack-contract.md` §3 |
| D-06 | 훅 실행 (Q5) | 동기 · 같은 트랜잭션 · `HookError` 422 · 외부 전송은 `after_commit_*` | `app/packs.py` |
| D-07 | 용어 사전 범위 (Q6) | 템플릿 · 메뉴 · 메시지 · 출력물. 식별자 · URL 불변 | `util/terms.py` |
| D-08 | 기본 역할 4 (Q7) | 관리자 · 생산 · 품질 · 현장 | `core.yaml: roles` |
| D-09 | 코어 버전 호환 (Q9) | `core_version 0.1.0` · `requires_core` semver | `packs.py` |
| D-10 | 스캐너 · 프린터 · 채번 형식 | 스캐너 = 키보드, 라벨 = 브라우저 인쇄, 채번 `prefix+YYMMDD-+3자리`(LOT 4자리) | `printing.py` · `sys_number_rule` 시드 |
| D-11 | 기능 136줄 전개 | `function-list.md` 의 화면 × 단위 기능 전개 전체가 가설. 근거 사업 둘 이상에 있는 기능만 | `function-list.md` |
| D-12 | 분할 · 합병 화면 | 코어에 전용 화면 없음. `lineage.split/merge` API + POP-02 의 버튼으로만 열고 기능 수에 세지 않는다. 화면은 팩이 만든다 | `routers/pop.py` |

## 8. 지켜야 할 것

- **계보는 한 줄, 추적은 조회.** 캐시 테이블 없음. `lot_genealogy` 는 `lineage` 만 쓴다.
- **측정값은 선언.** 공정별 값을 위해 테이블을 만들지 않는다. `bas_process_param` 에 행을 넣는다. 시계열만 예외(D-04).
- **코어에 업종어 0.** 템플릿의 사용자 문구는 `t()` 를 거친다.
- **팩은 7개 확장 지점 안에서만.** 밖이 필요하면 코어 변경 요청.
- **조용한 실패 금지 · 지어내지 않기 · 중복 만들지 않기.**
- 정본(`spec.md`)의 결함 · 모순은 고치지 말고 `decisions.md` 에 적고 최종 보고에 올린다.

## 9. 실측 방법

```bash
# spec.md 와 contracts 에서 직접 센다 — 모듈 12 · 화면 51 · 기능 132 + 배치 4 · 테이블 52
grep -c '^| F-'  contracts/function-list.md        # 132
grep -c '^| B-MIG-' contracts/function-list.md     # 4
grep -cE '^\| [0-9]+ \| [A-Z]{3}-[0-9]{2} ' contracts/screen-map.md   # 51 (CMN 제외)
grep -cE '^### `[a-z_]+`' contracts/db-schema.md   # 52
grep -c '^| E[1-7] ' spec.md                        # 7
make gate          # 코어 단독 + 팩 3
make gate-full     # 시드 멱등 포함 — 종료 판정은 이것으로
```
