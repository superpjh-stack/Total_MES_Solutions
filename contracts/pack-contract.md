# 팩 계약 — 업종 팩이 지켜야 할 것 (아키텍트 · 2026-10-09 · 초안)

> `spec.md` §3(확장 지점 7) · §4(`pack.yaml`)을 코드가 지키는 방식이다. `app/packs.py` 가 기동 때, `tools/check_pack.py` 가 G-P01 에서 이 문서를 판정한다.
> **팩은 이 문서 안에서만 산다.** 밖이 필요하면 `decisions.md` 에 `코어 변경 요청`(`goal.md` §4.3). 팩 작성자가 코어를 고치면 G-P01 FAIL.

## 1. 폴더

```
packs/<팩>/
├── pack.yaml            # 필수. §2
├── schema_ext.sql       # E2 · E4 테이블. x_<팩>_ 접두. 코어 ALTER 금지
├── routers/*.py         # E4. router = APIRouter(). 코어 경로 재정의 금지
├── templates/           # E4 · E7. 코어 templates/ 보다 먼저 검색 — 같은 이름은 덮어쓴다(WARN)
├── hooks.py             # E5. §5 의 서명
├── adapters/*.py        # E7. PrintAdapter · ErpAdapter · CollectDriver
├── seed/*.csv           # E1 · E3. permissions · process_params · inspection_items · codes · 예시 데이터
├── migrate.yaml         # 이관 매핑 (migration-files.md §6) — 선택
├── tests/               # 팩 테스트. @pytest.mark.fn("F-X-…")
├── gates.yaml           # 팩 게이트 기대값. §7
├── function-list.md     # 팩 기능 (코어 function-list.md 와 같은 열). 선택이지만 E4 가 있으면 필수
└── README.md
```
`packs/_template/` 가 이 모양 그대로 비어 있다. `make pack-new NAME=<팩>` 이 복사한다.

## 2. `pack.yaml` 필드

| 키 | 필수 | 뜻 · 규칙 |
|---|---|---|
| `pack` | ✓ | 폴더명과 같다. `^[a-z][a-z0-9_]*$`. `_` 로 시작하면 템플릿/더미(게이트 면제) |
| `name` · `company` | ✓ | UI 표기 · 회사명(없으면 `name`) |
| `requires_core` | ✓ | semver 범위. `core.yaml: core_version` 이 밖이면 기동 거부 |
| `terms` | | `{코어 중립어: 업종어}`. 키는 `core.yaml: terms_keys` 에 있어야 한다. 값은 자유(업종어 허용) |
| `menus.hide` | | 코어 메뉴 코드 목록. 숨긴 메뉴의 화면은 403 + 메뉴 없음. 테이블 · 테스트는 남는다 |
| `menus.rename` | | `{코드: 이름}` |
| `menus.order` | | 코어 + 팩 메뉴 코드 전체 순서. 빠진 것은 뒤에 코어 순서로 |
| `menus.add[]` | | `{code, name, after}`. `code` 는 코어 12 와 다르게 |
| `screens[]` | E4 때 | `{id: X-<MOD>-nn, name, module, path, channels[], owner}`. `path` 는 `/<module>/…`, 코어 경로와 겹치지 않게 |
| `roles[]` | | `{code, name}`. 주면 코어 기본 4 를 **대체**(관리자 `ADMIN` 은 반드시 포함) |
| `permissions` | | `seed/permissions.csv` 경로. 열 `menu_code,role_code,level,scopes`. 코어 + 팩 메뉴 × 역할 **전 칸** 있어야 한다 |
| `numbering` | | `{KIND: {prefix, date, digits}}`. 코어 종류는 형식만 바꾼다. 새 종류 추가 가능 |
| `channels` | | `{pop: [...], mobile: [...], board: [...]}` 화면 ID. 주면 코어 기본을 **대체** |
| `attrs` | E2 | `{테이블: [{key, label, type(number|text|bool|date|select), required, choices[]}]}`. 코어 테이블만. `ui.attrs_fields` 가 폼을 만들고 `packs.read_attrs` 가 읽는다 |
| `process_params` · `inspection_items` | E3 | CSV 경로(`migration-files.md` §2 의 `04_process_params.csv` 형식 · 검사 항목은 `qua_insp_plan` 시드) |
| `lineage.lot_kinds[]` | E6 | `{kind, base(MATERIAL|PRODUCT|SHIPMENT), label}` |
| `lineage.relations[]` | E6 | `{name, base(투입|생산|분할|합병|출하)}` |
| `lineage.states` | E6 | `{IN_STOCK, CONSUMED, SHIPPED}` 표시어 |
| `write_scope` | E4 때 | `{팩 모듈: [코어 테이블…]}`. 팩 라우터 · 훅이 쓸 수 있는 코어 테이블. `lot_genealogy` 를 넣어도 직접 SQL 은 금지(`lineage` 만) |
| `hooks` | E5 | 모듈 경로(기본 `hooks.py`) |
| `adapters` | E7 | `{printing, erp, collect}` 모듈 경로 또는 `null`(코어 기본) |
| `seeds[]` | | CSV 경로 순서. 멱등(키 열로 upsert) |
| `tests` · `gates` | | 폴더 · `gates.yaml` 경로 |

## 3. `attrs` 와 확장 테이블 — 어디에 두는가 (D-05)

| 값의 성격 | 둔다 | 안 된다 |
|---|---|---|
| 표시만 (검색 · 집계 · 제약 없음) | `attrs` + `pack.yaml: attrs` 선언 | `attrs` 키를 WHERE · GROUP BY · JOIN 에 쓰는 것(`check_pack` 이 `attrs->>` 를 WHERE 에서 찾으면 WARN, 집계 SQL 에서 찾으면 FAIL) |
| 검색 · 정렬 · 집계 · FK · 유니크 | `x_<팩>_<코어테이블>_ext` (코어 `id` 가 PK 겸 FK, 1:1, `on delete cascade`) | 코어 테이블 `ALTER` |
| 코어 행과 1:N | `x_<팩>_<이름>` | — |
| 시계열 (센서 로그) | `eqp_collect`(collect 경유) 또는 `x_<팩>_<이름>_log` | `pop_measure` 에 분 단위로 쌓는 것 |

## 4. 병합 · 격리 규칙 — 어기면 기동 거부(`PackError`) 또는 G-P01 FAIL

| # | 규칙 | 판정 |
|---|---|---|
| R1 | 코어 파일(`src/mescore/**`)을 고치지 않는다 | `check_pack`: `outputs/core.sha256`(Phase 0 에 찍음 · 아키텍트가 코어를 고칠 때만 갱신) 과 대조 |
| R2 | 코어 테이블에 `ALTER` · `DROP` · 트리거 추가 없음 | `schema_ext.sql` 정적 파싱 |
| R3 | 팩 테이블은 `x_<팩>_` 접두 · 공통 컬럼 5 + `attrs` | `check_schema` |
| R4 | 코어 화면 ID · 경로 · 기능 ID 를 재정의하지 않는다 (`rename` · `hide` · `order` 만) | `packs.load` |
| R5 | 팩 화면 ID `X-` · 모듈 코드 코어 12 와 다름 · 경로 `/<팩 모듈>/…` | `packs.load` |
| R6 | `lineage.*[].base` 는 코어 종류 · `terms` 키는 `terms_keys` 안 · `requires_core` 만족 | `packs.load` |
| R7 | 팩 라우터 · 훅의 쓰기 SQL 대상은 `x_<팩>_*` + `write_scope` 뿐 | `check_pack` 정적 스캔(`insert|update|delete … <table>`) |
| R8 | `lot_genealogy` · `sys_number_seq` 직접 INSERT/UPDATE 없음 — `lineage` · `numbering` 만 | 〃 |
| R9 | 코어 테스트(`tests/`)가 팩을 올린 채로도, 팩 폴더를 지운 채로도 전건 통과 | `make test` ×2 |
| R10 | 코어 템플릿을 덮어쓴 파일 목록을 `README.md` 에 적는다 | `check_pack` WARN 목록 ↔ README |
| R11 | 팩 안에 외부 CDN · 제어 명령 엔드포인트 · 비밀값 없음 | `check_security` |

## 5. 훅 서명 (`hooks.py`) — 전부 선택. 이름이 맞으면 등록된다

```python
from mescore.app.util.http import HookError
from mescore.app.packs import t

def validate_bas_item(cur, row: dict, user) -> None: ...        # validate_<코어 테이블>. row 는 저장될 값(dict, attrs 포함). 거부는 raise HookError(t("…"), fields=[...])
def on_order_created(cur, order: dict, user) -> None: ...
def on_work_order_created(cur, wo: dict, user) -> None: ...     # 예: 식수 × 1인량 → mat_requirement (write_scope 에 mat_requirement)
def on_work_order_closed(cur, wo: dict, user) -> None: ...
def on_result_started(cur, result: dict, user) -> None: ...
def on_result_closed(cur, result: dict, user) -> None: ...      # result["product_lot"] 이 이미 있다. 팩 kind 로 바꾸려면 lineage.retag(cur, lot_id, kind)
def on_lot_created(cur, lot: dict, user) -> None: ...
def on_inspection_judged(cur, insp: dict, user) -> None: ...   # 예: CCP 이탈 → qua_issue (write_scope 에 qua_issue)
def validate_shipment(cur, shipment: dict, lots: list[dict], user) -> None: ...   # 예: 금속검출 미통과 LOT 이 있으면 HookError
def on_collect(cur, raw: dict, user=None) -> None: ...          # 예: 가동 구간 → 실적 자동 생성 (write_scope 에 pop_work_result)
def after_commit_shipment_approved(payload: dict) -> None: ... # 트랜잭션 밖. erp.enqueue 등
def kpi_extra(frm, to) -> list[dict]: ...                       # [{"key","label","value","unit"}]
```
- 동기 · 같은 트랜잭션 · 예외는 `HookError` 만 422, 그 밖 예외는 500(조용히 삼키지 않는다).
- 훅은 코어 함수(`lineage` · `numbering` · `stats` · `collect`)를 쓸 수 있고 코어 테이블은 `write_scope` 안에서만 쓴다.

## 6. 팩 라우터 · 화면

- `routers/<모듈>.py` 에 `router = APIRouter()`. 경로는 `nav.path_of("X-CLR-01")`. 권한은 `rbac.require_fn("F-X-CLR-01")` — 팩 `function-list.md` 에 그 줄이 있어야 한다.
- 템플릿은 코어와 같은 `base.html` 을 상속하고 `ui` 매크로를 쓴다. 문구는 `t()`.
- 팩 화면의 채널 · 권한 칸은 코어와 같은 방식(`channels` · `permissions.csv` 의 팩 메뉴 행).

## 7. `gates.yaml`

```yaml
screens: 6            # 팩 화면 수 (X-)
tables: 5             # x_<팩>_ 테이블 수
functions: 18         # 팩 function-list.md 줄 수
design_source: ../NeedsFood MES Platform/docs/design/design.json   # 있으면 G-P03 (없으면 null)
scenarios:
  - id: S1
    name: 계보 10행
    test: tests/test_scenario_lineage.py::test_ten_rows
    expect: { genealogy_rows: 10, backward_materials: 2, stock_lots: 1 }
  - id: S2
    name: 금속검출 미통과 출하 금지
    test: tests/test_scenario_ship.py::test_block
    expect: { status: 422, code: hook_rejected }
terms_sample: [작업지시, 생산 LOT, 성적서]   # G-P05 — 이 키들이 화면에 치환 안 된 채 보이면 FAIL
```

## 8. 팩이 바꿀 수 **없는** 것 (요약)

오류 계약 · 응답 모양 · 인증 · 세션 · 코어 경로 · 코어 테이블 구조 · 쓰기 경계 · 계보 알고리즘 · 채번 알고리즘 · 집계 SQL 의 자리 · 검사 도구. 이 중 하나가 필요하면 `코어 변경 요청`.
