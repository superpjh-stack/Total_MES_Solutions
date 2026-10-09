# MES 표준플랫폼 — 명령 (CLAUDE.md 「명령」). 전부 `uv run …` — 시스템 python 을 쓰지 않는다.
# 팩은 `MES_PACK=<팩> make …` 로 고른다. DB 는 코어 단독 mes_core_db · 팩 mes_<팩>_db (한 번에 하나만 시드 · 스키마 재생성).
.PHONY: setup db-create db-schema db-seed db-reset pack-new pack-check pack-db contracts run test check-routes check-trace check-schema check-data check-security check-terms check-pack gate gate-full backup restore-check core-hash kpi-snapshot erp-flush

TOOLS := src/mescore/tools
PGHOST ?= /tmp
PORT ?= 8030
PACK := $(strip $(MES_PACK))
# DB 대상은 MES_PG_DSN(셸 · .env)을 앱과 같은 규칙으로 푼다 — 비면 mes_core_db / mes_<팩>_db (DEF-QA1-008 · tools/db_target.py).
# 쓰는 목표(setup · db-create · db-schema)에서만 한 번 계산한다(지연 · 메모).
_dbt = $(shell PGHOST=$(PGHOST) uv run python $(TOOLS)/db_target.py $(1))
DB = $(or $(_DB),$(eval _DB := $(call _dbt,name))$(_DB))
DB_DSN = $(or $(_DB_DSN),$(eval _DB_DSN := $(call _dbt,dsn))$(_DB_DSN))
DB_ADMIN = $(or $(_DB_ADMIN),$(eval _DB_ADMIN := $(call _dbt,admin))$(_DB_ADMIN))
PSQL = psql -q -d "$(DB_DSN)" -v ON_ERROR_STOP=1

setup:           # uv(Python 3.12) · 로컬 .env(난수 비밀) · DB 생성
	uv python pin 3.12 && uv sync
	uv run python $(TOOLS)/init_env.py
	@$(MAKE) --no-print-directory db-create
	@echo "DB $(DB) 준비됨 — 다음: make db-reset && make gate"

db-create:       # MES_PG_DSN 의 DB 가 없으면 만든다 (psql 줄은 DSN 비밀번호가 찍히지 않게 숨긴다)
	@echo "db-create → $(DB)"
	@psql -d "$(DB_ADMIN)" -Atc "select 1 from pg_database where datname='$(DB)'" | grep -q 1 || psql -q -d "$(DB_ADMIN)" -c 'create database "$(DB)"'

db-schema: db-create   # MES_PG_DSN 의 DB 스키마를 지우고 다시 만든다 (데이터가 전부 사라진다 — 한 번에 한 사람만). 팩이면 schema_ext.sql 도
	@echo "db-schema → $(DB) (drop schema public cascade)"
	@$(PSQL) -c 'set client_min_messages = warning; drop schema public cascade; create schema public;'
	@$(PSQL) -f src/mescore/db/schema.sql
	@$(PSQL) -f src/mescore/db/views.sql
	@if [ -n "$(PACK)" ] && [ -f packs/$(PACK)/schema_ext.sql ]; then $(PSQL) -f packs/$(PACK)/schema_ext.sql; fi
	@psql -d "$(DB_DSN)" -Atc "select '$(DB): 테이블 '||count(*) filter (where table_type='BASE TABLE')||' · 뷰 '||count(*) filter (where table_type='VIEW') from information_schema.tables where table_schema='public'"

db-seed:         # 코어 → 팩(process_params · inspection_items · seeds) → seed_dev1~3 (있는 것만). 두 번 돌려도 행 수가 같아야 한다 (G-C09)
	uv run python -m mescore.db.seed_core

db-reset: db-schema db-seed

pack-new:        # make pack-new NAME=<팩> — packs/_template 복사 (pack.yaml 의 pack 을 채운다)
	@test -n "$(NAME)" || { echo "NAME=<팩> 이 필요하다"; exit 1; }
	@test ! -e packs/$(NAME) || { echo "packs/$(NAME) 이 이미 있다"; exit 1; }
	cp -R packs/_template packs/$(NAME)
	sed -i '' 's/^pack: _template/pack: $(NAME)/' packs/$(NAME)/pack.yaml
	@echo "packs/$(NAME) 생성 — pack.yaml 의 name · company · terms 부터 채운다. 검증: MES_PACK=$(NAME) make pack-check"

pack-db:         # make pack-db NAME=<팩> (MES_PG_DSN 을 비우고 mes_<팩>_db 로) — 팩 DB 한 벌: createdb + 코어 스키마(+ schema_ext.sql) + 코어 시드 + 팩 시드(seed_core 가 pack.yaml 의 process_params · inspection_items · seeds 를 품는다). 팩이 PackError 면 팩 시드 단계에서 멈춘다
	@test -n "$(NAME)" || { echo "NAME=<팩> 이 필요하다"; exit 1; }
	@test -f packs/$(NAME)/pack.yaml || { echo "packs/$(NAME)/pack.yaml 이 없다"; exit 1; }
	@MES_PACK=$(NAME) MES_PG_DSN=postgresql:///mes_$(NAME)_db $(MAKE) --no-print-directory db-create db-schema
	MES_PACK=$(NAME) MES_PG_DSN=postgresql:///mes_$(NAME)_db uv run python -m mescore.db.seed_core
	@echo "mes_$(NAME)_db 준비됨 — 다음: MES_PACK=$(NAME) make check-pack test"

pack-check:      # 병합 규칙 R4~R6 (packs.load) — 위반이면 PackError
	@test -n "$(PACK)" || { echo "MES_PACK=<팩> 이 필요하다"; exit 1; }
	uv run python -c "from mescore.app import packs; p = packs.load('$(PACK)'); print('OK', p.name, '모듈', len(p.modules), '화면', len(p.screens), '역할', len(p.roles), '용어', len(p.terms), 'WARN', p.warnings)"

contracts:       # 렌더본 다시 찍기: db-schema.md §4 ← schema.sql + DB · screen-map.md §1(§4) ← core.yaml
	uv run python $(TOOLS)/gen_contracts.py

run:             # 8000 · 8020 은 다른 사업이 쓴다
	uv run uvicorn mescore.app.main:app --app-dir src --port $(PORT) --reload

test:
	uv run pytest -q

check-routes:    # G-C03 — 화면 51 + 공통 5 (+ 팩) HTTP 200 · placeholder 수 · 권한 없음 403
	uv run python $(TOOLS)/check_routes.py

check-trace:     # G-C01 · G-C02 (· G-P02 · G-P03) — core.yaml ↔ nav ↔ function-list.md ↔ 라우트 ↔ 테스트
	uv run python $(TOOLS)/check_trace.py

check-schema:    # G-C04 (· G-P02) — 계약 ↔ 실제 DB
	uv run python $(TOOLS)/check_schema.py

check-data:      # G-C05~G-C12 · G-C24 — QA2 가 만든다
	@test -f $(TOOLS)/check_data.py || { echo "G-C05  쓰기 경계  미검증  tools/check_data.py 없음 (QA2)"; exit 0; }
	uv run python $(TOOLS)/check_data.py

check-security:  # G-C13~G-C20 — QA3 가 만든다
	@test -f $(TOOLS)/check_security.py || { echo "G-C13  4채널  미검증  tools/check_security.py 없음 (QA3)"; exit 0; }
	uv run python $(TOOLS)/check_security.py

check-terms:     # G-C23 — 코어 금지어 0 · 템플릿 t() 누락 (MES_PACK 이 있으면 G-P05 도)
	uv run python $(TOOLS)/check_terms.py
	@if [ -n "$(PACK)" ]; then uv run python $(TOOLS)/check_terms.py --pack; fi

check-pack:      # G-P01 — 코어 해시 변동 0 · ALTER 0 · 경로 재정의 0 · write_scope 밖 쓰기 0 · lot_genealogy 직접 INSERT 0
	@test -n "$(PACK)" || { echo "MES_PACK=<팩> 이 필요하다"; exit 1; }
	uv run python $(TOOLS)/check_pack.py

gate:            # G-C01~G-C24 (코어 단독 MES_PACK=) → packs/ 의 팩마다 G-P01~G-P06. 판정표. 시드 멱동(G-C09)은 gate-full
	@MES_PACK= MES_ADDONS= uv run python $(TOOLS)/gate.py

gate-full:       # 시드를 한 번 더 돌려 행 수 diff 를 잰다 — 다른 사람이 시드 · 스키마를 돌리는 중에는 쓰지 않는다. 종료 판정은 이것으로
	@MES_PACK= MES_ADDONS= uv run python $(TOOLS)/gate.py --run-seeds

kpi-snapshot:    # KPI 스냅샷 배치 (kpi_snapshot — 개발3 stats.snapshot). 날짜를 주려면 DAY=YYYY-MM-DD
	uv run python -m mescore.app.stats snapshot $(DAY)

erp-flush:       # ifc_outbox 큐 비우기 — 어댑터가 501(D-02)이면 행은 `미확정` 으로 남는다 (G-C16)
	uv run python -c "from mescore.app import erp; print(erp.flush())"

core-hash:       # R1 기준값 outputs/core.sha256 — 아키텍트가 코어를 고친 뒤에만 다시 찍는다
	uv run python $(TOOLS)/core_hash.py

backup:          # G-C20 — MES_PG_DSN 의 DB 를 pg_dump → backups/<DB>-<일시>.dump + 테이블별 행 수(.json). backups/ 는 gitignore
	uv run python $(TOOLS)/backup.py backup

restore-check:   # G-C20 — MES_PG_DSN 의 DB 로 뜬 가장 최근 덤프를 별도의 임시 DB 에 복구해 행 수를 대조하고 임시 DB 를 지운다
	uv run python $(TOOLS)/backup.py restore-check
