# 공용 인터페이스 계약 (아키텍트 · 2026-10-09 · 초안)

> 7명이 **동시에** 일하기 위해 접점을 먼저 못 박는다. 개발 3명 · QA 3명 · 팩 작성자는 이대로 호출한다.
> §1~§3 · §8~§10 은 아키텍트가, §4~§7 의 공용 모듈은 각 소유자가 구현한다(웨이브 A R1). 시그니처를 바꿔야 하면 소유자가 `progress-devN.md` §1 에 먼저 공표한다.
> 이 문서와 실제 코드가 다르면 **코드가 맞다** — 발견자가 이 문서를 고친다. 엘컴화인 `interfaces.md` 를 일반화했다(`roll` → `lot`, 회사 고정값 → `pack.yaml`).

| 모듈 | 소유자 | 쓰는 사람 |
|---|---|---|
| `db.conn` · `app.packs` · `app.nav` · `app.contracts` · `app.rbac` · `app.auth` · `app.templating` · `app.audit` · `app.util.*` · `ui` 매크로 | 아키텍트 | 전원 |
| `app.numbering` | **개발1** | 개발1 · 2 · 3 · 팩 |
| `app.lineage` · `app.printing` · `app.collect` · `app.measure` + `home/_measure.html`(`mf.measure_fields`) | **개발2** | 개발2 · 3 · 팩 |
| `app.stats` · `app.erp` · `mescore.migrate` | **개발3** | 개발3 · QA2 · 팩 |

## 1. DB — `mescore.db.conn`

```python
q(sql, params=None) -> list[dict]   # SELECT. 항상 dict 리스트
q1(sql, params=None) -> dict|None   # 첫 행
x(sql, params=None) -> int          # INSERT/UPDATE/DELETE 한 문장. rowcount
tx()                                # with conn.tx() as cur: … 여러 문장을 한 트랜잭션으로
```
- DSN 은 `MES_PG_DSN`. 비우면 `settings` 가 `MES_PACK` 에 따라 `postgresql:///mes_core_db`(코어 단독 · `_` 팩) / `postgresql:///mes_<팩>_db` 로 정한다. **DB 연결 실패는 삼키지 않는다** → `DbUnavailable` → 503. 로그의 접속 문자열은 비밀번호를 가린다. `conn.table_counts()` 는 시드 멱등 · 백업 대조용(로그 · 세션 제외).
- 같이 성공하거나 같이 실패해야 하는 것은 `tx()` 하나에. `numbering.next(..., cur=cur)` · `lineage.*(cur, …)` · `packs.hook(...)(cur, …)` 가 그 커서를 받는다.
- **작업지시 행 잠금**: 작업지시를 고치는 쪽(수정 · 마감 · 취소 — `routers/job.py: lock_work_order`)은 `for update`, 그 지시에 무엇을 붙이는 쪽(실적 시작 `pop.assert_open` · 생산 LOT · 분할/합병 `lineage._assert_open`)은 `for share`. 한 트랜잭션은 지시 행을 하나만 잠그고 순서는 실적/LOT 행 → 지시 행 → 채번 카운터(교착 없음).
- `IntegrityError` · `DataError` 는 `main.py` 가 422 로 바꾼다. 사람이 읽을 문장은 라우터가 먼저 검사해 `http.validation_error` 로.

## 2. 팩 · 메뉴 · 계약 · 권한 · 렌더 (아키텍트 구현)

```python
# app.packs — core.yaml + packs/<팩>/pack.yaml 병합본. 기동 때 한 번
packs.load(name: str|None) -> Pack        # 병합 규칙 위반이면 PackError 로 기동 거부. name 이 비면 코어만
packs.current() -> Pack                   # .name .display_name .company .core_version .terms .modules .order .hidden .screens .common .roles .permissions .numbering .channels .attrs .lineage .write_scope .warnings
packs.t(text: str) -> str                 # 용어 치환 — 키가 그대로면 그 값, 아니면 긴 키부터 부분 치환, 사전에 없으면 원문 (D-07). 템플릿 전역 t() · 필터 |t
packs.hook(name: str) -> Callable         # 등록된 훅. 없으면 packs.NOOP_HOOK (아무 일도 안 함). packs.has_hook(name) -> bool
packs.attrs_of(table: str) -> list[AttrSpec]   # pack.yaml: attrs[table] — AttrSpec(key, label, type, required, choices)
packs.read_attrs(form: Mapping | Request, table) -> dict   # 폼의 attr_<key> 칸 → attrs. 필수 누락은 ValueError (라우터가 422 로)
packs.template_dirs() -> list[Path]       # packs/<팩>/templates 가 코어보다 먼저. packs.overridden_templates() 가 덮어쓴 목록
packs.router_modules() -> list[str]       # 코어 13 (mescore.app.routers.<m>) + 팩 packs/<팩>/routers/*.py (`_` 로 시작하는 파일 제외)
packs.core_tables() -> list[str]          # schema.sql 의 `-- @table` 52

# app.nav — 메뉴 · 경로의 원본 (core.yaml + 팩 menus/screens 병합). nav.rebuild() 로 다시 만든다(테스트)
nav.MENUS -> list[Menu]                   # 팩 hide 제외 · order 적용. Menu(code, name, module, owner, channels, screens, hidden, is_pack, seq). nav.ALL_MENUS 는 숨긴 것 포함
nav.SCREENS -> list[Screen]               # 코어 51 + 팩 X- 화면. Screen(screen_id, name, menu_code, module, path, owner, channels, is_pack, common, auth, probe)
nav.CORE_SCREENS (51) · nav.PACK_SCREENS · nav.COMMON (5) · nav.ALL (공통 + 화면)
nav.path_of("BAS-01") -> "/bas/items"     # 경로를 문자열로 다시 적지 않는다
nav.by_id("BAS-01") -> Screen · nav.by_path(path) · nav.menu("bas") -> Menu · nav.menu_of_screen(id) · nav.screens_of(module)
nav.channel_allowed("POP-02", "pop") -> bool   # web 은 전 화면 · 공통 화면은 전 채널 · 그 밖은 channels 선언대로
nav.DEVICE_CHANNEL = {web: 관리자 Web, pop: 현장 POP, mobile: 모바일, board: 현황판}

# app.contracts — function-list.md (+ 팩 function-list.md) 로더
contracts.function("F-BAS-01") -> Function(id, module, screen_id, name, kind, tables, channels, roles, scope, api, hooks, owner, text, is_pack)
#   .is_write .is_batch .is_token(F-IFC-01) .method .path .path_base(`?` 앞) .menu_code
contracts.functions_of("BAS-01") -> list[Function] · functions_of_module("bas") · functions() 136 · pack_functions() · all_functions()
contracts.batch_functions() -> list[Function]   # B-MIG-*
contracts.db_tables() -> {테이블: Table(name, module, desc, columns)}   # db-schema.md §4 렌더본 (공통 컬럼 6 제외)

# app.rbac — 권한 표 (DB sys_permission · sys_role)
rbac.require_screen("BAS-01")   # 화면 GET 의존성. 그 메뉴 칸이 없음 → 403, 미로그인 → 401, 숨긴 메뉴 → 403, 채널 허용 밖 → 403
rbac.require_fn("F-BAS-01")     # 기능 의존성. 쓰기 기능이면 쓰기 판정(scope 포함), 읽기 기능이면 조회 판정. 토큰 기능(F-IFC-01)은 사용자에게 늘 403
user.can("F-BAS-01") -> bool    # 템플릿 버튼 활성
user.id · user.login_id · user.user_name · user.role_code · user.role_name · user.device   # 요청마다 DB 에서 읽은 지금 값
rbac.current_user(request) -> User | None   # sys_session ⋈ sys_user ⋈ sys_role — 무효 · 만료 · 중지 · 비밀번호 변경이면 None (D-19)
rbac.invalidate()               # sys_permission · sys_role 변경 뒤 (F-SYS-05 · 06 · 08)
rbac.matrix() · rbac.roles() · rbac.cell(role_code, menu_code) -> Cell(level, scopes) · rbac.counts() · rbac.visible_menus(user)

# app.auth
auth.login(cur, login_id, password, device, *, client_ip=None) -> LoginResult(ok, session: Session(session_id, user, device), reason)   # 실패 횟수 · 잠금(D-14) · 접근 로그
auth.logout(cur, session_id) · auth.revoke_user_sessions(cur, user_id)   # F-SYS-03 · 비밀번호 재설정 때
auth.hash_password(raw) · auth.verify(raw, hashed)
auth.authenticate(request, login_id, password, device) · auth.open_session(request, session) · auth.close_session(request)   # main.py 가 쓴다
auth.require_collect_token(request)   # POST /ifc/collect — X-Collect-Token = MES_COLLECT_TOKEN, 아니면 401

# app.templating
templating.render(request, "bas/items.html", ctx, screen_id="BAS-01", status_code=200) -> HTMLResponse | JSONResponse
# 헤더 · 좌측 메뉴 · 우측 계약 패널 · 채널 레이아웃 · t() · 조회 로그 자동. 템플릿은 base.html 의 search · grid · actions 블록(또는 body)을 채운다.
# **백엔드 우선 (D-18)**: 요청 Accept 에 text/html 이 없으면 템플릿을 그리지 않고 ctx 를 JSON 으로 준다 (request · settings · 함수는 빠진다 ·
# dataclass · datetime · Decimal 은 풀린다 · `template` 키에 템플릿 이름). 테스트 · API 검증은 이 JSON 으로 판정한다. placeholder 는 {"placeholder": true, "owner", "note", "functions"}.
templating.placeholder(request, screen_id)   # 미구현 화면 — HTTP 200 + "미구현 — 담당 개발N" + 계약 문장

# app.audit
audit.log_change(request, user, fn_id, target: str, detail: dict|None = None)   # 쓰기 직후 — kind=change
audit.log_view(request, user, screen_id)   # templating.render 가 부른다 — kind=view
audit.write_log(kind=login_ok|login_fail|view|change|error, login_id=, user_id=, screen_id=, fn_id=, target=, detail=, ip=, device=)

# app.util.http — §8. 추가: http.after_commit(request, event, payload) → 응답 뒤 packs.hook("after_commit_<event>")(payload) (D-20)
```

라우터 한 개의 모양 (`app/routers/<모듈>.py` 또는 `packs/<팩>/routers/<모듈>.py` — `router = APIRouter()` 만 있으면 자동 include):

```python
@router.get(nav.path_of("BAS-01"), response_class=HTMLResponse)                 # F-BAS-04 품목 조회 = 화면 GET
def items(request: Request, user: rbac.User = rbac.require_fn("F-BAS-04")):
    rows = conn.q("select * from bas_item order by item_code")
    return templating.render(request, "bas/items.html", {"rows": rows}, screen_id="BAS-01")

@router.post(nav.path_of("BAS-01"))                                              # F-BAS-01 품목 등록
def create_item(request: Request, item_code: str = Form(...), …, user: rbac.User = rbac.require_fn("F-BAS-01")):
    if conn.q1("select 1 from bas_item where item_code = %s", (item_code,)):
        raise http.validation_error(t("이미 있는 품목 코드입니다"), fields=[{"name": "item_code", "label": t("품목 코드"), "reason": item_code}])
    with conn.tx() as cur:
        row = {"item_code": item_code, …, "attrs": packs.read_attrs(request, "bas_item")}
        packs.hook("validate_bas_item")(cur, row, user)                           # 팩 검증 (없으면 no-op)
        cur.execute("insert into bas_item (…) values (…)", …)
    audit.log_change(request, user, "F-BAS-01", f"bas_item:{item_code}")
    return http.saved(request, t("품목을 등록했습니다"))
```

- 화면 GET 을 등록하면 그 경로의 placeholder 는 저절로 빠진다. 메서드 · 경로가 `function-list.md` 의 `API` 열과 글자 그대로여야 `check-trace` 가 "이어졌다" 고 센다.
- 공용 매크로 `{% import "home/_macros.html" as ui %}` — `ui.grid` · `ui.field` · `ui.select` · `ui.scan_box` · `ui.write_button` · `ui.print_button` · `ui.undecided` · `ui.notes` · **`ui.attrs_fields(table)`**(팩 속성 폼 자동) · **`mf.measure_fields(params, values={}, latest={})`**(측정값 폼 자동 — 별 파일 `{% import "home/_measure.html" as mf %}` · `params = measure.params_for(process_id)` 를 라우터가 넘긴다 · 개발2) · `mf.measure_table(params, values)`.
- 사용자 문구는 전부 `t()` — 템플릿 `{{ t("생산 LOT") }}`, 파이썬 `from mescore.app.packs import t`.

## 3. 채번 — `app.numbering` (개발1)

```python
KINDS = core.yaml: numbering.keys()      # WORK_ORDER · LOT_MATERIAL · LOT_PRODUCT · LOT_SHIPMENT · SHIPMENT · DOCUMENT · ORDER · PLAN (+ 팩 추가)
numbering.next(kind, *, cur=None, at=None) -> str   # 발번 (카운터 +1). cur 를 주면 그 트랜잭션 안에서 — 롤백되면 번호도 되돌아간다
numbering.peek(kind, *, at=None) -> str             # 발번하지 않고 다음 번호만
numbering.rule(kind) -> dict | None                 # sys_number_rule 행. 없으면 None → 화면은 `미확정 (D-10)`
```
- 조립식: `prefix + to_char(기준 시각, date_format) + 일련번호(seq_digits, 0 채움)`. 카운터 범위 = 날짜 부분 값(날짜 형식이 비면 통산). 카운터 행 잠금.
- 형식 행이 없는 종류를 `next` 하면 `RuntimeError`(500) — 번호를 지어내지 않는다. 번호는 바코드로 찍히므로 영문 대문자 · 숫자 · `-` 만.
- **다른 모듈은 번호의 첫 글자로 종류를 판정하지 않는다** — `lineage.resolve` 가 테이블에서 찾는다.
- 팩은 `pack.yaml: numbering` 으로 접두어 · 형식 · 자릿수와 종류 추가(E1). 시드가 `sys_number_rule` 을 채운다.

## 4. 계보 — `app.lineage` (개발2)

노드는 LOT 하나(`lot.id`). 종류 `lot.kind` — 코어 `MATERIAL` · `PRODUCT` · `SHIPMENT` + 팩 등록(`base` 로 코어 종류에 귀속). **`lot_genealogy` 에 쓰는 곳은 이 모듈뿐이다.**
관계 상수 `lineage.INPUT`(투입) · `PRODUCE`(생산) · `SPLIT`(분할) · `MERGE`(합병) · `SHIP`(출하). 팩 관계는 `lineage.relation(name) -> Relation(name, base)`.
상태 `IN_STOCK`(재고) · `CONSUMED`(소진) · `SHIPPED`(출하) — `v_lot_state` 뷰. 방향 `FORWARD` · `BACKWARD`.

```python
# 쓰기 — 전부 conn.tx() 의 커서를 받는다. 검증 실패는 422
lineage.link(cur, parent_id, child_id, relation, *, by, qty=None) -> int            # 화살표 한 줄. genealogy_id. 자기 참조 · 순환 · 모르는 relation 422
lineage.assert_usable(cur, lot_ids) -> None                                         # PRODUCT 는 재고, MATERIAL 은 합격(또는 조건부)이어야 한다
lineage.split(cur, *, parent_id, count, by, qtys=None, relation=SPLIT, kind=None, process_id=None, equipment_id=None, attrs=None, user=None) -> list[dict]   # 1 → N (N ≥ 2 · D-503)
lineage.merge(cur, *, parent_ids, by, qty=None, relation=MERGE, kind=None, process_id=None, equipment_id=None, attrs=None, user=None) -> dict                 # N → 1 (코어 합병 N ≥ 2 · 팩 합병 계열 N ≥ 1 · D-503)
lineage.ship(cur, *, shipment_id, lot_id, by, user=None) -> int                      # F-SHP-05 (개발3 이 부른다). 출하 LOT 이 없으면 만든다(LOT_SHIPMENT 채번). 이미 출하 · 소진 · 불합격 422
lineage.unship(cur, *, shipment_id, lot_id, by, user=None) -> int                    # F-SHP-06 — 출하 화살표 삭제. 등록 상태의 출하만
lineage.consume_material(cur, *, work_result_id, material_lot_id, qty, by, unit=None) -> int    # F-POP-06 투입 스캔 → pop_input (계보는 종료 때) + 원재료면 mat_stock* 소비
lineage.cancel_consume(cur, *, input_id, by) -> int                                  # F-POP-07 — 종료 전만 · 재고 되돌림
lineage.make_material_lot(cur, *, item_id, qty, unit, by, partner_id=None, lot_no=None, made_at=None, attrs=None, insp_status="미검사", user=None) -> dict   # F-MAT-01 · 이관(lot_no 지정)
lineage.make_product_lot(cur, *, work_result_id, by, kind="PRODUCT", qty=None, unit=None, attrs=None, parent_id=None, user=None) -> dict   # parent_id 가 있으면 `생산` 1:1
lineage.retag(cur, lot_id, kind, *, by=None) -> dict                                 # 팩 kind 로 바꾼다 (pack-contract.md §5). kind_base 는 등록된 base
lineage.shipment_lot(cur, shipment_id) -> dict | None                                # 출하 헤더의 출하 LOT 행 (읽기)
# `user` 는 라우터의 rbac.User — validate_lot · after_save_lot · on_lot_created 훅에 넘긴다(없으면 None). `by` 는 login_id

# 읽기 — 어떤 테이블에도 쓰지 않는다
lineage.resolve(no) -> Node | None            # 번호(스캔값) → LOT
lineage.search(text, limit=50) -> list[Node]  # F-TRC-03
lineage.state(lot_id) -> str                  # 재고 | 소진 | 출하
lineage.parents_of(lot_id) / children_of(lot_id) -> list[Edge]
lineage.trace_backward(lot_id) -> Trace       # F-TRC-02
lineage.trace_forward(lot_id) -> Trace        # F-TRC-01

Node(id, no, kind, kind_label, item, state, work_order_no, qty, unit, kind_base, item_id, item_code, insp_status, work_order_id, shipment_id, remain_qty, made_at)
Edge(genealogy_id, parent: Node, child: Node, relation, relation_base, qty, depth)
Trace(start: Node, direction, edges) · .nodes() · .by_kind(kind) · .materials() · .shipments() · .stock() · .products()
lineage.node(lot_id) · nodes(lot_ids) · genealogy_rows(lot_ids) · relation(name) -> Relation(name, base) · lot_kind(kind) -> LotKind(kind, base, label) · kind_label(kind)
# 읽기 함수는 전부 선택 인자 cur 를 받는다 — 같은 트랜잭션 안에서(테스트 되돌림) 읽을 때
```
- `trace_*` 는 **재귀 조회 하나**(`db-schema.md` §3.3). 깊이 · 분기를 가정하지 않고 경로를 저장하지 않는다. `Trace.edges` 는 중복 없이 출발점에서 가까운 순.
- 팩 relation 은 `base` 로 동작한다 — `splice`(base 합병)는 `merge(relation="splice")`, `슬리팅`(base 분할)은 `split(relation="슬리팅")`. 추적 · 상태 계산은 base 만 본다.
- 작업 종료 전에 LOT 을 만들지 않는다. `pop_input` 에 모였다가 `make_product_lot` 이 한 번에 계보로 옮긴다.

## 5. 출력 — `app.printing` (개발2)

```python
printing.render_print(request, template, data, *, screen_id) -> HTMLResponse   # templates/print/<template>.html. 인쇄용 레이아웃
printing.barcode_svg(text, *, height=40) -> str                                 # Code128 인라인 SVG. 외부 CDN 0
printing.label_for(lot_id, *, size="100x50") -> dict                           # 라벨 데이터 {lot_no kind kind_base kind_label item_code item_name spec qty unit made_at insp_status state work_order_no partner_name attrs[{label value}] size}. 없는 LOT 404
printing.shipment_label_for(shipment_id) -> dict                                # 출하 라벨 데이터 (D-601 — 개발3 이 render_print("label_shipment", …) 로)
class PrintAdapter: def send(self, job: PrintJob) -> PrintResult               # 기본 구현 = 브라우저 인쇄(sent=False). 팩 adapters.printing 모듈의 adapter() / ADAPTER 로 교체(E7) — printing.adapter()
# render_print 의 ctx 에는 data + barcode_svg(함수) + printed_at + printed_by 가 들어간다. 양식 4 의 data 키는 docs/design/README.md 「출력물 4종」 표 그대로(label_lot 은 {"labels": [label], "size", **label})
```
코어 양식 4 — `print/work_order.html` · `print/label_lot.html` · `print/label_shipment.html` · `print/document.html`(성적서). 팩은 같은 이름으로 덮어쓰거나 추가.

## 6. 수집 — `app.collect` (개발2)

```python
collect.CollectMessage(equip_code, ts, tags: dict, source="gateway", resend=False)
collect.CollectMessage.from_payload(dict) -> CollectMessage   # 본문 형식 오류 422
collect.receive(cur, msg) -> ReceiveResult(raw_id, duplicate, unknown_tags, saved)   # POST /ifc/collect 가 부른다. ifc_collect_raw 적재(멱등 · 같은 메시지는 duplicate=True) → eqp_collect 정제 → hook("on_collect"). int(result) = raw_id
#   모르는 설비: 거부 사유를 ifc_collect_raw 에 **자동 커밋으로** 남긴 뒤 422 (호출자 트랜잭션이 되돌아가도 기록이 남는다)
collect.latest(equip_id) -> dict | None          # EQP-01 가동 현황
collect.series(equip_id, tag, frm, to) -> list   # EQP-04 수집값 조회
collect.aggregate(equip_id, tag, frm, to, agg) -> float | None   # on_result_closed 가 측정값 collect 소스를 채울 때 (agg = last|avg|max|min)
```
- `equip_code` ↔ `bas_equipment` 1:1 검증. 태그 이름은 `bas_process_param.param_key`(source=collect) 와 같게 두면 실적 측정값으로 이어진다.
- 제어 명령은 없다. 쓰기 방향 엔드포인트를 만들지 않는다.

## 7. 집계 · ERP · 이관 (개발3)

```python
# app.stats — 집계 SQL 의 유일한 자리
stats.production(frm, to, *, by="day|item|process|equipment") -> list[dict]
stats.quality(frm, to, *, by="day|item|defect") -> list[dict]
stats.delivery(frm, to) -> list[dict]            # 납기 준수
stats.equipment(frm, to) -> list[dict]           # 가동률 · 고장
stats.measure_series(param_key, frm, to, *, by="day|work_order|equipment", agg="avg") -> list[dict]
stats.board() -> dict                            # KPI-01 현황판 한 화면 분. kpi_snapshot 이 있으면 그것, 없으면 실시간
stats.indicators() -> list[dict]                 # kpi_indicator + hook("kpi_extra") 병합
stats.snapshot(cur, date) -> int                 # 배치만 쓴다 (make kpi-snapshot). 화면은 안 부른다

# app.erp — 어댑터. 기본은 전부 501
class ErpAdapter:
    def push(self, kind: str, payload: dict) -> ErpResult      # 기본: raise http.undecided("D-02", "ERP 연계")
    def pull(self, kind: str, since: datetime) -> list[dict]
erp.enqueue(cur, kind, payload) -> int           # ifc_outbox 에 넣는다 (after_commit_* 훅이 쓴다)
erp.flush(limit=100) -> dict                     # make erp-flush. 어댑터가 501 이면 그대로 남긴다 — 조용한 폴백 0

# mescore.migrate
migrate.run(command, dir, *, dry_run=False) -> MigrateReport   # basics | orders | lots | history
```

## 8. HTTP 헬퍼 — `app.util.http`

```python
http.validation_error(message, fields=None) -> HTTPException(422)
http.not_found(message=None) -> HTTPException(404)
http.undecided(decision_id, what) -> HTTPException(501)
http.saved(request, message, data=None) -> Response       # 브라우저 303 + 알림 · JSON 200
class HookError(Exception): message · fields              # 팩 훅이 올린다 → 422 hook_rejected
```

## 9. 훅 호출 지점 — 코어 라우터가 **반드시** 이 자리에서 부른다 (`pack-contract.md` §5 의 서명)

| 훅 | 부르는 코어 코드 | 시점 |
|---|---|---|
| `validate_<table>(cur, row, user)` | 모든 코어 INSERT/UPDATE 라우터 (`bas_* ord_* job_* mat_* pop_* qua_* eqp_* shp_* lot`) | 저장 직전, 같은 `tx` |
| `on_order_created(cur, order, user)` | `routers/ord.py` F-ORD-01 | 수주 저장 후 |
| `on_work_order_created(cur, wo, user)` | `routers/job.py` F-JOB-01 | 지시 저장 후 |
| `on_work_order_closed(cur, wo, user)` | `routers/job.py` F-JOB-03 | 마감 후 |
| `on_result_started(cur, result, user)` | `routers/pop.py` F-POP-02 | 시작 저장 후 |
| `on_result_closed(cur, result, user)` | `routers/pop.py` F-POP-03 | 측정값 · 생산 LOT 생성 **후** (코어가 collect 측정값을 채운 다음) |
| `on_lot_created(cur, lot, user)` | `lineage.make_product_lot` · `split` · `merge` · `routers/mat.py` F-MAT-01 | LOT 행 생성 후 |
| `on_inspection_judged(cur, insp, user)` | `routers/qua.py` F-QUA-05 · `routers/mat.py` F-MAT-04 | 판정 저장 후 |
| `validate_shipment(cur, shipment, lots, user)` | `routers/shp.py` F-SHP-07 | 승인 직전 |
| `on_collect(cur, raw, user=None)` | `collect.receive` | 정제 후 |
| `after_commit_<event>(payload)` | `main.py` 미들웨어 — `tx` 커밋 뒤 큐에 쌓인 이벤트 | 트랜잭션 밖. 실패해도 응답은 성공, `ifc_outbox` 에 남는다 |
| `kpi_extra(frm, to) -> list[Metric]` | `stats.indicators` | 조회 시 |

훅이 없으면 no-op. 코어는 훅 안에서 무엇이 일어나는지 모른다 — 훅이 코어 테이블에 쓰려면 `write_scope` 에 있어야 한다.

## 10. 검사 도구 출력 형식 (전 도구 공통)

```
G-C01  메뉴          PASS   메뉴 12 · 공통 5 = core.yaml
G-C03  화면          FAIL   200: 56/56 · placeholder 51 (기대 0)
G-P01  팩 격리       PASS   [printfilm] 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · scope 밖 쓰기 0
G-P06  착수 시간     미검증  outputs/pack-timing.md 없음
```
`G-nn  항목  PASS|FAIL|WARN|BLOCKED|미검증  실측` — `tools/gate.py` 가 파싱해 판정표를 만든다. `BLOCKED` 는 `decisions.md` 에 `상태: 차단` 인 D-번호가 있을 때만.
