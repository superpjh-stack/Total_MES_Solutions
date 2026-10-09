# API 계약 — 오류 · 응답 규약 (아키텍트 · 2026-10-09 · 초안)

> `goal.md` §2.5 오류 계약을 코드가 지키는 방식이다. QA1 이 이 표를 그대로 테스트 케이스로 쓴다.
> 구현은 `src/mescore/app/util/http.py`(예외 만들기)와 `src/mescore/app/main.py`(핸들러). 엔드포인트 목록은 `function-list.md` 의 `API` 열이다.
> 엘컴화인 `contracts/api-contract.md` 를 일반화했다 — 팩이 바꿀 수 없는 코어 규약이다.

## 1. 오류 계약

| 상황 | HTTP | `code` | 메시지 | 올리는 법 |
|---|---|---|---|---|
| 필수값 누락 · 코드 중복 · 없는 LOT 스캔 · 이미 출하된 LOT 재출하 · 자기 자신을 부모로 하는 계보 · 측정값 필수 누락 · 불합격 LOT 투입 | **422** | `validation_error` | 상황에 맞는 문장 + 항목별 사유 | `raise http.validation_error("…", fields=[…])` |
| 팩 훅이 거부 | **422** | `hook_rejected` | 훅이 준 문장 | 훅이 `raise HookError("…", fields=[…])` → 핸들러가 422 로 |
| 인증 실패 (미로그인 · 로그인 실패 · 무효가 된 세션: 중지 · 잠금 · 로그아웃 · 상태/비밀번호 변경 전 세션) | **401** | `unauthorized` | `로그인이 필요합니다` | `rbac.require_*` 가 낸다 — 요청마다 DB 확인 |
| 권한 없음 · 팩이 숨긴 메뉴 · 채널 허용 밖 화면 | **403** | `forbidden` | `접근 권한이 없습니다` | `rbac.require_screen` · `require_fn` · `nav.channel_allowed` |
| 대상 없음 (경로의 키 · 없는 주소) | **404** | `not_found` | `대상을 찾을 수 없습니다` | `raise http.not_found()` |
| DB 연결 실패 | **503** | `db_unavailable` | `서비스 일시 중단` | `conn` 이 `DbUnavailable` — 잡지 않는다. 접속 문자열 · 호스트는 응답에 싣지 않고 로그에도 비밀번호를 가린다 |
| ERP · 미확정 연계 · 미구현 어댑터 · 팩이 `미확정` 으로 둔 기능 | **501** | `undecided` | `… 미확정 (D-nn)` | `raise http.undecided("D-02", "ERP 연계")` |
| 처리되지 않은 예외 | **500** | `internal_error` | `예상하지 못한 오류` | 핸들러가 로그에 남긴다 |

- **조용한 실패 금지.** 오류를 잡아 빈 목록 · 기본값 · 하드코딩 결과를 돌려주지 않는다. DB 를 끊었는데 화면이 멀쩡하면 결함이다.
- 422 와 404 의 경계: **사용자가 입력 · 스캔한 번호**가 없으면 422, **경로에 박힌 키**가 없으면 404. 경로 키가 숫자여야 하는데 아닌 것도 404.
- 미구현 공용 모듈은 `NotImplementedError` → 500. 501 은 "사람이 아직 정하지 않은 것" 에만.
- **측정값 범위 이탈은 오류가 아니다.** 저장하고 `pop_measure.deviated = true` 로 표시한다(G-C24). 필수 누락만 422.

## 2. 응답의 모양

요청의 `Accept` 에 `text/html` 이 있으면 브라우저로 본다. 없으면(테스트 · 스크립트) JSON 이다.

| 경우 | 브라우저 (`Accept: text/html`) | 그 밖 (JSON) |
|---|---|---|
| 화면 GET | 200 HTML | **200 JSON** — 그 화면의 `ctx`(`templating.render` 가 받은 것 + `screen_id` · `user` · `functions` · `template`). placeholder 는 `placeholder: true` (백엔드 우선 · D-18) |
| 쓰기 성공 | **303** → 원래 화면 + 알림 한 번 | **200** `{"ok": true, "message": "…", …}` (`http.saved(request, msg, data={…})`) |
| 422 (폼 POST) | **303** → 원래 화면 + 알림(메시지 · 항목별 사유 · **입력값**). POP 은 큰 글씨, 닫으면 스캔칸으로. 원래 화면 = `Referer` → 요청 경로의 화면 경로 → 메인. **입력값 유지**: 알림(`flash`)에 `values {이름: 값 | [값…]}` — `http.validation_error(..., values={…})` 로 준 값, 없으면 요청 본문(urlencoded · `http.FormEcho` 가 복사 · 64KB 이하). 훅 거부 · DB 제약 422 도 같다. 비밀 칸(`password` · `token` · `secret` …)은 싣지 않는다. 폼은 `flash.values[이름]` 으로 다시 채운다(`_macros` · 템플릿 — 디자이너1). **예외(회전 8 · QA1 제안)**: 스캔칸(`data-scan`) · 비밀번호 칸은 비운다. 행 · 카드마다 같은 폼이 반복되어 입력값만으로 어느 폼인지 가를 수 없는 인라인 폼(QUA-04 조치 · EQP-03 조치 · EQP-01 상태 · QUA-01 행 수정 · 대기가 여럿인 QUA-02 판정)은 되채우지 않는다 — 목록은 `docs/design/README.md` 「이식 결과 (디자이너2 · 회전 7)」 | **422** `{"code": "validation_error"|"hook_rejected", "message": "…", "fields": [{"name": …, "reason": …}]}` |
| 422 (**스캔 진입 GET** `?no=`) | **그 화면을 422 로 다시 그린다** — 사유를 큰 글씨로, `data-scan` 포커스 유지. 오류 화면으로 보내지 않는다 | **422** `validation_error` |
| 422 (그 밖 브라우저 GET) | 422 오류 화면(`_error.html`) | **422** |
| 정적 파일 | `/static/<파일>?v={{ asset_v }}` — `asset_v` = `static/` **전체** 파일의 최신 mtime(`templating.asset_version`) | — |
| 401 | GET 은 **303** → `/login?next=…` · POST 는 401 오류 화면 | **401** `{"code": "unauthorized", "message": "로그인이 필요합니다"}` |
| 403 · 404 · 501 · 503 · 500 | 그 상태코드의 오류 화면 | 그 상태코드 + `{"code": …, "message": …}` (501 은 `decision` 포함) |

- 로그인: `POST /login`(`login_id` · `password` · `next` · `device`) — 성공 **303**, 실패 **401**(로그인 화면을 401 로 다시 그린다).
- **테스트는 JSON 쪽으로 판정한다.** `TestClient` 기본 `Accept: */*`.
- `/health` 는 인증 없이 200(DB 끊기면 503) — `status` · `system` · `pack` · `core_version` · `db.ok` · `menus` · `screens` · `functions` · `placeholders` · `pack_screens` · `router_include_errors`. 접속 문자열 · 호스트 · DB 이름은 싣지 않는다.
- **인증 없이 열리는 것은 `/health` · `/static/*` · `/login` · `/error` · `POST /ifc/collect`(토큰 헤더 `X-Collect-Token` 로 인증 — `MES_COLLECT_TOKEN`) 뿐이다.** `/docs` · `/redoc` 은 404. `/openapi.json` 은 시스템 모듈 조회 권한자만.
- 개발용 역할 로그인 `POST /login/as`(D-605)는 **`MES_ENV=dev` 이고 요청 상대 주소가 루프백(127.0.0.0/8 · ::1)일 때만** 있다 — 그 밖은 404(`settings.dev_login_allowed` · `main.py` 미들웨어). `MES_ENV` 는 비면 `prod`. 로그아웃은 `POST /logout` 만(`GET` 405 — 다른 사이트 링크로 로그아웃시키지 못하게). 세션 쿠키 `HttpOnly` · `SameSite=Lax` · dev 가 아니면 `Secure`.
- **채널**: `?device=pop|mobile|board` 또는 로그인 때 고른 `device` 가 세션에 남는다. `core.yaml`/`pack.yaml: channels` 에 없는 화면을 그 채널로 열면 403. 현황판은 오류 화면에서도 자동 새로고침이 이어진다.
- **스캔 화면 알림**(`static/app.js`): 알림이 떠 있어도 스캔 글자가 스캔칸으로 들어가고 Enter 가 보낸다. 닫으면 포커스가 스캔칸으로. `data-scan` 은 화면에 하나.
- **용어 치환**: 응답 본문의 사용자 문구(알림 · 라벨 · 메뉴명 · 오류 메시지)는 `t()` 를 거친 것이다. JSON 의 `message` 도 치환된 문장이다. `code` · `fields[].name` 의 **컬럼 식별자**는 치환하지 않는다(`fields[].label` 에 치환어).

## 3. DB 제약 위반은 422 다

라우터가 먼저 검사하는 것이 원칙이다. 놓친 경우에도 500 이 되지 않게 `main.py` 가 `psycopg.errors.IntegrityError`(유니크 · FK · NOT NULL · CHECK · 계보 지킴이 트리거)를 **422** 로 바꾼다(`fields` 에 제약 이름과 DB 메시지). `psycopg.DataError`(NUL · 자릿수 초과 · 형식 오류)도 **422**.

## 4. 수집 수신 API (`POST /ifc/collect`) — 송월 Data Gateway 메시지와 같다

```json
{ "equip_code": "EQ-001", "ts": "2026-10-09T10:00:00+09:00", "source": "gateway",
  "tags": { "run_state": 1, "temp_c": 72.5, "count": 1234 }, "resend": false }
```

- 응답 200 `{"ok": true, "raw_id": …}`. `equip_code` 가 `bas_equipment` 에 없으면 **422**(버리지 않고 `ifc_collect_raw.rejected_reason` 에 남긴 뒤 422). 태그 키가 `bas_process_param`/`core.yaml: collect_tags` 에 없으면 저장하되 `unknown_tags` 로 센다.
- 멱등: `(equip_code, ts, source)` 유니크. 같은 메시지 재전송은 200 + `duplicate: true`.
- 토큰 불일치 401. 본문 형식 오류 422.

## 5. 이관 배치 CLI

`uv run python -m mescore.migrate <명령> --dir <폴더> [--dry-run]` — 명령은 `function-list.md` 의 `B-MIG-01~04`. 출력은 `파일  읽음  적재  갱신  건너뜀  오류` 한 줄씩 + `sys_migration_log` 한 행. 오류가 1건이라도 있으면 종료 코드 1, `--dry-run` 은 DB 에 쓰지 않는다.
