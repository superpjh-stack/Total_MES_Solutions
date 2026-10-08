# 디자인 — 토큰 · 관리자 Web 원형 · 공통 규칙 (디자이너1 · 2026-10-09)

> `docs/design/` 은 개발자가 웨이브 A R2 에서 Jinja 템플릿으로 **그대로 옮기는** 정적 원형이다. 서버 · CDN · 웹폰트 · JS 프레임워크 0 — 브라우저로 파일을 그대로 연다.
> 소유: `tokens.css` · `web/` · 이 파일의 §1~§7 = 디자이너1. `pop/` · `mobile/` + §POP · 모바일 = 디자이너2. `board/` · `print/` · `home/` + §현황판 · 출력물 · 메인 = 디자이너3. 남의 절은 고치지 않는다.
> 원형과 계약(`contracts/`)이 다르면 **계약이 맞다** — 원형은 계약에 없는 것을 정하지 않고 `미확정` 으로 둔다.

## 1. 파일 지도

| 경로 | 무엇 | 이식 대상 |
|---|---|---|
| `tokens.css` | 전 채널 공용 디자인 토큰 **97** (라이트) + 다크 재정의 32 + 인쇄 | `static/tokens.css` 로 복사 |
| `web/base.html` | 관리자 Web 기본 레이아웃 — 헤더 · 좌측 메뉴 12 · 본문 3블록 · 우측 계약 패널 · 토스트 · 422 알림 · 빈 상태 · 푸터 | `templates/base.html` + `static/web.css`(`<style>` 블록) + `static/app.js`(레이아웃 동작) |
| `web/components.html` | `ui` 매크로 하나 = 한 절. 상태(필수 · 오류 · 읽기 전용 · 비활성 · 0건)까지 | `templates/home/_macros.html` |
| `web/screens/*.html` 12 + 2 | 모듈별 대표 화면 원형(아래 표) + `login.html` · `error.html` | `templates/<모듈>/*.html` · `templates/login/` · `_error.html` |
| `pop/` · `mobile/` | 디자이너2 — §POP · 모바일 | |
| `board/` · `print/` · `home/` | 디자이너3 — §현황판 · 출력물 · 메인 | |

### 원형 화면 12 + 2

| 파일 | 화면 | 보여 주는 것 (다른 화면이 따라 할 규칙) |
|---|---|---|
| `screens/bas_items.html` | BAS-01 품목 | 마스터 4기능 한 벌: 조회 조건 · 목록 · 수정 폼(코드 readonly) · **팩 속성 묶음(`attrs_fields`)** · 행 액션(인라인 확인) · 303 토스트 |
| `screens/ord_orders.html` | ORD-01 수주 | 헤더 + 상세 N줄 폼(한 `tx`) · 상세 행 들여쓰기 · 취소 인라인 확인 · 완료 건은 버튼 비활성 + 이유 |
| `screens/job_work_orders.html` | JOB-01 작업지시 | 계획 대비 실적 막대 + 숫자 · 상태 배지 · 조건이 안 맞는 마감/취소는 비활성(title) · 소요 원재료 표 |
| `screens/mat_receipts.html` | MAT-01 입고 | **422 재렌더 상태** — 상단 알림(메시지 + `fields[]`) + 틀린 칸 강조 · LOT 상태 · 검사 판정 배지 |
| `screens/pop_result_web.html` | 생산실적 (Web 읽기) | 실적 목록 + 상세: **측정값 읽기 전용 표**(이탈 표시) · 투입 LOT · 생산 LOT · 바코드. 화면 ID 는 `미확정`(POP-02 는 POP 전용) |
| `screens/qua_inspections.html` | QUA-02 검사 결과 | 항목 · 기준 · 값 · 이탈 한 표 · 판정 3버튼 인라인 확인(불합격 → 불량코드 N줄 펼침) |
| `screens/eqp_status.html` | EQP-01 가동 현황 | 상태 4 타일 + 설비 표 · 수집 없는 칸 `미수집` · 상태 기록 폼(제어 아님) |
| `screens/shp_shipments.html` | SHP-01 출하 등록 | 헤더 등록/수정 + 스캔된 LOT 읽기 · 승인 후 수정 비활성 · SHP-02 로 넘김 |
| `screens/trc_backward.html` | TRC-02 역방향 추적 | **계보 트리**(연결선 · 가지 접기 · 노드마다 지시/실적/측정값/검사 링크) + 깊이순 화살표 표 · 쓰기 0 |
| `screens/kpi_summary.html` | KPI-02 집계 | 탭 = `?kind=` 링크 · 타일 + 표 · 비율은 막대 + 숫자 · 쓰기 0 |
| `screens/sys_permissions.html` | SYS-03 권한 표 | **12 × 4 = 48칸 편집 그리드** · 칸 = select + scopes 체크 · ADMIN 의 sys 고정 · 시드 누락 칸 `미확정` · 팩 행 예시 |
| `screens/ifc_collect.html` | IFC-01 수집 수신 현황 | 설비별 마지막 수신 · 건수 · 거부 · 모르는 태그 · 거부 메시지 표 |
| `screens/login.html` | CMN-01 로그인 | 401 재렌더 · 채널(device) 라디오 4 · 역할 × 채널 안내 |
| `screens/error.html` | CMN-03 오류 | 403 상태 + 상태코드 7 의 문구 · 다음 행동 표(개발용) |

더미 값은 전부 `(예시)`. 회사명 · 시스템명은 `{{ t("시스템명") }}` 자리표시. 금지어(`spec.md` §12) 0 — 대소문자 무시 검색으로 확인했다(`job` 모듈 코드는 계약의 식별자).

## 2. 디자인 원칙 — 제조 현장의 관리 화면

1. **표가 주인공.** 한 화면의 중심은 `grid` 다. 카드 · 타일은 표의 보조(최대 6개). 그래프는 표 안의 막대 하나까지 — 차트 라이브러리 0.
2. **정보 밀도.** 본문 13px · 표 12px · 행 높이 28px. 여백은 기능적으로(블록 사이 12px · 패널 안 12/16px). 장식 아이콘 · 둥근 카드 남발 · 그라데이션 없음.
3. **숫자는 오른쪽 · 고정폭.** `td.num` + `font-variant-numeric: tabular-nums`. 천 단위 쉼표. 단위는 열 머리나 칸 오른쪽 작은 글자.
4. **상태색 의미 고정.** 정상 = 초록 · 경고 = 호박 · 오류 = 빨강 · 정보 = 파랑 · 중립 = 회색. LOT 재고 = 청록 · 소진 = 회색 · 출하 = 남색. 판정 합격/불합격/조건부/미검사 와 설비 가동/정지/점검/고장 은 상태 4종의 별칭(§3). 화면마다 다르게 쓰지 않는다. 강조 색상은 하나(`--c-accent`)이고 팩이 바꿀 수 있다.
5. **색만으로 말하지 않는다.** 배지에는 글자, 막대에는 숫자, 범위 이탈에는 "이탈", 권한 칸에는 select 글자. 다크 테마 · 흑백 인쇄에서도 뜻이 남는다.
6. **한 화면 한 작업.** 조회 조건 → 표 → 쓰기 폼/버튼 순서. 탭은 서버 링크 4개까지. 모달 · 확인 다이얼로그 · 브라우저 `confirm()` 은 쓰지 않는다 — 되돌릴 수 없는 동작은 **인라인 확인**(`details.confirm`).
7. **지어내지 않는다.** 데이터 없음 = `미수집`, 정하지 않음 = `미확정 (D-nn)`. 빈 표 · 0 · 기본값을 그려 넣지 않는다.
8. **쓰기 버튼은 안내지 보안이 아니다.** 권한 없으면 비활성 + 이유, 조건이 안 맞으면 비활성 + 이유(title). 서버가 403/422 로 막는다.
9. **오류는 그 자리에.** 422 는 폼 위 알림 + 틀린 칸 강조(입력값 유지). 스캔 진입 422 는 그 화면 재렌더. 오류 화면은 그 밖의 GET 만.
10. **폭 1280 기준 · 1024 보장.** 1180 아래에서 계약 패널이 접히고 메뉴가 좁아진다. 860 아래는 한 단(본문 먼저). 표는 패널 안에서만 가로로 넘친다.

## 3. 토큰 (`tokens.css`) 사용법

- 모든 채널 파일은 `var(--…)` 만 쓴다. 색상값 직접 기입은 바코드 `fill:#000`(인쇄) 하나만 예외.
- 라이트가 기본. 다크는 `@media (prefers-color-scheme: dark)` 에서 **같은 이름**을 다시 정의한다(`:root[data-theme="light"]` 로 강제 라이트, `:root[data-theme="dark"]` 로 강제 다크 — 현황판 야간 전환이 이것을 쓴다). 인쇄는 `@media print` 가 색을 걷는다.
- 이름 규칙: `--c-*` 색 · `--fs-*` 글자 · `--sp-*` 간격 · `--r-*` 모서리 · `--sh-*` 그림자 · `--w-/--h-/--z-*` 치수 · `--touch-*` 터치. 업종어 · 회사명 없음.

| 묶음 | 토큰 | 수 |
|---|---|---|
| 글꼴 | `--font-sans`(시스템 한글 스택) · `--font-mono` | 2 |
| 글자 크기 · 행간 | Web `--fs-xs~2xl` 6 + `--lh-*` 2 · POP `--fs-pop-*` 8 · 모바일 `--fs-mobile-*` 2 · 현황판 `--fs-board-*` 3 | 21 |
| 터치 | `--touch-min`(모바일 48) · `--touch-min-pop` = `--touch-pop`(56) · `--touch-pop-choice`(64) · `--touch-pop-primary`(80) · `--touch-pop-scan`(72) · `--touch-mobile-tab`(56) | 7 |
| 간격 | `--sp-1~7` (4 · 8 · 12 · 16 · 24 · 32 · 48) | 7 |
| 테두리 · 모서리 · 그림자 | `--bw` `--bw-strong` · `--r-sm/md/lg` · `--sh-1/2` · `--focus-ring` | 8 |
| 레이아웃 | `--w-page`(1280) `--w-side`(212) `--w-side-min`(176) `--w-desc`(272) `--w-mobile`(390) · `--h-hdr`(44) · `--z-hdr/side/toast` | 9 |
| 색 — 바탕 · 표면 · 선 · 글자 · 헤더 | `--c-bg` `--c-surface(-2,-3)` `--c-line(-strong)` `--c-ink(-2,-3,-inverse)` `--c-head(-ink,-ink-2)` | 13 |
| 색 — 강조 · 포커스 · 링크 | `--c-accent(-hover,-ink,-tint)` · `--c-focus` · `--c-focus-pop` · `--c-link` | 7 |
| 색 — 상태 4 + 중립 | `--c-ok/warn/err/info/neutral` 각 `-bg` `-line` | 15 |
| 색 — LOT 상태 3 | `--c-lot-stock/consumed/shipped` 각 `-bg` | 6 |
| 색 — 판정 4 · 설비 4 (별칭) | `--c-pass/fail/cond/none` · `--c-eq-run/stop/check/fault` 각 `-bg` | 16 |
| 색 — 미확정 · 미수집 · 이탈 · 인쇄 | `--c-undecided(-bg,-line)` `--c-empty` `--c-deviated(-bg)` `--c-print-*` 3 | 9 |
| **합** | | **97** (+ 다크 재정의 32) |

상태색 의미 — 고정표:

| 뜻 | 토큰 | 쓰는 곳 |
|---|---|---|
| 정상 · 완료 · 합격 · 가동 · 사용 | `--c-ok` | 배지 `badge-ok/pass/run` · 토스트 왼쪽 띠 · 양품률 막대 |
| 경고 · 조건부 · 범위 이탈 · 조치 중 | `--c-warn` | `badge-warn/cond` · `.deviated` · 타일 `.warn` |
| 오류 · 불합격 · 고장 · 발생 | `--c-err` | `badge-err/fail/fault` · 422 알림 · 필수 `*` · `.btn-err` |
| 정보 · 진행 · 등록 · 점검 | `--c-info` | `badge-info/check` |
| 중립 · 대기 · 취소 · 정지 · 미사용 · 소진 | `--c-neutral` | `badge-neutral/stop/consumed` · 흐린 행 |
| 재고 / 출하 (LOT) | `--c-lot-stock` / `--c-lot-shipped` | `badge-stock` / `badge-shipped` |
| 미확정 · 팩 · 고정 · 개발용 | `--c-undecided` | `.undecided` · `.tag` · 권한 표 빈 칸 |

디자이너2 요청 3건 반영(02:14): `--c-focus-pop`(노랑) 추가 · `--fs-pop-base` 20 · `--fs-mobile-base` 16 + `--fs-mobile-no` 15. 터치는 채널별로 나눴다 — `--touch-min` 48 은 **모바일** 최소, POP 최소는 **`--touch-min-pop` = `--touch-pop` = 56**(선택 64 · 주 버튼 80 · 스캔칸 72). `pop.css` 는 `--touch-min` 대신 `--touch-min-pop` 을 읽는다. `pop.css` 의 `#ffd600` 직접 기입은 `var(--c-focus-pop)` 로 바꿀 수 있다.

## 4. 레이아웃 블록 → Jinja 블록

`web/base.html` 의 `<!-- {% block … %} -->` 주석이 그 자리다. 주석을 풀면 템플릿이 된다.

| 원형(정적) | `templates/base.html` | 채우는 쪽 |
|---|---|---|
| `<title>…</title>` | `{{ screen_name }} · {{ t("시스템명") }}` | `templating.render` 가 `screen_id` 로 |
| `<body class="ch-web" data-screen>` | `class="ch-{{ device }}"` | 채널은 세션의 `device` |
| `header.hdr` 의 브랜드 · crumb · 사용자 · 역할 · 채널 · 로그아웃 | `{{ t("시스템명") }}` · `{{ menu_name }} › {{ screen_name }} <code>{{ screen_id }}</code>` · `{{ user.user_name }} <em>{{ user.role_name }}</em>` · `{% if user %}` 폼 | `rbac.current_user` |
| `nav.side` 의 `.mg` 12 · `li a.cur` | `{% for m in nav.MENUS %}` … `{% for s in m.screens %}` · `.on` = `m.code == active_menu` · `.cur` = `s.screen_id == screen_id` · `href="{{ s.path }}"` | `nav` (팩 `hide` · `rename` · `order` 반영됨). POP 전용 화면의 `<i class="ch">` 는 `s.channels` 로 |
| `main` 안 `<!-- {% block search %} -->` … | `{% block search %}{% endblock %}` — 비우면 패널을 그리지 않는다 | 개발자 |
| `section.panel.grid-panel` | `{% block grid %}{% endblock %}` | 개발자 (`ui.grid`) |
| `section.panel#form` / `section.actions` | `{% block actions %}{% endblock %}` | 개발자 (`ui.write_button`) |
| 본문 통째로 (권한 표 · 추적 · 카탈로그처럼 3블록이 안 맞을 때) | `{% block body %}` | 개발자 |
| `div.alert` (422 목록) | `{% if flash and flash.kind == 'error' %}` — `flash.message` + `{% for f in flash.fields %}` `f.label` `f.name` `f.reason` | `http.saved` / 422 핸들러가 세션 flash 에 |
| `div.toast` (303 뒤 1회) | `{% if flash and flash.kind == 'ok' %}` · `app.js` 가 8초 뒤 닫는다 | 〃 |
| `aside.desc` (계약 패널) | `{% if settings.show_contract_panel %}` · `{% for f in functions %}` `f.id` `f.name` `f.kind` · `.off` = `not user.can(f.id)` | `contracts.functions_of(screen_id)` |
| `footer.ftr` 갱신 시각 | `{{ now }}` · `{{ settings.session_idle_label }}` · `{{ core_version }}` | `templating` |
| `<style>` | `static/web.css` 로 빼서 `<link>` (파일마다 복사하지 않는다) | 아키텍트 |
| `<script>` | `static/app.js` 에 합친다. **원형 전용 블록("정적 파일이라 폼을 보내지 않는다")은 지운다** | 아키텍트 |

## 5. 컴포넌트 → `ui` 매크로 · 클래스

| 매크로 (`interfaces.md` §2) | 원형 절 (`components.html`) | 마크업 요점 |
|---|---|---|
| `ui.grid(columns, rows, empty)` | #grid | `table.grid` · `thead th[aria-sort]` · `td.num` `td.act` `td.wrap` · `tr.sel/.dim/.group/.dtl` · 0건 `td.empty > b` · `nav.pager` |
| `ui.field(label, name, value, type, required, readonly, step)` | #field | `label.f > span(라벨 + em.req + small.hint) + input/textarea + i.unit + small.reason` · 오류 `label.f.err` + `aria-invalid` |
| `ui.select(label, name, options, value, required, blank)` | #select | `label.f > span + select` · 긴 목록은 코드칸 + "찾기"(CMN-05 팝업) |
| `ui.scan_box(action, name, label, hidden, button)` | #scan_box | `form.scan-box` · `input[data-scan]` 하나 · call 블록 칸 · POP 확대는 디자이너2 |
| `ui.write_button(label, allowed, form, kind)` | #write_button | `button.btn.btn-primary` · 불가 = `disabled title="…"` + `span.why` |
| `ui.print_button(label)` | #print_button | `button.btn.no-print` `onclick="window.print()"` |
| `ui.undecided(decision, what)` | #undecided | `span.undecided` "미확정 (D-nn)" |
| `ui.notes(items)` | #notes | `ul.notes` |
| `ui.attrs_fields(table)` | #attrs_fields | `fieldset.attrs > legend "업종 속성" + div.form-grid.cols` · 이름 `attrs[key]` · 선언 없으면 안 그린다 |
| `ui.measure_fields(process_id, values, readonly)` (개발2) | #measure_fields | Web 읽기 전용 = `table.grid.compact` 항목·값·단위·하한·상한·수집원·판정 · 이탈 `span.deviated` · 입력 폼은 디자이너2 |
| — 상태 배지 | #badge | `span.badge.badge-{ok,warn,err,info,neutral,stock,consumed,shipped,pass,fail,cond,none,run,stop,check,fault,kind}` · `i.dot` · `span.tag` |
| — 바코드 | #barcode | `span.barcode > svg` + `span.bc-text` (`printing.barcode_svg`) |
| — 탭 | #tabs | `nav.tabs > a[aria-current="page"]` (링크) |
| — 인라인 확인 | #confirm | `details.confirm > summary.btn + div.confirm-box(.static) > span + form>button.btn-err + button[data-close-details]` |
| — 알림 | #alerts | `div.toast(.warn/.err)[data-auto]` · `div.alert(.warn/.info) > strong + ul.fields` |
| — 빈 상태 | #empty | `td.empty` · `td.muted` "미수집" · `p.empty-inline` |
| — 키-값 · 타일 · 트리 | #kv | `dl.kv` · `div.tiles > div.tile(.warn/.err) > .l .v .s` · `ul.tree > li > details > summary > span.node(.start) > .rel .no .qty .links` |

## 6. 접근성

- **키보드만으로 끝난다.** 메뉴 묶음 · 계약 패널 · 토스트 닫기 · 인라인 확인이 전부 `button`/`summary`(Enter · Space). 링크가 할 일은 `a`, 동작은 `button` — `div onclick` 없음.
- **포커스가 보인다.** `:focus-visible` 에 2px 링(`--focus-ring`). 입력칸은 테두리 강조 색상 + 링. POP 스캔칸은 `--c-focus-pop`(노랑).
- **색만으로 구분하지 않는다** (§2-5). 배지 글자 · 막대 옆 숫자 · "이탈" 표기 · select 글자.
- **대비.** 본문 `--c-ink`/`--c-surface` ≥ 12:1, 보조 글자 `--c-ink-2` ≥ 5:1, 상태색 글자는 각 `-bg` 위에서 ≥ 4.5:1(라이트 · 다크 모두). 자리표시 `--c-ink-3` 는 글자로만 쓰지 않는다(라벨은 따로).
- **표 머리 · 역할.** `th[scope]` · `th[aria-sort]` · 정렬 글리프는 CSS `::after`(스크린리더는 aria-sort 로 듣는다). 알림 `role="alert"`(422) / `role="status"`(토스트).
- **필수 표시** `<em class="req" aria-label="필수">*</em>` + `required`. 오류 칸 `aria-invalid="true"` + 바로 아래 사유.
- **크기.** Web 최소 클릭 높이 24px(행 액션) · 30px(버튼 · 입력). 터치 채널은 §POP · 모바일의 56/48.
- **움직임 0.** 애니메이션 · 자동 이동 없음. 토스트만 8초 뒤 사라진다(닫기 버튼 있음).

## 7. Jinja 이식 때 주의 5

1. **메뉴 · 경로를 글자로 다시 적지 않는다.** 원형의 `href="/bas/items"` · 메뉴 이름은 보기용이다. 템플릿은 `nav.MENUS` · `s.path` · `nav.path_of()` 를 돈다 — 팩 `hide/rename/order` 가 여기서만 반영된다.
2. **원형 전용 조각을 지운다.** `app.js` 의 "정적 파일이라 폼을 보내지 않는다" 블록 · `body[data-prototype]` · 더미 행 · 계약 패널의 "이 원형의 상태" 절. 남기면 폼이 서버로 가지 않는다(`grep data-prototype templates/` = 0).
3. **422 는 두 길이다.** 폼 POST → 303 + flash(알림 + `fields[]`) 로 `div.alert` 를 그리고 `fields[].name` 으로 그 칸에 `.err` 를 붙인다(입력값 유지). 스캔 진입 GET `?no=` → 그 화면을 **422 상태코드**로 재렌더(`templating.render(..., status_code=422)`) + `data-scan` 포커스. 오류 화면(`_error.html`)으로 보내지 않는다.
4. **`confirm()` · 모달 금지.** 삭제 · 취소 · 마감 · 판정 · 승인은 `details.confirm` 패턴(폼 POST 가 안에 있다). `app.js` 에 `window.confirm` 이 있으면 결함.
5. **`attrs_fields` · `measure_fields` 는 자리만 둔다.** `<!-- {{ ui.attrs_fields("bas_item") }} -->` 자리에 매크로 호출 하나 — 원형의 "업종 속성" 예시 칸을 손으로 옮기지 않는다(선언이 없으면 묶음이 통째로 안 그려져야 한다). 측정값 표/폼도 `bas_process_param` 행에서만 나온다(G-C24).

그 밖: 사용자 문구는 전부 `{{ t("…") }}` 를 거친다(원형은 시스템명만 자리표시) · `<style>` 은 `static/web.css` 하나로(파일마다 복사하지 않는다) · POP 전용 화면(POP-01~04)을 Web 메뉴에 그릴지는 `nav.channel_allowed` 로 정한다(원형은 흐린 "POP" 표식) · `pop_result_web.html` 의 화면 ID · 경로는 계약에 없다 — 개발2 · 아키텍트가 `decisions.md` 에 정한다.

---

## 현황판 · 출력물 · 메인 (디자이너3 · 2026-10-09)

파일: `board/board.html` `board/board_states.html` · `print/work_order.html` `print/label_lot.html` `print/label_shipment.html` `print/document.html` `print/barcode_spec.md` · `home/home.html` `home/dashboard.html`.
전부 `../tokens.css`(디자이너1)만 읽는다 — 색상값 직접 지정 0(바코드 `fill:#000` 만 예외, `barcode_spec.md` §2). 외부 CDN · 웹폰트 · 차트 라이브러리 0. 더미는 `(예시)`.
개발자는 각 파일 맨 위 주석의 "데이터(가설)" 를 보고 Jinja 로 옮긴다. 키 이름이 코드와 달라지면 **코드가 맞다** — 이 절을 고친다.

### 1. 현황판 — `stats.board()` 키 ↔ `data-key` (**확정** · 개발3 2026-10-09 — D-602)

> 개발3 확정: 아래 표의 키 · 형 · 목록 상한이 `app/stats.py: board()` 그대로다(`tests/test_kpi_api.py` 가 키 집합을 고정한다). 덧붙인 해석 — `production.actual_qty` = good + defect · `by_hour` 는 실적이 있는 첫 시간부터 23시까지 · `top_defects.share` = 1위 수량 대비 % · `equipment.items[].last_received_at` 은 `eqp_collect.max(ts)` 의 `HH:MM:SS` · `indicators[]` 는 `visible_yn=Y` 순서(seq) 6개 · 조건부는 합격에 세지 않는다(D-302). JSON 폴링(`Accept: application/json`)은 접근 로그를 남기지 않는다. 템플릿 `templates/kpi/board.html`(base.html 없이 · `body.ch-board`).

`GET /kpi/board?device=board` 첫 렌더는 서버가 채우고, `board_refresh_seconds`(기본 5)초마다 같은 경로를 `Accept: application/json` 으로 받아 `[data-key]` 글자만 바꾼다. **이식됨(A′)**: 폴링은 `static/board.js`(원형 스크립트에서 `[원형 전용]` 블록만 뺌) · 스타일은 `static/board.css` · 템플릿 `templates/kpi/board.html` 은 `base.html` · `app.js` 를 싣지 않는다(`app.js` 의 현황판 전체 새로고침과 겹치지 않는다 — 요청 1배). 응답은 `stats.board()` 그대로. `kpi_snapshot` 이 있으면 그것, 없으면 실시간(`source` 로 알린다).

| 응답 키 | 형 | 화면 자리(`data-key`) | 비고 |
|---|---|---|---|
| `today` | `YYYY-MM-DD` | 머리글 날짜 | |
| `source` | `실시간` \| `스냅샷 HH:MM` | 머리글 | `kpi_snapshot` 을 썼으면 스냅샷 시각 |
| `production.plan_qty` · `actual_qty` · `good_qty` · `defect_qty` · `unit` | number · str | 생산 대표 숫자 | 오늘 지시(`plan_date=today`)의 계획 합 · 종료 실적 합. 없으면 `null` → `미수집` |
| `production.achieve_rate` · `good_rate` | % number | 달성률 meter · 양품률 | `good_rate_target` = `kpi_indicator('production.good_rate').target_value`(없으면 `null` → `미확정`) |
| `production.by_hour[]` | `[{hour:"08", qty}]` | 시간대별 막대(SVG) | 0~23 중 실적 있는 시간부터. 빈 배열이면 막대 없음 |
| `quality.inspection_count` · `pass_count` · `fail_count` · `pass_rate` · `pass_rate_target` | | 품질 대표 숫자 | 오늘 판정(`judged_at`)된 검사. 조건부는 합격에 세지 않는다(미확정 — D-nn) |
| `quality.top_defects[]` | `[{defect_code, defect_name, qty, share}]` | 불량 상위 가로 막대 | `share` = 1위 대비 %. 최대 3 |
| `delivery.due_count` · `shipped_count` · `late_count` · `pending_count` · `on_time_rate` | | 납기 대표 숫자 | 오늘이 납기인 수주 상세 기준 |
| `delivery.late_orders[]` | `[{order_no, partner_name, item_name, due_date}]` | 지연 수주 표 | 납기 지남 · 미출하. 최대 2(품목은 생략) |
| `equipment.run` · `stop` · `check` · `fault` | number | 설비 상태 카드 4 | `eqp_run_log` 열린 구간 기준. `EQUIP_STATE` 코드 4 |
| `equipment.items[]` | `[{equip_code, equip_name, state, collect_yn, last_received_at}]` | 설비 표 | 수집 설비는 `collect.latest` 의 마지막 수신, 아니면 `null` → `미수집`. 최대 5 — 고장 · 정지 먼저 |
| `work_orders_count` · `work_orders[]` | `[{work_order_no, item_name, process_name, equipment_name, plan_qty, actual_qty, achieve_rate, status}]` | 진행 중 작업지시 표 | `status` 대기 · 진행. 진행 먼저. 최대 7(공정 · 설비 열은 벽걸이에서 생략) |
| `measure.measured_count` · `deviated_count` | number | 측정값 이탈 대표 숫자 | 오늘 `pop_measure` 전체 · `deviated=true` |
| `indicators[]` | `[{indicator_key, name, unit, value, target_value, status}]` | 지표 목록 | `stats.indicators()` 중 `visible_yn=Y`. `target_value` null → `미확정`. `status` good/warn/critical/null 은 서버가 계산(값 ≥ 목표 good · ≥ 95% warn · 그 밖 critical). 최대 6 |

화면 규칙: `null` → `미수집`(회색 · 보통 굵기), 목록 0건 → `미수집` 한 줄, 폴링 실패 → `html[data-state="stale"]` + "갱신 실패 HH:MM, 재시도 중"(마지막 값 유지 · 폴링 계속), 야간 → `html[data-theme="dark"]`(전환 조건 미확정). 상태색은 목표 대비 · 0 이 정상인 건수(지연 · 고장 · 이탈)에만. 조작 요소 0 — 링크 · 버튼 없음, `cursor:none`.

### 2. 출력물 4종 — 데이터 필드 (`printing.label_for` · `render_print` 의 `data` 와 맞춘다)

| 양식 | 호출 | 바코드 값 | 필드 |
|---|---|---|---|
| `print/work_order.html` 작업지시서 (A4 세로) | F-JOB-07 `render_print("work_order", data, screen_id="JOB-03")` | `wo.work_order_no` | `wo{work_order_no item_code item_name spec unit process_name equipment_code equipment_name plan_qty plan_date status plan_no order_no partner_name due_date bom_version note created_at created_by}` · `bom_rows[{seq item_code item_name required_qty unit lot_no}]`(`job_lot`) · `params[{seq label unit min_value max_value required_yn source}]`(`bas_process_param` 의 기록 빈칸 표 — `source=collect` 는 "자동 수집" 칸) · `printed_at printed_by` |
| `print/label_lot.html` LOT 라벨 (100×50 · 50×30mm) | F-MAT-07 · F-POP-08 `render_print("label_lot", printing.label_for(lot_id))` | `lot_no` | `lot_no kind kind_label item_code item_name spec qty unit made_at insp_status work_order_no partner_name attrs[{label value}]`(두 줄까지) · `size`(`100x50` 기본 \| `50x30`) — 템플릿이 `<body data-size>` 와 `@page{size}` 를 찍는다. `labels[]` 여러 장이면 `.label` 반복 = 페이지 하나씩 |
| `print/label_shipment.html` 출하 라벨 (100×50mm) | 경로 **미확정** — 가설 `GET /shp/shipments/{id}/label`(SHP-02 인쇄 버튼) | `shipment_no`(출하 LOT 번호 안은 미확정) | `shipment_no partner_code partner_name ship_date status approved_at approved_by lot_count total_qty unit order_no shipment_lot_no` |
| `print/document.html` 성적서 (A4 세로) | F-SHP-10 `render_print("document", data, screen_id="SHP-04")` | `doc.document_no` | `doc{document_no doc_type issued_at issued_by}` · **`snapshot`**(`shp_document.snapshot` 그대로 — DB 를 다시 읽지 않는다): `shipment{shipment_no partner_code partner_name ship_date order_no approved_at approved_by}` · `columns[{item_key label unit standard min_value max_value}]` · `lots[{lot_no item_code item_name qty unit inspection: null \| {insp_type inspected_at inspector judgement values{item_key:{value deviated item_judgement}}}}]` · `summary{lot_count passed failed conditional uninspected judgement}` |

공통: 화면에서는 `.no-print` 의 "인쇄" 버튼 하나(`ui.print_button`). 빈 값 `-`, 검사 없음 `미수집`. 범위 이탈은 `▲` + 굵게(색만으로 뜻을 주지 않는다). 팩은 같은 이름으로 양식을 덮어쓴다(E7) — 코어 양식은 중립어만.

### 3. 인쇄 여백 · 크기

| 양식 | `@page` | 여백 | 페이지 나눔 | 배경 |
|---|---|---|---|---|
| 작업지시서 | `A4 portrait` | `14mm 12mm` | `thead` 반복 · `tr` · 서명란 · 제목 뒤 나눔 금지 | `th` 배경 · 자동수집 칸 배경 제거 |
| 성적서 | `A4 portrait` | `14mm 12mm 16mm` | 같음 + 종합 판정 · 발행란 묶음 | 같음 |
| LOT 라벨 | `100mm 50mm` \| `50mm 30mm` | `0` (안쪽 여백 3mm/2mm 는 CSS — 절단 오차) | `.label` 마다 `page-break-after:always` | 없음 |
| 출하 라벨 | `100mm 50mm` | `0` (안쪽 3mm) | 같음 | `승인` 배지는 `print-color-adjust:exact` |

브라우저 인쇄 안내: 배율 100% · "페이지에 맞춤" 끔 · 머리글/바닥글 끔. 배율이 걸리면 quiet zone 이 줄어 스캔이 어려워진다.

### 4. 바코드 요약 (`print/barcode_spec.md`)

Code128 · 값 = 번호 글자 그대로(`A-Z 0-9 -` · 권장 ≤ 20자) · 인라인 SVG(`printing.barcode_svg`, `viewBox 0 0 {모듈} 100`, `preserveAspectRatio="none"`, `shape-rendering="crispEdges"`, `fill:#000` 고정, quiet zone 10 모듈 포함) · 높이 ≥ 8mm(50×30) / ≥ 12mm(그 밖) · 모듈 X ≥ 0.25mm(50×30 은 세트 B/C 자동 전환으로 0.19mm 까지) · 사람이 읽는 글자는 바코드 바로 아래 고정폭. ZPL 로 가면 SVG 대신 `^BC` + `^FD{값}`, 글꼴 · 좌표 환산은 드라이버(E7) — 기종 확정 전 `미확정`. 스캔 왕복 검증 10단계는 `barcode_spec.md` §5(QA3).

### 5. 메인 · 대시보드

- `home/home.html` CMN-02: `nav.MENUS` 순서(= 일하는 순서, 팩 `menus.order`)대로 카드 12. 카드 = 이름(`t()` · `rename` 자리) · 화면 수 · 오늘 건수 1 · 입력 역할 · 화면 링크. `data-level = rbac.cell(role, menu).level` — `없음` 이면 흐림 + 링크 없음, 팩 `hide` 면 카드 없음. 오늘 건수 출처(가설)는 파일 주석.
- `home/dashboard.html` CMN-04: 역할별 판 4(관리자 · 생산 · 품질 · 현장) 중 서버는 하나만. 공통 숫자 4(`today.work_orders results inspections_pending shipments_pending`) + 역할별 강조 1 + 바로가기(권한 칸 조회 이상만). 읽기만 — 쓰기 0, `kpi` 집계를 읽을 뿐.
- 현황판용 오류 상태는 `board/board_states.html` 3번(갱신 실패)이다. 오류 화면 `error.html` 은 디자이너1.

<!-- 아래 절은 디자이너2 소유("## POP · 모바일"). 디자이너1 이 README 본문을 쓸 때 이 절을 지우지 말고 그대로 둔다 — 파일을 통째로 다시 쓰면 다른 디자이너의 절이 사라진다(02:11 · 02:12 에 한 번 일어났다). -->

## POP · 모바일 (디자이너2 · 2026-10-09)

담당 디자이너2. 파일은 `docs/design/pop/` · `docs/design/mobile/` 뿐이다. 전부 정적 HTML — 서버 · CDN · 웹폰트 · 프레임워크 0, 브라우저로 파일을 그대로 연다.
색은 전부 `../tokens.css`(디자이너1)의 `--c-*` 를 쓴다 — `pop/pop.css` · `mobile/mobile.css` 맨 위 「토큰 매핑」 블록이 토큰을 채널 이름(`--fg --bg --line --primary --ok --err --warn --off`)으로 받고, 채널 **치수**만 거기서 정한다. 다크 테마는 토큰이 바뀌면 따라온다.
**디자이너1 에게 요청(토큰 3건)**: ① `--c-focus`(#8fb4e3)는 POP 에서 너무 옅다 — `--c-focus-pop`(노랑 계열) 추가 요청, 그때까지 `pop.css` 가 `#ffd600` 을 직접 쓴다. ② `--fs-pop-base 17` · `--touch-min 48` 은 이 채널 기준(글자 20 · 터치 56 · 주 버튼 80 · 스캔칸 72)보다 작다 — `--fs-pop-base: 20px` · `--touch-pop: 56px` 로 올리거나 POP 전용 이름 추가. ③ `--fs-mobile-base 15` → 16 (번호만 15 고정폭).

### 1. 파일

| 파일 | 화면 | 기능 | 보여 주는 것 |
|---|---|---|---|
| `pop/pop.css` · `pop/pop.js` | 공용 | — | POP 스타일(터치 확대) · 시연 스크립트(실제 구현은 `static/app.js` 하나) |
| `pop/base_pop.html` | base | — | 레이아웃 규칙 7 · 배지 · 버튼 모음 · 503 띠 |
| `pop/pop_work.html` | POP-01 | F-POP-01 | 오늘 지시 카드 + 지시 번호 스캔 |
| `pop/pop_result_start.html` | POP-02 | F-POP-02 | 지시 → 설비 · 작업자 터치 선택 → 시작 |
| `pop/pop_result_end.html` | POP-02 | F-POP-03 | 양품 · 불량 + **측정값 자동 폼 8칸(모든 상태)** + 생산 LOT · 라벨 안내 |
| `pop/pop_stop_scrap.html` | POP-02 | F-POP-04 · 05 | 정지 중 / 정지 시작(사유 버튼) · 폐기(수량 · 불량코드 버튼) |
| `pop/pop_inputs.html` | POP-03 | F-POP-06 · 07 | LOT 스캔 + 투입량 · 이력 · 취소 · **불합격 LOT 422 재렌더 상태** · 422 사유 5 |
| `pop/pop_labels.html` | POP-04 | F-POP-08 | 출력할 LOT 고르기 · 출력 안내(양식은 디자이너3 `print/label_lot`) |
| `pop/mat_receipts_pop.html` | MAT-01 | F-MAT-01 · 03 | 입고 1건 폼 · 오늘 입고 |
| `pop/mat_inspections_pop.html` | MAT-02 | F-MAT-04 · 05 | LOT 스캔 → 검사 항목 → 판정 3버튼 · 미검사 LOT |
| `pop/shp_scan.html` | SHP-02 | F-SHP-05 · 06 · 07 | 출하 선택 → LOT 스캔 목록 → 승인(관리자만 활성) · 422 사유 5 |
| `pop/eqp_status_pop.html` | EQP-01 · 02 · 03 | F-EQP-01~03 · 05 · 06 | 설비 카드 + **상태 기록**(제어 아님) · 점검 · 고장 · 조치 |
| `pop/qua_inspections_pop.html` | QUA-02 | F-QUA-04 · 05 | LOT 스캔 → 항목 값(이탈 표시) → 판정 · 불합격 불량 줄 |
| `pop/scan_states.html` | 참고 | — | 스캔칸 상태 7: 대기 · 입력 중 · 성공 · 422 · 503 · 알림 중 스캔 · 스캔칸 없는 화면 |
| `mobile/mobile.css` | 공용 | — | 390px 틀 · 하단 탭 · 카드 · 접기(details) · JS 0 |
| `mobile/base_mobile.html` | base | — | 레이아웃 규칙 7 · 구성 요소 |
| `mobile/trc_backward_m.html` | TRC-02 | F-TRC-02 | 계보를 세로 단계로 · 깊이 · 분기 접기 · 원재료 LOT 전부 |
| `mobile/trc_search_m.html` | TRC-03 | F-TRC-03 | 결과 카드 → 정/역추적 |
| `mobile/job_status_m.html` | JOB-02 | F-JOB-06 | 지시 카드 · 계획 대비 막대 |
| `mobile/mat_stock_m.html` | MAT-04 | F-MAT-08 | 품목 요약 줄 → LOT 잔량 접기 |
| `mobile/shp_status_m.html` | SHP-03 | F-SHP-08 | 출하 카드 · 납기 대비 · LOT 접기 |
| `mobile/kpi_summary_m.html` | KPI-02 | F-KPI-02~05 | 집계 종류 칩 · stat 타일 · **표 → 카드 접기 규칙** |
| `mobile/ord_delivery_calendar_m.html` | ORD-03 | F-ORD-06 | 월 → 주 접기(오늘 주만 열림) |

더미 값은 전부 `(예시)`. 글자 · 버튼 · 문구는 Jinja 로 옮길 때 `{{ t("…") }}` 를 거친다. 각 파일 머리 주석에 "Jinja 로 옮길 때" 가 있다.

### 2. POP 동작 사양 — `static/app.js` 가 구현한다 (S-01 ~ S-14)

`pop/pop.js` 가 같은 번호로 시연한다. 엘컴화인 `app.js` 의 동작 규칙을 일반화했고, 거기서 템플릿 쪽에 나뉘어 있던 "닫은 뒤 포커스 복귀" 를 app.js 하나로 합쳤다.

| 번호 | 사양 | 판정 방법 |
|---|---|---|
| **S-01** | `data-scan` 은 화면에 **하나**. 둘 이상이면 콘솔 오류(조용히 첫 것을 고르지 않는다). 스캔칸이 없는 화면(관리자 Web · 모바일)에서는 S-02~S-08 · S-10~S-12 가 동작하지 않고 알림의 「확인」이 포커스를 갖는다 | `document.querySelectorAll('[data-scan]').length === 1` |
| **S-02** | 화면이 열리면 스캔칸이 포커스를 갖는다(`autofocus` + 스크립트 둘 다) | 열자마자 글자를 치면 스캔칸에 들어간다 |
| **S-03** | 화면 아무 곳이나 눌렀다 놓으면 포커스가 스캔칸으로 돌아온다. **단** 다른 입력칸 · 선택칸 · 버튼 · 링크를 쓰는 중(`activeElement` 가 그것)에는 빼앗지 않는다 | 투입량 칸을 누르고 숫자를 칠 수 있다 · 빈 곳을 누르면 돌아온다 |
| **S-04** | 창이 다시 활성화되면(`window focus`) 스캔칸으로 | 다른 창 갔다 오면 바로 스캔된다 |
| **S-05** | 스캐너 = 키보드 입력 + Enter. **바코드 1회 = 요청 1회 = 1건.** 보내면 스캔칸을 비운다(서버가 다시 그리므로 저절로 빈다). 스캔칸 밖의 입력값(투입량 등)은 재렌더 때 서버가 직전 값으로 채운다 | 같은 LOT 두 번 스캔 = `pop_input` 2행 |
| **S-06** | 알림 팝업(`#popup-layer`)이 열려도 **포커스를 「확인」에 주지 않는다** — 스캔칸이 있으면 스캔칸이 갖는다 | 알림 띄운 채 글자를 치면 스캔칸에 들어간다 |
| **S-07** | 알림이 열린 채 **글자 키**(길이 1 · 공백 제외 · 수정키 없음)가 오면 알림을 닫고 그 글자는 스캔칸에 들어간다. **Enter**: 스캔칸에 글자가 있으면 전송(기본 동작), 빈 스캔칸이거나 포커스가 본문이면 닫기만. 「확인」 버튼 위 Enter 는 클릭, 다른 입력칸의 Enter 는 그 폼의 것 — 건드리지 않는다 | 알림 중 바코드 쏘기 → 알림 닫힘 + 전송 |
| **S-08** | 알림을 「확인」 · 바깥 누르기 · Esc · (빈 스캔칸) Enter 로 닫으면 포커스는 **스캔칸으로**(방금 누른 「확인」 이 포커스를 쥐고 있어도 `setTimeout 0` 뒤 돌려준다) | 닫은 직후 글자 치기 |
| **S-09** | 서버가 303 뒤에 실어 보낸 `#flash-data`(JSON: `title message fields[] kind`)를 읽어 알림으로 띄운다. `fields[].label — reason` 을 줄로. 파싱 실패는 콘솔 경고(화면은 멀쩡히 둔다) | 쓰기 성공 · 폼 POST 422 |
| **S-10** | 쓰기 성공은 본문의 결과 배너(`#scan-result.ok` · 28px 초록)로 1초 보이고 회색으로 가라앉는다. 팝업까지 띄울지는 화면이 정한다(스캔 반복 화면 — 투입 · 출하 스캔 — 은 배너만) | 배너 → 1초 → 회색 |
| **S-11** | 스캔 진입 GET `?no=` 의 없는 번호는 **그 화면이 422 로 다시 그려진다**(서버 — `api-contract.md` §2). app.js 는 `#scan-result.err`(`role=alert`)를 건드리지 않고 S-02 로 포커스만 잡는다. 폼 POST 의 422 는 303 + S-09 알림. 어느 쪽도 다음 스캔을 막지 않는다 | 없는 번호 스캔 → 빨간 배너 · 스캔칸 포커스 · URL 그대로 |
| **S-12** | 503(DB 끊김)은 서버가 POP 레이아웃의 오류 화면으로 그린다 — 빨간 띠 + 연결 「끊김」 + **스캔칸 `disabled`**. app.js 는 `disabled` 스캔칸에 포커스를 주지 않는다. 오프라인 큐 · 자동 재시도 없음(현황판과 다르다) | 띠 · 「다시 시도」 버튼만 |
| **S-13** | 시각 · 작업자 · 설비는 서버 렌더값. app.js 가 시계를 돌리지 않는다(초 단위 갱신 없음 — 낡은 화면을 새것처럼 보이지 않게) | 새로고침해야 바뀐다 |
| **S-14** | `data-demo` · `data-demo-popup` · `.demo` 는 **원형 전용** — 템플릿으로 옮길 때 지운다. 남아 있으면 폼이 서버로 가지 않는다 | `grep data-demo templates/` = 0 |

### 3. 측정값 자동 폼 — `ui.measure_fields(process_id, values=None)` 의 상태 표

`bas_process_param` 한 행 = 칸 하나. 칸을 손으로 만들지 않는다(G-C24). 원형: `pop/pop_result_end.html` 「측정값」 8칸.

| 상태 | `value_type` · 선언 | 칸 모양 | 저장 | 배지 |
|---|---|---|---|---|
| 빈 칸 · 필수 | number · `required_yn=Y` · min/max | `type=number inputmode=decimal step=any required` · 기준 「60 ~ 80」 줄 | 비우고 종료 → **422** 「필수 측정값이 비었습니다」 + `fields[label]` | 「필수」(빨강) |
| 범위 안 | number | 같음 | `value_num` · `deviated=false` | — |
| **범위 이탈** | number · 값이 min/max 밖 | 저장 뒤 조회 · 재렌더에서 칸 배경 주의색 | **422 아님** — 저장 + `deviated=true` | 「이탈」(주의색) |
| 선택 · 비움 | number · `required_yn=N` | placeholder 「비워도 된다」 | 행을 만들지 않는다 | — |
| 하한만 / 상한만 | min 또는 max 하나만 | 기준 「0.5 이상」 / 「12 이하」 | 한쪽만 검사 | 이탈 시 「이탈」 |
| 글자 | text | `type=text maxlength` · 단위 · 기준 없음 | `value_text` | — |
| 예/아니오 | bool | **2버튼**(radio) 예 · 아니오 — 체크박스가 아니다(「안 누름」 ≠ 「아니오」) | `value_num` 1/0 | 필수면 「필수」 |
| 선택지 | select · `choices jsonb` | 5개 이하 → 큰 버튼(radio) · 6개 이상 → `<select>`(56px) | `value_text` = 코드 | — |
| 수집 · 수신 중 | `source=collect` · `collect_tag` · `agg` | **읽기 전용** 「최근 수신 2.8 bar · 10:41」 · 「수집값 자동」 배지 · 기준 줄에 집계명 | 종료 때 코어가 구간(시작~종료 · 같은 설비)의 `eqp_collect` 대표값(`agg`)을 채운 뒤 `on_result_closed` | 「수집값 자동」 · 이탈이면 「이탈」 |
| 수집 · 미수신 | `source=collect` · 구간에 수신 0 | 읽기 전용 「미수집」 | `value_num NULL · source=collect` 행 — **필수여도 422 아님**(사람이 넣을 값이 아니다) | 「수집값 자동」 + 「미수집」 |
| `use_yn=N` | — | 칸을 그리지 않는다 | — | — |

칸 순서는 `seq`. 단위는 라벨 옆 회색(`unit`). 기준 줄은 min/max 가 둘 다 비면 없다. 입고검사(MAT-02) · 검사 결과(QUA-02)의 항목 칸도 같은 모양(`qua_insp_plan` 항목)으로 그려 사용자가 두 폼을 하나로 느끼게 한다.

### 4. 모바일 접힘 규칙

1. **폭 390px · 가로 넘침 0.** 모든 상자 `min-width:0`, 번호는 `overflow-wrap:anywhere`. 옆으로 미는 것은 필터 칩 줄 하나뿐.
2. **표를 쓰지 않는다 — 행 하나 = 카드 하나.** 첫 열(키) → 카드 제목, 상태 · 비율 열 → 제목 오른쪽 배지, 수치 열 → kv 두 열(라벨 84px · 고정폭 숫자), 열이 6개를 넘으면 뒤의 열은 `details` 「더 보기」, 합계 행 → 카드 위 stat 타일 2×2, 날짜 시계열 → `week-day` 줄(날짜 · 값 · 배지). 그래프 없음(막대 하나는 비율 1개에만).
3. **접기는 `details/summary`(JS 0).** 요약 줄 48px · 열림은 서버가 `open` 으로 정한다.
   - 추적(TRC-02): 깊이 1 펼침, 깊이 2 부터 접힘. 형제 3건 초과 시 그 단도 접힘(요약 줄에 건수). 「원재료 LOT 전부」 를 아래 따로(중복 제거 — `Trace.materials()`).
   - 재고(MAT-04): 품목 요약 줄(이름 · 현재고 · 부족 배지)만 보이고 LOT 은 접힘. 첫 품목(또는 검색어에 맞는 것)만 열림.
   - 출하(SHP-03): LOT 3건 초과면 접힘.
   - 납기 달력(ORD-03): 월 = 주 5~6개 `details`. 오늘이 든 주만 열림. 주 요약 = 기간 · 납기 건수 · 완료/지연 배지. 납기 없는 날은 줄 없음. 7열 격자는 쓰지 않는다.
4. **하단 탭 4** = 추적(TRC-01 · 02 · 03) · 현황(KPI-02 · SHP-03 · ORD-03) · 지시(JOB-02) · 재고(MAT-04). `channels.mobile` 밖 화면을 열면 403 — 탭 · 링크에 그 화면을 두지 않는다.
5. **상단 검색**은 어느 화면에서나 TRC-03 으로. 추적 화면에서는 `?no=` 로 바뀐다(없는 번호 → 같은 화면 422 + 빨간 배너).
6. **쓰기 0.** 버튼은 링크(조회 화면끼리)뿐. `data-scan` 없음 · 알림 팝업은 「확인」이 포커스.

### 5. 터치 크기 기준

| 요소 | POP | 모바일 |
|---|---|---|
| 기본 글자 | 20px (배지 16 · 안내 17) | 16px (번호 15 고정폭 · 배지 12) |
| 버튼 · 탭 · 선택 버튼 | **56px 이상** (선택 버튼 64) | 44~48px · 하단 탭 56 |
| 주 버튼(한 화면 하나) | **80px** · 26px 글자 · 가로 100% | — (쓰기 없음) |
| 스캔칸 | **72px** · 30px 고정폭 · 테두리 3px · 포커스 5px 노랑 | — |
| 결과 배너 · 알림 문장 | **28~30px** 굵게 | 16px 굵게 |
| 표 행 | 56px 이상 | 표 없음(카드) |
| 간격 · 여백 | 상자 사이 10~14px · 본문 좌우 16px | 좌우 16px · 카드 사이 8px |
| 대비 | 글자 `--c-ink` / `--c-surface` 바탕 · 상태는 **색 + 글자**(배지) — 색만으로 말하지 않는다 | 같음 |
| 선택 | 라디오를 큰 버튼으로(`.choice`) · 체크박스 없음 | — |

---

## 이식 요청 (디자이너3 · 웨이브 A′ · 2026-10-09)

이식한 파일: `templates/kpi/board.html` · `static/board.css` · `static/board.js`(새 파일) · `templates/print/{work_order,label_lot,label_shipment,document}.html` · `static/print.css`(새 파일) · `templates/home/main.html` · `templates/dashboard/index.html` · `templates/trc/{_cards,_trace,search}.html` · `templates/ifc/{collect,erp}.html` · `templates/kpi/{summary,indicators}.html`. 라우터가 넘기는 ctx 키 · 폼 name 은 바꾸지 않았다. 캡처 `outputs/design/{board,print,home,trc}/*.png`.

| # | 대상 | 요청 | 지금 상태 |
|---|---|---|---|
| 1 | 디자이너1 `static/style.css` | 토큰 §1 을 `static/tokens.css` 로 **분리**해 달라. 현황판(`kpi/board.html`)과 출력물 4종은 `base.html` 을 쓰지 않는 독립 문서라 `style.css` 전체(Web 레이아웃 · `.panel` · `table.grid` · `body.ch-board`)를 실을 수 없다 | `board.css` · `print.css` 맨 위에 `TEMP-TOKENS` 블록(필요한 토큰만 · 값은 `tokens.css` 와 같다)을 임시로 두었다. `tokens.css` 가 생기면 두 파일에서 그 블록을 지우고 `<link>` 한 줄을 넣는다 |
| 2 | 개발1 `routers/home.py: cards_for` | 카드의 "오늘 건수" `c.today` — 지금은 `None`(→ `미수집`). `stats` 의 공개 함수로 채워 달라(출처 가설은 `home/home.html` 머리 주석: bas 오늘 변경 · ord 오늘 납기 · job 오늘 지시 · mat 오늘 입고 · pop 오늘 실적 · qua 검사 대기 · eqp 고장 중 · shp 출하 대기 · kpi 측정값 이탈 · sys 오늘 로그인 · ifc 오늘 수신 거부). 집계 SQL 은 `stats` 에만 | 템플릿은 `c.today` 가 오면 그대로 보인다(숫자 · 0 도 보인다) |
| 3 | 아키텍트 · 개발3 `decisions.md` | 현황판 **야간(다크) 전환 조건** 미확정. 템플릿은 가설로 `?theme=dark` → `html[data-theme="dark"]` 를 찍는다(그 밖은 `light` 고정 · `prefers-color-scheme` 무시). 시각 고정 · 설정값 중 하나로 확정해 달라(D-nn) | `board_dark.png` 로 모양만 확인 |
| 4 | 개발3 `routers/dashboard.py` | 타일 링크 · 강조 링크는 템플릿이 `user.can_open` + `nav.channel_allowed` 로 판단한다(권한 없으면 링크 없는 타일). 역할별 판은 `user.role_code`(`ADMIN PROD QA FIELD`)로 고르고, 그 밖(팩 역할)은 생산 판 모양. 원형의 `recent[]`(최근 5건)는 ctx 에 없어 그리지 않았다 — 필요하면 키를 넘겨 달라 | — |
| 5 | 디자이너2 `static/mobile.css` | `trc/_trace.html` · `trc/search.html` · `kpi/summary.html` · `ifc/collect.html` 의 모바일 카드는 `m-sec · m-card · kv · links · fold · trace · t-node` 마크업 그대로다. `body.ch-mobile .m-only` 만 보이고 `.web-only`(트리 · 표)는 숨긴다(`trc/_cards.html: styles()`). 원형의 하단 탭 4 · `.m-top` 검색 틀은 `base.html` 몫이라 넣지 않았다 | `trc/backward_mobile.png` |
| 6 | 개발2 `printing.label_for` | 라벨 한 장의 `attrs[]` 두 줄 — 50×30 은 한 줄만 찍는다. 라벨 표시용 속성 선언이 없으면 빈 줄. 그대로 두면 된다(요청 아님 · 확인 사항) | — |
| 7 | 검증 | `make check-terms` 는 다른 담당 파일(`style.css` 강조색 · `job/status.html` 스크롤)의 금지어로 한때 FAIL 했다가 지금은 PASS. `pytest` 는 같은 DB 를 여러 담당이 동시에 써서 `test_trc_api`(쓰기 0 검사 — `shp_shipment` 건수가 중간에 늘었다) · `test_job_work_orders` · `test_measure`(`_measure.html` 개발2/디자이너2 동시 수정)가 흔들렸다. 내 파일만으로 돌리면 통과 — 커밋 전 단독 실행 결과는 보고서 | — |
