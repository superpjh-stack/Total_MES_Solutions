-- 뷰 3 — 저장하지 않고 계산하는 값 (contracts/db-schema.md §3.4). make db-schema 가 schema.sql 다음에 적용한다.
--   v_lot_stock           LOT 잔량 (MATERIAL: qty − Σ pop_input · PRODUCT: qty − Σ 자식 계보 qty − Σ 열린 실적(종료 전)의 pop_input — 회전 5 · DEF-QA2-001)
--   v_lot_state           LOT 상태 재고/소진/출하 — 계보와 잔량으로만 판정 (상태 컬럼 없음). PRODUCT: 출하 계보 → 출하 · 분할/합병/생산 → 소진(LOT 통째) · 그 밖 → 잔량(계보 + 열린 투입) ≤ 0 이면 소진 (D-41)
--   (create or replace — 열이 같으면 운영 DB 에 그대로 다시 적용할 수 있다)
--   v_work_order_progress 작업지시 진행 여부 — 실적 유무로 계산

-- PRODUCT 소비 = 계보(종료 때 쓰인 투입 · 분할 · 합병 · 출하) + 아직 종료 전 실적에 스캔된 투입(취소 제외). 종료되면 그 투입은 계보로 넘어가므로 두 번 세지 않는다.
-- 이것으로 종료 전 두 실적에 같은 생산 LOT 을 이중 투입해 잔량을 넘기는 것을 lineage.consume_material 의 잔량 검사가 막을 수 있다(DEF-QA2-001 · 개발2).
create or replace view v_lot_stock as
select l.id as lot_id, l.lot_no, l.kind, l.kind_base, l.qty,
       case l.kind_base
           when 'MATERIAL' then coalesce((select sum(i.qty) from pop_input i where i.material_lot_id = l.id and i.canceled_yn = 'N'), 0)
           when 'PRODUCT'  then coalesce((select sum(g.qty) from lot_genealogy g where g.parent_lot_id = l.id), 0)
                              + coalesce((select sum(i.qty) from pop_input i join pop_work_result r on r.id = i.work_result_id
                                           where i.material_lot_id = l.id and i.canceled_yn = 'N' and r.ended_at is null), 0)
           else 0
       end as consumed_qty,
       coalesce(l.qty, 0) - case l.kind_base
           when 'MATERIAL' then coalesce((select sum(i.qty) from pop_input i where i.material_lot_id = l.id and i.canceled_yn = 'N'), 0)
           when 'PRODUCT'  then coalesce((select sum(g.qty) from lot_genealogy g where g.parent_lot_id = l.id), 0)
                              + coalesce((select sum(i.qty) from pop_input i join pop_work_result r on r.id = i.work_result_id
                                           where i.material_lot_id = l.id and i.canceled_yn = 'N' and r.ended_at is null), 0)
           else 0
       end as remain_qty
  from lot l;

create or replace view v_lot_state as
select l.id as lot_id, l.lot_no, l.kind, l.kind_base,
       case
           when l.kind_base = 'SHIPMENT' then '출하'
           when l.kind_base = 'PRODUCT' and exists (select 1 from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '출하') then '출하'
           when l.kind_base = 'PRODUCT' and exists (select 1 from lot_genealogy g where g.parent_lot_id = l.id
                                                      and g.relation_base in ('분할', '합병', '생산')) then '소진'
           -- 부분 투입 (회전 4 · 개발3 17) + 열린 투입 (회전 7 · D-41 · DEF-QA2-008): 분할/합병/생산 부모가 아니면 잔량으로 판정한다.
           --   잔량(v_lot_stock — 계보 + 종료 전 실적의 투입) ≤ 0 이면 종료 전이라도 소진. 수량 모르는 투입(계보 qty NULL · 열린 pop_input qty NULL)이
           --   있거나 LOT 수량이 없는데 투입이 있으면 소진. 화면 · 추적 · assert_usable 이 같은 값을 본다 — 「재고」 인데 잔량 0 인 LOT 은 없다.
           when l.kind_base = 'PRODUCT'
                and ((l.qty is not null and s.remain_qty <= 0)
                     or exists (select 1 from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '투입' and g.qty is null)
                     or exists (select 1 from pop_input i join pop_work_result r on r.id = i.work_result_id
                                 where i.material_lot_id = l.id and i.canceled_yn = 'N' and r.ended_at is null and i.qty is null)
                     or (l.qty is null and (exists (select 1 from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '투입')
                                            or exists (select 1 from pop_input i join pop_work_result r on r.id = i.work_result_id
                                                        where i.material_lot_id = l.id and i.canceled_yn = 'N' and r.ended_at is null)))) then '소진'
           when l.kind_base = 'MATERIAL' and l.qty is not null and s.remain_qty <= 0 then '소진'
           else '재고'
       end as state
  from lot l
  join v_lot_stock s on s.lot_id = l.id;

create or replace view v_work_order_progress as
select w.id as work_order_id, w.work_order_no, w.status,
       exists (select 1 from pop_work_result r where r.work_order_id = w.id) as started,
       (w.status = '마감') as closed,
       (select count(*) from pop_work_result r where r.work_order_id = w.id) as result_count,
       (select count(*) from pop_work_result r where r.work_order_id = w.id and r.ended_at is null) as open_count,
       coalesce((select sum(r.good_qty) from pop_work_result r where r.work_order_id = w.id), 0) as good_qty,
       coalesce((select sum(r.defect_qty) from pop_work_result r where r.work_order_id = w.id), 0) as defect_qty
  from job_work_order w;
