-- kimchi 팩 확장 테이블 7 + 뷰 2 (schema_ext.md 를 그대로 옮김 · 개발3 · 2026-10-09)
-- 규약(pack-contract.md §3 · §4 R2 · R3): x_kimchi_ 접두 · 공통 컬럼 6(id · created_at · created_by · updated_at · updated_by · attrs)
-- · 1:1 ext 는 코어 id 가 PK 겸 FK(on delete cascade) · 코어 테이블 ALTER · DROP · 트리거 없음 · FK 는 코어를 가리킬 수 있다.
-- 센서 시계열은 전부 코어 eqp_collect — 이 파일의 로그 4 는 수기 · 집계 · 사건 로그다. 적용: MES_PACK=kimchi make db-schema.

set client_min_messages = warning;

-- 1. 품목별 공정 조건 기준 (E4 · 원천 WSH_STD + SLT_STD) — X-COND-01
create table x_kimchi_item_std (
    id            bigserial primary key,
    process_id    bigint not null references bas_process (id),     -- 세척/절임 P03 · 냉장·숙성 P09(aging_days)
    item_id       bigint not null references bas_item (id),        -- 품목
    size_type     text,                                            -- 원물 크기구분 (bas_code SIZE_TYPE) — NULL = 전체
    param_key     text not null,                                   -- bas_process_param.param_key 또는 aging_days (라우터가 검증)
    std_value     numeric(12,3),                                   -- 기준값 — NULL = 미확정
    min_value     numeric(12,3),                                   -- 하한
    max_value     numeric(12,3),                                   -- 상한
    tolerance     numeric(12,3),                                   -- 허용편차 — NULL 이면 알람 판정 안 함 (미확정)
    unit          text,
    haccp_chk_yn  char(1) not null default 'N',
    valid_from    date not null,                                   -- 적용 시작일
    use_yn        char(1) not null default 'Y',
    created_at    timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs         jsonb not null default '{}',
    constraint x_kimchi_item_std_haccp_chk check (haccp_chk_yn in ('Y', 'N')),
    constraint x_kimchi_item_std_use_chk check (use_yn in ('Y', 'N'))
);
create unique index x_kimchi_item_std_uq on x_kimchi_item_std (process_id, item_id, coalesce(size_type, ''), param_key, valid_from);
create index x_kimchi_item_std_item_key_ix on x_kimchi_item_std (item_id, param_key);

-- 2. 절임통 운영 배치 (E4 · 원천 SLT_TANK_OPR) — pop_work_result 1:1 ext (D-501)
create table x_kimchi_tank (
    id                   bigint primary key references pop_work_result (id) on delete cascade,   -- 절임 실적 1 = 절임통 배치 1
    equipment_id         bigint not null references bas_equipment (id),   -- 절임통 (실적의 설비와 같아야 한다)
    std_id               bigint references x_kimchi_item_std (id),         -- 적용한 절임 조건(염도 행)
    target_salinity_pct  numeric(6,2),                                     -- 투입 당시 기준 스냅샷
    target_hours         numeric(8,2),
    input_weight_kg      numeric(12,3),
    plan_end_at          timestamptz,                                      -- started_at + target_hours
    completed_at         timestamptz,
    final_salinity_pct   numeric(6,2),                                     -- 완료 시 염도 (센서 last 또는 수기)
    status               text not null default '투입',                      -- bas_code TANK_STATUS 투입/진행/완료
    sensor_equipment_id  bigint references bas_equipment (id),             -- 연결된 염도센서 — 매핑 미확정이면 NULL
    created_at           timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs                jsonb not null default '{}',
    constraint x_kimchi_tank_status_chk check (status in ('투입', '진행', '완료'))
);
create index x_kimchi_tank_equip_status_ix on x_kimchi_tank (equipment_id, status);
create unique index x_kimchi_tank_open_uq on x_kimchi_tank (equipment_id) where status <> '완료';   -- 같은 절임통에 미완료 배치 1개

-- 5. 기준 이탈 알람 (E4 · E5 · 원천 AGE_ENV_ALARM 일반화) — sanitizer_log 가 참조하므로 먼저 만든다
create table x_kimchi_env_alarm (
    alarm_no        text not null,                                    -- numbering ALARM
    kind            text not null,                                    -- bas_code ALARM_KIND
    equipment_id    bigint not null references bas_equipment (id),
    tag             text not null,                                    -- collect_tag (temp_c · humidity_pct · sanitizer_ppm · salinity_pct)
    first_value     numeric(12,3),
    last_value      numeric(12,3),
    limit_text      text,                                             -- 판정 당시 기준 스냅샷
    count           integer not null default 1,                       -- 합쳐진 이탈 횟수 (D-512)
    lot_id          bigint references lot (id),                       -- 절임통 배치 (염도)
    work_result_id  bigint references pop_work_result (id),
    param_id        bigint references bas_process_param (id),
    status          text not null default '발생',                      -- 발생/확인/해제
    first_at        timestamptz not null,
    last_at         timestamptz not null,
    acked_at        timestamptz, acked_by text,
    cleared_at      timestamptz, cleared_by text, action_desc text,
    id              bigserial primary key,
    created_at      timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs           jsonb not null default '{}',
    constraint x_kimchi_env_alarm_no_uq unique (alarm_no),
    constraint x_kimchi_env_alarm_status_chk check (status in ('발생', '확인', '해제'))
);
create index x_kimchi_env_alarm_open_ix on x_kimchi_env_alarm (equipment_id, tag) where status <> '해제';
create index x_kimchi_env_alarm_first_ix on x_kimchi_env_alarm (first_at desc);

-- 3. 소독수 농도 수기 로그 (E4 · 원천 WSH_SANITIZER_LOG 의 수기 부분) — X-WSH-01
create table x_kimchi_sanitizer_log (
    id             bigserial primary key,
    equipment_id   bigint not null references bas_equipment (id),    -- 소독수 공급장치
    work_order_id  bigint references job_work_order (id),
    ppm_value      numeric(8,2) not null,
    contact_min    numeric(8,2),
    dosing_rate    numeric(8,3),
    source         text not null default 'manual',                   -- manual/collect
    deviated       char(1) not null default 'N',                     -- 10ppm 미달
    alarm_id       bigint references x_kimchi_env_alarm (id),
    measured_at    timestamptz not null,
    canceled_yn    char(1) not null default 'N',
    created_at     timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs          jsonb not null default '{}',
    constraint x_kimchi_sanitizer_log_source_chk check (source in ('manual', 'collect')),
    constraint x_kimchi_sanitizer_log_dev_chk check (deviated in ('Y', 'N')),
    constraint x_kimchi_sanitizer_log_cancel_chk check (canceled_yn in ('Y', 'N'))
);
create index x_kimchi_sanitizer_log_equip_ix on x_kimchi_sanitizer_log (equipment_id, measured_at desc);

-- 4. 테이핑기 실적 집계 로그 (E4 · 원천 PKG_TAPING_LOG) — X-PKG-01
create table x_kimchi_taping_log (
    id              bigserial primary key,
    equipment_id    bigint not null references bas_equipment (id),   -- 자동포장기
    work_result_id  bigint references pop_work_result (id),          -- 진행 중 포장 실적 (없으면 NULL)
    work_order_id   bigint references job_work_order (id),
    pack_qty        numeric(12,0) not null,                          -- 이번 구간 포장 수량(박스) — 증분
    cum_count       numeric(12,0),                                   -- 설비 카운터 누계 원값 (collect)
    run_status      text,                                            -- 가동/정지
    run_minutes     numeric(8,1),
    source          text not null default 'manual',                  -- manual/collect
    raw_id          bigint references ifc_collect_raw (id),
    logged_at       timestamptz not null,
    created_at      timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs           jsonb not null default '{}',
    constraint x_kimchi_taping_log_source_chk check (source in ('manual', 'collect')),
    constraint x_kimchi_taping_log_run_chk check (run_status is null or run_status in ('가동', '정지')),
    constraint x_kimchi_taping_log_uq unique (equipment_id, logged_at, source)
);

-- 6. LOT 확장 (E2 집계 · 검색용 · 원천 AGE_STOCK + PKG_COLD_STOCK 현재 위치) — lot 1:1 ext
create table x_kimchi_lot_ext (
    id                     bigint primary key references lot (id) on delete cascade,
    aging_start_date       date,                                     -- 숙성 투입일 (AGING)
    aging_due_date         date,                                     -- 완료 예정일 = 시작 + aging_days (없으면 21 · D-511)
    aging_end_date         date,
    shippable_yn           char(1) not null default 'N',             -- 출하 가능 (validate_shipment 거부 3)
    location_equipment_id  bigint references bas_equipment (id),     -- 현재 냉장고 (검색 · FIFO 정렬 — attrs 가 아니라 ext · D-05)
    tank_equipment_id      bigint references bas_equipment (id),     -- TANK LOT 의 절임통 (역추적 노드 표시용 비정규화)
    created_at             timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs                  jsonb not null default '{}',
    constraint x_kimchi_lot_ext_ship_chk check (shippable_yn in ('Y', 'N'))
);
create index x_kimchi_lot_ext_location_ix on x_kimchi_lot_ext (location_equipment_id);
create index x_kimchi_lot_ext_due_ix on x_kimchi_lot_ext (aging_due_date);

-- 7. 냉장고 입출고 이력 (E4 · 원천 PKG_COLD_STOCK) — X-AGE-02
create table x_kimchi_cold_move (
    id            bigserial primary key,
    lot_id        bigint not null references lot (id),               -- PRODUCT · AGING
    equipment_id  bigint not null references bas_equipment (id),     -- 냉장고
    trx_type      text not null,                                     -- 입고/출고
    qty           numeric(12,3) not null,
    unit          text,
    device        text,                                              -- web / pop / mobile
    moved_at      timestamptz not null,
    canceled_yn   char(1) not null default 'N',
    created_at    timestamptz not null default now(), created_by text, updated_at timestamptz, updated_by text,
    attrs         jsonb not null default '{}',
    constraint x_kimchi_cold_move_type_chk check (trx_type in ('입고', '출고')),
    constraint x_kimchi_cold_move_cancel_chk check (canceled_yn in ('Y', 'N'))
);
create index x_kimchi_cold_move_lot_ix on x_kimchi_cold_move (lot_id, moved_at);
create index x_kimchi_cold_move_equip_ix on x_kimchi_cold_move (equipment_id, moved_at desc);

-- 뷰 2 (팩 · 선택) — 저장하지 않고 계산한다
-- 절임통 × 현재 배치 (X-TANK-01 현황판). 절임통 = 공정 P03 에 속하고 collect_yn=N 인 설비(TK-nn). 미완료 배치는 절임통당 최대 1.
create view x_kimchi_v_tank_board as
select e.id as equipment_id, e.equip_code, e.equip_name,
       k.id as work_result_id, k.status as tank_status, k.target_salinity_pct, k.target_hours, k.input_weight_kg, k.plan_end_at, k.completed_at,
       k.final_salinity_pct, k.sensor_equipment_id, k.std_id,
       r.started_at, r.ended_at, r.product_lot_id, w.work_order_no, w.item_id, i.item_code, i.item_name, l.lot_no, l.kind as lot_kind
  from bas_equipment e
  join bas_process p on p.id = e.process_id and p.process_code = 'P03'
  left join x_kimchi_tank k on k.equipment_id = e.id and k.status <> '완료'
  left join pop_work_result r on r.id = k.id
  left join job_work_order w on w.id = r.work_order_id
  left join bas_item i on i.id = w.item_id
  left join lot l on l.id = r.product_lot_id
 where e.use_yn = 'Y' and e.collect_yn = 'N';

-- 숙성 재고 — lot(kind=AGING) × v_lot_state=재고 × v_lot_stock × ext
create view x_kimchi_v_aging_stock as
select l.id as lot_id, l.lot_no, l.item_id, i.item_code, i.item_name, l.qty, l.unit, k.remain_qty, s.state, l.insp_status, l.made_at,
       x.aging_start_date, x.aging_due_date, x.aging_end_date, x.shippable_yn, x.location_equipment_id, e.equip_code as location_code, e.equip_name as location_name,
       (current_date - x.aging_start_date) as elapsed_days
  from lot l
  join v_lot_state s on s.lot_id = l.id
  join v_lot_stock k on k.lot_id = l.id
  left join x_kimchi_lot_ext x on x.id = l.id
  left join bas_item i on i.id = l.item_id
  left join bas_equipment e on e.id = x.location_equipment_id
 where l.kind = 'AGING' and s.state = '재고';
