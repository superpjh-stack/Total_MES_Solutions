-- foodservice 팩 확장 테이블 8 — schema_ext.md (기획자1) 를 그대로 옮겼다 (개발1 · 2026-10-09).
-- 규칙: contracts/pack-contract.md §3 · §4 R2 · R3 — x_foodservice_ 접두 · 공통 컬럼 6(id · created_at · created_by · updated_at · updated_by · attrs)
--       · x_foodservice_<코어>_ext 는 코어 id 가 PK 겸 FK (1:1 · on delete cascade) · 코어 테이블 ALTER · DROP · 트리거 0.
-- 적용: MES_PACK=foodservice make db-schema (코어 schema.sql · views.sql 다음에 이 파일).

-- 1. 메뉴 · 원부자재 확장 (bas_item 1:1) — 조리공정 FK(지시 기본값 · 검색) · 보관기준온도(판정)
create table x_foodservice_item_ext (
    id               bigint primary key references bas_item (id) on delete cascade,
    cook_process_id  bigint references bas_process (id),            -- 조리공정구분 — 메뉴(item_type=제품)만. PRC-030/040/050/060 중 하나(훅 검증)
    storage_temp     numeric(5,1),                                  -- 보관기준온도(℃) — NULL = (미확정)
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}'
);

-- 2. 레시피 확장 (bas_bom 1:1) — 배치(솥) 기준인분: 소요량 · 배치수 집계에 쓴다 (D-502)
create table x_foodservice_bom_ext (
    id               bigint primary key references bas_bom (id) on delete cascade,
    batch_serve_qty  numeric(10,2) not null,                        -- 1솥 산출 인분. 1인량 = bas_bom_dtl.qty ÷ 이 값
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}',
    constraint x_foodservice_bom_ext_serve_chk check (batch_serve_qty > 0)
);

-- 3. 조리 공정 기준 (bas_process 1:1) — 표준 소요시간(지연 판정) · 배치 기준수량(배치수 산출) · 수집 방식
create table x_foodservice_process_ext (
    id               bigint primary key references bas_process (id) on delete cascade,
    std_lead_min     integer,                                       -- 표준 소요시간(분). NULL = (미확정 D-506 · 니즈푸드 D-08)
    batch_std_qty    numeric(10,2),                                 -- 배치(솥) 기준수량(인분). NULL 이면 활성 레시피 batch_serve_qty 로 대체
    collect_type     text,                                          -- 자동(PLC) / 반자동(POP) / 수동 — 표시 · 필터
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}'
);

-- 4. 설비 임계 (bas_equipment 1:1) — 냉장/냉동 구분 · 임계온도 (on_collect 판정값)
create table x_foodservice_equipment_ext (
    id               bigint primary key references bas_equipment (id) on delete cascade,
    storage_kind     text,                                          -- 냉장 · 냉동 · NULL(구분 미확인 D-10)
    temp_limit       numeric(5,1),                                  -- 상한(℃). 냉장 5 · 냉동 -18 (AD2-053). NULL 이면 판정하지 않는다
    humi_limit       numeric(5,1),                                  -- 상대습도 상한(%RH) — AD2-052 "명시되어 있지 않다" → NULL
    collect_path     text,                                          -- PLC(Ethernet) / RS-485→Edge — 표시 · 필터
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}',
    constraint x_foodservice_equipment_ext_kind_chk check (storage_kind is null or storage_kind in ('냉장', '냉동'))
);

-- 5. 수주 확장 (ord_order 1:1) — 납기시간(출고지시 정렬) · 급식유형(검색)
create table x_foodservice_order_ext (
    id               bigint primary key references ord_order (id) on delete cascade,
    due_time         time,                                          -- 납기시간(HH:MI)
    service_type     text,                                          -- 이동급식 / 위탁급식
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}',
    constraint x_foodservice_order_ext_type_chk check (service_type is null or service_type in ('이동급식', '위탁급식'))
);

-- 6. LOT 확장 (lot 1:1 · 원료 LOT · 배치 LOT 공용) — 유통기한(FIFO · 경과 거부) · 배치번호(유니크)
create table x_foodservice_lot_ext (
    id               bigint primary key references lot (id) on delete cascade,
    expiry_date      date,                                          -- kind=MATERIAL. FIFO 추천 정렬 · 경과 투입 거부
    batch_seq        integer,                                       -- kind=BATCH. 같은 지시 안 종료 순
    batch_no         text,                                          -- B-01 형식 (TD3-017 목업)
    work_order_id    bigint references job_work_order (id),         -- 유니크 제약용 복제 (lot.work_order_id 와 같다 — 훅이 채움)
    work_result_id   bigint references pop_work_result (id),        -- 배치를 만든 실적
    input_type       text,                                          -- 자동(PLC) / POP수동 / 스마트패드 — on_result_closed 가 collect 행 유무로 보정
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}',
    constraint x_foodservice_lot_ext_batch_uq unique (work_order_id, batch_no)
);
create index x_foodservice_lot_ext_expiry_idx on x_foodservice_lot_ext (expiry_date);

-- 7. 샘플링 검식 기준 (qua_insp_plan 1:1)
create table x_foodservice_insp_plan_ext (
    id               bigint primary key references qua_insp_plan (id) on delete cascade,
    sample_freq      text,                                          -- 원문 "10솥당 1솥" · "입고 건별 1회"
    sample_n         integer,                                       -- N솥당 — 원문 파싱 (니즈푸드 D-204). 파싱 불가면 NULL
    sample_k         integer,                                       -- M솥
    sample_qty       numeric(10,2),                                 -- 빈도 형식이 아닐 때의 샘플링 수량
    apply_from       date,                                          -- 적용시작일
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}'
);

-- 8. 보관온도 · 환경 이탈 기록 (1:N · 이탈 사건만 — 시계열은 eqp_collect)
create table x_foodservice_env_alarm (
    id               bigserial primary key,
    equipment_id     bigint not null references bas_equipment (id),
    collect_id       bigint references eqp_collect (id),            -- 원천 수집 행
    tag              text not null,                                 -- PV_TEMP · TEMP · HUMI
    ts               timestamptz not null,                          -- 수집 시각
    value_num        numeric(14,3) not null,
    limit_value      numeric(14,3) not null,                        -- 판정에 쓴 임계
    kind             text not null,                                 -- 상한 초과 · 하한 미달
    acked_at         timestamptz,                                   -- 확인 처리 (화면 없음 — 이관 단계)
    acked_by         text,
    created_at       timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs            jsonb not null default '{}',
    constraint x_foodservice_env_alarm_uq unique (equipment_id, tag, ts),
    constraint x_foodservice_env_alarm_kind_chk check (kind in ('상한 초과', '하한 미달'))
);
create index x_foodservice_env_alarm_ts_idx on x_foodservice_env_alarm (ts desc);
create index x_foodservice_env_alarm_equip_idx on x_foodservice_env_alarm (equipment_id, ts desc);
