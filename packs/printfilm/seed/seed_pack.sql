-- printfilm 팩 테이블 · 속성 시드 (개발2 · 2026-10-09) — 코어 seed_core 가 받지 않는 시드를 CSV 그대로 읽어 멱등으로 넣는다 (2회 실행 행 수 diff 0).
--   seed_core 는 seeds[] 파일 이름이 codes* · items* · processes* · equipment* · partners* 인 것만 받고, processes* 의 attrs.* 열은 버린다 (pack-contract.md §2).
--   그래서 판사양 · 아니록스 · 잉크조성(+조성 행) · 불량코드(attrs.defect_group) · 공정 구분(bas_process.attrs.process_type) · 인쇄 지표(kpi_indicator) 는 여기서 넣는다.
--   → 코어 변경 요청(progress-dev2.md §3): seeds[] 에 x_<팩>_ 테이블 파일 · *.attrs.* 열 · defect_codes* 지원.
-- 실행 순서 (프로젝트 루트에서): **이 파일 → make db-seed** (→ 이 파일 다시 돌려도 diff 0).
--   seed_core 는 process_params(EX-PR-10 참조) 를 seeds[](processes_example.csv) 보다 먼저 넣어 공정이 없으면 NOT NULL 로 실패한다 → 공정 · 품목도 여기서 먼저 넣는다 (코어 변경 요청: 적재 순서).
--   psql -q -h /tmp -d mes_printfilm_db -v ON_ERROR_STOP=1 -f packs/printfilm/seed/seed_pack.sql && MES_PACK=printfilm make db-seed
-- 데이터 원본은 seed/*.csv 뿐 — 이 파일에 값은 없다. 규격 값(도수 · 선수 · 셀 용적 · Lab)은 CSV 에서도 비어 있다(미확정). kpi_indicator 4행만 여기 적는다(hooks.md §6).
\set ON_ERROR_STOP on
begin;

-- 공정 (processes_example.csv — seed_core 의 processes* 로더와 같은 upsert + attrs.process_type)
create temp table t_procs (process_code text, process_name text, seq text, use_yn text, process_type text) on commit drop;
\copy t_procs from 'packs/printfilm/seed/processes_example.csv' with (format csv, header true)
insert into bas_process (process_code, process_name, seq, use_yn, attrs, created_by)
select process_code, process_name, coalesce(nullif(seq, ''), '0')::int, coalesce(nullif(use_yn, ''), 'Y'),
       case when nullif(process_type, '') is null then '{}'::jsonb else jsonb_build_object('process_type', process_type) end, 'seed:printfilm'
  from t_procs
    on conflict (process_code) do update set process_name = excluded.process_name, seq = excluded.seq, use_yn = excluded.use_yn,
       attrs = bas_process.attrs || excluded.attrs;

-- 품목 (items_example.csv — seed_core 의 items* 로더와 같은 upsert · 판사양이 참조한다)
create temp table t_items (item_code text, item_name text, item_type text, spec text, unit text, use_yn text) on commit drop;
\copy t_items from 'packs/printfilm/seed/items_example.csv' with (format csv, header true)
insert into bas_item (item_code, item_name, item_type, spec, unit, use_yn, created_by)
select item_code, item_name, item_type, nullif(spec, ''), nullif(unit, ''), coalesce(nullif(use_yn, ''), 'Y'), 'seed:printfilm' from t_items
    on conflict (item_code) do update set item_name = excluded.item_name, item_type = excluded.item_type, spec = excluded.spec, unit = excluded.unit;

create temp table t_plates (plate_code text, plate_name text, item_code text, color_count text, spec_note text, use_yn text) on commit drop;
\copy t_plates from 'packs/printfilm/seed/plates_example.csv' with (format csv, header true)
insert into x_printfilm_plate (plate_code, plate_name, item_id, color_count, spec_note, use_yn, created_by)
select p.plate_code, p.plate_name, i.id, nullif(p.color_count, '')::int, nullif(p.spec_note, ''), coalesce(nullif(p.use_yn, ''), 'Y'), 'seed:printfilm'
  from t_plates p left join bas_item i on i.item_code = p.item_code
    on conflict (plate_code) do update set plate_name = excluded.plate_name, item_id = excluded.item_id, color_count = excluded.color_count,
       spec_note = excluded.spec_note, use_yn = excluded.use_yn;

create temp table t_anilox (anilox_code text, anilox_name text, line_count text, cell_volume text, note text, use_yn text) on commit drop;
\copy t_anilox from 'packs/printfilm/seed/anilox_example.csv' with (format csv, header true)
insert into x_printfilm_anilox (anilox_code, anilox_name, line_count, cell_volume, note, use_yn, created_by)
select anilox_code, anilox_name, nullif(line_count, '')::numeric, nullif(cell_volume, '')::numeric, nullif(note, ''), coalesce(nullif(use_yn, ''), 'Y'), 'seed:printfilm'
  from t_anilox
    on conflict (anilox_code) do update set anilox_name = excluded.anilox_name, line_count = excluded.line_count, cell_volume = excluded.cell_volume,
       note = excluded.note, use_yn = excluded.use_yn;

create temp table t_inks (ink_code text, ink_name text, color_name text, target_l text, target_a text, target_b text, note text, use_yn text) on commit drop;
\copy t_inks from 'packs/printfilm/seed/inks_example.csv' with (format csv, header true)
insert into x_printfilm_ink_formula (ink_code, ink_name, color_name, target_l, target_a, target_b, note, use_yn, created_by)
select ink_code, ink_name, nullif(color_name, ''), nullif(target_l, '')::numeric, nullif(target_a, '')::numeric, nullif(target_b, '')::numeric, nullif(note, ''),
       coalesce(nullif(use_yn, ''), 'Y'), 'seed:printfilm'
  from t_inks
    on conflict (ink_code) do update set ink_name = excluded.ink_name, color_name = excluded.color_name, target_l = excluded.target_l, target_a = excluded.target_a,
       target_b = excluded.target_b, note = excluded.note, use_yn = excluded.use_yn;

create temp table t_ink_comp (ink_code text, seq_no text, component_name text, ratio_pct text) on commit drop;
\copy t_ink_comp from 'packs/printfilm/seed/ink_components_example.csv' with (format csv, header true)
insert into x_printfilm_ink_formula_component (ink_formula_id, seq_no, component_name, ratio_pct, created_by)
select k.id, c.seq_no::int, c.component_name, c.ratio_pct::numeric, 'seed:printfilm'
  from t_ink_comp c join x_printfilm_ink_formula k on k.ink_code = c.ink_code
    on conflict (ink_formula_id, seq_no) do update set component_name = excluded.component_name, ratio_pct = excluded.ratio_pct;

-- 불량코드 (defect_codes_example.csv — seed_core 가 받지 않는 파일 이름 · attrs.defect_group)
create temp table t_defects (defect_code text, defect_name text, process_code text, use_yn text, defect_group text) on commit drop;
\copy t_defects from 'packs/printfilm/seed/defect_codes_example.csv' with (format csv, header true)
insert into bas_defect_code (defect_code, defect_name, process_id, use_yn, attrs, created_by)
select d.defect_code, d.defect_name, p.id, coalesce(nullif(d.use_yn, ''), 'Y'),
       case when nullif(d.defect_group, '') is null then '{}'::jsonb else jsonb_build_object('defect_group', d.defect_group) end, 'seed:printfilm'
  from t_defects d left join bas_process p on p.process_code = d.process_code
    on conflict (defect_code) do update set defect_name = excluded.defect_name, process_id = excluded.process_id, use_yn = excluded.use_yn, attrs = excluded.attrs;

-- 인쇄 지표 정의 (hooks.md §6 · D-510 — 권한 표에서 kpi 는 조회 ×4 라 화면 등록은 아무도 못 한다). 목표값은 (미확정) → NULL
insert into kpi_indicator (indicator_key, name, unit, target_value, calc_kind, visible_yn, seq, created_by) values
  ('avg_delta_e',      '평균 ΔE (검사) (예시)', null, null, 'pack:avg_delta_e',      'Y', 101, 'seed:printfilm'),
  ('fail_roll_count',  '불합격 롤 수 (예시)',   '개', null, 'pack:fail_roll_count',  'Y', 102, 'seed:printfilm'),
  ('stock_roll_count', '재고 롤 수 (예시)',     '개', null, 'pack:stock_roll_count', 'Y', 103, 'seed:printfilm'),
  ('splice_count',     'splice 건수 (예시)',    '건', null, 'pack:splice_count',     'Y', 104, 'seed:printfilm')
    on conflict (indicator_key) do update set name = excluded.name, unit = excluded.unit, calc_kind = excluded.calc_kind, seq = excluded.seq;

commit;
select 'printfilm 팩 시드 — 판사양 '||(select count(*) from x_printfilm_plate)||' · 아니록스 '||(select count(*) from x_printfilm_anilox)
       ||' · 잉크조성 '||(select count(*) from x_printfilm_ink_formula)||' · 조성 행 '||(select count(*) from x_printfilm_ink_formula_component)
       ||' · 불량코드(EX-DF) '||(select count(*) from bas_defect_code where defect_code like 'EX-DF-%')
       ||' · 공정 구분 '||(select count(*) from bas_process where attrs ? 'process_type')||' · 지표(pack:) '||(select count(*) from kpi_indicator where calc_kind like 'pack:%') as result;
