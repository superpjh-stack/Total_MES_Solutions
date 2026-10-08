-- MES 표준플랫폼 코어 스키마 — 테이블 52 (contracts/db-schema.md §4 의 원본). 아키텍트만 고친다.
-- 적용: make db-schema (public 스키마를 지우고 다시 만든다 — 데이터가 전부 사라진다). 뷰는 views.sql.
-- 규약: 소문자 snake_case · 모듈 접두어 · *_code 유니크 · *_no 유니크 · *_id FK(on delete restrict) · *_yn char(1) · status text + CHECK.
-- 공통 컬럼 6(id · created_at · created_by · updated_at · updated_by · attrs)은 맨 아래 DO 블록이 전 테이블에 붙인다 —
-- 표(db-schema.md §4)에는 적지 않는다. `-- @table 이름 | 모듈 | 설명` 과 컬럼 끝의 `-- 설명` 을 tools/gen_contracts.py 가 읽는다.
-- 금지어 0 (G-C23): 이 파일에는 업종어가 없다. 팩 테이블은 packs/<팩>/schema_ext.sql 의 x_<팩>_* 뿐이다.

set client_min_messages = warning;

-- ════════════════════════════════════════════════════════════════════
-- bas 기준정보 (10)
-- ════════════════════════════════════════════════════════════════════

-- @table bas_process | bas | 공정 | 셋 다
create table bas_process (
    id            bigserial primary key,
    process_code  text not null,                                   -- 공정 코드 (유니크)
    process_name  text not null,                                   -- 공정 이름
    seq           integer not null default 0,                      -- 순서
    use_yn        char(1) not null default 'Y',                    -- 사용 여부
    constraint bas_process_code_uq unique (process_code),
    constraint bas_process_use_chk check (use_yn in ('Y', 'N'))
);

-- @table bas_item | bas | 품목 | 셋 다
create table bas_item (
    id         bigserial primary key,
    item_code  text not null,                                      -- 품목 코드 (유니크)
    item_name  text not null,                                      -- 품목명
    item_type  text not null,                                      -- 구분 — 공통코드 ITEM_TYPE (제품/반제품/원재료/부자재)
    spec       text,                                               -- 규격
    unit       text,                                               -- 단위
    use_yn     char(1) not null default 'Y',                       -- 사용 여부
    constraint bas_item_code_uq unique (item_code),
    constraint bas_item_use_chk check (use_yn in ('Y', 'N'))
);

-- @table bas_bom | bas | BOM 헤더 | 임진강 `BAS_BOM` · 니즈푸드 BOM 테이블
create table bas_bom (
    id       bigserial primary key,
    item_id  bigint not null references bas_item (id),             -- 상위 품목
    version  text not null default '1',                            -- 버전
    use_yn   char(1) not null default 'Y',                         -- 사용 여부
    constraint bas_bom_item_version_uq unique (item_id, version),
    constraint bas_bom_use_chk check (use_yn in ('Y', 'N'))
);

-- @table bas_bom_dtl | bas | BOM 구성품 | 임진강 `BAS_BOM_DTL`
create table bas_bom_dtl (
    id                 bigserial primary key,
    bom_id             bigint not null references bas_bom (id),    -- BOM 헤더
    component_item_id  bigint not null references bas_item (id),   -- 구성품 품목 (자기 자신 금지는 라우터가)
    qty                numeric(18,3) not null,                     -- 소요량
    unit               text,                                       -- 단위
    loss_rate          numeric(7,3) not null default 0,            -- 손실률(%)
    seq                integer not null default 0,                 -- 순서
    constraint bas_bom_dtl_qty_chk check (qty > 0)
);
create index bas_bom_dtl_bom_idx on bas_bom_dtl (bom_id);

-- @table bas_process_param | bas | 공정 측정값 정의 (E3) — 이 행이 POP 종료 폼을 만든다 | 임진강 `SLT_STD WSH_STD`(기준) + 니즈푸드 `BAS_PROCESS_STD` 의 일반화 — **테이블 폭발을 막는 자리**
create table bas_process_param (
    id           bigserial primary key,
    process_id   bigint not null references bas_process (id),      -- 공정
    param_key    text not null,                                    -- 키 (영문 — pop_measure.param_key · collect 태그와 잇는다)
    label        text not null,                                    -- 화면 라벨
    unit         text,                                             -- 단위
    value_type   text not null default 'number',                   -- 형식 number/text/bool/select
    choices      jsonb,                                            -- select 일 때 선택지 목록
    min_value    numeric(18,4),                                    -- 하한 (범위 이탈은 저장 + deviated)
    max_value    numeric(18,4),                                    -- 상한
    required_yn  char(1) not null default 'N',                     -- 필수 여부 (누락 422)
    source       text not null default 'manual',                   -- 수집원 manual/collect
    collect_tag  text,                                             -- collect 일 때 태그 이름 (기본 param_key)
    agg          text not null default 'last',                     -- collect 대표값 last/avg/max/min
    seq          integer not null default 0,                       -- 순서
    use_yn       char(1) not null default 'Y',                     -- 사용 여부
    constraint bas_process_param_key_uq unique (process_id, param_key),
    constraint bas_process_param_type_chk check (value_type in ('number', 'text', 'bool', 'select')),
    constraint bas_process_param_source_chk check (source in ('manual', 'collect')),
    constraint bas_process_param_agg_chk check (agg in ('last', 'avg', 'max', 'min')),
    constraint bas_process_param_req_chk check (required_yn in ('Y', 'N')),
    constraint bas_process_param_use_chk check (use_yn in ('Y', 'N'))
);

-- @table bas_equipment | bas | 설비 | 셋 다 + 송월 `BAS_EQUIPMENTS`
create table bas_equipment (
    id          bigserial primary key,
    equip_code  text not null,                                     -- 설비 코드 (유니크 · collect 의 equip_code 와 1:1)
    equip_name  text not null,                                     -- 설비 이름
    process_id  bigint references bas_process (id),                -- 공정
    collect_yn  char(1) not null default 'N',                      -- 수집 설비 여부
    use_yn      char(1) not null default 'Y',                      -- 사용 여부
    constraint bas_equipment_code_uq unique (equip_code),
    constraint bas_equipment_collect_chk check (collect_yn in ('Y', 'N')),
    constraint bas_equipment_use_chk check (use_yn in ('Y', 'N'))
);

-- @table bas_partner | bas | 거래처 | 셋 다
create table bas_partner (
    id            bigserial primary key,
    partner_code  text not null,                                   -- 거래처 코드 (유니크)
    partner_name  text not null,                                   -- 거래처명
    partner_type  text not null,                                   -- 구분 — 공통코드 PARTNER_TYPE (고객/공급/외주)
    contact       text,                                            -- 연락처
    use_yn        char(1) not null default 'Y',                    -- 사용 여부
    constraint bas_partner_code_uq unique (partner_code),
    constraint bas_partner_use_chk check (use_yn in ('Y', 'N'))
);

-- @table sys_role | sys | 역할 | 셋 다
create table sys_role (
    id         bigserial primary key,
    role_code  text not null,                                      -- 역할 코드 (유니크 · ADMIN 시드 필수)
    role_name  text not null,                                      -- 역할 이름
    use_yn     char(1) not null default 'Y',                       -- 사용 여부
    constraint sys_role_code_uq unique (role_code),
    constraint sys_role_use_chk check (use_yn in ('Y', 'N'))
);

-- @table sys_user | sys | 사용자 | 셋 다
create table sys_user (
    id                   bigserial primary key,
    login_id             text not null,                            -- 로그인 ID (유니크)
    user_name            text not null,                            -- 이름
    password_hash        text not null,                            -- 비밀번호 해시 (PBKDF2) — 평문 없음
    role_id              bigint not null references sys_role (id), -- 역할
    worker_id            bigint,                                   -- 작업자 연결 (선택 · FK 는 bas_worker 뒤에 붙인다)
    status               text not null default '사용',             -- 상태 사용/중지/잠금
    fail_count           integer not null default 0,               -- 로그인 실패 횟수
    last_login_at        timestamptz,                              -- 마지막 로그인
    password_changed_at  timestamptz not null default now(),       -- 비밀번호 변경 시각 — 바뀌면 그 전 세션이 전부 끊긴다 (D-19)
    constraint sys_user_login_uq unique (login_id),
    constraint sys_user_status_chk check (status in ('사용', '중지', '잠금'))
);

-- @table bas_worker | bas | 작업자 | 임진강 · 니즈푸드
create table bas_worker (
    id           bigserial primary key,
    worker_code  text not null,                                    -- 작업자 코드 (유니크)
    worker_name  text not null,                                    -- 이름
    process_id   bigint references bas_process (id),               -- 담당 공정
    user_id      bigint references sys_user (id),                  -- 사용자 계정 (선택)
    use_yn       char(1) not null default 'Y',                     -- 사용 여부
    constraint bas_worker_code_uq unique (worker_code),
    constraint bas_worker_use_chk check (use_yn in ('Y', 'N'))
);
alter table sys_user add constraint sys_user_worker_fk foreign key (worker_id) references bas_worker (id);

-- @table bas_defect_code | bas | 불량코드 | 엘컴화인 · 임진강 `QUA_DEFECT_TYPE`
create table bas_defect_code (
    id           bigserial primary key,
    defect_code  text not null,                                    -- 불량 코드 (유니크)
    defect_name  text not null,                                    -- 불량 이름
    process_id   bigint references bas_process (id),               -- 공정 (선택)
    use_yn       char(1) not null default 'Y',                     -- 사용 여부
    constraint bas_defect_code_uq unique (defect_code),
    constraint bas_defect_code_use_chk check (use_yn in ('Y', 'N'))
);

-- @table bas_code | bas | 공통코드 (그룹 + 코드 한 테이블) | 셋 다
create table bas_code (
    id          bigserial primary key,
    group_code  text not null,                                     -- 그룹 (코어 그룹은 core.yaml: code_groups)
    code        text not null,                                     -- 코드
    code_name   text not null,                                     -- 이름
    seq         integer not null default 0,                        -- 순서
    is_core     char(1) not null default 'N',                      -- 코어 예약 코드 여부 (삭제 422)
    use_yn      char(1) not null default 'Y',                      -- 사용 여부
    constraint bas_code_group_code_uq unique (group_code, code),
    constraint bas_code_core_chk check (is_core in ('Y', 'N')),
    constraint bas_code_use_chk check (use_yn in ('Y', 'N'))
);

-- ════════════════════════════════════════════════════════════════════
-- ord 수주 · 계획 (4)
-- ════════════════════════════════════════════════════════════════════

-- @table ord_order | ord | 수주 헤더 | 임진강 `ORD_ORDER` · 니즈푸드 `SAL_ORDER` · 엘컴화인 `sales_order`
create table ord_order (
    id          bigserial primary key,
    order_no    text not null,                                     -- 수주 번호 (유니크 · numbering ORDER)
    partner_id  bigint not null references bas_partner (id),       -- 거래처
    order_date  date not null,                                     -- 수주일
    due_date    date,                                              -- 납기
    status      text not null default '등록',                      -- 상태 등록/진행/완료/취소
    note        text,                                              -- 비고
    constraint ord_order_no_uq unique (order_no),
    constraint ord_order_status_chk check (status in ('등록', '진행', '완료', '취소'))
);

-- @table ord_order_dtl | ord | 수주 상세 | ord_order 와 같다 (§1: 임진강 `ORD_*` · 니즈푸드 `SAL_ORDER*`)
create table ord_order_dtl (
    id        bigserial primary key,
    order_id  bigint not null references ord_order (id),           -- 수주 헤더
    line_no   integer not null,                                    -- 줄 번호
    item_id   bigint not null references bas_item (id),            -- 품목
    qty       numeric(18,3) not null,                              -- 수량
    unit      text,                                                -- 단위
    status    text not null default '대기',                        -- 상태 대기/지시/출하 (job 이 지시 연결 상태만 바꾼다)
    constraint ord_order_dtl_line_uq unique (order_id, line_no),
    constraint ord_order_dtl_status_chk check (status in ('대기', '지시', '출하'))
);

-- @table ord_order_hist | ord | 수주 변경 이력 | 임진강 `ORD_ORDER_HIST`
create table ord_order_hist (
    id            bigserial primary key,
    order_id      bigint not null references ord_order (id),       -- 수주 헤더
    changed_at    timestamptz not null default now(),              -- 변경 시각
    changed_by    text,                                            -- 변경자 login_id
    field         text not null,                                   -- 바뀐 항목
    before_value  text,                                            -- 전 값
    after_value   text                                             -- 후 값
);
create index ord_order_hist_order_idx on ord_order_hist (order_id, changed_at desc);

-- @table ord_plan | ord | 생산계획 | 임진강 `ORD_PLAN` · 니즈푸드 `PRD_PLAN`
create table ord_plan (
    id            bigserial primary key,
    plan_no       text not null,                                   -- 계획 번호 (유니크 · numbering PLAN)
    order_dtl_id  bigint references ord_order_dtl (id),            -- 수주 상세 (선택)
    item_id       bigint not null references bas_item (id),        -- 품목
    plan_date     date not null,                                   -- 계획일
    plan_qty      numeric(18,3) not null,                          -- 계획 수량
    unit          text,                                            -- 단위
    status        text not null default '계획',                    -- 상태 계획/확정/취소
    constraint ord_plan_no_uq unique (plan_no),
    constraint ord_plan_status_chk check (status in ('계획', '확정', '취소'))
);

-- ════════════════════════════════════════════════════════════════════
-- job 작업지시 (2) · shp 출하 헤더 · 공용 lot
-- ════════════════════════════════════════════════════════════════════

-- @table job_work_order | job | 작업지시 | 셋 다
create table job_work_order (
    id             bigserial primary key,
    work_order_no  text not null,                                  -- 지시 번호 (유니크 · numbering WORK_ORDER)
    item_id        bigint not null references bas_item (id),       -- 품목
    process_id     bigint not null references bas_process (id),    -- 공정
    equipment_id   bigint references bas_equipment (id),           -- 설비 (선택)
    plan_id        bigint references ord_plan (id),                -- 생산계획 (선택)
    order_dtl_id   bigint references ord_order_dtl (id),           -- 수주 상세 (선택)
    bom_id         bigint references bas_bom (id),                 -- BOM (선택)
    plan_qty       numeric(18,3) not null,                         -- 계획 수량
    unit           text,                                           -- 단위
    plan_date      date,                                           -- 계획일
    status         text not null default '대기',                   -- 상태 대기/진행/마감/취소 (진행 여부는 실적 유무로 계산)
    closed_at      timestamptz,                                    -- 마감 시각
    closed_by      text,                                           -- 마감자 login_id
    note           text,                                           -- 비고
    constraint job_work_order_no_uq unique (work_order_no),
    constraint job_work_order_status_chk check (status in ('대기', '진행', '마감', '취소'))
);

-- @table shp_shipment | shp | 출하 헤더 | 셋 다
create table shp_shipment (
    id           bigserial primary key,
    shipment_no  text not null,                                    -- 출하 번호 (유니크 · numbering SHIPMENT)
    partner_id   bigint not null references bas_partner (id),      -- 거래처
    ship_date    date not null,                                    -- 출하일
    order_id     bigint references ord_order (id),                 -- 수주 (선택)
    status       text not null default '등록',                     -- 상태 등록/승인/취소
    approved_at  timestamptz,                                      -- 승인 시각
    approved_by  text,                                             -- 승인자 login_id
    note         text,                                             -- 비고
    constraint shp_shipment_no_uq unique (shipment_no),
    constraint shp_shipment_status_chk check (status in ('등록', '승인', '취소'))
);

-- @table lot | 공용 | 추적 단위 (D-03) — MATERIAL · PRODUCT · SHIPMENT + 팩 등록 kind | 엘컴화인 3테이블 · 니즈푸드 배치 · 임진강 공정 LOT
create table lot (
    id              bigserial primary key,
    lot_no          text not null,                                 -- LOT 번호 (유니크 · 바코드 — 영문 대문자 · 숫자 · - 만)
    kind            text not null,                                 -- 종류 MATERIAL/PRODUCT/SHIPMENT + 팩 등록
    kind_base       text not null,                                 -- 코어 종류 3 중 하나 (lineage 가 채움)
    item_id         bigint references bas_item (id),               -- 품목 (SHIPMENT 는 NULL)
    work_order_id   bigint references job_work_order (id),         -- 작업지시 (선택)
    process_id      bigint references bas_process (id),            -- 공정 (선택)
    equipment_id    bigint references bas_equipment (id),          -- 설비 (선택)
    work_result_id  bigint,                                        -- 생성 실적 (선택 · FK 는 pop_work_result 뒤에)
    partner_id      bigint references bas_partner (id),            -- MATERIAL 공급처 (선택)
    shipment_id     bigint references shp_shipment (id),           -- SHIPMENT 만
    qty             numeric(18,3),                                 -- 수량
    unit            text,                                          -- 단위
    insp_status     text not null default '미검사',                -- 검사 상태 미검사/합격/불합격/조건부
    made_at         timestamptz not null default now(),            -- 생성 시각
    note            text,                                          -- 비고
    constraint lot_no_uq unique (lot_no),
    constraint lot_no_chk check (lot_no ~ '^[A-Z0-9-]+$'),
    constraint lot_kind_base_chk check (kind_base in ('MATERIAL', 'PRODUCT', 'SHIPMENT')),
    constraint lot_shipment_chk check ((kind_base = 'SHIPMENT') = (shipment_id is not null)),
    constraint lot_insp_chk check (insp_status in ('미검사', '합격', '불합격', '조건부'))
);
create index lot_kind_idx on lot (kind_base, made_at desc);
create index lot_item_idx on lot (item_id);
create index lot_work_order_idx on lot (work_order_id);

-- @table job_lot | job | 지시 ↔ 소요 품목/LOT 매핑 | 엘컴화인 `job_lot`(D-10) · 니즈푸드 소요량
create table job_lot (
    id             bigserial primary key,
    work_order_id  bigint not null references job_work_order (id), -- 작업지시
    item_id        bigint not null references bas_item (id),       -- 소요 품목
    required_qty   numeric(18,3),                                  -- 소요량
    unit           text,                                           -- 단위
    lot_id         bigint references lot (id)                      -- 지정 투입 LOT (선택)
);
create index job_lot_wo_idx on job_lot (work_order_id);

-- ════════════════════════════════════════════════════════════════════
-- mat 자재 (4)
-- ════════════════════════════════════════════════════════════════════

-- @table mat_receipt | mat | 입고 | 셋 다
create table mat_receipt (
    id            bigserial primary key,
    receipt_no    text not null,                                   -- 입고 번호 (유니크)
    item_id       bigint not null references bas_item (id),        -- 품목
    partner_id    bigint references bas_partner (id),              -- 공급처
    receipt_date  date not null,                                   -- 입고일
    qty           numeric(18,3) not null,                          -- 수량
    unit          text,                                            -- 단위
    lot_id        bigint references lot (id),                      -- 생성된 원재료 LOT
    note          text,                                            -- 비고
    constraint mat_receipt_no_uq unique (receipt_no)
);

-- @table mat_stock | mat | 품목별 현재고 (거래 합과 같아야 한다) | 임진강 `MAT_STOCK` · 니즈푸드 `MAT_PROD_STOCK`
create table mat_stock (
    id       bigserial primary key,
    item_id  bigint not null references bas_item (id),             -- 품목 (유니크)
    qty      numeric(18,3) not null default 0,                     -- 현재고
    unit     text,                                                 -- 단위
    constraint mat_stock_item_uq unique (item_id)
);

-- @table mat_stock_trx | mat | 재고 거래 | 임진강 `MAT_STOCK_TRX` · 니즈푸드 `MAT_STOCK_MOVE`
create table mat_stock_trx (
    id         bigserial primary key,
    item_id    bigint not null references bas_item (id),           -- 품목
    lot_id     bigint references lot (id),                         -- LOT (선택)
    trx_type   text not null,                                      -- 거래 구분 입고/투입/조정/출하
    qty        numeric(18,3) not null,                             -- 수량 (부호)
    unit       text,                                               -- 단위
    ref_table  text,                                               -- 참조 테이블
    ref_id     bigint,                                             -- 참조 ID
    reason     text,                                               -- 사유 (조정은 필수 — 라우터)
    trx_at     timestamptz not null default now(),                 -- 거래 시각
    constraint mat_stock_trx_type_chk check (trx_type in ('입고', '투입', '조정', '출하'))
);
create index mat_stock_trx_item_idx on mat_stock_trx (item_id, trx_at desc);

-- @table mat_requirement | mat | 소요량 | 임진강 `MAT_REQUIRE` · 니즈푸드 소요량
create table mat_requirement (
    id            bigserial primary key,
    period_from   date not null,                                   -- 기간 시작
    period_to     date not null,                                   -- 기간 끝
    item_id       bigint not null references bas_item (id),        -- 품목
    required_qty  numeric(18,3) not null default 0,                -- 소요량
    stock_qty     numeric(18,3) not null default 0,                -- 현재고
    shortage_qty  numeric(18,3) not null default 0,                -- 부족량
    unit          text,                                            -- 단위
    source        text not null default 'calc',                    -- 출처 calc/hook (훅이 만든 행은 재계산이 덮지 않는다)
    calc_at       timestamptz not null default now(),              -- 계산 시각
    constraint mat_requirement_uq unique (period_from, period_to, item_id, source),
    constraint mat_requirement_source_chk check (source in ('calc', 'hook'))
);

-- ════════════════════════════════════════════════════════════════════
-- pop 생산실적 (5) · lot_genealogy
-- ════════════════════════════════════════════════════════════════════

-- @table pop_work_result | pop | 실적 (작업 1회) | 셋 다
create table pop_work_result (
    id              bigserial primary key,
    work_order_id   bigint not null references job_work_order (id), -- 작업지시
    process_id      bigint not null references bas_process (id),   -- 공정
    equipment_id    bigint references bas_equipment (id),          -- 설비 (선택)
    worker_id       bigint references bas_worker (id),             -- 작업자 (선택)
    started_at      timestamptz not null default now(),            -- 시작 시각
    ended_at        timestamptz,                                   -- 종료 시각 (NULL = 진행 중)
    good_qty        numeric(18,3),                                 -- 양품 수량
    defect_qty      numeric(18,3),                                 -- 불량 수량
    unit            text,                                          -- 단위
    product_lot_id  bigint references lot (id),                    -- 생산 LOT (종료 때 lineage 가 채운다)
    note            text                                           -- 비고
);
create index pop_work_result_wo_idx on pop_work_result (work_order_id, started_at desc);
alter table lot add constraint lot_work_result_fk foreign key (work_result_id) references pop_work_result (id);

-- @table lot_genealogy | 공용 | 계보 — 화살표 한 줄 = 부모 LOT → 자식 LOT. lineage 만 쓴다 | 엘컴화인 `roll_genealogy`
create table lot_genealogy (
    id             bigserial primary key,
    parent_lot_id  bigint not null references lot (id),            -- 부모 LOT
    child_lot_id   bigint not null references lot (id),            -- 자식 LOT
    relation       text not null,                                  -- 관계 (코어 5 + 팩 등록 — lineage.link 가 검증)
    relation_base  text not null,                                  -- 코어 관계 투입/생산/분할/합병/출하 (추적 SQL 이 본다)
    qty            numeric(18,3),                                  -- 이 화살표의 수량
    linked_at      timestamptz not null default now(),             -- 연결 시각
    linked_by      text,                                           -- 연결자 login_id
    constraint lot_genealogy_uq unique (parent_lot_id, child_lot_id, relation),
    constraint lot_genealogy_self_chk check (parent_lot_id <> child_lot_id),
    constraint lot_genealogy_base_chk check (relation_base in ('투입', '생산', '분할', '합병', '출하'))
);
create index lot_genealogy_parent_idx on lot_genealogy (parent_lot_id);
create index lot_genealogy_child_idx on lot_genealogy (child_lot_id);

-- 계보 지킴이 — 자기 참조 · 순환 금지 · 행 불변 (db-schema.md §3.2). 관계 이름 검증은 lineage.link (팩이 더하므로 DB 에 박지 않는다)
create function lot_genealogy_guard() returns trigger
language plpgsql as $$
declare
    v_hit bigint;
begin
    if tg_op = 'UPDATE' then
        if (new.parent_lot_id, new.child_lot_id, new.relation, new.relation_base)
           is distinct from (old.parent_lot_id, old.child_lot_id, old.relation, old.relation_base) then
            raise exception '계보 행의 부모 · 자식 · 관계는 고칠 수 없다 (id=%)', old.id using errcode = 'check_violation';
        end if;
        return new;
    end if;
    if new.parent_lot_id = new.child_lot_id then
        raise exception '자기 자신을 부모로 하는 계보는 만들 수 없다 (lot_id=%)', new.parent_lot_id using errcode = 'check_violation';
    end if;
    -- 동시에 A→B 와 B→A 가 들어와 서로를 못 보는 경우를 막는다
    perform pg_advisory_xact_lock(hashtext('lot_genealogy'));
    with recursive down (lot_id) as (
        select new.child_lot_id
        union
        select g.child_lot_id from lot_genealogy g join down d on g.parent_lot_id = d.lot_id
    )
    select lot_id into v_hit from down where lot_id = new.parent_lot_id limit 1;
    if v_hit is not null then
        raise exception '계보 순환: LOT % 은 LOT % 의 자손이다', new.parent_lot_id, new.child_lot_id using errcode = 'check_violation';
    end if;
    return new;
end;
$$;
create trigger lot_genealogy_no_cycle
    before insert or update on lot_genealogy
    for each row execute function lot_genealogy_guard();

-- @table pop_stop | pop | 정지 | 엘컴화인 `work_stop` · 니즈푸드 `PRC_DELAY`
create table pop_stop (
    id              bigserial primary key,
    work_result_id  bigint not null references pop_work_result (id), -- 실적
    reason_code     text not null,                                 -- 사유 — 공통코드 STOP_REASON
    started_at      timestamptz not null default now(),            -- 정지 시작
    ended_at        timestamptz,                                   -- 정지 끝
    note            text                                           -- 비고
);
create index pop_stop_result_idx on pop_stop (work_result_id);

-- @table pop_scrap | pop | 폐기 | 엘컴화인 `work_scrap` · 임진강 불량
create table pop_scrap (
    id              bigserial primary key,
    work_result_id  bigint not null references pop_work_result (id), -- 실적
    defect_code_id  bigint references bas_defect_code (id),        -- 불량코드
    qty             numeric(18,3) not null,                        -- 수량
    unit            text,                                          -- 단위
    scrapped_at     timestamptz not null default now()             -- 폐기 시각
);
create index pop_scrap_result_idx on pop_scrap (work_result_id);

-- @table pop_input | pop | 투입 스캔 (종료 때 투입 계보로 옮겨진다) | 엘컴화인 `material_input` · 니즈푸드 BOM 투입
create table pop_input (
    id               bigserial primary key,
    work_result_id   bigint not null references pop_work_result (id), -- 실적
    material_lot_id  bigint not null references lot (id),          -- 투입한 원재료 LOT
    qty              numeric(18,3),                                -- 투입량
    unit             text,                                         -- 단위
    scanned_at       timestamptz not null default now(),           -- 스캔 시각
    canceled_yn      char(1) not null default 'N',                 -- 취소 여부
    constraint pop_input_cancel_chk check (canceled_yn in ('Y', 'N'))
);
create index pop_input_result_idx on pop_input (work_result_id);
create index pop_input_lot_idx on pop_input (material_lot_id);

-- @table pop_measure | pop | 측정값 기록 (E3) — 실적 1건당 키당 1행 | 임진강 `SLT_SALINITY_LOG MIX_CCP_RESULT` · 니즈푸드 설비 측정값 · 엘컴화인 색차 측정값의 일반화
create table pop_measure (
    id              bigserial primary key,
    work_result_id  bigint not null references pop_work_result (id), -- 실적
    param_id        bigint references bas_process_param (id),      -- 측정값 정의 (선택 — 정의가 지워져도 기록은 남는다)
    param_key       text not null,                                 -- 키
    value_num       numeric(18,4),                                 -- 숫자 값
    value_text      text,                                          -- 글자 값
    unit            text,                                          -- 단위
    source          text not null default 'manual',                -- 수집원 manual/collect
    deviated        boolean not null default false,                -- 범위 이탈 (저장하고 표시 — 오류 아님)
    measured_at     timestamptz not null default now(),            -- 측정 시각
    constraint pop_measure_uq unique (work_result_id, param_key),
    constraint pop_measure_source_chk check (source in ('manual', 'collect'))
);
create index pop_measure_key_idx on pop_measure (param_key, measured_at);

-- ════════════════════════════════════════════════════════════════════
-- qua 품질 (5)
-- ════════════════════════════════════════════════════════════════════

-- @table qua_insp_plan | qua | 검사 계획 (항목 정의) | 니즈푸드 `QUA_INSP_PLAN` · 임진강 `BAS_CCP_STD`
create table qua_insp_plan (
    id          bigserial primary key,
    insp_type   text not null,                                     -- 검사 유형 입고/공정/최종 — 공통코드 INSP_TYPE
    item_id     bigint references bas_item (id),                   -- 품목 (선택)
    process_id  bigint references bas_process (id),                -- 공정 (선택)
    item_key    text not null,                                     -- 항목 키
    label       text not null,                                     -- 항목 라벨
    unit        text,                                              -- 단위
    value_type  text not null default 'number',                    -- 형식 number/text/bool/select
    standard    text,                                              -- 기준 (글자)
    min_value   numeric(18,4),                                     -- 하한
    max_value   numeric(18,4),                                     -- 상한
    seq         integer not null default 0,                        -- 순서
    use_yn      char(1) not null default 'Y',                      -- 사용 여부
    constraint qua_insp_plan_type_chk check (insp_type in ('입고', '공정', '최종')),
    constraint qua_insp_plan_vtype_chk check (value_type in ('number', 'text', 'bool', 'select')),
    constraint qua_insp_plan_use_chk check (use_yn in ('Y', 'N'))
);
create unique index qua_insp_plan_uq on qua_insp_plan (insp_type, coalesce(item_id, 0), coalesce(process_id, 0), item_key);

-- @table qua_inspection | qua | 검사 1건 (최신 검사가 그 LOT 의 판정) | 셋 다
create table qua_inspection (
    id            bigserial primary key,
    lot_id        bigint not null references lot (id),             -- 검사한 LOT
    insp_type     text not null,                                   -- 검사 유형 입고/공정/최종
    inspected_at  timestamptz not null default now(),              -- 검사 시각
    inspector     text,                                            -- 검사자 login_id
    judgement     text,                                            -- 판정 NULL/합격/불합격/조건부
    judged_at     timestamptz,                                     -- 판정 시각
    judged_by     text,                                            -- 판정자 login_id
    note          text,                                            -- 비고
    constraint qua_inspection_type_chk check (insp_type in ('입고', '공정', '최종')),
    constraint qua_inspection_judge_chk check (judgement is null or judgement in ('합격', '불합격', '조건부'))
);
create index qua_inspection_lot_idx on qua_inspection (lot_id, inspected_at desc);

-- @table qua_insp_item | qua | 검사 항목 값 | 임진강 CCP 결과 · 니즈푸드 검사 항목
create table qua_insp_item (
    id              bigserial primary key,
    inspection_id   bigint not null references qua_inspection (id), -- 검사
    plan_id         bigint references qua_insp_plan (id),          -- 계획 항목 (선택)
    item_key        text not null,                                 -- 항목 키
    value_num       numeric(18,4),                                 -- 숫자 값
    value_text      text,                                          -- 글자 값
    unit            text,                                          -- 단위
    item_judgement  text,                                          -- 항목 판정
    deviated        boolean not null default false,                -- 기준 이탈
    constraint qua_insp_item_uq unique (inspection_id, item_key)
);

-- @table qua_defect | qua | 불량 (판정에 붙는 불량코드별 수량) | 엘컴화인 `inspection_defect` · 임진강 `QUA_DEFECT`
create table qua_defect (
    id              bigserial primary key,
    inspection_id   bigint not null references qua_inspection (id), -- 검사
    defect_code_id  bigint not null references bas_defect_code (id), -- 불량코드
    qty             numeric(18,3),                                 -- 수량
    position        text,                                          -- 위치
    note            text                                           -- 비고
);
create index qua_defect_insp_idx on qua_defect (inspection_id);

-- @table qua_issue | qua | 이상 · 시정 | 니즈푸드 · 임진강 `QUA_ISSUE`
create table qua_issue (
    id             bigserial primary key,
    issue_no       text not null,                                  -- 이상 번호 (유니크)
    occurred_at    timestamptz not null default now(),             -- 발생 시각
    process_id     bigint references bas_process (id),             -- 공정 (선택)
    lot_id         bigint references lot (id),                     -- LOT (선택)
    inspection_id  bigint references qua_inspection (id),          -- 검사 (선택)
    content        text not null,                                  -- 내용
    cause          text,                                           -- 원인
    action         text,                                           -- 조치 내용
    action_by      text,                                           -- 조치 담당
    action_at      timestamptz,                                    -- 조치 일시
    status         text not null default '발생',                    -- 상태 발생/조치/종결 — 공통코드 ISSUE_STATUS
    source         text not null default 'manual',                 -- 출처 manual/hook
    constraint qua_issue_no_uq unique (issue_no),
    constraint qua_issue_status_chk check (status in ('발생', '조치', '종결')),
    constraint qua_issue_source_chk check (source in ('manual', 'hook'))
);

-- ════════════════════════════════════════════════════════════════════
-- eqp 설비 (4) · ifc 수집 원문
-- ════════════════════════════════════════════════════════════════════

-- @table eqp_run_log | eqp | 가동 구간 | 임진강 `EQP_RUN_LOG` · 니즈푸드 `EQP_STATUS` · 송월 `PRC_EQUIP_STATUS`
create table eqp_run_log (
    id            bigserial primary key,
    equipment_id  bigint not null references bas_equipment (id),   -- 설비
    state         text not null,                                   -- 상태 가동/정지/점검/고장 — 공통코드 EQUIP_STATE
    started_at    timestamptz not null default now(),              -- 구간 시작
    ended_at      timestamptz,                                     -- 구간 끝
    source        text not null default 'manual',                  -- 출처 manual/collect
    note          text,                                            -- 비고
    constraint eqp_run_log_state_chk check (state in ('가동', '정지', '점검', '고장')),
    constraint eqp_run_log_source_chk check (source in ('manual', 'collect'))
);
create index eqp_run_log_equip_idx on eqp_run_log (equipment_id, started_at desc);

-- @table eqp_check | eqp | 점검 | 임진강 `EQP_CHECK` · 니즈푸드 `EQP_INSPECT`
create table eqp_check (
    id            bigserial primary key,
    equipment_id  bigint not null references bas_equipment (id),   -- 설비
    checked_at    timestamptz not null default now(),              -- 점검 일시
    item          text not null,                                   -- 점검 항목
    result        text,                                            -- 결과
    checker       text,                                            -- 점검자
    note          text                                             -- 비고
);
create index eqp_check_equip_idx on eqp_check (equipment_id, checked_at desc);

-- @table eqp_fault | eqp | 고장 | 임진강 · 니즈푸드 `EQP_FAULT`
create table eqp_fault (
    id            bigserial primary key,
    equipment_id  bigint not null references bas_equipment (id),   -- 설비
    occurred_at   timestamptz not null default now(),              -- 발생 시각
    symptom       text not null,                                   -- 증상
    fixed_at      timestamptz,                                     -- 복구 시각
    fix_action    text,                                            -- 조치 내용
    fixed_by      text,                                            -- 조치자
    run_log_id    bigint references eqp_run_log (id)               -- 가동 로그의 고장 구간
);
create index eqp_fault_equip_idx on eqp_fault (equipment_id, occurred_at desc);

-- @table ifc_collect_raw | ifc | 수집 원문 (모르는 설비도 거부 사유와 함께 남긴다) | 송월 `PRC_MONITOR_DATA DAT_COLLECT_LOGS`
create table ifc_collect_raw (
    id               bigserial primary key,
    equip_code       text not null,                                -- 설비 코드 (메시지 그대로)
    ts               timestamptz not null,                         -- 메시지 시각
    source           text not null default 'gateway',              -- 출처
    payload          jsonb not null,                               -- 메시지 원문
    resend           boolean not null default false,               -- 재전송 여부
    received_at      timestamptz not null default now(),           -- 수신 시각
    rejected_reason  text,                                         -- 거부 사유 (NULL = 정제됨)
    constraint ifc_collect_raw_uq unique (equip_code, ts, source)
);

-- @table eqp_collect | eqp | 수집값 정제본 (시계열) | 니즈푸드 `EQP_COLLECT` · 임진강 `IF_SENSOR_RAW` · 송월 `PRC_MONITOR_DATA`
create table eqp_collect (
    id            bigserial primary key,
    equipment_id  bigint not null references bas_equipment (id),   -- 설비
    tag           text not null,                                   -- 태그
    ts            timestamptz not null,                            -- 시각
    value_num     numeric(18,4),                                   -- 숫자 값
    value_text    text,                                            -- 글자 값
    raw_id        bigint references ifc_collect_raw (id),          -- 원문
    constraint eqp_collect_uq unique (equipment_id, tag, ts)
);
create index eqp_collect_series_idx on eqp_collect (equipment_id, tag, ts desc);

-- ════════════════════════════════════════════════════════════════════
-- shp 발행본 · kpi (2) · sys (나머지 7) · ifc (2)
-- ════════════════════════════════════════════════════════════════════

-- @table shp_document | shp | 성적서 · 거래명세서 발행본 (스냅샷 — 발행 뒤 불변) | 엘컴화인 성적서 · 평창 거래명세서
create table shp_document (
    id           bigserial primary key,
    document_no  text not null,                                    -- 문서 번호 (유니크 · numbering DOCUMENT)
    doc_type     text not null default '성적서',                    -- 종류 성적서/거래명세서
    shipment_id  bigint not null references shp_shipment (id),     -- 출하
    issued_at    timestamptz not null default now(),               -- 발행 시각
    issued_by    text,                                             -- 발행자 login_id
    snapshot     jsonb not null default '{}',                      -- 발행 시점의 LOT · 검사 값
    constraint shp_document_no_uq unique (document_no),
    constraint shp_document_type_chk check (doc_type in ('성적서', '거래명세서'))
);

-- @table kpi_indicator | kpi | 지표 정의 | 임진강 `KPI_MASTER` · 니즈푸드 `KPI_INDICATOR`
create table kpi_indicator (
    id             bigserial primary key,
    indicator_key  text not null,                                  -- 지표 키 (유니크)
    name           text not null,                                  -- 이름
    unit           text,                                           -- 단위
    target_value   numeric(18,4),                                  -- 목표값
    calc_kind      text not null,                                  -- 산식 core:<집계 키> 또는 pack:<kpi_extra 키>
    visible_yn     char(1) not null default 'Y',                   -- 현황판 표시 여부
    seq            integer not null default 0,                     -- 순서
    constraint kpi_indicator_key_uq unique (indicator_key),
    constraint kpi_indicator_visible_chk check (visible_yn in ('Y', 'N'))
);

-- @table kpi_snapshot | kpi | 현황판 일 스냅샷 (배치만 쓴다) | 임진강 `KPI_RESULT DSH_METRIC_TS`
create table kpi_snapshot (
    id             bigserial primary key,
    snap_date      date not null,                                  -- 날짜
    indicator_key  text not null,                                  -- 지표 키
    value          numeric(18,4),                                  -- 값
    calc_at        timestamptz not null default now(),             -- 계산 시각
    constraint kpi_snapshot_uq unique (snap_date, indicator_key)
);

-- @table sys_permission | sys | 권한 표 칸 (메뉴 × 역할 전 칸) | 엘컴화인 `sys_permission` · 임진강 `SYS_ROLE_AUTH`
create table sys_permission (
    id         bigserial primary key,
    role_id    bigint not null references sys_role (id),           -- 역할
    menu_code  text not null,                                      -- 메뉴(모듈) 코드
    level      text not null default '없음',                       -- 없음/조회/입력
    scopes     text[] not null default '{}',                       -- 입력 범위 (일반 · 입고검사 · 승인 · 지표 · 재전송 …)
    constraint sys_permission_uq unique (role_id, menu_code),
    constraint sys_permission_level_chk check (level in ('없음', '조회', '입력'))
);

-- @table sys_session | sys | 세션 (요청마다 사용자 상태와 함께 확인 · D-19) | 엘컴화인(D-26 쿠키 → DB)
create table sys_session (
    id                bigserial primary key,
    session_id        text not null,                               -- 세션 ID (유니크 · 쿠키에는 이것만)
    user_id           bigint not null references sys_user (id),    -- 사용자
    device            text not null default 'web',                 -- 채널 web/pop/mobile/board
    issued_at         timestamptz not null default now(),          -- 발급 시각
    expires_at        timestamptz not null,                        -- 만료 시각
    revoked_at        timestamptz,                                 -- 무효화 시각 (로그아웃 · 중지)
    password_version  bigint not null default 0,                   -- 로그인 때의 비밀번호 판 (password_changed_at epoch)
    constraint sys_session_id_uq unique (session_id),
    constraint sys_session_device_chk check (device in ('web', 'pop', 'mobile', 'board'))
);
create index sys_session_user_idx on sys_session (user_id);

-- @table sys_access_log | sys | 접근 로그 (로그인 · 조회 · 변경 · 오류) | 셋 다 `SYS_LOG`
create table sys_access_log (
    id         bigserial primary key,
    logged_at  timestamptz not null default now(),                 -- 시각
    user_id    bigint references sys_user (id),                    -- 사용자 (선택)
    login_id   text,                                               -- 로그인 ID
    kind       text not null,                                      -- 종류 login_ok/login_fail/view/change/error
    screen_id  text,                                               -- 화면 ID
    fn_id      text,                                               -- 기능 ID
    target     text,                                               -- 대상 (테이블:번호)
    detail     jsonb not null default '{}',                        -- 상세 (비밀번호 · 세션 ID 없음)
    ip         text,                                               -- 접속 IP
    device     text,                                               -- 채널
    constraint sys_access_log_kind_chk check (kind in ('login_ok', 'login_fail', 'view', 'change', 'error'))
);
create index sys_access_log_at_idx on sys_access_log (logged_at desc);

-- @table sys_number_rule | sys | 채번 규칙 (조립식 — prefix + to_char(date_format) + seq) | 엘컴화인
create table sys_number_rule (
    id           bigserial primary key,
    kind         text not null,                                    -- 종류 (유니크 · core.yaml: numbering + 팩)
    prefix       text not null default '',                         -- 접두어
    date_format  text not null default '',                         -- 날짜 형식 (to_char · 비면 통산)
    seq_digits   integer not null default 3,                       -- 일련번호 자릿수
    use_yn       char(1) not null default 'Y',                     -- 사용 여부
    constraint sys_number_rule_kind_uq unique (kind),
    constraint sys_number_rule_use_chk check (use_yn in ('Y', 'N'))
);

-- @table sys_number_seq | sys | 채번 카운터 (행 잠금으로 올린다 — numbering 만 쓴다) | 엘컴화인
create table sys_number_seq (
    id         bigserial primary key,
    kind       text not null,                                      -- 종류
    seq_scope  text not null default '',                           -- 날짜 부분 값 (카운터 범위)
    last_seq   integer not null default 0,                         -- 마지막 번호
    constraint sys_number_seq_uq unique (kind, seq_scope)
);

-- @table sys_migration_log | sys | 이관 로그 | 엘컴화인
create table sys_migration_log (
    id            bigserial primary key,
    command       text not null,                                   -- 명령 basics/orders/lots/history
    dir           text,                                            -- 폴더
    file          text,                                            -- 파일
    read_count    integer not null default 0,                      -- 읽음
    inserted      integer not null default 0,                      -- 적재
    updated       integer not null default 0,                      -- 갱신
    skipped       integer not null default 0,                      -- 건너뜀
    errors        integer not null default 0,                      -- 오류 수
    error_detail  jsonb not null default '[]',                     -- 오류 상세
    dry_run       boolean not null default false,                  -- 시험 실행 여부
    started_at    timestamptz not null default now(),              -- 시작
    ended_at      timestamptz,                                     -- 끝
    run_by        text                                             -- 실행자
);

-- @table sys_backup_hist | sys | 백업 이력 | 임진강 · 니즈푸드 `SYS_BACKUP_HIST`
create table sys_backup_hist (
    id           bigserial primary key,
    dump_path    text,                                             -- 덤프 경로
    row_counts   jsonb not null default '{}',                      -- 테이블별 행 수
    started_at   timestamptz not null default now(),               -- 시작
    ended_at     timestamptz,                                      -- 끝
    ok           boolean,                                          -- 성공 여부
    verified_at  timestamptz,                                      -- 복구 확인 시각
    verify_ok    boolean,                                          -- 복구 확인 결과
    message      text                                              -- 메시지
);

-- @table ifc_erp_link | ifc | ERP 연계 기록 | 임진강 `IF_ERP_LINK` · 송월 `DAT_IF_LOGS`
create table ifc_erp_link (
    id         bigserial primary key,
    kind       text not null,                                      -- 연계 종류
    direction  text not null,                                      -- 방향 push/pull
    ref_table  text,                                               -- 참조 테이블
    ref_id     bigint,                                             -- 참조 ID
    status     text not null default '미확정',                      -- 상태 대기/성공/실패/미확정
    message    text,                                               -- 메시지
    linked_at  timestamptz not null default now(),                 -- 시각
    constraint ifc_erp_link_dir_chk check (direction in ('push', 'pull')),
    constraint ifc_erp_link_status_chk check (status in ('대기', '성공', '실패', '미확정'))
);

-- @table ifc_outbox | ifc | 외부 전송 큐 (after_commit_* 훅이 넣고 erp.flush 가 비운다) | 엘컴화인 `erp.py` 일반화 `[가설]`
create table ifc_outbox (
    id          bigserial primary key,
    event       text not null,                                     -- 사건
    payload     jsonb not null default '{}',                       -- 페이로드
    status      text not null default '대기',                       -- 상태 대기/전송/실패/미확정
    attempts    integer not null default 0,                        -- 시도 횟수
    last_error  text,                                              -- 마지막 오류
    sent_at     timestamptz,                                       -- 전송 시각
    constraint ifc_outbox_status_chk check (status in ('대기', '전송', '실패', '미확정'))
);

-- ════════════════════════════════════════════════════════════════════
-- 공통 컬럼 — 전 테이블 (created_at · created_by · updated_at · updated_by · attrs). id 는 각 테이블에 있다
-- ════════════════════════════════════════════════════════════════════
do $$
declare t text;
begin
    for t in select table_name from information_schema.tables
              where table_schema = 'public' and table_type = 'BASE TABLE' order by table_name loop
        execute format('alter table %I add column created_at timestamptz not null default now(), '
                       'add column created_by text, add column updated_at timestamptz, add column updated_by text, '
                       'add column attrs jsonb not null default ''{}''', t);
    end loop;
end $$;

-- 비밀번호가 바뀌면 password_changed_at 을 올린다 → 그 전 세션은 다음 요청부터 401 (D-19)
create function sys_user_password_guard() returns trigger
language plpgsql as $$
begin
    if new.password_hash is distinct from old.password_hash then
        new.password_changed_at := now();
    end if;
    return new;
end;
$$;
create trigger sys_user_password_trg before update on sys_user for each row execute function sys_user_password_guard();
