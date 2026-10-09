# QA2 — 계보 · 측정값 · 데이터 (G-C04 뷰 · G-C05~G-C12 · G-C24 · 팩 3 G-P04 재검산)

- 작성: QA2 · 2026-10-09 (회전 4 진행 중 코드 기준 — 같은 날 커밋 `3d2bdf3`(v_lot_state 부분 투입) · `2bf68da`(lineage) 반영본)
- 도구: `src/mescore/tools/check_data.py` (gate 가 부른다 — `G-nn  항목  PASS|FAIL  실측`). **고치지 않았다.**
- 전용 DB `mes_qa2_db` 를 매번 처음부터(스키마 52 + 뷰 3) 만든다. `MES_PG_DSN` 을 그 DB 로 덮어쓰며, `mes_qa2*` 가 아닌 DB 는 거부한다.
- 기대값 출처: `goal.md` §2 · `contracts/db-schema.md` §2·§3 · `spec.md` §2.2 · `core.yaml` · 팩 `gates.yaml` (개발 테스트 단언은 쓰지 않는다).

## 1. 판정 요약 (코어 단독 · `MES_PACK=`)

| 게이트 | 판정 | 핵심 실측 |
|---|---|---|
| G-C04 뷰 3 | **FAIL**(1/4) | 뷰 3 전 행 = 내 SQL · 원재료 부분/취소 투입 PASS · 부분 투입 생산 LOT 잔량 판정 PASS · **반제품 이중 스캔 잔량 초과 FAIL**(DEF-QA2-001). 게이트 G-C04 자체는 check_schema 소관 — 이 행들은 gate 가 읽지 않는다 |
| G-C05 쓰기 경계 | PASS | 라우터 16 정적 스캔 경계 밖 0 · 공용 모듈 계약 밖 0 · lot_genealogy 쓰기 = lineage.py 뿐 · 조회 GET 132(빈 DB) / 442(채워진 DB) 전후 업무 테이블 40 diff 0 |
| G-C06 계보 10행 | PASS | API 22회 → 10행 · 투입 3 합병 2 분할 3 출하 2 · §3.3 표와 화살표 1:1 |
| G-C07 추적 | PASS | 역방향 원재료 ①② · 화살표 9 / 정방향 9 · ③ 재고 · 임의 분기 5단 · 무작위 DAG 300 · 깊이 20 분기 100 → lineage 0.046s / 0.009s |
| G-C08 키 연결 | **FAIL** | 내 SQL 로는 지시 · 실적 2 · 측정값 2 · 검사 · 출하 다 이어짐 · 채번 형식 13건 · 카운터 일치 — **추적 화면의 지시 링크 404**(DEF-QA2-002) |
| G-C09 시드 멱등 | PASS | seed_core ×2 diff 0 (테이블 50 · 행 161) · 시드 행 40 (예시)/EX 표기 |
| G-C10 집계 | PASS | production 12 · quality 9 · delivery 6 · equipment 3 · measure_series 270 · core_metrics 3 대조 불일치 0 |
| G-C11 빈 화면 | **FAIL**(경미) | 빈 DB 54화면 미수집 표시 PASS · `미확정` 에 (D-nn) 없음 2곳(DEF-QA2-003) |
| G-C12 범위 밖 | PASS | 라우트 147 제어성 0 · /eqp 쓰기 4(상태·점검·고장) · DB 테이블 52 = spec §2.2 · 이름 금지어 0 · 외부 장치/AI 라이브러리 0 |
| G-C24 측정값 | PASS | BAS API 선언 3 → 폼 칸 3 · 필수 누락 422(저장 0) · 이탈 25 저장+표시 · collect avg 3(구간 밖 9 제외) · 수신 0 → 미수집 · 선언 변경 즉시 반영 · measure_series 일치 |

### gate 에 읽히는 판정 줄 (`gate.per_gate` 로 이 도구 출력을 파싱한 결과)

```
G-C05 PASS 검사 5 전부 PASS
G-C06 PASS 검사 2 전부 PASS
G-C07 PASS 검사 7 전부 PASS
G-C08 FAIL 검사 3 · 통과 못한 1 — LOT 번호 → 화면 링크 따라가기 (API): … 지시 링크 /job/status?wo=W261009-001 → 404
G-C09 PASS 검사 2 전부 PASS
G-C10 PASS 검사 6 전부 PASS
G-C11 FAIL 검사 2 · 통과 못한 1 — 미확정 표기 — (D-nn) 동반: KPI-01 「목표 미확정 %」 · SYS-06 「미확정 (MES_MIGRATE_DIR 없음)」
G-C12 PASS 라우트 147 중 제어 · 명령성 0 · …
G-C24 PASS 폼 칸 ['m_qa2_req', 'm_qa2_rng', 'm_qa2_col'] · …
```
`참고` 로 시작하는 행은 gate 가 읽지 않는 관찰(결함 목록 경미 항목)이다.

## 2. 결함

| ID | 등급 | 게이트 | 내용 | 재현 | 담당 |
|---|---|---|---|---|---|
| DEF-QA2-001 | **중대** | G-C04 · G-C06 | 생산(반제품) LOT 을 **종료 전** 두 실적에 이중 스캔하면 잔량을 넘어 받아들인다. 생산 LOT 20 → 실적 E 15 · 실적 F 15 → 둘 다 200, 종료 뒤 `v_lot_stock` 소비 30 · 잔량 **−10**. `consume_material` 의 잔량 검사가 `v_lot_stock.remain_qty` 를 보는데 PRODUCT 소비는 계보(종료 때)만 세고 열린 `pop_input` 은 안 센다(원재료는 센다 — 71 투입 422 정상) | check_data `view_material` | 개발2 (`lineage.consume_material`) · 아키텍트(`v_lot_stock` 정의 — 열린 pop_input 포함 여부) |
| DEF-QA2-002 | **중대** | G-C08 | TRC-01/02 노드 링크 `work_order` = `/job/status?wo=<지시 번호>` 인데 JOB-02 는 `wo` 를 **id** 로만 받아(`wo_of_path → id_of_path`) **404**. LOT 번호 → 지시 · 실적 · 측정값 드릴다운(D-604)이 끊긴다 | `GET /trc/backward?no=<분할①>` → start_links.work_order → GET → 404 | 개발3(trc `_links`) · 개발1(job `?wo=`) — D-604 인자 형식 확정 필요 |
| DEF-QA2-003 | 경미 | G-C11 | 미정 값 표기에 D-번호 없음: KPI-01 현황판 「목표 미확정 %」(목표 NULL — D-602) · SYS-06 「이관 실행 폴더 미확정 (MES_MIGRATE_DIR 없음)」. goal G-C11 형식은 `미확정 (D-nn)` | 빈 DB `/kpi/board` · `/sys/backup` HTML | 개발3·디자이너3(KPI-01) · 개발1(SYS-06) |
| DEF-QA2-004 | 경미 | (참고) G-C24 | 측정값 선언을 `use_yn=N` 으로 끄면 **지난 실적**의 POP-02 화면에서 그 기록(pop_measure 값 3)이 사라진다 — 화면이 현재 선언만 그린다. 기록은 DB 에 남음 | `POP-02?id=<실적>` 선언 변경 전후 | 개발2 |
| DEF-QA2-005 | 경미 | (참고) G-C10 | `stats.totals("equipment").mttr_hours` 가 설비별 MTTR 의 평균(0.4167h) — 복구 고장 전체 평균(0.4444h)과 다르다. totals 문서의 "비율의 평균이 아니다" 원칙과 어긋남(합계 줄 · 현황판) | 설비 2대 고장 1 · 2건 | 개발3 |
| DEF-QA2-006 | 경미 | G-P04 kimchi | `gates.yaml` S1 기대값과 재현이 다르다: genealogy_rows **9** ↔ 실제 **10**(혼합 API 가 별도 LOT) · p1_remain_qty **150 재고** ↔ 실제 **0 소진**(P1 850 전량 투입). 팩 테스트는 10 · 0 으로 단언(기대값을 테스트에서 바꿈) | `check_data --pack kimchi` · `--pack-readonly kimchi` | 개발3(kimchi) · 기획자3 — gates.yaml 정정 또는 시나리오 수정 |

치명 0 · 중대 2 · 경미 4.

## 3. 통과 실측 (요지)

- **G-C06**: 수주 → 계획 확정 → 지시(계획·수주 상세 연결) → 입고 2 · 입고검사 합격 2 → 실적①(M① 50) · 실적②(M① 50 + M② 50) → 합병(2:1, 100) → 분할 3(30·30·40) → 최종검사 합격 ①② → 출하 등록 · 스캔 ①② · 승인(admin). `lot_genealogy` 10행, `relation = relation_base`.
- **G-C07**: 시나리오 LOT 9개 × 2방향 — 노드 · 화살표 id · 최단 depth 가 내 SQL 과 같고, TRC API JSON 의 edge_count · genealogy_id 도 같다. 없는 번호 422. 임의 분기 5단(분할 2~3 · 1:1 생산 · 합병 · 2단 건너뛰기 화살표) 9노드/20화살표 · 무작위 DAG 300노드/516화살표 표본 40 × 2방향 불일치 0 · 순환/자기참조 거부. 깊이 20 분기 100: 2,000 화살표 · 깊이 20 · 정 0.046s / 역 0.009s / 내 SQL 0.005s. `lot_genealogy` 에 경로 컬럼 0 · 클로저 테이블 0. 임의 계보는 한 트랜잭션에서 만들고 되돌린다.
- **G-C08**: 분할① → 지시 W…-001 · 실적 2 · 측정값 2 · 검사(자기 1 · 조상 포함 3) · 출하 1. `sys_number_seq` 쓰는 파일 numbering.py 뿐 · 이번 실행 번호 13건 전부 `prefix + to_char(date_format) + seq_digits` · 범위별 최대 일련번호 = 카운터.
- **G-C10**: 기간 3(오늘 · ±30일 · 2000-01 빈 기간) × by 전부 × agg 6. 재료: 판정 합격/불합격(불량 2)/조건부 · 수주 4(정시 · 지연 미출하 · 대기 · 늦은 승인 출하) · 설비 로그(가동 → 정지 → 고장 → 조치 가동) 2대 · 측정값 키 6.
- **G-C04 뷰**: v_lot_stock 22 · v_lot_state 22 · v_work_order_progress 10 행 전부 §3.4(회전 4 문장) 재구현과 일치. 원재료 100 → 투입 30 + 20 취소 → 소비 30 · 잔량 70 · 재고 · 71 투입 422 · mat_stock = Σ mat_stock_trx. 생산 LOT 40 중 15 투입 → 잔량 25 · 재고.
- **G-C24**: 공정 · 수집 설비 · 선언 3행을 **BAS API**(F-BAS-09·17·13)로만 만들었다. 코어 코드가 선언 키를 아는 곳 0. collect 값은 `POST /ifc/collect`(토큰)로 넣었다. 선언 변경(필수화 · 4번째 추가 · 수집 칸 끔) → 새 실적 폼 `[m_qa2_req, m_qa2_rng, m_qa2_new]` · 필수화된 칸 누락 422.

## 4. 팩 3 재검산 (`check_data --pack <팩>` = mes_qa2_db 에 팩 스키마 · 시드 → gates.yaml scenarios 테스트로 데이터 생성 → **내 SQL** 로 대조 · `--pack-readonly` = 팩 DB 읽기만)

| 팩 | 내 SQL 대조 (mes_qa2_db / 팩 DB 읽기) | write_scope 정적 스캔 |
|---|---|---|
| printfilm | S1 10행 · 투입3 splice2 슬리팅3 출하2 · base 투입3 합병2 분할3 출하2 · 역방향 9 · 정방향(M①) 9 · 팩 종류 LOT 6 · 소진3 출하2 재고1 — **PASS / PASS** (기대값은 gates.yaml 에서 읽는다) | PASS (밖 0 · lot_genealogy 직접 0) |
| foodservice | 소요량 첫 기간 MAT-1001 144/120/24 · MAT-1002 42/80/0 (= 1200×12/100 · 1200×3.5/100) · 부족 = max(소요−가용,0) 14행/270행 전부 · collect 측정값 21행/60행 = eqp_collect 구간 재집계 · S1 실적① RPM 73.5 · STIR_TIME 30 · TEMP 161.25 · 출고 LOT 역방향 6 · 원료 2 — **PASS / PASS** | PASS (시드 스크립트 seed_pack.py 는 대상 밖) |
| kimchi | 역방향 원재료 3 · 깊이 5 · TANK 2 소진 · salinity_pct 2 · S3 알람 3행 첫 count 2 PASS / **genealogy_rows 10 ≠ 9 · P1 잔량 0 소진 ≠ 150 재고 FAIL**(DEF-QA2-006) — 두 DB 같은 결과 | PASS |

foodservice 는 `seed_core` 만으로는 S1~S7 이 로그인 401 로 실패한다 — 팩 README 대로 `packs/foodservice/seed_pack.py` 까지 돌려야 한다(도구가 있으면 같이 돈다).

## 5. 명령

```
uv run python src/mescore/tools/check_data.py                 # 코어 (gate 가 --run-seeds 를 붙여 부른다 — 시드는 늘 2회)
uv run python src/mescore/tools/check_data.py -v              # + 단계 메모
uv run python src/mescore/tools/check_data.py --pack printfilm|foodservice|kimchi
uv run python src/mescore/tools/check_data.py --pack-readonly printfilm|foodservice|kimchi
make check-terms                                              # 이 도구 파일 금지어 0 확인 (G-C23)
```
실행 시간: 코어 약 20s · 팩 4~9s.

## 6. 내 SQL 원문

역방향(조상 전부 · 방문 집합 · 최단 깊이):
```sql
with recursive up (lot_id, d) as (
    select %(id)s::bigint, 0
    union
    select g.parent_lot_id, up.d + 1 from lot_genealogy g join up on g.child_lot_id = up.lot_id
)
select lot_id, min(d) as d from up group by lot_id
```
정방향(자손 전부):
```sql
with recursive dn (lot_id, d) as (
    select %(id)s::bigint, 0
    union
    select g.child_lot_id, dn.d + 1 from lot_genealogy g join dn on g.parent_lot_id = dn.lot_id
)
select lot_id, min(d) as d from dn group by lot_id
```
지나간 화살표: 역방향 `select id … from lot_genealogy where child_lot_id = any(%(ids)s)` · 정방향 `… where parent_lot_id = any(%(ids)s)`.

뷰 3 재구현(뷰를 읽지 않는다 — 상태는 Python 에서 §3.4 문장대로):
```sql
select l.id, l.kind_base, l.qty,
       (select coalesce(sum(i.qty), 0) from pop_input i where i.material_lot_id = l.id and i.canceled_yn = 'N') as input_qty,
       (select coalesce(sum(g.qty), 0) from lot_genealogy g where g.parent_lot_id = l.id) as child_qty,
       (select count(*) from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '출하') as n_ship_out,
       (select count(*) from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base in ('분할', '합병', '생산')) as n_whole,
       (select count(*) from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '투입') as n_input,
       (select count(*) from lot_genealogy g where g.parent_lot_id = l.id and g.relation_base = '투입' and g.qty is null) as n_input_noqty
  from lot l;

select w.id, w.status, count(r.id) as n, count(r.id) filter (where r.ended_at is null) as n_open,
       coalesce(sum(r.good_qty), 0) as good, coalesce(sum(r.defect_qty), 0) as defect
  from job_work_order w left join pop_work_result r on r.work_order_id = w.id group by w.id, w.status;
```

집계 재계산 — 원행만 SQL 로 가져오고 묶음 · 비율은 Python(분모 0 → None):
```sql
-- 생산 계획 쪽 / 실적 쪽 (키: plan_date|item_id|process_id|equipment_id ↔ ended_at::date|w.item_id|r.process_id|r.equipment_id)
select <키> as k, plan_qty from job_work_order where status <> '취소' and plan_date between %s and %s;
select <키> as k, r.good_qty, r.defect_qty from pop_work_result r join job_work_order w on w.id = r.work_order_id
 where r.ended_at is not null and r.ended_at::date between %s and %s;
-- 품질
select n.judged_at::date as day, l.item_id, n.judgement from qua_inspection n join lot l on l.id = n.lot_id
 where n.judgement is not null and n.judged_at::date between %s and %s;
select d.defect_code_id, d.qty, d.inspection_id from qua_defect d join qua_inspection n on n.id = d.inspection_id
 where n.judgement is not null and n.judged_at::date between %s and %s;
-- 납기 (수주별 승인 출하 최소 ship_date 로 정시/지연/대기)
select id, partner_id, due_date from ord_order where status <> '취소' and due_date between %s and %s;
select order_id, ship_date from shp_shipment where status = '승인' and order_id is not null;
-- 설비 (구간을 [frm 00:00, to+1 00:00) 로 잘라 상태별 초 · 열린 구간은 now())
select equipment_id, state, started_at, ended_at from eqp_run_log;
select equipment_id, occurred_at, fixed_at from eqp_fault where occurred_at::date between %s and %s;
-- 측정값
select m.id, m.value_num, m.deviated, m.measured_at, m.measured_at::date as day, r.work_order_id, r.equipment_id
  from pop_measure m join pop_work_result r on r.id = m.work_result_id
 where m.param_key = %s and m.value_num is not null and m.measured_at::date between %s and %s;
```

팩 collect 측정값 재집계(foodservice):
```sql
select value_num, ts from eqp_collect where equipment_id = %s and tag = %s and ts >= %s and ts <= %s and value_num is not null order by ts;
```

## 7. 원문 출력 (코어 · 마지막 실행)

```
G-C11  빈 DB 화면 — 미수집 표시  PASS  업무 테이블 0 인 DB 에서 화면 54(코어 51 + 공통) 열기 — 200 아님 0 · 행 없는 <tbody> 0 · 주 목록이 빈데 미수집/미확정 글자 없음 0 · 값 칸 표본 9 중 미수집 없음 0
G-C11  미확정 표기 — (D-nn) 동반  FAIL  화면 본문의 `미확정` 중 `(D-nn)` 이 바로 붙지 않은 곳 ['KPI-01:「% 목표 미확정 % 불량 미수집 시간」', 'SYS-06:「실행 폴더 미확정 (MES_MIGRAT」'] (goal.md G-C11: 미정이면 `미확정 (D-nn)`)
G-C05  조회 화면 전후 업무 테이블 40 diff 0 (빈 DB)  PASS  GET 132회(화면 · 추적 · 라벨 · 인쇄 · 팝업 · 집계 — JSON+HTML) 응답 {2: 132} · 행 수 · 최종 수정 시각 바뀐 테이블 0
G-C09  시드 2회 행 수 diff 0  PASS  make db-seed(seed_core) ×2 rc=0/0 · 테이블 50 · 행 161 · 달라진 테이블 0
G-C09  시드 값 (예시) 표기  PASS  시드 행 40 검사 — 이름에 (예시) 없음 0 · 번호에 EX 없음 0
G-C06  코어 시나리오 lot_genealogy 10행 (API)  PASS  API 22회(수주 · 계획 확정 · 지시 · 입고 2 · 입고검사 2 · 시작/투입/종료 ×2 · 합병 · 분할 · 최종검사 2 · 출하 · 스캔 2 · 승인) → 행 10 · relation {'투입': 3, '합병': 2, '분할': 3, '출하': 2} · db-schema.md §3.3 표와 다른 화살표 빠짐 0 더함 0
G-C06  relation_base 저장  PASS  코어 relation 5종은 relation = relation_base — 다른 행 0
G-C07  역방향 — 출하 LOT → 원재료 ①②  PASS  lineage.trace_backward 원재료 ['M261009-0001', 'M261009-0002'] · 화살표 9 / 내 with recursive 원재료 2 · 화살표 9 (기대 2 · 9)
G-C07  정방향 — 원재료① → 생산①② → 합병 → 분할①②③ → 출하 · ③ 재고  PASS  lineage.trace_forward 노드 8 · 화살표 9 · 재고 ['P261009-0006'] / 내 SQL 노드 8 · 화살표 9 · v_lot_state 분할③ 재고 · 분할① 출하 · 합병 소진 · 원재료① 소진 · 원재료② 재고
G-C07  내 with recursive = lineage.trace_* (시나리오 LOT 9 × 2방향 · API 3)  PASS  노드 · 화살표 · 최단 깊이 불일치 0 · TRC API(JSON) 불일치 0 · 없는 번호 422(기대 422)
G-C07  경로 저장 0  PASS  lot_genealogy 컬럼 13 중 경로성 0 · 경로/클로저 테이블 0
G-C08  LOT 번호 → 지시 · 실적 · 측정값 · 검사 · 출하 (내 SQL)  PASS  분할① P261009-0004 → 지시 W261009-001 · 실적 2 · 측정값 2 · 검사(자기 1 · 조상 포함 3) · 출하 1 · lineage.resolve 지시 W261009-001
G-C08  LOT 번호 → 화면 링크 따라가기 (API)  FAIL  TRC-02 start_links ['backward', 'forward', 'inspection', 'lot', 'work_order'] → 지시 · POP-02 측정값 · QUA-02 검사 · SHP-02 출하 — 불일치 ['지시 링크 /job/status?wo=W261009-001 → 404']
G-C08  채번 — numbering.py 한 곳 · sys_number_rule 형식  PASS  sys_number_seq 를 쓰는 다른 파일 0 · 이번 실행 번호 13 중 형식 밖 0 · 일련번호 최대 ≠ 카운터 0
G-C07  임의 분기 5단 (분할 · 합병 · 생산 · 건너뛰기)  PASS  노드 9 · 정방향 화살표 20 · 최대 깊이 6 · 재고 잎 1 — 노드 9 × 2방향 내 SQL 대조 불일치 0 · 잎→원재료 1 아님 0
G-C07  무작위 DAG 300 노드 대조 · 순환 거부  PASS  노드 300 · 화살표 516 · 표본 40 × 2방향 불일치 0 · 순환 · 자기참조 받아들임 0
G-C07  깊이 20 · 분기 100 · 2초  PASS  lineage 정방향 화살표 2000 · 깊이 20 · 0.045s / 역방향 화살표 20 · 0.008s / 내 SQL 화살표 2000 · 깊이 20 · 0.005s · 노드 집합 같음 True
참고  G-C24 선언을 끈 뒤 지난 실적의 기록 값  WARN  qa2_col 을 use_yn=N 으로 바꾼 뒤 실적 #3 화면에 그 기록(pop_measure 값 3) 안 보임 — 화면이 현재 선언만 그려 기록이 사라져 보인다
G-C24  측정값 선언 3행 → 폼 · 422 · 이탈 · collect · 집계 · 즉시 반영  PASS  폼 칸 ['m_qa2_req', 'm_qa2_rng', 'm_qa2_col'] · HTML 입력 ['m_qa2_req', 'm_qa2_rng'] · 수집 칸 라벨 있음 · 필수 누락 422 · 저장 측정값 0 · LOT None · 범위 이탈 25 → 200 · deviated True · 화면 '이탈' 있음 · collect 수신 [200, 200, 200] → 대표값(avg) 3.0 (기대 3 — 구간 밖 9 제외) · 수신 0 실적 종료 200 · collect 값 None · 화면 미수집 있음 · 선언 변경 뒤 새 실적 폼 ['m_qa2_req', 'm_qa2_rng', 'm_qa2_new'] · 범위 칸 필수화 → 누락 422 · stats.measure_series(day · avg) 불일치 0 · 코어가 선언 키를 아는 곳 0
G-C04  뷰 3 = 내 SQL (전 행)  PASS  v_lot_stock 22행 불일치 0 · v_lot_state 22행 불일치 0 · v_work_order_progress 10행 불일치 0
G-C04  부분 투입 · 취소 투입 (원재료)  PASS  원재료 100 → 투입 30 + 투입 20 취소 → v_lot_stock 소비 30.0 · 잔량 70.0 (기대 30 · 70) · 상태 재고 · 잔량 넘는 71 투입 422(기대 422) · mat_stock 350.0→320.0 = Σ mat_stock_trx 320.0
G-C04  반제품 투입 — 종료 전 이중 스캔이 잔량을 넘는가  FAIL  생산 LOT 20 을 실적 E 에 15 스캔(종료 전) 뒤 실적 F 에 15 스캔 → 200(기대 422 — 합 30 > 20). 둘 다 종료 뒤 v_lot_stock 소비 30.0 · 잔량 -10.0 · 상태 소진 — PRODUCT 소비는 계보(종료 때)로만 세서 종료 전 pop_input 이 잔량 검사에 안 잡힌다(원재료는 잡힌다)
G-C04  반제품 부분 투입 뒤 상태 (잔량 판정)  PASS  생산 LOT 40 중 15 투입 → v_lot_stock 잔량 25.0 · v_lot_state 재고 (db-schema.md §3.4 회전 4: 투입의 부모로만 나오면 잔량으로 — 기대 재고)
G-C10  stats.production = QA2 SQL  PASS  대조 12회(기간 3 × by/agg) · 불일치 0 
G-C10  stats.quality = QA2 SQL  PASS  대조 9회(기간 3 × by/agg) · 불일치 0 
G-C10  stats.delivery = QA2 SQL  PASS  대조 6회(기간 3 × by/agg) · 불일치 0 
G-C10  stats.equipment = QA2 SQL  PASS  대조 3회(기간 3 × by/agg) · 불일치 0 
G-C10  stats.measure_series = QA2 SQL  PASS  대조 270회(기간 3 × by/agg) · 불일치 0 
G-C10  stats.core_metrics = QA2 SQL  PASS  대조 3회(기간 3 × by/agg) · 불일치 0 
참고  G-C10 합계 줄 — 설비 MTTR  WARN  stats.totals(equipment).mttr_hours 0.41666666666666663 · 복구된 고장 전체 평균 0.4444444444444444 — 설비가 둘 이상 고장 수가 다르면 '설비별 평균의 평균' 이 된다
G-C05  라우터별 쓰기 SQL 정적 스캔 = db-schema.md §2  PASS  라우터 16 · 직접 SQL + lineage/measure/collect/erp/stats/numbering 호출을 테이블로 펼침 · 동적 테이블 ['bas:{m.table}→8'] — 경계 밖 0 · 컬럼 제한(t.col) 밖 UPDATE 0 · trc 0 · kpi ['kpi_indicator'] (kpi_indicator 만)
G-C05  공용 모듈 쓰기 = 계약  PASS  lineage · measure · collect · erp · stats · numbering · audit · auth · main · printing · templating 의 쓰기 테이블 계약 밖 0
G-C05  lot_genealogy 쓰는 코드 = lineage.py 뿐  PASS  src/mescore(도구 제외) + packs/ 전 .py 에서 lot_genealogy INSERT/UPDATE/DELETE 하는 다른 파일 0 · 라우터 직접 SQL 0
G-C05  조회 화면 전후 업무 테이블 40 diff 0 (채워진 DB)  PASS  GET 442회(화면 · 추적 · 라벨 · 인쇄 · 팝업 · 집계 — JSON+HTML) 응답 {2: 442} · 행 수 · 최종 수정 시각 바뀐 테이블 0
G-C12  범위 밖 0 — 제어 · 업종 전용 기능  PASS  라우트 147 중 제어 · 명령성 0 · /eqp 쓰기 ['/eqp/checks', '/eqp/faults', '/eqp/faults/{id}/fix', '/eqp/status'] (상태 기록 · 점검 · 고장만) · DB 테이블 52 = spec §2.2 52 (빠짐 0 · 더함 0) · 경로/테이블/컬럼/메뉴/화면 이름의 금지어 0 · 외부 장치 · 연계 · AI 라이브러리 import 0
# check_data — 행 35 · FAIL 3 · WARN 2 · 19s · DB mes_qa2_db
```

## 8. 원문 출력 (팩 3)

```
G-P01  [printfilm] write_scope 밖 쓰기 정적 스캔 (QA2)  PASS  파일 7 · write_scope {'prt': [], 'clr': [], 'rll': ['lot', 'lot_genealogy'], 'hooks': ['lot']} · 밖 0 · lot_genealogy 직접 0 · 시드 스크립트 0(시드는 write_scope 대상 밖으로 봄)
G-P04  [printfilm] 시나리오 테스트로 데이터 만들기 (mes_qa2_db)  PASS  gates.yaml scenarios ['S1:ok', 'S2:ok', 'S3:ok'] — 판정은 아래 내 SQL 행
G-P04  [printfilm] S1 계보 10행 (내 SQL · mes_qa2_db)  PASS  출하 LOT X261009-0003 — 행 10 · relation {'투입': 3, 'splice': 2, '슬리팅': 3, '출하': 2} · base {'투입': 3, '합병': 2, '분할': 3, '출하': 2} · 역방향 화살표 9 · 정방향(M①) 9 · 팩 종류 LOT 6 · 상태 {'출하': 2, '재고': 1, '소진': 3} (gates.yaml S1.expect: 10 · {'투입': 3, 'splice': 2, '슬리팅': 3, '출하': 2} · 9 · 9 · 6 · {'소진': 3, '출하': 2, '재고': 1})
# check_data — 행 3 · FAIL 0 · WARN 0 · 4s · DB mes_qa2_db
G-P01  [foodservice] write_scope 밖 쓰기 정적 스캔 (QA2)  PASS  파일 2 · write_scope {'hooks': ['mat_requirement', 'qua_issue', 'job_lot', 'lot']} · 밖 0 · lot_genealogy 직접 0 · 시드 스크립트 ['seed_pack.py'](시드는 write_scope 대상 밖으로 봄)
G-P04  [foodservice] 시나리오 테스트로 데이터 만들기 (mes_qa2_db)  PASS  gates.yaml scenarios ['S1:ok', 'S2:ok', 'S3:ok', 'S4:ok', 'S5:ok', 'S6:ok', 'S7:ok', 'S8:ok'] — 판정은 아래 내 SQL 행
G-P04  [foodservice] S1 소요량 144/120/24 (내 SQL · mes_qa2_db)  PASS  mat_requirement(source=hook) 첫 기간 2026-10-09 {'MAT-1001': (144.0, 120.0, 24.0), 'MAT-1002': (42.0, 80.0, 0.0)} · 내 산식 1200×12.000/100 · 1200×3.500/100 → {'MAT-1001': (144.0, 120.0, 24.0), 'MAT-1002': (42.0, 80.0, 0.0)} · 전 14행 중 부족 ≠ max(소요−가용,0) 0
G-P04  [foodservice] S1 배치 측정값 = eqp_collect 재집계 (내 SQL · mes_qa2_db)  PASS  collect 측정값 21행 재집계 불일치 0 · S1 실적① 값 {'RPM': 73.5, 'STIR_TIME': 30.0, 'TEMP': 161.25} (gates.yaml: RPM 73.5 · STIR_TIME 30 · TEMP 161.25)
G-P04  [foodservice] S1 계보 6행 · 역추적 원료 2 (내 SQL · mes_qa2_db)  PASS  출하 LOT X261009-0001 — 역방향 화살표 6 · 원료 LOT 2 · 배치 2
# check_data — 행 5 · FAIL 0 · WARN 0 · 9s · DB mes_qa2_db
G-P01  [kimchi] write_scope 밖 쓰기 정적 스캔 (QA2)  PASS  파일 10 · write_scope {'cond': [], 'wsh': [], 'tank': [], 'pkg': [], 'age': ['lot', 'lot_genealogy'], 'alm': [], 'hooks': ['lot', 'pop_measure', 'qua_issue']} · 밖 0 · lot_genealogy 직접 0 · 시드 스크립트 0(시드는 write_scope 대상 밖으로 봄)
G-P04  [kimchi] 시나리오 테스트로 데이터 만들기 (mes_qa2_db)  PASS  gates.yaml scenarios ['S1:ok', 'S2:ok', 'S3:ok', 'S4:ok'] — 판정은 아래 내 SQL 행
G-P04  [kimchi] S1 계보 · 역추적 (내 SQL · mes_qa2_db)  PASS  출하 LOT X261009-0001 — 역방향 화살표 10 {'투입': 6, '혼합': 3, '출하': 1} · 원재료 3 · 최대 깊이 5 · TANK 2 상태 ['소진'] · salinity_pct 측정값 2 (gates.yaml: backward_materials 3 · backward_depth 5 · tank_lots 2 · tank_state 소진 · salinity_measure_rows 2)
G-P04  [kimchi] S1 행 수 · P1 잔량 = gates.yaml (내 SQL · mes_qa2_db)  FAIL  시나리오 LOT 사이 lot_genealogy 10행(gates.yaml genealogy_rows 9) · 전처리 P1 잔량/상태 [(0.0, '소진')](gates.yaml p1_remain_qty 150 · 재고) — 팩 테스트는 10 · 0 으로 단언(합병 계열 API 가 별도 LOT · P1 850 전량 투입) — 기대값 출처(gates.yaml)와 재현이 다르다
G-P04  [kimchi] S3 알람 (내 SQL · mes_qa2_db)  PASS  x_kimchi_env_alarm 행 3 · 반복 이탈 합친 count [2, 1, 1] (gates.yaml: 행 3 · 첫 알람 count 2 — S3 1회분 기준)
# check_data — 행 5 · FAIL 1 · WARN 0 · 6s · DB mes_qa2_db
```
