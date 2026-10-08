-- 뷰 3 — 저장하지 않고 계산하는 값 (contracts/db-schema.md §3.4). make db-schema 가 schema.sql 다음에 적용한다.
--   v_lot_stock           LOT 잔량 (MATERIAL: qty − Σ pop_input · PRODUCT: qty − Σ 자식 계보 qty)
--   v_lot_state           LOT 상태 재고/소진/출하 — 계보와 잔량으로만 판정 (상태 컬럼 없음)
--   v_work_order_progress 작업지시 진행 여부 — 실적 유무로 계산

create view v_lot_stock as
select l.id as lot_id, l.lot_no, l.kind, l.kind_base, l.qty,
       case l.kind_base
           when 'MATERIAL' then coalesce((select sum(i.qty) from pop_input i where i.material_lot_id = l.id and i.canceled_yn = 'N'), 0)
           when 'PRODUCT'  then coalesce((select sum(g.qty) from lot_genealogy g where g.parent_lot_id = l.id), 0)
           else 0
       end as consumed_qty,
       coalesce(l.qty, 0) - case l.kind_base
           when 'MATERIAL' then coalesce((select sum(i.qty) from pop_input i where i.material_lot_id = l.id and i.canceled_yn = 'N'), 0)
           when 'PRODUCT'  then coalesce((select sum(g.qty) from lot_genealogy g where g.parent_lot_id = l.id), 0)
           else 0
       end as remain_qty
  from lot l;

create view v_lot_state as
select l.id as lot_id, l.lot_no, l.kind, l.kind_base,
       case
           when l.kind_base = 'SHIPMENT' then '출하'
           when l.kind_base = 'PRODUCT' and exists (select 1 from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '출하') then '출하'
           when l.kind_base = 'PRODUCT' and exists (select 1 from lot_genealogy g where g.parent_lot_id = l.id
                                                      and g.relation_base in ('분할', '합병', '생산', '투입')) then '소진'
           when l.kind_base = 'MATERIAL' and l.qty is not null and s.remain_qty <= 0 then '소진'
           else '재고'
       end as state
  from lot l
  join v_lot_stock s on s.lot_id = l.id;

create view v_work_order_progress as
select w.id as work_order_id, w.work_order_no, w.status,
       exists (select 1 from pop_work_result r where r.work_order_id = w.id) as started,
       (w.status = '마감') as closed,
       (select count(*) from pop_work_result r where r.work_order_id = w.id) as result_count,
       (select count(*) from pop_work_result r where r.work_order_id = w.id and r.ended_at is null) as open_count,
       coalesce((select sum(r.good_qty) from pop_work_result r where r.work_order_id = w.id), 0) as good_qty,
       coalesce((select sum(r.defect_qty) from pop_work_result r where r.work_order_id = w.id), 0) as defect_qty
  from job_work_order w;
