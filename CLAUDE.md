# CLAUDE.md

**MES 표준플랫폼** — 코어 한 벌(`src/mescore`) + 업종 팩(`packs/<팩>`). 한 배포 = 코어 + 팩 하나(`MES_PACK`).
이 시스템의 본체는 **`lot` + `lot_genealogy` 재귀 계보**와 **`bas_process_param` → `pop_measure` 측정값**이다. 업종이 바뀌어도 이 둘은 선언만 바뀐다.
완료 기준: **코어만으로 입고 → 출하 → 역추적이 돌고, 참조 팩 3개(kimchi · foodservice · printfilm)가 코어 수정 0 으로 각 사업의 핵심 시나리오를 재현한다.**

## 먼저 읽는다

1. **`goal.md`** — 목표 · 수용 게이트 G-C01~G-C24 · G-P01~G-P06 · 팀 편성 · 루프 프로토콜 · 기동 프롬프트. **전원 필독. 사람만 고친다.**
2. **`intro.md` · `problem.md` · `spec.md`** — 정본. 모듈 12 · 테이블 52 · 확장 지점 7 · 금지어의 출처. 읽기만 한다.
3. `contracts/` — 코드 계약. **개발은 이것만 보고 만든다.** 계약에 없는 것을 혼자 정하지 않는다.
   - `function-list.md` 기능 136줄(화면 132 + 이관 배치 4) — ID · API · 쓰는 테이블 · 권한 · 계약 문장
   - `db-schema.md` 테이블 52 · 쓰기 경계 · `lot_genealogy` 설계 근거
   - `screen-map.md` 화면 51 + 공통 5 → 경로 · 담당 · 채널 · 파일 소유권
   - `interfaces.md` 공용 모듈 시그니처(`packs nav rbac numbering lineage printing stats collect erp audit`) · `api-contract.md` 오류 계약
   - `pack-contract.md` 팩이 지켜야 할 것 — `pack.yaml` 규격 · 확장 지점 7 · 병합 규칙 · `check_pack` 판정
   - `migration-files.md` 표준 Import 파일 4종
4. `decisions.md` — 결정 대장 D-nn (`확정` / `가설` / `차단` / `코어 변경 요청`). **여기 없는 것을 마음대로 정하지 않는다.**
5. `progress.md` — 검증된 현황의 유일한 진실. 실측값 + 검증 명령만 적는다.

계약과 코드가 다르면 **코드가 맞다** — 발견자가 계약을 고친다. 단 `schema.sql` · `core.yaml` · `function-list.md` · `pack-contract.md` 는 아키텍트만 고친다(요청은 `progress-devN.md` §3).

## 정본 (읽기 전용)

- `intro.md` · `problem.md` · `spec.md` — 이 폴더 루트. 수치가 어긋나면 `spec.md` 가 맞고 `decisions.md` 에 적는다.
- 근거 사업 폴더 `../Limjingang Kimchi MES Platform` · `../NeedsFood MES Platform` · `../lcomFine MES` · `../Songwol Data Gateway` — **읽기만.** 구조와 작성법을 이식하되 업종어 · 회사 고정값은 가져오지 않는다.

## 환경

- PostgreSQL 17 (unix socket `/tmp`). DB **`mes_core_db`**(코어 단독) · `mes_kimchi_db` · `mes_foodservice_db` · `mes_printfilm_db`(팩별). 포트 **8030**(8000 니즈푸드 · 8020 엘컴화인이 쓴다).
- `uv` / Python 3.12. **명령은 전부 `uv run …`** — 시스템 `python3` 를 쓰지 않는다.
- 환경변수 접두 `MES_` (`.env.example`). `MES_PACK` 이 팩을 고른다(비우면 코어 단독). 비밀(`MES_SESSION_SECRET` · `MES_SEED_PASSWORD`)은 로컬 `.env`(gitignore)에만 — **코드 · 문서에 값을 적지 않는다**(G-C19). `make setup` 이 `.env` 를 난수로 만든다.
- **이 폴더 밖은 읽기만 한다.** push · 배포 · 외부 전송 없음.

## 명령

`make setup` · `db-schema` · `db-seed` · `db-reset` · `pack-new NAME=…`(`_template` 복사) · `pack-check`(병합 규칙) · `contracts`(렌더본 다시 찍기) · `run` · `test` · `check-routes` · `check-trace` · `check-schema` · `check-data` · `check-security` · `check-terms` · `check-pack` · **`gate`**(코어 단독 → 팩 3 판정표) · **`gate-full`**(시드 재실행 포함 — 종료 판정은 이것으로) · `backup` · `restore-check`.
모든 `make` 는 `MES_PACK=<팩>` 접두로 팩을 고른다. 시드 · 스키마 재생성은 한 번에 하나만(`db-schema` 는 데이터를 전부 지운다).

## 규모 (`spec.md` 에서 센 값 — `make check-trace`)

코어 모듈 **12**(`bas ord job mat pop qua eqp shp trc kpi sys ifc`) · 화면 **51** + 공통 5 · 기능 **132** + 이관 배치 **4** · 테이블 **52** · 공용 모듈 9 · 역할 4 · 권한 48칸(입력 18 · 조회 23 · 없음 7) · 채널 4 · 확장 지점 **7** · 참조 팩 3 + `_template`.

| 담당 | 모듈 | 기능 | 공용 모듈 | 참조 팩 |
|---|---|---|---|---|
| 개발1 | `bas` `job` `sys` + 로그인 · 메인 | 59 | `numbering.py` | `foodservice` |
| 개발2 | `mat` `pop` `qua` `eqp` | 38 | `lineage.py` · `printing.py` · `collect.py` · `ui.measure_fields` | `printfilm` |
| 개발3 | `ord` `shp` `trc` `kpi` `ifc` + 이관 배치 | 35 + 4 | `stats.py` · `erp.py` · `migrate/` | `kimchi` |

## 코드 규약 (contracts/interfaces.md)

- 패키지 `mescore` (`src/mescore/{app,db,tools}`). 라우터는 `app/routers/<모듈>.py` 에 `router = APIRouter()` — `main.py` 가 자동 include 한다(코어 → 팩 순). **개발자는 `main.py` · `packs.py` · `core.yaml` 을 만지지 않는다.**
- 경로: `nav.path_of("BAS-01")`. 화면 GET 을 등록하면 그 경로의 placeholder 가 빠진다. 메서드 · 경로는 `function-list.md` 의 `API` 열과 글자 그대로.
- 권한: 화면 `rbac.require_screen("BAS-01")` · 기능 `rbac.require_fn("F-BAS-01")`. **쓰기 엔드포인트에 `require_fn` 이 빠지면 조회 역할의 쓰기가 통과한다.** 권한 표 · 역할은 DB 데이터.
- 세션: 사용자 상태는 **요청마다 DB**(`rbac.current_user`). 중지 · 잠금 · 로그아웃한 세션은 다음 요청부터 401.
- DB: `conn.q / q1 / x / tx`. 함께 성공해야 하는 것은 `tx()` 하나에. 작업지시 행 잠금 규칙은 `interfaces.md` §1.
- 계보: `lot_genealogy` 에 쓰는 곳은 `lineage` 뿐. 번호는 `numbering` 뿐. 집계 SQL 은 `stats` 뿐. 라벨 · 바코드는 `printing` 뿐. 수집 수신은 `collect` 뿐.
- 측정값: 공정별 값을 위해 테이블을 만들지 않는다. `bas_process_param` 선언 → `ui.measure_fields` 자동 폼 → `pop_measure` 기록. 시계열만 `eqp_collect` 또는 팩 테이블(D-04).
- 용어: 템플릿의 사용자 문구는 **`{{ t("생산 LOT") }}`** 를 거친다. 코어 코드 · 템플릿 · 시드에 `spec.md` §12 금지어 0(G-C23).
- 훅: 코어 쓰기 라우터는 `packs.hook("on_…")(cur, row, user)` 를 정해진 자리(`interfaces.md` §9)에서 부른다. 훅이 없으면 아무 일도 없다. `HookError` → 422.
- 오류: `http.validation_error`(422) · `http.not_found`(404) · `http.undecided("D-nn")`(501). 쓰기 성공 `http.saved(request, msg)` 직후 `audit.log_change(...)`.
- 스캔 화면: `ui.scan_box` 하나(`data-scan`). 없는 번호는 **그 화면을 422 로 다시 그린다**. 스크립트는 `static/app.js` 만.
- 렌더: `templating.render(request, tpl, ctx, screen_id=...)`. 공용 매크로 `templates/home/_macros.html`.
- 테스트: 기능마다 하나 이상, `@pytest.mark.fn("F-BAS-01")`. 코어 테스트(`tests/`)는 **어떤 팩에서도** 통과해야 한다. 팩 테스트는 `packs/<팩>/tests/`.
- 팩: `packs/<팩>/` 안에서만. 코어 테이블 `ALTER` 금지 · 코어 경로 재정의 금지 · `write_scope` 밖 쓰기 금지 · `lot_genealogy` 직접 INSERT 금지. 확장 지점 7 밖이 필요하면 `decisions.md` 에 `코어 변경 요청`.

## 작업 원칙

- **지어내지 않는다.** 코어 시드는 `(예시)`. 참조 팩 시드는 근거 사업 시드 중 `(예시)` 가 붙은 것만. 데이터가 없으면 `미수집`, 정해지지 않았으면 `미확정 (D-nn)`.
- **조용한 실패 금지.** `try/except` 로 하드코딩 결과를 끼워넣지 않는다.
- **쓰기 경계.** 모듈은 자기 테이블에만 쓴다(`db-schema.md` §2). **`trc` · `kpi` 는 어떤 테이블에도 쓰지 않는다**(지표 정의 · 스냅샷 배치 제외).
- **범위 밖 금지.** 설비 제어 · AI · 실 외부 연계는 메뉴 · 엔드포인트 · 테이블 어디에도 만들지 않는다.
- **용어.** 코어는 중립어(품목 · LOT · 작업지시 · 실적 · 측정값 · 검사 · 출하 · 추적 · 분할 · 합병). 업종어는 팩의 `terms` 로만.
- **한 파일은 한 사람만 만진다.** 소유권은 `screen-map.md` §3. 팩 폴더는 그 팩 담당만.
- **게이트를 낮추지 않는다.** 금지어를 빼거나 `write_scope` 를 넓혀 통과시키는 것도 낮추는 것이다.
- 정본의 결함 · 모순은 고치지 말고 `decisions.md` 에 적는다.
