# Rodem MES Solution — MES 표준플랫폼

중소 제조기업용 MES(제조 실행 시스템)의 공통 골격을 **코어 한 벌**로 만들고, 업종마다 다른 부분은 **업종 팩**으로 붙이는 플랫폼입니다.
새 업종 MES 는 코어를 복사하지 않고, 코어 수정 없이 팩만 써서 만듭니다.

```
업종 팩 (kimchi · foodservice · printfilm · 새 팩 …)
  용어 사전 · 메뉴 추가/숨김 · 확장 테이블 · 전용 화면 · 훅
        │  pack.yaml + schema_ext.sql + routers/ + hooks.py
        ▼
표준 코어 (업종 무관 · 고치지 않는다)
  기준정보 · 수주/계획 · 작업지시 · 자재 · 생산실적(POP) · 품질 · 설비 · 출하 · LOT 추적
  현황/KPI · 시스템 · 인터페이스   /   관리자 Web · 현장 POP · 모바일 · 현황판
```

이 시스템의 중심은 두 가지입니다. 업종이 바뀌어도 이 둘은 선언만 바뀝니다.

- **LOT 계보** — `lot` + `lot_genealogy` 재귀 계보로 입고 → 투입 → 생산 → 분할 · 합병 → 출하를 거슬러 추적합니다.
- **공정 측정값** — `bas_process_param` 선언만으로 측정값 입력 폼이 생기고 `pop_measure` 에 기록됩니다. 공정마다 테이블을 만들지 않습니다.

## 규모

| 항목 | 수 |
|---|---|
| 코어 모듈 | 12 (`bas ord job mat pop qua eqp shp trc kpi sys ifc`) |
| 화면 | 51 + 공통 5 |
| 기능 | 132 + 이관 배치 4 |
| 테이블 | 52 |
| 역할 | 4 (관리자 · 생산 · 품질 · 현장) |
| 채널 | 4 (관리자 Web · 현장 POP · 모바일 · 현황판) |
| 확장 지점 | 7 |
| 참조 팩 | 3 (`kimchi` · `foodservice` · `printfilm`) + `_template` |

## 기술 스택

- Python 3.12 · [uv](https://docs.astral.sh/uv/) · FastAPI · Jinja2 서버 렌더링
- PostgreSQL 17 (psycopg 3)
- pytest · Makefile 게이트

## 빠른 시작

PostgreSQL 17 과 uv 가 설치되어 있어야 합니다. 기본 DB 접속은 unix socket(`/tmp`)입니다.

```bash
make setup       # Python 3.12 · 의존성 · 로컬 .env 생성(비밀값은 난수)
make db-reset    # 코어 스키마 + 시드 (DB 데이터를 모두 지우고 다시 만든다)
make run         # http://127.0.0.1:8030
```

업종 팩으로 띄우려면 명령 앞에 `MES_PACK` 을 붙입니다.

```bash
make pack-db NAME=kimchi          # 팩 DB 한 벌 (mes_kimchi_db)
MES_PACK=kimchi make run
```

화면을 시험할 샘플 데이터는 별도 DB 에 넣습니다. 샘플은 모두 `SMP-` 코드와 `(예시)` 이름을 가지며 실제 회사 데이터가 아닙니다.

```bash
MES_PG_DSN=postgresql:///mes_demo_db uv run python scripts/sample.py   # 업무 테이블마다 약 100건
make sample-today                                                       # 오늘 날짜 입고 · 생산 · 출하 (하루 한 번)
```

## 환경 변수

`.env.example` 을 참고합니다. 실제 값은 로컬 `.env`(git 에 올리지 않음)에만 둡니다.

| 변수 | 뜻 |
|---|---|
| `MES_PACK` | 업종 팩. 비우면 코어 단독 |
| `MES_PG_DSN` | DB 접속 문자열. 비우면 `mes_core_db` 또는 `mes_<팩>_db` |
| `MES_ENV` | `prod`(기본) 또는 `dev` |
| `MES_SESSION_SECRET` · `MES_SEED_PASSWORD` | 세션 서명 비밀 · 시드 계정 비밀번호 (`make setup` 이 만든다) |
| `MES_ADDONS` | 코어 밖 선택 모듈. `agent` = MES AI Agent |
| `ANTHROPIC_API_KEY` | AI Agent 의 자유 질문 · 답변용 Claude API 키 (선택) |

## 업종 팩 만들기

```bash
make pack-new NAME=towel     # packs/_template 복사
MES_PACK=towel make pack-check
```

팩은 `packs/<팩>/` 안에서만 만듭니다. 코어 테이블 변경, 코어 경로 재정의, 계보 직접 쓰기는 금지이며 `check_pack` 이 판정합니다.
규칙은 [`contracts/pack-contract.md`](contracts/pack-contract.md) 에 있습니다.

## MES AI Agent (선택 모듈)

`.env` 에 `MES_ADDONS=agent` 를 두면 사이드바 끝에 **MES AI Agent** 메뉴가 생깁니다. 코어 밖 패키지 `src/mesagent` 이며 끄면 메뉴와 경로가 모두 사라집니다.

- **호출어** — 「로뎀」 이라고 부른 질문에만 답합니다. 예) `로뎀, 오늘의 재고량?`
- **음성 질의 · 답변** — 브라우저 내장 음성 인식 · 합성을 씁니다(Chrome · Edge, localhost 또는 HTTPS).
- **오케스트레이터** — 질문마다 정형 지표 SQL, LLM 이 쓰는 DB 조회 SQL, RAG 문서 조회 중 어느 길로 풀지 정합니다.
- **정형 지표** — 재고량 · 생산량 · 출하량 · 입고량 · 불량률 · 작업지시 현황은 API 키 없이도 답합니다.
- **안전** — SELECT 한 문장만, 읽기 전용 트랜잭션, 5초 · 200행 상한, 역할별 테이블 제한, 질문과 SQL 은 접근 로그에 남습니다.

## 배포 (Docker)

`docker-compose.yml` 은 PostgreSQL 17 · 앱 · Caddy 세 컨테이너를 띄웁니다. Caddy 가 Let's Encrypt 인증서로 HTTPS 를 맡습니다.
운영 세션 쿠키가 `Secure` 라서 HTTP 로는 로그인되지 않기 때문입니다(D-42 · D-50).

```bash
MES_DOMAIN=mes.example.com MES_SAMPLE=1 docker compose up -d --build
docker compose logs app | grep "첫 기동"      # 시드 계정 비밀번호 (첫 기동 때 한 번만 찍힌다)
```

| 변수 | 뜻 |
|---|---|
| `MES_DOMAIN` | **필수.** 이 서버를 가리키는 도메인. Hostinger VPS 는 기본 호스트 이름(`srvNNNN.hstgr.cloud`)을 써도 된다 |
| `MES_SAMPLE` | `1` 이면 빈 DB 에 샘플 데이터(예시)를 넣고, 기동할 때마다 오늘 날짜 데이터를 하루 한 번 채운다 |
| `MES_PACK` | 업종 팩. 비우면 코어 단독 |
| `ANTHROPIC_API_KEY` | AI Agent 자유 질문용 키 (선택) |
| `MES_BUILD_CONTEXT` | 이미지 소스. 서버에 저장소가 없으면 `https://github.com/superpjh-stack/Total_MES_Solutions.git#main` |
| `MES_HTTP_PORT` · `MES_HTTPS_PORT` | 기본 80 · 443. 80 을 다른 앱이 쓰면 다른 번호로 둔다(인증서는 443 만으로 받는다) |
| `MES_SESSION_SECRET` · `MES_SEED_PASSWORD` | 비우면 첫 기동 때 난수로 만들어 볼륨 `appdata` 에 둔다 |

- 서버의 443 포트가 비어 있고 밖에서 열려 있어야 하며, 도메인의 DNS A 레코드가 서버 IP 를 가리켜야 인증서가 나옵니다.
- DB 는 compose 내부망에만 있고 밖으로 열지 않습니다. 데이터는 볼륨 `pgdata` 에 남습니다.
- 로컬에서 `docker compose` 를 돌리면 저장소의 `.env` 가 값으로 읽힙니다. 운영 서버에는 `.env` 를 두지 않습니다.

## 검증

```bash
make test        # pytest
make gate        # 코어 단독 게이트 G-C01~G-C24 → 팩마다 G-P01~G-P06
make gate-full   # 시드 재실행 포함. 종료 판정은 이것으로 한다
```

## 폴더 구조

```
src/mescore/      코어 — app/(라우터 · 템플릿 · 공용 모듈) · db/(스키마 · 시드) · tools/(검사 도구 · 게이트) · migrate/
src/mesagent/     선택 모듈 MES AI Agent
packs/            업종 팩 — kimchi · foodservice · printfilm · _template
domains/          메인 › 도메인별 프로세스 카탈로그 (김치 · 급식 · 인쇄 · 금속)
contracts/        코드 계약 — 기능표 · DB 스키마 · 화면 지도 · 인터페이스 · API · 팩 계약
tests/            코어 테스트
scripts/          샘플 데이터 스크립트
outputs/          게이트 산출물 · 코어 해시
```

## 문서

| 문서 | 내용 |
|---|---|
| [`intro.md`](intro.md) · [`problem.md`](problem.md) · [`spec.md`](spec.md) | 소개 · 문제 정의 · 명세 (정본) |
| [`goal.md`](goal.md) | 목표 · 수용 게이트 · 팀 편성 |
| [`CLAUDE.md`](CLAUDE.md) | 작업 규약 · 코드 규약 |
| [`contracts/`](contracts/) | 개발 계약 |
| [`decisions.md`](decisions.md) | 결정 대장 D-nn |
| [`progress.md`](progress.md) | 검증된 현황 |

## 아직 정해지지 않은 것

- **사내망 HTTP 운영 (D-42)** — Docker 배포는 Caddy HTTPS 로 해결했습니다(D-50). HTTPS 없이 사내망 HTTP 로만 쓰는 경우의 설정은 아직 정하지 않았습니다.
- **설비 알람 (D-501)** — 테이블을 52 → 54 로 늘릴지 결정을 기다립니다.
