-- printfilm 확장 스키마 — schema_ext.md 의 테이블 8 (개발2 · 2026-10-09). pack-contract.md §3 · §4 R2 · R3.
-- 규약: 접두 x_printfilm_ · 공통 컬럼 6(id · created_at · created_by · updated_at · updated_by · attrs) · 코어 ALTER · 트리거 · 뷰 0.
--       1:1 ext 는 코어 id 가 PK 겸 FK(on delete cascade) — 컬럼명은 _template 규약대로 `id`(schema_ext.md 의 lot_id · work_order_id 와 같은 뜻).
--       그 밖 FK 는 on delete restrict(기본). 규격 값은 없다 — 도수 · 선수 · 셀 용적 · Lab 은 전부 NULL 허용(미확정).
-- 적용: MES_PACK=printfilm make db-schema (코어 schema.sql · views.sql 다음에 이 파일).

-- @table x_printfilm_plate | PACK | 판사양 (엘컴화인 plate_spec)
create table x_printfilm_plate (
    id            bigserial primary key,
    plate_code    text not null,                                    -- 판 코드 (유니크)
    plate_name    text not null,                                    -- 판명
    item_id       bigint references bas_item (id),                  -- 대상 품목(제품)
    color_count   integer,                                          -- 도수 (가설 D-18 · 값 미확정)
    spec_note     text,                                             -- 사양 메모
    use_yn        char(1) not null default 'Y',                     -- 사용 여부
    created_at    timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs         jsonb not null default '{}',
    constraint x_printfilm_plate_code_uq unique (plate_code),
    constraint x_printfilm_plate_use_chk check (use_yn in ('Y', 'N'))
);

-- @table x_printfilm_anilox | PACK | 아니록스 (엘컴화인 anilox)
create table x_printfilm_anilox (
    id            bigserial primary key,
    anilox_code   text not null,                                    -- 아니록스 코드 (유니크)
    anilox_name   text not null,                                    -- 명칭
    line_count    numeric(10,2),                                    -- 선수 (가설 · 값 미확정)
    cell_volume   numeric(10,3),                                    -- 셀 용적 (가설 · 값 미확정)
    note          text,                                             -- 비고
    use_yn        char(1) not null default 'Y',
    created_at    timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs         jsonb not null default '{}',
    constraint x_printfilm_anilox_code_uq unique (anilox_code),
    constraint x_printfilm_anilox_use_chk check (use_yn in ('Y', 'N'))
);

-- @table x_printfilm_ink_formula | PACK | 잉크조성 (엘컴화인 ink_formula)
create table x_printfilm_ink_formula (
    id            bigserial primary key,
    ink_code      text not null,                                    -- 잉크 코드 (유니크)
    ink_name      text not null,                                    -- 잉크명
    color_name    text,                                             -- 색 이름
    target_l      numeric(7,2),                                     -- 기준 색상값 L (가설)
    target_a      numeric(7,2),                                     -- 기준 색상값 a
    target_b      numeric(7,2),                                     -- 기준 색상값 b
    note          text,
    use_yn        char(1) not null default 'Y',
    created_at    timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs         jsonb not null default '{}',
    constraint x_printfilm_ink_formula_code_uq unique (ink_code),
    constraint x_printfilm_ink_formula_use_chk check (use_yn in ('Y', 'N'))
);

-- @table x_printfilm_ink_formula_component | PACK | 잉크조성 조성 행 1:N (엘컴화인 ink_formula_component)
create table x_printfilm_ink_formula_component (
    id              bigserial primary key,
    ink_formula_id  bigint not null references x_printfilm_ink_formula (id) on delete cascade,   -- F-X-PRT-11 이 함께 지운다
    seq_no          integer not null,                               -- 행 순번
    component_name  text not null,                                  -- 성분명
    ratio_pct       numeric(6,3) not null,                          -- 비율 % (엘컴화인 D-209 소수 셋째 자리)
    created_at      timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs           jsonb not null default '{}',
    constraint x_printfilm_ink_formula_component_uq unique (ink_formula_id, seq_no),
    constraint x_printfilm_ink_formula_component_ratio_chk check (ratio_pct > 0 and ratio_pct <= 100)
);

-- @table x_printfilm_color_record | PACK | 조색 기록 (엘컴화인 color_record) — Job 참조 필수
create table x_printfilm_color_record (
    id              bigserial primary key,
    work_order_id   bigint not null references job_work_order (id) on delete restrict,   -- Job (엘컴화인 job_id)
    ink_formula_id  bigint references x_printfilm_ink_formula (id) on delete restrict,   -- 기준 잉크조성 (F-X-PRT-11 삭제 422 의 참조)
    color_name      text not null,                                  -- 색 이름
    seq_no          integer not null,                               -- 차수
    color_l         numeric(7,2),                                   -- 색상값 L (가설)
    color_a         numeric(7,2),
    color_b         numeric(7,2),
    note            text,
    recorded_at     timestamptz not null default now(),             -- 기록 일시
    created_at      timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs           jsonb not null default '{}',
    constraint x_printfilm_color_record_uq unique (work_order_id, color_name, seq_no)
);

-- @table x_printfilm_color_record_mix | PACK | 배합비 행 1:N (엘컴화인 color_record_mix) — 합 100 은 F-X-CLR-02 가 검사
create table x_printfilm_color_record_mix (
    id               bigserial primary key,
    color_record_id  bigint not null references x_printfilm_color_record (id) on delete cascade,
    seq_no           integer not null,
    component_name   text not null,
    ratio_pct        numeric(6,3) not null,                         -- 배합비 % (소수 셋째 자리)
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}',
    constraint x_printfilm_color_record_mix_uq unique (color_record_id, seq_no),
    constraint x_printfilm_color_record_mix_ratio_chk check (ratio_pct > 0 and ratio_pct <= 100)
);

-- @table x_printfilm_lot_ext | PACK | 롤 검색 · FK 컬럼 (코어 lot 1:1 — id = lot.id) — lot.kind='ROLL' 인 행에만 있다
create table x_printfilm_lot_ext (
    id            bigint primary key references lot (id) on delete cascade,   -- = lot.id (schema_ext.md 의 lot_id)
    process_type  text not null,                                    -- 공정 구분 인쇄/후가공/슬리팅 — F-X-RLL-03/05 의 WHERE (그래서 attrs 가 아니라 ext)
    equipment_id  bigint references bas_equipment (id),             -- 가공 설비 (lot.equipment_id 와 중복 — CR-2 · D-514, CR-2 뒤 제거)
    slit_seq      integer,                                          -- 슬리팅 분할 순번 1..N (슬리팅 롤만)
    created_at    timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs         jsonb not null default '{}',
    constraint x_printfilm_lot_ext_type_chk check (process_type in ('인쇄', '후가공', '슬리팅'))
);
create index x_printfilm_lot_ext_type_idx on x_printfilm_lot_ext (process_type);

-- @table x_printfilm_job_work_order_ext | PACK | Job 의 인쇄 기준 FK 3 (코어 job_work_order 1:1 — id = job_work_order.id)
create table x_printfilm_job_work_order_ext (
    id              bigint primary key references job_work_order (id) on delete cascade,   -- = job_work_order.id
    plate_id        bigint references x_printfilm_plate (id) on delete restrict,          -- 판사양 (F-X-PRT-03 삭제 422 의 근거)
    anilox_id       bigint references x_printfilm_anilox (id) on delete restrict,         -- 아니록스
    ink_formula_id  bigint references x_printfilm_ink_formula (id) on delete restrict,    -- 잉크조성
    created_at      timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs           jsonb not null default '{}'
);
