# 기능 명세 — MES 표준플랫폼

> 관련 문서: `intro.md`(소개 · 코어와 팩의 경계), `problem.md`(문제 · 목표 G1~G10 · 확정 필요 사항 Q1~Q10)
> 근거: 임진강김치 MES · 니즈푸드 MES · 엘컴화인 MES · 송월타월 Data Gateway (`intro.md` §3)
> 버전: v0.1 (2026-10-09, 네 사업의 구현을 일반화한 첫 판)

**표기 규칙**
- `[기준]`: 근거 사업 두 곳 이상에서 실제로 쓰여 검증된 것. 그대로 따른다.
- `[가설]`: 표준화하면서 새로 정한 것. 참조 팩 3개를 작성하며 바뀔 수 있다(`problem.md` §8 Q1~Q10).
- **코어는 고치지 않는다.** 팩이 할 수 있는 일은 §3 의 확장 지점 7개뿐이다. 그 밖의 요구는 코어 변경 요청(`decisions.md` D-번호)으로 올린다.

---

## 1. 시스템 구성

### 1.1 계층

```
┌──────────────────────── 채널 4 (같은 앱 · 같은 DB) ────────────────────────┐
│  관리자 Web        현장 POP(스캔 · 확대)      모바일(390px)      현황판(자동 새로고침) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP (Jinja2 서버 렌더 + static/app.js)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│  packs/<업종>/            pack.yaml · schema_ext.sql · routers/ · hooks.py · seed/ · tests/ │
│  ─────────────────────────────── 팩 로더 app/packs.py ───────────────────────────── │
│  src/mescore/app/        main · settings · packs · nav · rbac · auth · templating      │
│                          numbering · lineage · printing · stats · collect · erp · audit │
│                          routers/{bas,ord,job,mat,pop,qua,eqp,shp,trc,kpi,sys,ifc,home}  │
│  src/mescore/db/         conn · schema.sql · seed_core.py · migrate/                     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ psycopg
                          ┌────────────▼────────────┐
                          │ PostgreSQL 17  (DB 하나)  │
                          │ 코어 테이블 + 팩 확장 테이블 │
                          └─────────────────────────┘
      외부 접점(어댑터 뒤) : Data Gateway(collect) · ERP(erp) · 라벨 프린터(printing)
```

### 1.2 기술 스택 `[기준]`

| 영역 | 선택 | 근거 |
|---|---|---|
| 언어 · 도구 | Python 3.12 · `uv` · 명령은 전부 `uv run …` | 네 사업 공통 |
| 웹 | FastAPI · Jinja2 서버 렌더 · 최소 JS(`static/app.js` 하나) | 임진강 · 니즈푸드 · 엘컴화인 |
| DB | PostgreSQL 17 · psycopg 3 · SQL 직접 작성(ORM 없음) · `conn.q/q1/x/tx` | 〃 |
| 테스트 | pytest · 기능마다 `@pytest.mark.fn("F-…")` | 엘컴화인 |
| 실행 | Makefile(`setup run test gate …`) · Docker Compose(앱 + PostgreSQL) | 〃 |
| 설정 | 환경변수 접두어 `MES_`(`MES_PACK` `MES_PG_DSN` `MES_PORT` `MES_SESSION_SECRET` `MES_SEED_PASSWORD`) · 팩은 `pack.yaml` | `[가설]` 접두어 통일 |
| 바코드 | 인라인 SVG(Code128) · 외부 CDN 0 | 엘컴화인 G-14 |

### 1.3 실행 모드

| 모드 | `MES_PACK` | 설명 |
|---|---|---|
| 코어 단독 | 비움 또는 `_template` | 중립 용어 · 역할 4 · 기본 채번. 코어 게이트 검증용 |
| 팩 적용 | `kimchi` `foodservice` `printfilm` 또는 새 팩 | 한 배포 = 코어 + 팩 하나 (`problem.md` §7) |

기동 순서: `settings` → `packs.load(MES_PACK)` → 코어 매니페스트 + 팩 매니페스트 병합 → 스키마 검증(코어 + `schema_ext.sql`) → `nav` · `rbac` · `numbering` · `terms` 초기화 → 라우터 자동 include(코어 → 팩) → 훅 등록. 병합 규칙 위반(§4.3)이면 기동 거부 + 위반 항목 출력.

---

## 2. 코어 도메인 모델

### 2.1 모듈 12 `[기준]`

| 코드 | 모듈 | 하는 일 | 쓰는 테이블 | 근거 사업 |
|---|---|---|---|---|
| `bas` | 기준정보 | 품목 · BOM · 공정 · 공정 측정값 정의 · 설비 · 거래처 · 작업자 · 불량코드 · 공통코드 | `bas_*` | 넷 다 |
| `ord` | 수주 · 계획 | 수주 · 수주 상세 · 납기 달력 · 생산계획 | `ord_*` | 임진강 · 니즈푸드 · 엘컴화인(확장) |
| `job` | 작업지시 | 작업지시 · 지시 LOT · 상태(대기 · 진행 · 마감 · 취소) | `job_*` | 넷 다 |
| `mat` | 자재 | 입고 · 입고검사 · 원재료 LOT · 재고 · 투입 · 소요량 | `mat_*` + `lot`(kind=MATERIAL) | 넷 다 |
| `pop` | 생산실적 | 작업 시작 · 종료 · 정지 · 폐기 · 측정값 · 생산 LOT 생성 | `pop_*` + `lot`(kind=PRODUCT) + `lot_genealogy`(투입 · 생산) | 넷 다 |
| `qua` | 품질 | 검사 계획 · 검사 결과 · 불량 · 이상 · 시정 조치 | `qua_*` | 넷 다 |
| `eqp` | 설비 | 가동 상태 · 가동 로그 · 점검 · 고장 · 수집값 조회 | `eqp_*` | 임진강 · 니즈푸드 · 송월 |
| `shp` | 출하 | 출하 등록 · LOT 스캔 · 승인 · 출하 LOT · 성적서(COA) | `shp_*` + `lot`(kind=SHIPMENT) + `lot_genealogy`(출하) | 넷 다 |
| `trc` | LOT 추적 | 정방향 · 역방향 추적 · 번호 검색. **쓰지 않는다** | 없음 | 엘컴화인(재귀) · 임진강 |
| `kpi` | 현황 · KPI | 생산 · 품질 · 납기 · 설비 집계 · 지표 정의 · 현황판. **쓰지 않는다**(지표 정의 제외) | `kpi_indicator` 만 쓰기 | 임진강 · 니즈푸드 · 엘컴화인 |
| `sys` | 시스템 | 사용자 · 역할 · 권한 표 · 접근 로그 · 채번 규칙 · 백업 · 이관 로그 | `sys_*` | 넷 다 |
| `ifc` | 인터페이스 | 설비 수집 메시지 수신 · ERP 연계 로그 · 외부 전송 큐 | `ifc_*` | 니즈푸드 · 송월 · 엘컴화인(erp) |

공통 화면 5: 로그인 · 메인(IA) · 오류 · 대시보드 · 팝업. 메인은 모듈 카드를 **일하는 순서**로 늘어놓는다(엘컴화인 D-417).

### 2.2 코어 테이블 `[기준]` — 52 `[가설: 수 — 근거 사업 둘 이상에 대응물이 있는 것만]`

접두어는 모듈 코드. `lot` · `lot_genealogy` 두 개만 접두어가 없다(모듈 넷이 함께 쓴다).

| 모듈 | 테이블 | 비고 |
|---|---|---|
| bas (10) | `bas_item` `bas_bom` `bas_bom_dtl` `bas_process` `bas_process_param` `bas_equipment` `bas_partner` `bas_worker` `bas_defect_code` `bas_code` | `bas_process_param` 이 공정별 측정값의 **정의**(§3.3). `bas_code` 는 그룹 + 코드 한 테이블 |
| ord (4) | `ord_order` `ord_order_dtl` `ord_order_hist` `ord_plan` | |
| job (2) | `job_work_order` `job_lot` | `job_lot` 은 지시 ↔ LOT 매핑(엘컴화인 D-10) |
| mat (4) | `mat_receipt` `mat_stock` `mat_stock_trx` `mat_requirement` | 원재료 LOT 자체는 `lot` |
| 공용 (2) | **`lot`** **`lot_genealogy`** | §2.4 |
| pop (5) | `pop_work_result` `pop_stop` `pop_scrap` `pop_input` `pop_measure` | `pop_measure` 가 측정값 **기록**. `pop_input` 은 투입 스캔(LOT 생성 시 계보로 옮김) |
| qua (5) | `qua_insp_plan` `qua_inspection` `qua_insp_item` `qua_defect` `qua_issue` | `qua_insp_item` 은 검사 항목별 값 |
| eqp (4) | `eqp_run_log` `eqp_check` `eqp_fault` `eqp_collect` | `eqp_collect` 는 `ifc` 가 받은 설비 수집값의 정제본 |
| shp (2) | `shp_shipment` `shp_document` | 출하 LOT 은 `lot`. `shp_document` 는 COA · 거래명세서 발행 기록 |
| kpi (2) | `kpi_indicator` `kpi_snapshot` | `kpi_snapshot` 은 현황판용 일 단위 스냅샷(배치가 쓴다 · 화면은 안 쓴다) |
| sys (9) | `sys_user` `sys_role` `sys_permission` `sys_session` `sys_access_log` `sys_number_rule` `sys_number_seq` `sys_migration_log` `sys_backup_hist` | 권한 표 = `sys_permission` 데이터(G-17 방식) |
| ifc (3) | `ifc_collect_raw` `ifc_erp_link` `ifc_outbox` | `ifc_collect_raw` 모양은 송월 `PRC_MONITOR_DATA` 와 같게 |

모든 코어 테이블의 공통 컬럼: `id bigserial pk` · `created_at` `created_by` `updated_at` `updated_by` · **`attrs jsonb not null default '{}'`**(§3.2) · `pack_ext_id`(없음 — 확장 테이블이 코어를 가리킨다).

### 2.3 쓰기 경계 `[기준: 엘컴화인 G-05]`

| 모듈 | 쓸 수 있는 테이블 | 쓰면 안 되는 대표 사례 |
|---|---|---|
| `bas` `ord` `qua` `eqp` `sys` | 자기 접두어 테이블 | — |
| `job` | `job_*` · `ord_order_dtl.status`(수주 연결 상태만) | LOT 을 미리 만드는 것 |
| `mat` | `mat_*` · `lot`(kind=MATERIAL) | `job_work_order.status` |
| `pop` | `pop_*` · `lot`(kind=PRODUCT) · `lot_genealogy`(`투입` `생산` 과 팩이 등록한 생산 관계) — **`lineage` 를 통해서만** | `job` 상태 직접 변경(훅 `on_result_closed` 가 한다) · `mat_stock` 직접 차감(`pop_input` → 트리거 없이 `mat` 의 소비 함수 호출) |
| `shp` | `shp_*` · `lot`(kind=SHIPMENT) · `lot_genealogy`(`출하`) — `lineage.ship` 으로만 | `lot.status` 직접 변경 |
| `trc` · `kpi`(스냅샷 배치 제외) | **없음** | 추적 · 집계 결과를 담는 테이블 |
| `ifc` | `ifc_*` · `eqp_collect` | 실적 테이블(수집값이 실적이 되는 것은 팩 훅의 일) |
| 팩 라우터 | `x_<팩>_*` 과 `pack.yaml` 의 `write_scope` 에 선언한 코어 테이블 | 선언 밖 코어 테이블. `check_pack` 이 정적 스캔으로 잡는다 |

저장하지 않고 계산하는 값 — LOT 상태(`v_lot_state`: 재고 · 소진 · 출하) · 원재료 잔량(`v_lot_stock`) · 작업지시 진행 여부(실적 유무).

### 2.4 LOT 과 계보 `[기준: 엘컴화인 roll_genealogy 일반화]`

**`lot`** — 추적 단위 하나. `[가설: 단일 테이블, Q2]`

| 컬럼 | 뜻 |
|---|---|
| `lot_no` | 번호. `numbering` 이 만든다. 바코드로 찍히므로 영문 대문자 · 숫자 · `-` 만 |
| `kind` | `MATERIAL` · `PRODUCT` · `SHIPMENT` + 팩이 등록한 종류(`ROLL` · `BATCH` · `TANK` …) |
| `item_id` · `work_order_id` · `process_id` · `equipment_id` | 어디서 났는가(없으면 NULL) |
| `qty` · `unit` | 수량 |
| `insp_status` | `미검사` · `합격` · `불합격` · `조건부`(검사가 쓴다) |
| `attrs` | 팩 속성(§3.2) |

**`lot_genealogy`** — 화살표 한 줄 = 부모 LOT → 자식 LOT. `(parent_lot_id, child_lot_id, relation)` 유니크. 자기 자신 금지.

| 관계 `relation` | 뜻 | 만드는 곳 |
|---|---|---|
| `투입` | 원재료 LOT → 생산 LOT | `pop` 작업 종료(`pop_input` 마다 한 줄) |
| `생산` | 생산 LOT → 다음 공정 생산 LOT (1:1) | `pop` 다음 공정 실적 |
| `분할` | 생산 LOT 1 → N | `lineage.split` |
| `합병` | 생산 LOT N → 1 | `lineage.merge` |
| `출하` | 생산 LOT → 출하 LOT | `shp` LOT 스캔 |
| 팩 추가 | `splice` · `슬리팅` · `혼합` · `숙성` … | 팩 `pack.yaml: lineage.relations` (`분할` · `합병` 의 별칭으로 등록) |

추적은 **재귀 조회 하나**(`lineage.trace_backward/forward`)다. 경로를 어디에도 저장하지 않고 깊이 · 분기 수를 가정하지 않는다. 엘컴화인 설계도 §3 예시(투입 3 + splice 2 + 슬리팅 3 + 출하 2 = 10행)가 `printfilm` 팩의 계보 게이트다.

---

## 3. 확장 지점 7 — 팩이 할 수 있는 일의 전부

| # | 확장 지점 | 무엇을 바꾸는가 | 어디에 적는가 | 코드 변경 |
|---|---|---|---|---|
| E1 | 설정 | 용어 · 메뉴(추가 · 숨김 · 이름 · 순서) · 역할 · 권한 표 · 채번 · 채널별 화면 · 공통코드 | `pack.yaml` · `seed/` | 없음 |
| E2 | 속성 | 코어 행에 업종 컬럼을 더한다 | `attrs jsonb`(표시용) 또는 확장 테이블 `x_<팩>_<코어>_ext`(집계 · 검색 · 제약용) | `schema_ext.sql` |
| E3 | 공정 측정값 | 공정 · 실적에 붙는 측정 항목(염도 · 온도 · RPM · ΔE) | `bas_process_param` 시드 → `pop_measure` 기록 · 검사 항목은 `qua_insp_plan` 시드 | 없음 |
| E4 | 모듈 | 코어에 없는 화면 · 테이블 · API | `packs/<팩>/routers/*.py` · `schema_ext.sql`(`x_<팩>_*`) · `templates/` | 라우터 |
| E5 | 훅 | 코어 사건에 업종 규칙을 끼운다 | `hooks.py` | 함수 |
| E6 | 계보 | LOT 종류 · 관계 종류 · 상태 표시 | `pack.yaml: lineage` | 없음 |
| E7 | 어댑터 | 설비 수집 · ERP · 프린터 · 라벨 양식 | `adapters/*.py` · `templates/print/` | 드라이버 |

### 3.1 E1 설정 — `pack.yaml` 로 끝나는 것

- **용어 사전** `terms:` — 코어 중립어 → 업종어. 적용 범위는 템플릿 문구 · 메뉴명 · 메시지 · 출력물 · 바코드 라벨 제목. **코드 식별자 · 테이블명 · URL 슬러그 · 기능 ID 는 바뀌지 않는다** `[가설 Q6]`. 템플릿은 `{{ t("생산 LOT") }}` 로 쓰고 사전에 없으면 원문이 나온다.
- **메뉴** `menus:` — 코어 메뉴 12 에 대해 `hide` · `rename` · `order` · `add`(팩 모듈). 숨긴 메뉴의 화면은 404 가 아니라 **403 + 메뉴 없음**(권한 표에서 "없음" 칸과 같은 처리). 숨겨도 테이블은 남는다(코어 테스트가 쓴다).
- **역할 · 권한** `roles:` · `permissions:` — `sys_role` · `sys_permission` 시드. 메뉴 × 역할 칸 값은 `없음` · `조회` · `입력` + 범위 조건(엘컴화인 "입고검사만" 같은 괄호 조건은 `scopes` 로).
- **채번** `numbering:` — 종류별 접두어 · 날짜 형식 · 자릿수. `sys_number_rule` 시드.
- **채널** `channels:` — 화면 ID 별 `web` `pop` `mobile` `board` 허용 목록.

### 3.2 E2 속성 — `attrs` 와 확장 테이블의 쓰임 규칙 `[가설 Q4]`

| 값의 성격 | 어디에 | 예 |
|---|---|---|
| 화면에 **표시만** 한다 · 검색 · 집계 · 제약에 안 쓴다 | `attrs jsonb` (`pack.yaml: attrs:` 에 키 · 라벨 · 형식 선언 → 화면 폼 · 그리드 자동) | 롤 폭 · 비고 · 거래처 담당자 |
| **검색 · 정렬 · 집계 · FK · 유니크**에 쓴다 | 확장 테이블 `x_<팩>_<코어테이블>_ext` (코어 `id` 를 PK 겸 FK 로, 1:1) | 판사양 ID(FK) · 염도 목표값(집계) · 식수(집계) |
| 코어 행과 **1:N** 이다 | E4 팩 테이블 `x_<팩>_*` | 잉크 조성 구성품 · 절임통 염도 로그 |

코어 테이블에 `ALTER` 는 금지. `check_pack` 이 `schema_ext.sql` 을 파싱해 `alter table <코어>` 가 있으면 FAIL.

### 3.3 E3 공정 측정값 — 테이블 폭발을 막는 자리 `[가설 Q3]`

`bas_process_param`(공정 ID · 키 · 라벨 · 단위 · 형식 · 하한 · 상한 · 필수 여부 · 수집원 `manual|collect`) 에 선언하면:

- POP 작업 종료 화면에 그 공정의 측정값 입력칸이 **자동으로** 생긴다(필수 · 범위 검증 포함, 범위 밖은 422 가 아니라 저장 + `이탈` 표시).
- `pop_measure`(실적 ID · 키 · 값 · 단위 · 이탈 여부 · 수집원) 에 한 행씩 쌓인다.
- 수집원이 `collect` 면 `ifc` 가 받은 `eqp_collect` 값 중 그 실적 구간(시작~종료 · 설비 일치)의 대표값(평균 · 최종 · 최대 — 선언)을 훅 `on_result_closed` 가 채운다.
- 현황 · KPI 는 키 단위로 집계한다(`stats.measure_series(key, from, to, group_by)`).

**경계**: 측정값이 **시계열 자체**(염도 1분 간격 로그 · 냉장고 온도 로그)면 `pop_measure` 가 아니라 `eqp_collect`(수집) 또는 팩 테이블(수기 로그)이다. `pop_measure` 는 실적 한 건당 키당 한 행이다.

### 3.4 E4 모듈 — 라우터 · 테이블 · 화면 추가

- 라우터는 `packs/<팩>/routers/<모듈>.py` 에 `router = APIRouter()`. 코어 `main.py` 가 코어 라우터 다음에 자동 include 한다. **코어 경로를 재정의하면 기동 거부.**
- 테이블은 `x_<팩>_<이름>`. 코어 컬럼 규약(공통 컬럼 5 + `attrs`)을 따른다. FK 로 코어를 가리킬 수 있고, 코어는 팩을 모른다.
- 화면은 `pack.yaml: screens:` 에 ID · 이름 · 모듈 · 경로 · 채널 · 담당을 선언하고 `nav` 가 코어 화면과 같은 방식으로 읽는다. ID 접두어는 `X-`(예 `X-CLR-01`), 기능 ID 는 `F-X-CLR-01`.
- 템플릿은 `packs/<팩>/templates/` 가 코어 `templates/` 보다 **먼저** 검색된다 — 같은 이름을 두면 **코어 템플릿을 덮어쓴다**. 이것은 허용하되 `check_pack` 이 덮어쓴 목록을 WARN 으로 찍는다(화면 전면 교체가 필요한 경우를 위한 탈출구).

### 3.5 E5 훅 — 코어 사건의 수명주기 `[가설 Q5]`

`hooks.py` 에 함수를 정의하면 이름으로 등록된다. 전부 **동기 · 코어 트랜잭션 안 · 예외는 `HookError`(422) 로 전체 롤백**. 외부 전송은 `after_commit_*` 에서만.

| 훅 | 언제 | 받는 것 | 흔한 쓰임 |
|---|---|---|---|
| `validate_<테이블>(cur, row, user)` | 코어 INSERT/UPDATE 직전 | 저장될 행 | 업종 제약(김치: 절임 전 염도 목표 필수) |
| `on_work_order_created(cur, wo, user)` | 작업지시 등록 후 | 지시 행 | 급식: 레시피 → 식수 소요량 계산해 `mat_requirement` 생성 |
| `on_result_started / on_result_closed(cur, result, user)` | 작업 시작 · 종료 | 실적 행 | 인쇄: 종료 시 Roll 생성(`lineage.make_product_lot`) · 수집값 대표값 채우기 |
| `on_lot_created(cur, lot, user)` | LOT 생성 후 | LOT 행 | 라벨 자동 출력 큐 |
| `on_inspection_judged(cur, insp, user)` | 검사 판정 후 | 검사 행 | 불합격 시 `qua_issue` 자동 생성 · CCP 이탈 알림 |
| `validate_shipment(cur, shipment, lots, user)` | 출하 승인 직전 | 출하 + LOT 목록 | 미검사 LOT 출하 금지 · 금속검출 미통과 금지 |
| `after_commit_<사건>(payload)` | 커밋 후(트랜잭션 밖) | 사건 페이로드 | ERP 전송 · 프린터 호출 (`ifc_outbox` 를 거친다) |
| `kpi_extra(from, to) -> list[Metric]` | 현황 집계 시 | 기간 | 업종 지표(레시피 표준화율 · 염도 합격률) |

### 3.6 E6 계보 — 선언만으로 끝나는 것

```yaml
lineage:
  lot_kinds:            # 코어 3종에 추가. 화면 라벨은 terms 로
    - { kind: ROLL,  base: PRODUCT, label: 롤 }
  relations:            # base 는 코어 5종 중 하나. 추적 · 상태 계산은 base 로 한다
    - { name: splice,   base: 합병 }
    - { name: 슬리팅,   base: 분할 }
  states:               # v_lot_state 의 표시어
    { IN_STOCK: 재고, CONSUMED: 소진, SHIPPED: 출하 }
```

### 3.7 E7 어댑터 — 인터페이스는 코어, 드라이버는 팩

| 어댑터 | 코어 인터페이스 | 기본 구현 | 팩 드라이버 예 |
|---|---|---|---|
| `collect` | `CollectMessage(equip_code, ts, tags{}, source)` 수신 → `ifc_collect_raw` → `eqp_collect` | HTTP POST `/ifc/collect` 수신 (송월 메시지 규격과 같음) | MQTT 구독 드라이버 |
| `erp` | `ErpAdapter.push(kind, payload)` · `pull(kind, since)` | 전부 **501 `미확정 (D-nn)`** · 조용한 폴백 0 | 더존 · SAP 연동 |
| `printing` | `PrintJob(template, data) -> HTML(바코드 SVG 포함)` | 인쇄용 화면(브라우저 인쇄) | 라벨 프린터(ZPL) 드라이버 |
| 라벨 · 출력물 양식 | `templates/print/<이름>.html` | 작업지시서 · LOT 라벨 · 출하 라벨 · 성적서 4종 | 팩이 같은 이름으로 덮어쓰거나 추가 |

### 3.8 분류표 — 근거 사업의 고유 기능은 어느 확장 지점인가 (G4 의 기대값)

| 사업 | 고유 기능 | 확장 지점 |
|---|---|---|
| 임진강김치 | 절임통 운영(`SLT_TANK_OPR`) · 절임 기준 · 편차 | E4 모듈(`x_kimchi_tank`) + E3 측정값(염도 · 절임시간) |
| 〃 | 염도 로그(센서) · 냉장고 온습도 로그 · 환경 알람 | E7 collect + 코어 `eqp_collect` · 알람은 E5 `on_collect` `[가설]` |
| 〃 | CCP 기준 · CCP 결과 · 금속검출 로그 | E3 검사 항목(`qua_insp_plan`) + E5 `validate_shipment`(금속검출 미통과 출하 금지) |
| 〃 | 숙성 냉장 재고 | E6 lot_kind `AGING` + E2 ext(숙성 시작일) |
| 〃 | 소독수 로그 · 테이핑 로그 | E4 팩 테이블(수기 로그) |
| 니즈푸드 | 메뉴 · 레시피 BOM · 식수 | 코어 `bas_item` + `bas_bom`(E1 용어: 품목 → 메뉴, BOM → 레시피) + E2 ext(식수 · 1인량) |
| 〃 | 레시피 기반 소요량 계산 | E5 `on_work_order_created` → 코어 `mat_requirement` |
| 〃 | 배치(솥) 실적 · RPM · 교반시간 · 온도 | 코어 `pop_work_result` + E6 lot_kind `BATCH` + E3 측정값(collect) |
| 〃 | 검식 · 공정중 검사 | E3 검사 항목 |
| 〃 | AI Agent 8화면 | 범위 밖(선택 팩 `agent`) |
| 엘컴화인 | Job-Lot-Roll · splice · 슬리팅 | E6 (`ROLL` · `splice` · `슬리팅`) + E1 용어(작업지시 → Job) |
| 〃 | 판사양 · 아니록스 · 잉크조성 · 조색 기록 · ΔE | E4 모듈(`x_printfilm_plate` `x_printfilm_anilox` `x_printfilm_ink_formula` `x_printfilm_color_record`) + E3 측정값(ΔE) |
| 〃 | COA | 코어 `shp_document` + E7 양식 |
| 〃 | 이관 배치 6 | 코어 `migrate/` 표준 Import 파일 + 팩 매핑 |
| 〃 | 영업관리(설계도 밖 확장) | 코어 `ord`(E1 메뉴 노출) |
| 송월타월 | DTF 인쇄 실적 자동 생성 | E7 collect + E5 `on_collect` 가 가동 구간 → `pop_work_result` `[가설]` |

세 참조 팩을 쓰면서 이 표에 **들어가지 않는 기능이 나오면** 확장 지점이 모자란 것이다 → 코어 변경 요청(D-번호).

---

## 4. `pack.yaml` 규격

### 4.1 전체 모양

```yaml
pack: printfilm                   # 폴더명과 같다. 영문 소문자
name: 엘컴화인 MES                 # UI 표기
company: 엘컴화인(주)
requires_core: ">=0.1,<1.0"       # Q9
env_prefix: MES_                  # 바꾸지 않는다

terms:                            # E1 용어 사전 (코어 중립어 → 업종어)
  작업지시: Job
  생산 LOT: Roll
  실적: 인쇄 실적
  성적서: COA

menus:                            # E1 메뉴
  hide: [ord]                     # 수주 메뉴 숨김(엘컴화인 초기 범위)
  rename: { pop: 생산 실적 POP, trc: LOT 추적 }
  order: [bas, prt, job, mat, clr, pop, rll, qua, shp, trc, kpi, sys]
  add:
    - { code: prt, name: 인쇄 기준 관리, after: bas }
    - { code: clr, name: 조색 기록, after: mat }
    - { code: rll, name: 후가공·슬리팅 롤 이력, after: pop }

screens:                          # E4 팩 화면 (코어 화면은 코어 매니페스트에)
  - { id: X-PRT-01, name: 판사양 관리, module: prt, path: /prt/plates, channels: [web], owner: 개발1 }
  - { id: X-CLR-01, name: 조색 기록, module: clr, path: /clr/records, channels: [web, pop], owner: 개발2 }

roles:                            # E1 역할 (코어 기본 4 를 대체하거나 추가)
  - { code: ADMIN, name: 관리자 }
  - { code: PROD,  name: 생산 }
  - { code: QA,    name: 품질 }
  - { code: FIELD, name: 현장 }
permissions: seed/permissions.csv # 메뉴 × 역할 칸 (없음|조회|입력[:scope])

numbering:                        # E1 채번
  WORK_ORDER: { prefix: J, date: YYMMDD-, digits: 3 }
  LOT_PRODUCT: { prefix: R, date: YYMMDD-, digits: 4 }
  SHIPMENT:    { prefix: S, date: YYMMDD-, digits: 3 }
  DOCUMENT:    { prefix: C, date: YYMMDD-, digits: 3 }

channels:                         # E1 채널별 화면 허용
  pop:   [POP-01, POP-02, X-CLR-01, SHP-02]
  mobile: [TRC-01, TRC-02, KPI-01]
  board: [KPI-01]

attrs:                            # E2 표시용 속성
  lot: [ { key: width_mm, label: 폭(mm), type: number }, { key: length_m, label: 길이(m), type: number } ]

process_params: seed/process_params.csv   # E3 (공정 · 키 · 라벨 · 단위 · 형식 · 하한 · 상한 · 필수 · 수집원)
inspection_items: seed/inspection_items.csv

lineage:                          # E6
  lot_kinds: [ { kind: ROLL, base: PRODUCT, label: 롤 } ]
  relations: [ { name: splice, base: 합병 }, { name: 슬리팅, base: 분할 } ]

write_scope:                      # 팩 라우터가 쓸 수 있는 코어 테이블 (§2.3)
  clr: []                         # 조색 기록은 x_printfilm_* 만
  rll: [lot, lot_genealogy]       # lineage 를 통해서만 — check_pack 이 직접 SQL 을 잡는다

hooks: hooks.py                   # E5
adapters:                         # E7
  printing: adapters/label_html.py
  erp: null                       # 코어 기본(501)
seeds: [seed/codes.csv, seed/items_example.csv]
tests: tests/
gates: gates.yaml                 # 팩 게이트 기대값 (§10.2)
```

### 4.2 코어 매니페스트

코어도 같은 형식의 `src/mescore/core.yaml` 을 가진다(모듈 12 · 코어 화면 · 기본 역할 4 · 기본 채번 · 기본 관계 5 · 금지어 목록). 팩 로더는 **코어 → 팩 순으로 병합**한다.

### 4.3 병합 규칙 — 어기면 기동 거부

1. 팩은 코어 화면 ID · 경로 · 기능 ID 를 **재정의하지 못한다**(이름 · 숨김 · 순서만).
2. 팩 화면 ID 는 `X-` 로, 팩 테이블은 `x_<팩>_` 로, 팩 모듈 코드는 코어 12 와 겹치지 않게.
3. `lineage.relations[].base` 와 `lot_kinds[].base` 는 코어 종류여야 한다.
4. `requires_core` 를 만족하지 않으면 거부.
5. `write_scope` 에 `lot_genealogy` 를 넣어도 직접 INSERT 는 금지(`lineage` 호출만). 정적 스캔.
6. `terms` 의 키는 코어 중립어 목록(`core.yaml: terms_keys`)에 있어야 한다 — 오타로 치환이 안 되는 것을 막는다.

---

## 5. 공용 모듈 인터페이스 `[기준: 엘컴화인 interfaces.md 일반화]`

| 모듈 | 책임 | 쓰는 사람 |
|---|---|---|
| `db.conn` | `q q1 x tx` · `DbUnavailable` → 503 · 비밀번호 마스킹 | 전원 |
| `app.packs` | `load(name) -> Pack` · `current()` · `t(text)` 용어 치환 · `hook(name)` | 전원(간접) |
| `app.nav` | `GROUPS MENUS SCREENS COMMON` · `path_of(id)` · `by_id(id)` · `menu(code)` — 코어 + 팩 병합본 | 전원 |
| `app.contracts` | `function(id)` · `functions_of(screen_id)` — `contracts/function-list.md` 로더 | 전원 · 검사 도구 |
| `app.rbac` | `require_screen(id)` · `require_fn(id)` · `current_user(request)` · `user.can(fn)` · `matrix() roles() cell()` · `invalidate()` — 권한 표는 DB, 사용자 상태는 **요청마다 DB** | 전원 |
| `app.auth` | 로그인 · 로그아웃 · 세션(`sys_session`) · 비밀번호 해시 · 잠금 | `sys` · `home` |
| `app.templating` | `render(request, tpl, ctx, screen_id=, status_code=)` — 헤더 · 메뉴 · 채널 레이아웃 · 용어 치환 · 조회 로그 | 전원 |
| `app.numbering` | `next(kind, *, cur=None, at=None)` · `peek` · `rule` — `sys_number_rule` 조립식 · 카운터 잠금 · 트랜잭션 롤백 동반 | `job mat pop shp` · 팩 |
| `app.lineage` | 쓰기 `link assert_usable make_product_lot split merge ship unship`(전부 `cur` 받음) · 읽기 `resolve search state parents_of children_of trace_backward trace_forward` · `Node Edge Trace` | `pop shp trc` · 팩 |
| `app.printing` | `render_print(template, data) -> HTMLResponse` · `barcode_svg(text)` · 어댑터 `PrintAdapter` | `job mat pop shp` · 팩 |
| `app.stats` | 생산 · 품질 · 납기 · 설비 집계 SQL **유일한 자리** · `measure_series(key, …)` · `kpi_extra` 훅 병합 | `kpi` · QA 대조 |
| `app.collect` | `CollectMessage` 수신 → `ifc_collect_raw` → `eqp_collect` 정제 · 설비 코드 ↔ 태그 매핑 검증 · `on_collect` 훅 | `ifc` |
| `app.erp` | `ErpAdapter` 인터페이스 · 기본 501 · `ifc_outbox` 재시도 | `after_commit_*` 훅 |
| `app.audit` | `log_change(request, user, fn_id, target)` · 조회 로그 | 전원(쓰기 직후) |
| `app.util.http` | `validation_error(msg, fields)`(422) · `not_found`(404) · `undecided("D-nn")`(501) · `saved(request, msg)` | 전원 |
| `app.ui`(매크로) | `grid field select scan_box write_button print_button undecided notes measure_fields attrs_fields` | 템플릿 |

라우터 한 개의 모양은 엘컴화인 `interfaces.md` §2 와 같다(화면 GET = `nav.path_of` + `rbac.require_fn`, 쓰기 POST = 검증 → `conn.x` 또는 `tx` → `audit.log_change` → `http.saved`). **`main.py` 는 아무도 만지지 않는다.**

---

## 6. 화면 · 메뉴 · 채널

### 6.1 코어 화면 `[가설: 51 — 참조 팩 작성 후 확정]`

| 모듈 | 화면 ID | 화면 |
|---|---|---|
| 공통 | `CMN-01~05` | 로그인 · 메인(IA) · 오류 · 대시보드 · 팝업 |
| bas | `BAS-01~09` | 품목 · BOM · 공정 · 공정 측정값 · 설비 · 거래처 · 작업자 · 불량코드 · 공통코드 |
| ord | `ORD-01~04` | 수주 · 수주 이력 · 납기 달력 · 생산계획 |
| job | `JOB-01~03` | 작업지시 · 지시 현황 · 작업지시서 출력 |
| mat | `MAT-01~05` | 입고 · 입고검사 · 원재료 LOT · 재고 · 소요량 |
| pop | `POP-01~04` | 작업 목록(스캔) · 작업 시작/종료(측정값) · 투입 스캔 · LOT 라벨 |
| qua | `QUA-01~04` | 검사 계획 · 검사 결과 · 불량 집계 · 이상 · 시정 |
| eqp | `EQP-01~04` | 가동 현황 · 점검 · 고장 · 수집값 조회 |
| shp | `SHP-01~04` | 출하 등록 · LOT 스캔/승인 · 출하 현황 · 성적서 |
| trc | `TRC-01~03` | 정방향 추적 · 역방향 추적 · 번호 검색 |
| kpi | `KPI-01~03` | 현황판 · 생산/품질/납기/설비 집계 · 지표 정의 |
| sys | `SYS-01~06` | 사용자 · 역할 · 권한 표 · 접근 로그 · 채번 규칙 · 백업/이관 |
| ifc | `IFC-01~02` | 수집 수신 현황 · ERP 연계 로그 |

각 화면은 기능 ID `F-<화면>-nn` 을 1개 이상 가진다(`contracts/function-list.md`). 코어 기능 수는 참조 팩 작성 후 센다 `[가설]`.

### 6.2 채널 `[기준: 엘컴화인 G-13]`

| 채널 | 레이아웃 | 규칙 |
|---|---|---|
| 관리자 Web | 좌측 메뉴 + 검색 · 그리드 · 액션 블록 | 기본 |
| POP | 확대 · 스캔칸 1개(`data-scan`)가 포커스 · 바코드 1회 = 1건 · 알림 중 스캔 허용 · 없는 번호는 **그 화면 422 재렌더** | 스캐너는 키보드 입력 |
| 모바일 | 폭 390px 가로 스크롤 0 · 조회 중심 | `channels.mobile` 에 선언한 화면만 |
| 현황판 | 조작 없음 · 자동 새로고침 · 마지막 갱신 시각 | `kpi_snapshot` 또는 실시간 집계 |

---

## 7. API · 오류 계약 `[기준]`

- 화면 GET 과 쓰기 POST 는 `function-list.md` 의 `API` 열과 **메서드 · 경로가 글자 그대로**. `check_trace` 가 이것으로 기능 ↔ 라우트를 잇는다.
- JSON 이 필요한 곳(현황판 폴링 · 수집 수신 · 추적 결과)은 같은 경로에 `Accept: application/json` 또는 `/api/…` 접두어 `[가설]`.

| 상황 | HTTP | 화면 |
|---|---|---|
| 필수값 누락 · 코드 중복 · 없는 LOT 스캔 · 이미 출하된 LOT · 자기 자신 계보 · 훅 거부 | **422** | 메시지(POP 은 큰 글씨, 다음 스캔을 막지 않음) |
| 인증 실패 | **401** | 브라우저 GET 은 `/login` 303 |
| 권한 없음 · 숨긴 메뉴 | **403** | `접근 권한이 없습니다` |
| DB 연결 실패 | **503** | `서비스 일시 중단` |
| ERP · 미확정 연계 · 미구현 어댑터 | **501** | `미확정 (D-nn)` 명시. 조용한 폴백 금지 |
| 처리되지 않은 예외 | **500** | `예상하지 못한 오류` + 로그 |

---

## 8. 업종 팩 작성 절차

### 8.1 단계

| 단계 | 하는 일 | 산출 | 확인 |
|---|---|---|---|
| 1 | `cp -r packs/_template packs/<팩>` · `pack.yaml` 의 `pack name company terms roles numbering` | `pack.yaml` | `MES_PACK=<팩> make pack-check` (병합 규칙) |
| 2 | `make setup db-schema db-seed run` → 로그인 → 코어 화면이 업종 말로 뜨는지 | — | `make gate` 코어 게이트 전부 PASS (여기까지 G7 의 4시간) |
| 3 | 설계 산출물이 있으면 `uv run tools/import_design.py <design.json 또는 폴더>` → `contracts/function-list.md` · `screen-map.md` 초안 · 용어 사전 후보(TD3 화면명 ↔ 코어 중립어) | `contracts/` | `make check-trace` 가 산출물 ID ↔ 코어 화면 매핑 누락을 찍는다 |
| 4 | 빠진 것을 §3.8 처럼 **분류**한다 — E1~E7 중 어디인가. 어디에도 안 들어가면 D-번호 | `decisions.md` | — |
| 5 | E1 · E3 · E6 는 `pack.yaml` · `seed/*.csv` 로 끝낸다 | 시드 | `make db-seed` ×2 행 수 diff 0 |
| 6 | E2 · E4 는 `schema_ext.sql` · `routers/` · `templates/` | 코드 | `make check-schema check-routes check-pack` |
| 7 | E5 · E7 은 `hooks.py` · `adapters/` | 코드 | 훅 단위 테스트 · 어댑터는 501 기본 유지 여부 |
| 8 | `gates.yaml` 에 팩 게이트 기대값(화면 수 · 테이블 수 · 핵심 시나리오 · 계보 행 수) | `gates.yaml` | `make gate` 팩 게이트 |
| 9 | 브라우저 한 바퀴(E2E) 캡처 `outputs/e2e/` | 캡처 | G-C22 |

### 8.2 `_template` 팩의 내용

`pack.yaml`(모든 키에 주석 · 기본값) · `schema_ext.sql`(빈 파일 + 규약 주석) · `routers/_example.py`(화면 1 · 기능 2 의 최소 예) · `hooks.py`(모든 훅의 빈 서명) · `adapters/`(인터페이스만) · `seed/*.csv`(헤더만) · `tests/test_pack_smoke.py` · `gates.yaml` · `README.md`(이 절의 요약).

### 8.3 참조 팩 3 — 핵심 시나리오 (G5)

| 팩 | 용어 사전 핵심 | 추가 모듈 | 측정값 | 계보 | 훅 | 핵심 시나리오(팩 게이트) |
|---|---|---|---|---|---|---|
| `kimchi` | 품목 → 품목, 생산 LOT → 배치, 공정 측정값 → 공정 조건 | `x_kimchi_tank`(절임통 운영) · 소독수 · 테이핑 로그 | 염도 · 절임시간 · 세척 횟수 · 냉장 온습도(collect) | `TANK` `AGING` kinds | 금속검출 미통과 출하 금지 · CCP 이탈 → `qua_issue` | 입고 → 절임통 투입(염도 기록) → 혼합 → 금속검출 합격 → 포장 → 출하 → 역추적 |
| `foodservice` | 품목 → 메뉴, BOM → 레시피, 생산 LOT → 배치(솥), 작업지시 → 조리 지시 | 없음(코어 + ext) | RPM · 교반시간 · 온도(collect) · 검식 | `BATCH` kind | `on_work_order_created` 식수 소요량 → `mat_requirement` | 수주(식수) → 조리 지시 → 소요량 자동 → 배치 실적(교반기 값) → 검식 → 출하 |
| `printfilm` | 작업지시 → Job, 생산 LOT → Roll, 성적서 → COA | `x_printfilm_plate anilox ink_formula color_record` | ΔE · 인쇄 속도 · 길이 | `ROLL` · `splice` · `슬리팅` | 작업 종료 시 Roll 생성 | 엘컴화인 설계도 §3 예시 = `lot_genealogy` **10행** · 역추적 LOT ①② 도달 · 슬리팅 ③ 재고 |

---

## 9. 디렉터리 구조 `[가설]`

```
Standard MES Platform/
├── intro.md · problem.md · spec.md            # 이 문서들
├── goal.md · CLAUDE.md · decisions.md · progress.md   # 구현 단계에 추가 (엘컴화인 형식)
├── contracts/                                  # function-list · db-schema · screen-map · interfaces · api-contract · pack-contract
├── pyproject.toml · uv.lock · Makefile · docker-compose.yml · Dockerfile · .env.example
├── src/mescore/
│   ├── core.yaml                               # 코어 매니페스트 (§4.2)
│   ├── app/  main.py settings.py packs.py nav.py contracts.py rbac.py auth.py templating.py
│   │         numbering.py lineage.py printing.py stats.py collect.py erp.py audit.py
│   │         routers/{home,bas,ord,job,mat,pop,qua,eqp,shp,trc,kpi,sys,ifc}.py
│   │         util/{http,screen,terms}.py  templates/{base.html,home/_macros.html,<모듈>/*.html,print/*.html}  static/{app.js,app.css}
│   ├── db/   conn.py schema.sql views.sql seed_core.py migrate/{importer.py,formats.md}
│   └── tools/ gate.py check_routes.py check_schema.py check_data.py check_trace.py check_security.py check_terms.py check_pack.py import_design.py
├── packs/
│   ├── _template/   pack.yaml schema_ext.sql routers/ templates/ hooks.py adapters/ seed/ tests/ gates.yaml README.md
│   ├── kimchi/ · foodservice/ · printfilm/     # 참조 팩 3
├── tests/            # 코어 테스트 (어떤 팩에서도 통과)
├── outputs/          # 게이트 리포트 · e2e 캡처 · pack-timing.md
└── docs/             # 근거 사업 산출물 링크 · 이관 메모
```

---

## 10. 검증 도구와 게이트

### 10.1 도구 7 `[기준 5 + 가설 2]`

| 도구 | 하는 일 | 출력 |
|---|---|---|
| `check_routes` | 코어 + 팩 화면 전부 HTTP 200 · `_placeholder` 0 | `G-C03` |
| `check_schema` | `contracts/db-schema.md` ↔ 실제 DB 컬럼 단위 대조 · 팩 확장 테이블 접두어 | `G-C04` `G-P02` |
| `check_data` | 쓰기 경계 정적 스캔 + 조회 전후 행 수 diff · 집계 재계산 대조 · 빈 화면 `미수집/미확정` | `G-C05` `G-C10` `G-C11` |
| `check_trace` | 기능 ↔ 라우트 ↔ 테스트 1:1 · 산출물 ID ↔ 화면 매핑 | `G-C02` `G-P03` |
| `check_security` | RBAC 칸 전부 · 비밀 0 · 세션 무효화 | `G-C17~19` |
| `check_terms` `[가설]` | 코어 코드 · 템플릿 · 시드에 금지어 0 · 팩 용어 사전 키 유효 | `G-C23` |
| `check_pack` `[가설]` | 코어 파일 수정 0(해시) · 코어 테이블 `ALTER` 0 · 코어 경로 재정의 0 · `write_scope` 밖 쓰기 0 · `lot_genealogy` 직접 INSERT 0 · 템플릿 덮어쓰기 목록 | `G-P01` |

### 10.2 게이트

**코어 게이트 G-C01~G-C24** — 엘컴화인 G-01~G-22 를 코어 기준으로 옮기고 2개를 더한다. 판정은 `make gate` 출력뿐.

| # | 항목 | 게이트 |
|---|---|---|
| G-C01 | 메뉴 | 코어 메뉴 12 · `nav` 단일 소스 = `core.yaml` |
| G-C02 | 기능 | 코어 기능 전부가 계약 한 줄 = 라우트 = 테스트, 고아 0 |
| G-C03 | 화면 | 코어 화면 + 공통 5 전부 200 · placeholder 0 |
| G-C04 | 스키마 | 계약 = 실제 DB · 코어 테이블 수 `[가설 52]` |
| G-C05 | 쓰기 경계 | §2.3 · `trc` `kpi` 쓰기 0 |
| G-C06 | 계보 재현 | 코어 시나리오: 원재료 2 → 생산 LOT 2 → 합병 1 → 분할 3 → 출하 1 = `lot_genealogy` 10행 (엘컴화인 예시의 중립판) |
| G-C07 | 추적 | 역방향 · 정방향 · 재귀 · 분기 5단 이상 |
| G-C08 | 키 연결 | LOT 번호 하나로 지시 · 실적 · 측정값 · 검사 · 출하 조회 · 채번은 `numbering` 한 곳 |
| G-C09 | 시드 멱등 | ×2 diff 0 · `(예시)` 표기 |
| G-C10 | 집계 | `stats` 값 = QA 별도 SQL |
| G-C11 | 빈 화면 | `미수집` · `미확정 (D-nn)` |
| G-C12 | 범위 밖 0 | 설비 제어 · 업종 전용 기능이 코어에 없음 |
| G-C13 | 4채널 | §6.2 |
| G-C14 | 출력물 | 작업지시서 · LOT 라벨 · 출하 라벨 · 성적서 4종 · 바코드 SVG · 스캔 왕복 |
| G-C15 | 이관 | 표준 Import 파일 멱등 적재 · 건수 · 오류 리포트 |
| G-C16 | ERP | 501 명시 · 조용한 폴백 0 |
| G-C17 | RBAC | 권한 표 전 칸 · 없음 = 숨김 + 403 · 조회 = 쓰기 403 · 역할은 데이터 |
| G-C18 | 접근 로그 | 로그인 · 조회 · 변경 |
| G-C19 | 비밀 | 저장소 · 문서에 0 |
| G-C20 | 백업 | `make backup` · `restore-check` 행 수 일치 |
| G-C21 | 빌드 | pytest 전건 · check-routes · `/health` 200 |
| G-C22 | 브라우저 한 바퀴 | 역할 바꿔 가며 입고 → 출하 → 역추적 캡처 |
| G-C23 | 용어 중립 `[가설]` | 금지어 0 (§12) |
| G-C24 | 측정값 `[가설]` | `bas_process_param` 선언만으로 POP 입력칸 · `pop_measure` 기록 · 범위 이탈 표시 · `stats.measure_series` 집계가 된다 |

**팩 게이트 G-P01~G-P06** — 기대값은 팩의 `gates.yaml`.

| # | 항목 | 게이트 |
|---|---|---|
| G-P01 | 격리 | `check_pack` 전 항목 0 · 팩을 빼도 코어 테스트 전건 통과 |
| G-P02 | 규모 | 팩 화면 수 · 테이블 수 · 기능 수 = `gates.yaml` |
| G-P03 | 추적표 | 산출물 ID(있으면) ↔ 코어/팩 화면 1:1 · 고아 0 |
| G-P04 | 시나리오 | `gates.yaml: scenarios` 의 핵심 시나리오가 API 로 재현 (예: printfilm 계보 10행) |
| G-P05 | 용어 | 화면 · 메뉴 · 라벨에 코어 중립어가 **치환 안 된 채** 노출 0 (`terms` 에 있는 키 기준) |
| G-P06 | 착수 시간 | `outputs/pack-timing.md` 에 단계 1~2 실측 ≤ 4h (G7 · 참조 팩은 면제) |

---

## 11. 비기능 요구사항

| 항목 | 요구 |
|---|---|
| 성능 | 화면 GET 1초 이내(시드 1만 행 기준) · 추적 재귀 깊이 20 · 분기 100 에서 2초 이내 · 현황판 폴링 5초 |
| 동시성 | 채번 카운터 잠금 · 작업지시 행 `for update/for share` 규칙(엘컴화인 D-107 계열)을 코어 `job` 에 내장 |
| 보안 | 세션은 DB(`sys_session`) · 요청마다 사용자 상태 재확인 · 비밀번호 해시 · 비밀은 `.env` 만 · 접근 로그 |
| 운영 | `make backup/restore-check` · Docker Compose 1벌 · `/health` · 로그에 DSN 비밀번호 마스킹 |
| 이식 | 코어는 팩 없이 기동 · 한 PC 에서 전부 동작 · 외부 CDN 0 |
| 호환 | 코어 semver · `requires_core` 검사 · 코어 변경 시 참조 팩 3 의 게이트가 회귀 테스트 |

---

## 12. 금지어 목록과 용어 사전 기본값 `[가설]`

`check_terms` 가 코어(`src/mescore/`)에서 찾으면 FAIL 인 업종어. 팩에서는 자유.

| 출처 | 금지어 |
|---|---|
| 김치 | 절임 · 절임통 · 염도 · 숙성 · 양념 · 버무림 · 금속검출 · 소독수 · 세척 · 탈수 · 김치 · 율무 · 아이스박스 |
| 급식 | 솥 · 인분 · 식수 · 검식 · 레시피 · 조리 · 취사 · 볶음 · 무침 · 급식 · 교반 · 메뉴(음식 뜻) |
| 인쇄필름 | Roll · 롤 · Job · 판사양 · 아니록스 · 잉크 · 조색 · 배합비 · ΔE · 후가공 · 슬리팅 · splice · COA |
| 타월 | DTF · 나염 · 승화 · 전사 · 타월 · 수건 · 자수 |

코어 중립어 목록(`core.yaml: terms_keys`) — 품목 · BOM · 공정 · 설비 · 거래처 · 작업자 · 수주 · 생산계획 · 작업지시 · 원재료 LOT · 생산 LOT · 출하 LOT · 실적 · 작업 시작 · 작업 종료 · 투입 · 측정값 · 검사 · 불량 · 이상 · 출하 · 성적서 · 추적 · 현황판 · 분할 · 합병. 팩은 이 키만 치환한다.

---

## 13. 기존 사업의 표준 이관 경로 (범위 밖 · 경로만)

| 사업 | 팩 | 이관 순서 | 주의 |
|---|---|---|---|
| 엘컴화인 | `printfilm` | 테이블 30 → 코어 + ext 매핑(`material_lot roll shipment` → `lot` kind 3종 · `roll_genealogy` → `lot_genealogy` relation 매핑 · `color_record` 등 → `x_printfilm_*`) → 표준 Import 파일 → `make migrate` → `check_data` 로 행 수 · 계보 10행 대조 | 가장 가깝다. `numbering lineage printing erp stats` 는 코어가 그대로 흡수 |
| 니즈푸드 | `foodservice` | `design.json` → `import_design.py` → 49화면 ↔ 코어/팩 매핑표 → 테이블 37 매핑(`BAS_MENU` → `bas_item` 등) → Import | AI Agent 8화면은 선택 팩 `agent` 이전까지 보류 |
| 임진강김치 | `kimchi` | 64화면 · 테이블 67 → 공정별 로그 테이블의 절반 이상이 E3 측정값 · E7 collect 로 흡수 → 나머지 `x_kimchi_*` | 공정 체인 추적을 `lot_genealogy` 로 바꾸는 것이 가장 큰 변경 |

이관은 **운영 DB 를 건드리지 않고** 복제본에서 하며, 각 단계는 D-번호로 결정을 남긴다.

---

## 14. 수용 기준 (이 명세의 완료 판정)

`problem.md` §4.1 G1~G10 을 `make gate` 로 실측한다.

| 목표 | 판정 명령 · 기대값 |
|---|---|
| G1 코어 한 바퀴 | `MES_PACK= make gate` → G-C01~G-C24 전부 PASS · `outputs/e2e/core/` 캡처 |
| G2 코어 규모 | `make check-schema` 테이블 ≤ 55 · `make check-trace` 화면 ≤ 55 · 공용 모듈 9 파일 존재 · `contracts/db-schema.md` 각 테이블의 "근거 사업" 열에 둘 이상 |
| G3 용어 중립 | `make check-terms` 금지어 0 |
| G4 확장 지점 | §3.8 분류표의 모든 행이 E1~E7 중 하나 · `decisions.md` 에 "확장 지점 부족" 차단 0 |
| G5 팩 재현 | `MES_PACK=kimchi|foodservice|printfilm make gate` 각각 G-P04 PASS (printfilm 은 10행) · 코어 파일 해시 변동 0 |
| G6 팩 격리 | 팩 3개 각각에서 G-P01 PASS · `packs/<팩>` 삭제 후 `uv run pytest tests/` 전건 통과 |
| G7 착수 속도 | 새 더미 팩 `_timing` 으로 단계 1~2 실측 ≤ 4h (`outputs/pack-timing.md`) |
| G8 정본 연결 | 니즈푸드 `design.json` 으로 `import_design.py` → `function-list.md` 49행 · 매핑 누락 목록 출력 · `design.json` 없이 돌리면 빈 양식 생성 |
| G9 4채널 | G-C13 PASS · 팩별 `channels` 선언대로 |
| G10 도구 공용 | `src/mescore/tools/` 7종 · 참조 팩 3 에 `tools/` 폴더 없음(기대값 `gates.yaml` 만) |

범위 밖(실패로 보지 않음): 실 ERP · 실 프린터 · 실 Data Gateway 연결 · 기존 운영 DB 실제 이관 · AI Agent · 멀티테넌트 · 다국어.
