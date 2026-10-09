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
| POP 본문 (회전 4) | `{% block pop_body %}` — base 가 `main.pop-main` + 제목 줄 `.screen-head`(설비 `who_equip` · 시각 · 연결 · 뒤로) + 상단 탭으로 두른다. 비우면 search · grid · form · actions 를 POP 패널로 | 디자이너2 · 개발2 |
| 모바일 본문 (회전 4) | `{% block mobile_body %}` — base 가 `.m-frame` = `.m-top`(제목 · 사용자 · TRC-03 번호 검색) + `.m-main` + 하단 탭 4 `.m-tabs` 로 두른다. 비우면 search → `.m-filter` · grid → `.m-sec`. 모바일엔 `.hdr` `.side` `.desc` `.ftr` 가 없다 | 디자이너2 · 3 |
| 422 입력값 유지 (회전 4) | flash `values{name: 값}` 이 오면 `ui.field` · `ui.select` 가 그 칸을 되채운다(`with context` import · 비밀번호 · readonly · disabled 제외) | 아키텍트(`util/http.py` · `main._back_with_flash`) |
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
| `undecided` | str (`미확정 (D-602)` · 이미 `t()`) | 목표 칸 `data-empty` · 첫 렌더 빈 목표 | 회전 5 · DEF-QA2-003 — 목표 NULL 칸 문구. 템플릿은 이 값을 그대로 쓴다(없으면 같은 글자를 스스로 만든다) |
| `production.plan_qty` · `actual_qty` · `good_qty` · `defect_qty` · `unit` | number · str | 생산 대표 숫자 | 오늘 지시(`plan_date=today`)의 계획 합 · 종료 실적 합. 없으면 `null` → `미수집` |
| `production.achieve_rate` · `good_rate` | % number | 달성률 meter · 양품률 | `good_rate_target` = `kpi_indicator('production.good_rate').target_value`(없으면 `null` → `미확정 (D-602)` — G-C11 형식 · 회전 5) |
| `production.by_hour[]` | `[{hour:"08", qty}]` | 시간대별 막대(SVG) | 0~23 중 실적 있는 시간부터. 빈 배열이면 막대 없음 |
| `quality.inspection_count` · `pass_count` · `fail_count` · `pass_rate` · `pass_rate_target` | | 품질 대표 숫자 | 오늘 판정(`judged_at`)된 검사. 조건부는 합격에 세지 않는다(미확정 — D-nn) |
| `quality.top_defects[]` | `[{defect_code, defect_name, qty, share}]` | 불량 상위 가로 막대 | `share` = 1위 대비 %. 최대 3 |
| `delivery.due_count` · `shipped_count` · `late_count` · `pending_count` · `on_time_rate` | | 납기 대표 숫자 | 오늘이 납기인 수주 상세 기준 |
| `delivery.late_orders[]` | `[{order_no, partner_name, item_name, due_date}]` | 지연 수주 표 | 납기 지남 · 미출하. 최대 2(품목은 생략) |
| `equipment.run` · `stop` · `check` · `fault` | number | 설비 상태 카드 4 | `eqp_run_log` 열린 구간 기준. `EQUIP_STATE` 코드 4 |
| `equipment.items[]` | `[{equip_code, equip_name, state, collect_yn, last_received_at}]` | 설비 표 | 수집 설비는 `collect.latest` 의 마지막 수신, 아니면 `null` → `미수집`. 최대 5 — 고장 · 정지 먼저 |
| `work_orders_count` · `work_orders[]` | `[{work_order_no, item_name, process_name, equipment_name, plan_qty, actual_qty, achieve_rate, status}]` | 진행 중 작업지시 표 | `status` 대기 · 진행. 진행 먼저. 최대 7(공정 · 설비 열은 벽걸이에서 생략) |
| `measure.measured_count` · `deviated_count` | number | 측정값 이탈 대표 숫자 | 오늘 `pop_measure` 전체 · `deviated=true` |
| `indicators[]` | `[{indicator_key, name, unit, value, target_value, status}]` | 지표 목록 | `stats.indicators()` 중 `visible_yn=Y`. `target_value` null → `미확정 (D-602)`(`board.undecided` 가 오면 그 글자). `status` good/warn/critical/null 은 서버가 계산(값 ≥ 목표 good · ≥ 95% warn · 그 밖 critical). 최대 6 |

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

- `home/home.html` CMN-02: `nav.MENUS` 순서(= 일하는 순서, 팩 `menus.order`)대로 카드 12. 카드 = 이름(`t()` · `rename` 자리) · 화면 수 · 오늘 건수 1(라벨 `t(c.today_label)` · 출처 `title=c.today_source` — D-108) · 입력 역할 · 화면 링크. `data-level = rbac.cell(role, menu).level` — `없음` 이면 흐림 + 링크 없음, 팩 `hide` 면 카드 없음. 오늘 건수 출처(가설)는 파일 주석.
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
| **S-05** | 스캐너 = 키보드 입력 + Enter. **바코드 1회 = 요청 1회 = 1건.** 보내면 스캔칸을 비운다(서버가 다시 그리므로 저절로 빈다). 스캔칸 밖의 입력값(투입량 등)은 재렌더 때 서버가 직전 값으로 채운다 — **폼 POST 422 뒤에는 `flash.values` 가 직전 저장값보다 앞선다**(회전 7 · DEF-QA3-008). 스캔칸은 422 뒤에도 비운다 | 같은 LOT 두 번 스캔 = `pop_input` 2행 |
| **S-06** | 알림 팝업(`#popup-layer`)이 열려도 **포커스를 「확인」에 주지 않는다** — 스캔칸이 있으면 스캔칸이 갖는다 | 알림 띄운 채 글자를 치면 스캔칸에 들어간다 |
| **S-07** | 알림이 열린 채 **글자 키**(길이 1 · 공백 제외 · 수정키 없음)가 오면 알림을 닫고 그 글자는 스캔칸에 들어간다. **Enter**: 스캔칸에 글자가 있으면 전송(기본 동작), 빈 스캔칸이거나 포커스가 본문이면 닫기만. 「확인」 버튼 위 Enter 는 클릭, 다른 입력칸의 Enter 는 그 폼의 것 — 건드리지 않는다 | 알림 중 바코드 쏘기 → 알림 닫힘 + 전송 |
| **S-08** | 알림을 「확인」 · 바깥 누르기 · Esc · (빈 스캔칸) Enter 로 닫으면 포커스는 **스캔칸으로**(방금 누른 「확인」 이 포커스를 쥐고 있어도 `setTimeout 0` 뒤 돌려준다) | 닫은 직후 글자 치기 |
| **S-09** | 서버가 303 뒤에 실어 보낸 `#flash-data`(JSON: `title message fields[] kind`)를 읽어 알림으로 띄운다. `fields[].label — reason` 을 줄로. 파싱 실패는 콘솔 경고(화면은 멀쩡히 둔다) | 쓰기 성공 · 폼 POST 422 |
| **S-10** | 쓰기 성공은 본문의 결과 배너(`#scan-result.ok` · 28px 초록)로 1초 보이고 회색으로 가라앉는다. 팝업까지 띄울지는 화면이 정한다(스캔 반복 화면 — 투입 · 출하 스캔 — 은 배너만) | 배너 → 1초 → 회색 |
| **S-11** | 스캔 진입 GET `?no=` 의 없는 번호는 **그 화면이 422 로 다시 그려진다**(서버 — `api-contract.md` §2). app.js 는 `#scan-result.err`(`role=alert`)를 건드리지 않고 S-02 로 포커스만 잡는다. 폼 POST 의 422 는 303 + S-09 알림. 어느 쪽도 다음 스캔을 막지 않는다 | 없는 번호 스캔 → 빨간 배너 · 스캔칸 포커스 · URL 그대로 |
| **S-12** | 503(DB 끊김)은 서버가 POP 레이아웃의 오류 화면으로 그린다 — 빨간 띠 + 연결 「끊김」 + **스캔칸 `disabled`**. app.js 는 `disabled` 스캔칸에 포커스를 주지 않는다. 오프라인 큐 · 자동 재시도 없음(현황판과 다르다) | 띠 · 「다시 시도」 버튼만 |
| **S-13** | 시각 · 작업자 · 설비는 서버 렌더값. app.js 가 시계를 돌리지 않는다(초 단위 갱신 없음 — 낡은 화면을 새것처럼 보이지 않게) | 새로고침해야 바뀐다 |
| **S-14** | `data-demo` · `data-demo-popup` · `.demo` 는 **원형 전용** — 템플릿으로 옮길 때 지운다. 남아 있으면 폼이 서버로 가지 않는다 | `grep data-demo templates/` = 0 |
| **S-15** | 고르기 칩 `button[data-pick-into=칸 id][data-pick-value=번호]` — 누르면 그 칸(쉼표 목록)에 번호를 넣고 다시 누르면 뺀다(`aria-pressed`). 칸이 값의 주인(손으로 고쳐도 칩 표시가 따라온다) · 전송은 그 폼의 버튼. 스캔칸 포커스를 빼앗지 않는다(S-03 버튼 예외) | POP-02 종료 폼 `merge_lot_ids` |

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

## 이식 정리 (디자이너3 · 회전 5 · 2026-10-09)

바꾼 파일: `static/{board,print}.css` · `templates/kpi/{board,summary,indicators}.html` · `templates/print/*.html` 4 · `templates/home/main.html` · `templates/dashboard/index.html` · `templates/trc/{_cards,_trace,search,backward,forward}.html` · `templates/trc/_trace_m.html`(새 파일). 캡처 `outputs/design/{board,print,home,trc}/r5_*.png`.

| # | 항목 | 결과 |
|---|---|---|
| 1 | `TEMP-TOKENS` 삭제 | `board.css` · `print.css` 의 임시 토큰 블록을 지웠다. `kpi/board.html` · `print/*.html` 4 가 `board.css`/`print.css` 앞에 `<link rel="stylesheet" href="/static/tokens.css?v=…">`. 임시 블록이 쓰던 토큰 26 개 전부 `tokens.css` 에 있다(인쇄 `@media print` 재정의도 `tokens.css` 쪽). 색상값 직접 지정 0(바코드 `fill:#000` 만) |
| 2 | 메인 카드 오늘 건수 | `t(c.today_label or '오늘')` + `title="{{ c.today_source }}"`(개발1 D-108). 값 None → `미수집` 그대로 |
| 3 | 모바일 본문 분리 | TRC-01/02 · TRC-03 · KPI-02 · CMN-02 · CMN-04 가 `{% block mobile_body %}` 를 가진다. `{% block body %}` 를 통째로 바꾸는 화면은 `{% if device == 'mobile' %}{{ self.mobile_body() }}{% else %}…{% endif %}` 로 나눈다(base 의 기본 분기를 거치지 않으므로). 모바일 본문은 화면 제목 · `.panel` 테두리를 다시 그리지 않는다(`.m-top` 몫). TRC-01/02 는 결과가 있으면 추적 번호 칸을 빼고(`.m-top` 검색과 겹침) 빈 진입 · 422 에서만 `form.m-search[data-scan]`. TRC-03 은 `.m-top` 검색이 없으니 본문 맨 위 `form.m-search` 하나. KPI-02 는 조회 조건을 `details.fold` 로 접고 표(`ui.grid`)를 그리지 않는다(카드와 두 벌로 나오던 것). 메인은 시스템 줄 · 범례를 빼고 카드 한 줄씩. 390px 실측 `scrollWidth − clientWidth = 0`(8 화면 · 아래) |
| 4 | QA2-003 KPI-01 목표 미확정 | 템플릿 고정 글자였다 → `미확정 (D-602)`(`board.undecided` 가 오면 그것). `data-empty` 도 같은 글자라 폴링이 지워도 같다. 목표 칸이 비면 `is-empty` 가 바깥 `span[data-key]` 에 붙어 뒤의 `%` 를 숨긴다. KPI-03 안내 문구의 맨 `미확정` 도 `(D-602)` 동반. 현황판 · KPI-03 본문의 맨 `미확정` 0 |
| 5 | QA3-006 추적 노드 수량 | 노드 수량 = `node.qty`(lot.qty) · 화살표 수량 = `edge.qty` 를 나눴다. Web 트리: 관계 옆 굵은 수가 화살표 수량(`합병 50.000 →`) · 노드 끝이 LOT 수량(`100.000 EA`). 화살표 표: `화살표 수량` · `LOT 수량` 두 열. 모바일 카드: 관계 줄 `합병 50.000 → P-…` + `LOT 수량`. 개발3 키 `edges[].qty`(화살표) · `edges[].lot_qty` · `edges[].unit`(도착 LOT) 를 쓴다 |
| 6 | 현황판 503 | DB 끊긴 서버(8033 · 유효 세션)에서 `GET /kpi/board?device=board` → 503 `_error.html` · `body.ch-board[data-refresh-seconds=5]` · `app.js` 실림 · `<noscript>` refresh. 폴링 중 503 은 `board.js` 의 stale(마지막 값 유지). `r5_board_503.png` |
| 7 | 현황판 큰 숫자 넘침 | 실적 + 계획 글자 수가 11 을 넘으면 `.hero[data-long]` 로 한 단계 줄인다(112 → 84px) · `.hero` 줄바꿈 허용. 품질 목표 `미확정 (D-602)` 는 26px. 1920×1080 칸 밖 요소 0 |

모바일 390px 실측(`document.documentElement.scrollWidth − clientWidth`, 칸 밖 요소 수): TRC-01 `M-EX-0001` 0/0 · TRC-02 `X-EX-0001` 0/0 · TRC-02 422 0/0 · TRC-03 0/0 · KPI-02 생산 0/0 · KPI-02 품질+측정값 0/0 · CMN-02 0/0 · CMN-04 0/0.

**요청**
- 디자이너1 `base.html`: TRC-01/02 에서도 `.m-top` 번호 검색이 TRC-03(`?q=`)으로 간다 — 원형(`mobile/trc_backward_m.html`)대로 이 두 화면에서는 `action=현재 경로 · name=no` 로 바꿔 주면 본문의 빈 진입 추적 칸을 지운다.
- 디자이너1 `_error.html`: 현황판 채널 503 은 벽걸이 1920 에서 글자가 작다(제목 ≈ 18px). `body.ch-board` 일 때 상태 · 문구를 현황판 크기(48px 이상)로.
- 개발3 `routers/dashboard.py`: 모바일 CMN-04 의 `shortcuts` 가 관리자에게 0 건(「열 수 있는 화면이 없습니다」) — 모바일 채널 허용 화면(TRC-03 · KPI-02 · JOB-02 · MAT-04)을 넘기는지 확인.

## 이식 요청 (디자이너2 · 웨이브 A′ · 2026-10-09)

이식한 것: `static/app.js`(S-01~S-14 + 디자이너1 base 의 메뉴 · 계약 패널 접기 · 토스트 · 알림 닫기 · 인라인 확인 취소) · `static/pop.css` · `static/mobile.css`(새 파일) · `templates/pop/{_layout,_ui,work,result,inputs,labels}.html` · `mat/{receipts,inspections,stock,lots,requirements}.html` · `qua/inspections.html` · `eqp/{status,checks,faults}.html` · `shp/{scan,status,shipments,documents}.html` · `home/_measure.html`(모양만 — 매크로 서명 · 폼 name · 상태 11 로직 그대로). 원형 전용(`data-demo` · `.demo` · `pop.js`) 0. 캡처 `outputs/design/pop/*.png` · `outputs/design/mobile/*.png`.

| # | 누구 · 어디 | 요청 | 지금은 |
|---|---|---|---|
| 1 | 디자이너1 `base.html` | **POP · 모바일 채널 분기를 base 로** — `templates/pop/_layout.html` 의 `{% block body %}` 세 갈래(ch-pop `main.pop-main` + 제목 줄 `.screen-head`(설비 · 시각 · 연결 · 뒤로) / ch-mobile `.m-frame`(`.m-top` 제목 + TRC-03 번호 검색 · `.m-main` · 하단 탭 4 `.m-tabs`) / 그 밖 3블록)와 `{% block pop_body %}` · `{% block mobile_body %}` 를 base 가 품으면 `_layout.html` 은 지운다. 하단 탭 4 = 추적 TRC-03 · 현황 KPI-02 · 지시 JOB-02 · 재고 MAT-04(`menus` 에 있는 모듈 + `nav.channel_allowed(id, 'mobile')` 만) | 디자이너2 파일 11개가 `pop/_layout.html` 을 extends. 디자이너3 의 모바일 화면은 base 틀 그대로(헤더 + 좌측 메뉴) — 틀이 둘이다 |
| 2 | 디자이너1 `base.html` | 모바일에서도 `.hdr` · `.side` 를 그린다. `mobile.css` 는 `.m-frame` 이 있는 화면에서만 `body.ch-mobile:has(.m-frame) > .hdr …` 로 숨긴다(`:has()` — Chrome 105+ · Safari 15.4+). base 가 분기를 품으면 `:has()` 는 없어진다 | `mobile.css` 맨 위 |
| 3 | 디자이너1 `_error.html` | **503(S-12)** 은 POP 레이아웃으로 — 빨간 띠 `div.offline-bar[role=alert]`(「서비스 일시 중단 (503) — 연결이 돌아오면 스캔을 이어서 한다」) + `input[data-scan][disabled]` + 「다시 시도」 버튼. `app.js` 는 `disabled` 스캔칸에 포커스를 주지 않는다 · 자동 새로고침 없음. 모양은 `pop.css` `.offline-bar` 에 있다 | `_error.html` 은 로그인 카드 모양 하나 |
| 4 | 개발2 `routers/mat.py` MAT-01 · `routers/eqp.py` EQP-01 | 원형의 스캔 진입 `GET /mat/receipts?item_code=`(품목 바코드 → 품목 칸 채움) · `GET /eqp/status?equip_code=`(설비 카드로) 가 라우터에 없어 **두 화면은 스캔칸을 두지 않았다**(S-01 — 없는 화면). 넣어 주면 `ui.scan_box` 한 줄을 더한다 | 품목 · 설비는 select(56px) |
| 5 | 개발2 `routers/pop.py` POP-02 | 작업 시작의 「작업자」 기본 선택 — 로그인 사용자의 `bas_worker` id 가 ctx 에 없어 아무것도 안 눌려 있다(비우면 서버가 로그인 작업자). `worker_id_default` 를 넘겨 주면 `checked` 로 | 선택 버튼 · 미선택 |
| 6 | 개발2 `routers/pop.py` POP-03 | 「투입량 직전 값 유지」는 이력 맨 위 행(`rows[0].qty`)으로 채운다 — 취소된 행이 맨 위면 그 값. `last_qty` 를 넘겨 주면 그것으로 | `rows[0].qty` |
| 7 | 개발3 `routers/shp.py` SHP-03 | 모바일 카드의 「납기 대비」는 템플릿이 `ship_date − due_date` 로 센다(수주 없으면 「-」). `stats.delivery` 의 행별 값이 있으면 그것으로 바꾼다 | 템플릿 계산 |
| 8 | 디자이너1 `style.css` | 관리자 Web 에서 디자이너2 템플릿이 쓰는 class — `.result(.err/.ok) .result-msg .result-fields` · `.choice(.c2 .c3 .c4 .big) label>input+span` · `.measure .m-field(.deviated .collect) .lbl .range .readonly` · `.steps .step(.on .done)` · `.cards .card(.sel)` · `.notice` · `.pop-main`. POP 에서는 `pop.css` 가 그린다; Web 에서 같은 화면(MAT-02 · QUA-02 의 검사 항목 · POP-01~04 관리자 조회)을 열면 `style.css` 의 `.m-field` 최소 규칙만 받는다 | Web 은 최소 모양 |
| 9 | 아키텍트 `check_terms` | 템플릿의 `t()` 누락 검사는 태그 안 속성(`placeholder=` · `title=`)을 안 본다 — 디자이너2 템플릿은 속성 문구도 `{{ t('…') }}` 로 두었다. 검사 범위를 속성까지 넓혀도 통과한다 | — |
| 10 | 검증 | `pytest` 는 같은 DB 를 여러 담당이 동시에 써서 `test_job_work_orders` 2건(개발1 화면 · 디자이너2 파일 밖)이 흔들렸다 — 보고서에 단독 실행 결과 | — |

S-01~S-14 구현 위치(`static/app.js`): S-01 `scans.length !== 1 → console.error` · S-02 `focusScan()` 즉시 + `autofocus`(매크로) · S-03 `document click → setTimeout(focusScan)` + `idle()`(INPUT SELECT TEXTAREA BUTTON A 제외) · S-04 `window focus` · S-05 폼 그대로(가로채지 않는다) · S-06 `popup()` 끝에 `focusScan()` · S-07 `keydown`(capture) 글자 키 → `closePopup()` + `scan.focus()` · Enter 는 빈 스캔칸 · 본문일 때만 닫기 · S-08 `closePopup()` → `setTimeout(focusScan, 0)` · 바깥 · Esc · S-09 `#flash-data` JSON → `popup(title, message, fields, kind)` · `ul.fields li = label — reason` · S-10 `banner()` → `#scan-result.ok` 1초 뒤 `.result` · `#scan-result[data-flash-banner]` 면 팝업 없이 배너만(POP-03 · SHP-02) · S-11 `#scan-result.err` 는 건드리지 않음 · S-12 `scan.disabled` 면 포커스 없음 · 자동 새로고침은 `body.ch-board` 만 · S-13 시계 없음 · S-14 `data-demo` 0.

## 이식 요청 (디자이너1 · 웨이브 A′ · 2026-10-09)

웨이브 A′ 에서 `docs/design/web/` 원형을 실제 템플릿으로 옮겼다 — `static/style.css`(토큰 `@import` + Web 레이아웃 + 컴포넌트 + 채널 최소 규칙) · `static/tokens.css`(디자이너3 요청 — 토큰 `:root` 라이트 + 다크 + 인쇄를 분리. `base.html` 을 쓰지 않는 현황판 `kpi/board.html` · 출력물 `print/*.html` 은 `<link rel="stylesheet" href="/static/tokens.css">` 만 읽으면 된다. `style.css` 가 첫 줄에서 `@import url("tokens.css")` 하므로 Web 화면은 바꿀 것이 없다. `board.css` · `print.css` 의 `TEMP-TOKENS` 블록은 지워도 된다) · `base.html` · `home/_macros.html`(서명 그대로 · 꾸밈은 kwargs · `confirm_button` · `badge` · `bar` · `empty_row` · `flash_reason` 추가 · `measure_fields` 는 `home/_measure.html` 위임) · `login.html` · `_error.html` · `_placeholder.html` · `bas/ job/ sys/ ord/` 18 화면. 캡처 `outputs/design/web/*.png` 36장(1280 · 모바일 2장은 390).
`base.html` 블록: `search`(비우면 조회 조건 패널 없음) · `grid` · **`form`**(표 아래 쓰기 폼 패널 — 새로 둔 블록 · 비우면 안 그린다) · `actions` · `body`. `ui.field/select` 는 `{% import "home/_macros.html" as ui with context %}` 로 가져오면 422 flash 의 `fields[].name` 과 같은 칸에 `.err` + 사유를 붙인다(`with context` 가 없으면 그냥 그린다).

라우터 ctx 키가 모자라 원형대로 못 한 것 — 담당이 넘겨 주면 템플릿만 바꾼다(`progress.md` 가 아니라 여기):

| 화면 | 원형 | 지금 | 필요한 ctx 키 · 담당 |
|---|---|---|---|
| 전 화면 422 재렌더 | 틀린 칸 강조 + **입력값 유지** | 틀린 칸 강조만(flash `fields[]`). 303 뒤라 입력값은 비어 있다 | flash 에 `values{name: 값}` 을 실어 주거나(util/http.py `_back_with_flash` · 아키텍트) 422 를 그 화면 재렌더로 — 그러면 `ui.field(value=…)` 가 채운다 |
| 전 화면 표 | `th[aria-sort]` 서버 정렬 `?sort=` · 페이지 `?page=` · "상한 N건 — 전체 M건" | app.js 가 브라우저에서 정렬 · 쪽 넘김(`grid_page_size`). 상한은 `LIST_LIMIT` 글자로 | 서버 정렬 · 전체 건수(`total`)를 주면 `aria-sort` · `.pager .sum` 으로 바꾼다 (개발1 · 3) |
| ORD-01 수주 | 모든 헤더 행 아래 상세 행(tr.dtl) | 열린 수주(`opened`)의 `lines` 만 | 행마다 `lines` 가 오면 전부 펼친다 (개발3) · 조회 조건 거래처 select 는 `partners` 로 바꿀 수 있다(지금은 글자 일부 일치 `partner`) |
| ORD-01 등록 폼 | 상세 N줄 + `app.js` 가 줄 복제 | 빈 줄 3 고정 (줄 추가 스크립트는 `app.js` — 디자이너2) | `app.js` 에 "마지막 줄 복제" 가 생기면 `tfoot` 의 + 버튼을 되살린다 |
| JOB-01 작업지시 | 진행 중 지시의 품목 · 공정 `disabled select` | 읽기 전용 글자 칸(`item_ro` · `process_ro` — 서버가 받지 않는다) | 그대로 둬도 된다 |
| SYS-03 권한 표 | 칸 아래 "변경 n칸" 요약 | 없음 | 저장 전 변경 수는 스크립트 영역(`app.js`) |
| 로그인 | 역할 × 채널 × 입력 메뉴 표 | 채널 4 설명만 | `rbac.matrix()` 를 로그인 ctx 에 주면 표로 그린다(아키텍트 `main._login_page`) — 지금은 DB 값을 지어내지 않으려고 뺐다 |
| 계약 패널 | `settings.show_contract_panel` | `settings.env == 'dev'` 일 때만 그린다(`data-env`) | 설정 키가 생기면 바꾼다(아키텍트) |
| 모바일 채널 JOB-02 · ORD-03 | `.m-frame` + 하단 탭 4 | `base.html` 헤더 · 좌측 메뉴 + 표를 카드로(`cardify` · `body.ch-mobile` 과 폭 480 아래 둘 다) · ORD-03 은 주 단위 `details` | 디자이너2 `pop/_layout.html` 의 모바일 틀을 `base.html` 이 품으면 두 화면도 하단 탭이 붙는다 — 다음 회전에 합친다 |

`app.js`(디자이너2) 에 필요한 동작 — 없어도 깨지지 않게 CSS 로 받쳐 두었다: `[data-toast-close]` · `.toast[data-auto]` 8초 뒤 제거(지금은 CSS 애니메이션으로 숨긴다) · `[data-alert-close]` · `[data-close-details]`(인라인 확인의 취소) · `#side-toggle`(`body.side-collapsed`) · `#desc-toggle`(`body.desc-closed` / 1180 아래 `desc-open`). 좌측 메뉴는 `app.js` 의 `.menu-head` 클릭(`.menu-group.open`)을 그대로 쓰도록 `mg menu-group` · `mg-h menu-head` 두 이름을 같이 달았다. `templating.asset_version()` 은 `style.css` · `app.js` 의 mtime 만 보므로 `tokens.css` 만 바꾸면 캐시가 안 풀린다 — `style.css` 를 같이 건드리거나 `asset_version` 에 `tokens.css` 를 더한다(아키텍트).

## 이식 요청 (디자이너1 · 회전 4 · 2026-10-09)

바꾼 파일: `templates/base.html` · `_error.html` · `login.html` · `home/_macros.html` · `static/style.css`. 캡처 `outputs/design/web/r4_*.png`(BAS-01 · POP-01 · JOB-02 × Web · POP · 모바일 + MAT-04 · TRC-03 모바일 + 503 POP). BAS-01 은 POP · 모바일 채널 밖이라 403, POP-01 은 모바일 채널 밖이라 403 — 그 화면 캡처가 채널 차단 확인이다.

**처리한 것**

| # | 요청 | 결과 |
|---|---|---|
| 디자이너2-1 | POP · 모바일 분기를 base 로 | `base.html` 이 채널 틀 셋을 그린다 — ch-pop: `.hdr` + 상단 탭 `.pop-tabs` + `div.main > main.pop-main`(`.screen-head` 제목 · 설비 · 시각 · 연결 · 뒤로) / ch-mobile: `.m-frame`(`.m-top` · `.m-main` · `.m-tabs` 4) / 그 밖: Web 3단. `{% block pop_body %}` · `{% block mobile_body %}` 를 base 가 둔다. 내용 블록은 출력하지 않는 자리에서 정의하고 틀이 `self.body()` 로 부른다 — **`{% block body %}` 를 통째로 바꾼 화면(TRC · KPI · 메인 · 대시보드)도 채널 틀 안에 들어간다**(모바일 틀이 하나가 됐다). `<main>` 은 화면마다 하나(POP 바깥은 `div.main`) |
| 디자이너2-1 | `pop/_layout.html` 은 그대로 · 결과 같게 | `_layout.html` 의 body 가 이미 `<main class="pop-main">` · `<div class="m-frame">` 을 그리면 base 는 틀을 겹쳐 두르지 않고 그대로 낸다(문자열 검사 — `_layout.html` 을 지우는 회전에 이 두 줄도 지운다). POP-01 · MAT-04 결과 DOM 이 전과 같다(main 1 · pop-main 1 · screen-head 1 · 상단 탭 13 / m-frame 1 · 하단 탭 4) |
| 디자이너2-2 | 모바일에서 `.hdr` `.side` 를 그리지 않는다 | 모바일은 `.hdr` · `.side` · `.desc` · `.ftr` 를 아예 안 그린다. `style.css` §5 의 모바일 헤더 · 메뉴 규칙을 지웠다. 하단 탭은 `menus` 에 있는 모듈 + `nav.channel_allowed(id, 'mobile')`. `.m-top` 번호 검색은 TRC-03 자신에서는 뺀다(본문 검색과 겹침) |
| 디자이너2-3 | 503 POP(S-12) | `_error.html` 이 `device == 'pop' and status == 503` 이면 POP 틀 — `.hdr` + `div.offline-bar[role=alert]`(「서비스 일시 중단 (503) — 연결이 돌아오면 스캔을 이어서 한다」) + `main.pop-main` + `form.scan-box` 안 `input[data-scan][disabled]` + 「다시 시도」 + `.result.err`(방금 스캔은 저장 안 됨). `app.js` 를 싣는다(S-12 disabled → 포커스 없음 · POP 자동 새로고침 없음). 「다시 시도」 = GET 이면 같은 주소, POST 면 이전 화면(POST 주소를 GET 으로 열면 405). 현황판 채널 오류 화면의 자동 새로고침은 그대로 |
| 디자이너2-8 | Web 최소 모양 | `style.css` §3 「디자이너2 템플릿의 Web 최소 모양」 — `.pop-main(.screen-head .who)` · `.result(.err .ok) .result-msg .result-fields` · `.choice(.c2 .c3 .c4 .big · .ok .warn .err) label>input+span` · `.m-field.collect` · `.steps .step(.on .done)`(메인 카드의 `.card .step` 과 겹치지 않게 `.steps` 아래로) · `.card.sel` · `a.card` · `.notice` |
| 디자이너1 · 422 | 입력값 유지 | **준비만** — 아키텍트의 flash `values` 커밋이 아직 없다(`git log -- util/http.py` 마지막 = Phase 0). `ui.field` · `ui.select` 서명은 그대로, 첫 줄에서 `flash.get('values')` 를 읽어 그 칸 `name` 이 있으면 value 로 쓴다(비밀번호 · readonly · disabled 제외 · 라우터 value 보다 앞선다). **`flash.values` 로 쓰면 안 된다 — flash 는 dict 라 `dict.values` 메서드가 잡힌다.** 확인: 가짜 flash 로 렌더 → `item_code` 되채움 · `pw` 빈 값 · select `A&B` selected |
| 디자이너1 · 로그인 | 역할 × 채널 × 입력 메뉴 표 | 개발1 `role_summary`(`aa9e22a` · `GET /login` — code · name · channels[device label] · write_menus[code name label] · read_count) + `n_menus` 로 안내 칸에 표(입력 메뉴 = 메뉴명 + 범위 `(승인)` 등 · 조회 = read_count/n_menus). 제목 「역할 n · 채널 4」 와 개발용 역할 버튼도 이 목록에서. `POST /login` 실패 재렌더(401)에는 키가 없어 표를 숨기고 버튼은 코어 역할 4(확인함). 개발용 버튼에 `formnovalidate` — 아이디 칸 `required` 때문에 `/login/as` 가 브라우저에서 막히던 것. 캡처 `r4_login.png` |

**아키텍트에게** — ① `util/http.py: flash(..., values=)` + `main._back_with_flash` 가 `await request.form()` 의 값을 `values{}` 로(비밀번호 · `csrf` 류 키 제외 · 파일 제외). 템플릿은 이미 받는다. ② `templating.asset_version()` 에 `tokens.css` 를 더해 달라(웨이브 A′ 요청 그대로).

## 다음 회전 디자이너2 · 3 몫 (디자이너1 · 회전 4)

| 누구 | 할 일 | 왜 |
|---|---|---|
| 디자이너2 | `templates/pop/_layout.html` 을 지우고 extends 하는 17 파일(`pop/{work,result,inputs,labels}` · `mat/{receipts,inspections,stock,lots,requirements}` · `qua/inspections` · `eqp/{status,checks,faults}` · `shp/{scan,status,shipments,documents}`)을 `{% extends "base.html" %}` 로. `{% block head_extra %}` 를 쓰던 곳은 `{% block head %}` 로. 블록 이름 `pop_body` · `mobile_body` · `who_equip` 는 같다 | base 가 같은 틀을 그린다. 지운 뒤 디자이너1 이 base 의 「이미 그린 틀이면 그대로」 두 줄을 지운다 |
| 디자이너2 | `static/mobile.css` 맨 위 `body.ch-mobile:has(.m-frame) > .hdr …` 세 줄과 `@layer pop-token-fallback`(토큰 임시값) 을 지운다. `pop.css` 의 토큰 임시값도 | 모바일엔 `.hdr` · `.side` 가 없다 · 토큰은 `style.css` 가 `tokens.css` 를 `@import` |
| 디자이너2 | `.m-main > .alert`(모바일 422 · info 알림) 와 `.toast` 의 모바일 위치를 하단 탭과 겹치지 않게 `mobile.css` 에서 | base 가 `.m-main` 맨 위에 알림을 그린다(모양은 `style.css` 기본) |
| 디자이너3 | `trc/{search,backward,forward}.html` · `kpi/summary.html` · `home/main.html` · `dashboard/index.html` 의 모바일 분기 — 이제 base 의 `.m-frame` 안에 들어간다. `.m-only` 카드 · 자체 검색 줄이 `.m-top` 과 겹치지 않는지 · 모바일 머리 제목을 화면 안에서 다시 그리지 않는지 본다. 가능하면 `{% block body %}` 대신 `{% block mobile_body %}` 로 모바일 본문을 나눈다 | 모바일 틀이 하나가 됐다(전에는 base 헤더 + 좌측 메뉴) |
| 디자이너3 | `board.css` · `print.css` 의 `TEMP-TOKENS` 블록을 지우고 `kpi/board.html` · `print/*.html` 에 `<link rel="stylesheet" href="/static/tokens.css">` 한 줄 | `tokens.css` 가 웨이브 A′ 부터 있다 |
| 디자이너3 | 현황판 오류 화면(503)도 `_error.html` 의 ch-board 자동 새로고침을 쓰는지 확인 — `kpi/board.html` 이 503 을 자기 화면 안 「연결 끊김」 으로 그리면 그대로 | S-12 · 자동 새로고침은 board 만 |

## 이식 결과 (디자이너2 · 회전 5 · 2026-10-09)

**디자이너1: base.html 의 「이미 그린 틀이면 그대로 낸다」 분기를 지워도 된다.** `templates/pop/_layout.html` 은 지웠고 이를 extends 하던 17 파일이 전부 `{% extends "base.html" %}` 다(`head_extra` → `head`). 이제 어느 템플릿도 `<main class="pop-main">` · `<div class="m-frame">` 을 스스로 그리지 않는다 — base 의 `'<main class="pop-main">' in body_html` · `'<div class="m-frame">' in body_html` 두 분기는 늘 거짓이다. 머리 주석의 「pop/_layout.html(디자이너2)은 옮겨 가는 동안 남는다 …」 줄도 함께.

| 한 것 | 파일 | 확인 |
|---|---|---|
| `_layout.html` 삭제 · 17 파일 base 로 | `templates/{pop,mat,qua,eqp,shp}/*.html` | 전후 HTML(공백 정규화 · 시각 가림) 72 응답 비교 — Web · POP(field · admin) 전부 같음. 차이는 ① 모바일 `main.m-main` 에 `id="main"`(base 쪽 개선) ② POP-01 · POP-04 의 목록 맨 위 카드 1장(같은 DB 를 다른 담당이 동시에 써서 생긴 데이터 차이 — 마크업 같음) 뿐 |
| 토큰 임시 `@layer pop-token-fallback` 삭제 | `pop.css` · `mobile.css` | 지운 토큰 이름 전부 `tokens.css` 에 있음(빠진 것 0) |
| `body.ch-mobile:has(.m-frame) > .hdr …` 삭제 | `mobile.css` | 모바일 8 화면 `.hdr/.side/.ftr` 0 · 390px 가로 넘침 0 |
| 모바일 알림 · 토스트 | `mobile.css` | `.m-main > .alert` 는 흐름 안(위 `.m-top` 아래 · 거터 한 번) · `.toast` 는 하단 탭 바로 위(390 틀 폭 · safe-area). 실측: 토스트 아래끝 776 < 탭 위끝 786 · 알림 위끝 120 > `.m-top` 아래끝 108 |
| MAT-01 · EQP-01 POP 스캔칸 | `mat/receipts` · `eqp/status` | 스캔칸 1 · 열자마자 포커스. EQP-01 스캔한 설비 카드 `.card.sel` = 4px 강조선 + 옅은 강조 바탕 + 「스캔한 설비」 표지 · `aria-current` |
| POP-02 종료 폼 `merge_lot_ids` | `pop/result` · `pop.css` · `app.js` S-15 | 칸 하나(번호 · 쉼표) + 이 지시의 재고 생산 LOT 칩. 한 바퀴: 칩 → 칸 `P…` → 다시 눌러 빠짐 → 종료 → 새 LOT 계보에 `합병` 1행 · 칩 LOT `소진` |
| POP-02 꺼진 선언의 지난 기록(`params[].recorded_only`) | `pop/result` · `pop.css` | 종료 폼: 입력칸 아래 회색 점선 「지난 기록」 상자(읽기 전용 · 「선언 꺼짐」 배지). 종료 뒤: 측정값 표 아래 「선언 꺼짐 · 지난 기록만: …」 한 줄 |
| QUA-02 검사 공정 폼 `#insp-process-form` | `qua/inspections` · `pop.css` | 패널 한 줄 — 공정 선택 + 「이 공정의 검사 항목」 + 설명 한 줄. name · id 그대로 |
| 목록 서버 정렬 `?sort=` | `pop/_ui.html` `sort_th` · `sort_keep` · 6 화면 | 관리자 Web 표 머리글만(POP · 모바일은 정렬 없음 — 터치 화면은 서버 기본순). MAT-01 · MAT-03 · QUA-02 · QUA-04 · EQP-02 · EQP-03 의 허용 열(라우터 `*_SORT`)만 링크 · `th[aria-sort]` · ▲▼↕ · 같은 열 다시 = 반대 방향 · 조회 조건 유지 · 「조회」 폼에 숨은 `sort`. `app.js` 화면 정렬은 `th.th-sort` 를 건너뛴다 |
| 금지어 | `app.js` | `splice` → `filter`/`concat` (G-C23 PASS) |

캡처 `outputs/design/pop/r5_*.png` — POP 한 바퀴(`r5_pop01_work` → `r5_pop02_end` · `r5_pop02_merge_pick` → `r5_pop03_inputs` → `r5_pop02_ended` → `r5_pop04_label`) · `r5_mat01_scan` · `r5_eqp01_scan_sel` · `r5_qua02_process_form(_el)` · 모바일 `r5_mobile_mat04_alert` · `r5_mobile_shp03_toast`(알림 · 토스트는 위치 확인용으로 페이지에 넣어 찍음 — 모바일은 쓰기가 없어 실제 422 · 저장 토스트가 나지 않는다).

| 다음 회전 요청 | 누구 | 왜 |
|---|---|---|
| base.html 의 두 분기 · 머리 주석 한 줄 삭제 | 디자이너1 | 위 |
| `style.css` 에 `th.th-sort a`(색 상속 · 밑줄 없음 · 화살표 `--c-ink-3`) · `th[aria-sort=ascending|descending] a`(굵게) | 디자이너1 | 지금은 브라우저 기본 링크 모양 |
| `home/_measure.html` 의 `measure_table` 에서 `recorded_only` 행에 「선언 꺼짐」 표지 | 개발2(그 파일 주인) | 지금은 POP-02 가 표 아래 한 줄로만 구분 |
| 조회 역할(관리자)의 POP-03 스캔칸 — POST 403(QA3 §126) | 개발2 · 디자이너2 | 스캔칸을 숨기면 S-01(스캔칸 하나) 화면 규칙이 깨진다. `user.can('F-POP-06')` 이 거짓이면 스캔칸 `disabled` + 「이 역할은 투입 권한이 없다」 로 할지 다음 회전에 정한다 |

## 이식 결과 (디자이너2 · 회전 7 · 2026-10-09) — DEF-QA3-008 POP · Web 폼 422 입력값 유지

규칙: 폼 POST 422 → 303 뒤 `flash.get('values')`(kind ≠ ok)로 칸을 되채운다. **값이 라우터가 준 값(직전 저장값 · 기본값)보다 앞선다.** 비밀번호 · readonly · 수집값(`is_collect`)은 되채우지 않는다. **스캔칸(`data-scan`)은 되채우지 않는다(S-05).**
두 갈래로 고쳤다.
- **폼 하나 · 이름이 안 겹침** → `{% import "home/_macros.html" as uf with context %}` 를 하나 더 두고 쓰기 폼 칸만 `uf.field/select`(→ 매크로가 `flash.values` 로 되채우고 틀린 칸 `.err`). 조회 조건(`block search`) · 행마다 반복되는 인라인 폼은 그대로 `ui`(with context 없음) — 쓰기 폼 422 가 조회 조건이나 다른 행 칸을 덮지 않게.
- **한 화면에 폼이 여럿이고 이름이 겹침**(note · qty …) → 템플릿에서 `fv = flash.get('values')` 를 읽고 「그 폼만 보내는 칸」으로 어느 폼이 돌아왔는지 가른 뒤 `ui`(context 없음)에 값을 골라 넘긴다. 손으로 쓴 `<input>` 도 같은 식.

| 화면 | 파일 | 되채우는 칸 | 가르는 칸 |
|---|---|---|---|
| POP-03 투입 | `pop/inputs` | 투입량 `qty`(값이 있으면 `last_qty` 보다 앞섬) | — (스캔칸 `barcode` 는 비움) |
| POP-02 시작 | `pop/result` | 설비 · 작업자(choice) · 비고 | `work_order_id` |
| POP-02 종료 | `pop/result` | 양품 · 불량 · `merge_lot_ids` · 측정값 `m_<key>` · 팩 속성 `attr_<key>` | `good_qty` |
| POP-02 정지 · 폐기 · 분할 · 합병 | `pop/result` | 사유 · 비고 / 폐기 수량 · 불량코드 / LOT · 분할 수 · 수량 / 합병 LOT · 수량 | 정지 = 나머지 · 폐기 `qty` · 분할 `count` · 합병 `lot_ids` |
| MAT-01 입고(POP · Web) | `mat/receipts` | 품목 · 거래처 · 수량 · 단위 · 입고일 · 비고 · 팩 속성 | `uf` |
| MAT-02 입고검사 | `mat/inspections` | 검사 항목 `i_<key>` · 판정 · 비고 | `lot_id` = 이 LOT |
| MAT-04 재고 조정 | `mat/stock` | 품목 · 조정 수량 · 사유 | `uf` |
| QUA-01 검사 계획 | `qua/plans` | 유형 · 품목 · 공정(`uf`) · 항목 3줄(같은 이름 3번 → `values` 목록을 줄 번호로) | `item_key` |
| QUA-02 검사 결과 | `qua/inspections` | 항목 저장 폼(유형 · 비고 · `i_<key>`) · 판정 폼(판정 · 불량코드 · 수량 · 비고 — **대기 판정이 하나일 때만**: 검사 # 가 URL 에만 있어 값으로 가를 수 없다) | `lot_id` 유무 |
| QUA-04 품질이상 | `qua/issues` | 발생 시각 · 공정 · LOT · 내용 · 원인 | `uf` |
| EQP-02 점검 · EQP-03 고장 | `eqp/checks` · `eqp/faults` | 등록 폼 전 칸 | `uf` |
| SHP-01 출하 | `shp/shipments` | 수정 · 등록 폼(이름이 같다) | 수정 폼에 숨은 칸 `shipment_edit=1`(라우터는 모르는 칸 — 무시) |
| SHP-04 성적서 | `shp/documents` | 출하 · 종류 | `uf` |

되채우지 않는 것(그대로 둔 이유): SHP-02 · POP-01 · POP-04 · MAT-03(스캔칸뿐) · EQP-01 상태(설비 카드마다 같은 폼 — 어느 카드인지 값에 없음) · QUA-04 조치 · EQP-03 조치 · QUA-01 행 수정(행마다 인라인 폼 — 같은 이유).

측정값: 개발2 `home/_measure.html` 은 `values{param_key: 행}` 만 읽는다 — 매크로는 손대지 않고, 422 뒤에는 템플릿이 보냈던 `m_<key>`(`i_<key>`) 값을 `{value_num, value_text, deviated: false}` 행 모양으로 덮어 넘긴다(number · bool · select · text 모두 이 두 키로 그려진다). **개발2 요청 없음.** 다만 매크로가 `flash.values` 를 직접 읽게 바꾸면 세 화면의 덮어쓰기 블록을 지울 수 있다(선택).

실측(8032 · headless Chrome · 코어 DB): POP-03 실적 #5305 투입량 3.000 → 3.5 + `NOPE-R7-0000` 스캔 → 알림 뒤 투입량 **3.5** · 스캔칸 빈 값 → `M261009-1189` 스캔 → 이력 첫 줄 **3.500 kg** 저장. POP-02 #5304 양품 12 · 불량 1 · 합칠 LOT `NOPE-MERGE-R7` → 422 뒤 **12 · 1 · NOPE-MERGE-R7** 유지 · 폐기 수량 빈 값(다른 폼 안 덮음). POP-02 #5576 측정값 4칸 7.25 · 8.25 · 9.25 · 10.25 → 422 뒤 그대로. MAT-02 `M261009-1229` 항목 73칸 · 비고 유지 · 스캔칸 빈 값. Web(PROD · QA): MAT-01 수량 −5 · 단위 · 비고 유지(조회 조건 `frm` 은 조회값 그대로) · EQP-02 점검 항목 · 결과 · 비고 · EQP-03 증상 · QUA-04 원인 · LOT · SHP-01 등록 비고 · 출하일 유지.
캡처 `outputs/design/pop/r7_pop03_422_qty_kept.png` · `r7_pop03_saved_3_5.png` · `r7_pop02_end_422_kept(_full).png` · `r7_pop02_end_422_measure_kept.png` · `r7_mat02_422_kept.png` · `r7_web_mat01_422_kept.png` · `r7_web_eqp02_422_kept.png`.

