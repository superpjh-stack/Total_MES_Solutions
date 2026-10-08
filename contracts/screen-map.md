# 화면 맵 — 코어 화면 51 + 공통 5 (아키텍트 · 2026-10-09 · 초안)

> 메뉴 · 경로의 원본은 `src/mescore/core.yaml` 이고 `app/nav.py` 가 읽는다. **§1 은 그 렌더본**이라 구현 뒤에는 손으로 고치지 않는다(`make contracts`).
> 이름은 코어 중립어다 — 팩이 `terms` · `menus.rename` 으로 바꾼다. 경로 · 화면 ID 는 팩이 바꾸지 못한다(`pack-contract.md` §4).
> 팩 화면은 `packs/<팩>/pack.yaml: screens` 에 `X-` 접두로 따로 선언되고 `make contracts` 가 §4 에 붙인다.

## 1. 코어 화면 51 → 경로 · 담당 · 채널 (렌더본)

<!-- BEGIN:generated screens -->
| # | 화면 ID | 모듈 | 메뉴 | 화면 | 경로 | 담당 | 채널 | 기능 |
|---|---|---|---|---|---|---|---|---|
| 1 | BAS-01 | bas | 기준정보 | 품목 | `/bas/items` | 개발1 | 관리자 Web | F-BAS-01 ~ 04 (4) |
| 2 | BAS-02 | bas | 기준정보 | BOM | `/bas/bom` | 개발1 | 관리자 Web | F-BAS-05 ~ 08 (4) |
| 3 | BAS-03 | bas | 기준정보 | 공정 | `/bas/processes` | 개발1 | 관리자 Web | F-BAS-09 ~ 12 (4) |
| 4 | BAS-04 | bas | 기준정보 | 공정 측정값 정의 | `/bas/process-params` | 개발1 | 관리자 Web | F-BAS-13 ~ 16 (4) |
| 5 | BAS-05 | bas | 기준정보 | 설비 | `/bas/equipment` | 개발1 | 관리자 Web | F-BAS-17 ~ 20 (4) |
| 6 | BAS-06 | bas | 기준정보 | 거래처 | `/bas/partners` | 개발1 | 관리자 Web | F-BAS-21 ~ 24 (4) |
| 7 | BAS-07 | bas | 기준정보 | 작업자 | `/bas/workers` | 개발1 | 관리자 Web | F-BAS-25 ~ 28 (4) |
| 8 | BAS-08 | bas | 기준정보 | 불량코드 | `/bas/defect-codes` | 개발1 | 관리자 Web | F-BAS-29 ~ 32 (4) |
| 9 | BAS-09 | bas | 기준정보 | 공통코드 | `/bas/codes` | 개발1 | 관리자 Web | F-BAS-33 ~ 36 (4) |
| 10 | ORD-01 | ord | 수주 · 계획 | 수주 | `/ord/orders` | 개발3 | 관리자 Web | F-ORD-01 ~ 04 (4) |
| 11 | ORD-02 | ord | 수주 · 계획 | 수주 이력 | `/ord/order-history` | 개발3 | 관리자 Web | F-ORD-05 (1) |
| 12 | ORD-03 | ord | 수주 · 계획 | 납기 달력 | `/ord/delivery-calendar` | 개발3 | 관리자 Web, 모바일 | F-ORD-06 (1) |
| 13 | ORD-04 | ord | 수주 · 계획 | 생산계획 | `/ord/plans` | 개발3 | 관리자 Web | F-ORD-07 ~ 10 (4) |
| 14 | JOB-01 | job | 작업지시 | 작업지시 | `/job/work-orders` | 개발1 | 관리자 Web | F-JOB-01 ~ 05 (5) |
| 15 | JOB-02 | job | 작업지시 | 지시 현황 | `/job/status` | 개발1 | 관리자 Web, 모바일 | F-JOB-06 (1) |
| 16 | JOB-03 | job | 작업지시 | 작업지시서 출력 | `/job/print` | 개발1 | 관리자 Web | F-JOB-07 (1) |
| 17 | MAT-01 | mat | 자재 | 입고 | `/mat/receipts` | 개발2 | 현장 POP, 관리자 Web | F-MAT-01 ~ 03 (3) |
| 18 | MAT-02 | mat | 자재 | 입고검사 | `/mat/inspections` | 개발2 | 현장 POP, 관리자 Web | F-MAT-04 ~ 05 (2) |
| 19 | MAT-03 | mat | 자재 | 원재료 LOT | `/mat/lots` | 개발2 | 관리자 Web, 현장 POP | F-MAT-06 ~ 07 (2) |
| 20 | MAT-04 | mat | 자재 | 재고 | `/mat/stock` | 개발2 | 관리자 Web, 모바일 | F-MAT-08 ~ 09 (2) |
| 21 | MAT-05 | mat | 자재 | 소요량 | `/mat/requirements` | 개발2 | 관리자 Web | F-MAT-10 ~ 11 (2) |
| 22 | POP-01 | pop | 생산실적 | 작업 목록 (스캔) | `/pop/work` | 개발2 | 현장 POP | F-POP-01 (1) |
| 23 | POP-02 | pop | 생산실적 | 작업 시작 · 종료 | `/pop/result` | 개발2 | 현장 POP | F-POP-02 ~ 05 (4) |
| 24 | POP-03 | pop | 생산실적 | 투입 스캔 | `/pop/inputs` | 개발2 | 현장 POP | F-POP-06 ~ 07 (2) |
| 25 | POP-04 | pop | 생산실적 | LOT 라벨 | `/pop/labels` | 개발2 | 현장 POP | F-POP-08 (1) |
| 26 | QUA-01 | qua | 품질 | 검사 계획 | `/qua/plans` | 개발2 | 관리자 Web | F-QUA-01 ~ 03 (3) |
| 27 | QUA-02 | qua | 품질 | 검사 결과 | `/qua/inspections` | 개발2 | 관리자 Web, 현장 POP | F-QUA-04 ~ 06 (3) |
| 28 | QUA-03 | qua | 품질 | 불량 집계 | `/qua/defect-stats` | 개발2 | 관리자 Web | F-QUA-07 (1) |
| 29 | QUA-04 | qua | 품질 | 이상 · 시정 | `/qua/issues` | 개발2 | 관리자 Web | F-QUA-08 ~ 11 (4) |
| 30 | EQP-01 | eqp | 설비 | 가동 현황 | `/eqp/status` | 개발2 | 현장 POP, 관리자 Web | F-EQP-01 ~ 02 (2) |
| 31 | EQP-02 | eqp | 설비 | 점검 | `/eqp/checks` | 개발2 | 현장 POP, 관리자 Web | F-EQP-03 ~ 04 (2) |
| 32 | EQP-03 | eqp | 설비 | 고장 | `/eqp/faults` | 개발2 | 현장 POP, 관리자 Web | F-EQP-05 ~ 07 (3) |
| 33 | EQP-04 | eqp | 설비 | 수집값 조회 | `/eqp/collect` | 개발2 | 관리자 Web | F-EQP-08 (1) |
| 34 | SHP-01 | shp | 출하 | 출하 등록 | `/shp/shipments` | 개발3 | 현장 POP, 관리자 Web | F-SHP-01 ~ 04 (4) |
| 35 | SHP-02 | shp | 출하 | LOT 스캔 · 승인 | `/shp/scan` | 개발3 | 현장 POP, 관리자 Web | F-SHP-05 ~ 07 (3) |
| 36 | SHP-03 | shp | 출하 | 출하 현황 | `/shp/status` | 개발3 | 관리자 Web, 모바일 | F-SHP-08 (1) |
| 37 | SHP-04 | shp | 출하 | 성적서 | `/shp/documents` | 개발3 | 관리자 Web | F-SHP-09 ~ 10 (2) |
| 38 | TRC-01 | trc | LOT 추적 | 정방향 추적 | `/trc/forward` | 개발3 | 관리자 Web, 모바일 | F-TRC-01 (1) |
| 39 | TRC-02 | trc | LOT 추적 | 역방향 추적 | `/trc/backward` | 개발3 | 관리자 Web, 모바일 | F-TRC-02 (1) |
| 40 | TRC-03 | trc | LOT 추적 | 번호 검색 | `/trc/search` | 개발3 | 관리자 Web, 모바일 | F-TRC-03 (1) |
| 41 | KPI-01 | kpi | 현황 · KPI | 현황판 | `/kpi/board` | 개발3 | 현황판 | F-KPI-01 (1) |
| 42 | KPI-02 | kpi | 현황 · KPI | 집계 (생산 · 품질 · 납기 · 설비) | `/kpi/summary` | 개발3 | 관리자 Web, 모바일 | F-KPI-02 ~ 05 (4) |
| 43 | KPI-03 | kpi | 현황 · KPI | 지표 정의 | `/kpi/indicators` | 개발3 | 관리자 Web | F-KPI-06 ~ 08 (3) |
| 44 | SYS-01 | sys | 시스템 | 사용자 | `/sys/users` | 개발1 | 관리자 Web | F-SYS-01 ~ 04 (4) |
| 45 | SYS-02 | sys | 시스템 | 역할 | `/sys/roles` | 개발1 | 관리자 Web | F-SYS-05 ~ 07 (3) |
| 46 | SYS-03 | sys | 시스템 | 권한 표 | `/sys/permissions` | 개발1 | 관리자 Web | F-SYS-08 ~ 09 (2) |
| 47 | SYS-04 | sys | 시스템 | 접근 로그 | `/sys/logs` | 개발1 | 관리자 Web | F-SYS-10 (1) |
| 48 | SYS-05 | sys | 시스템 | 채번 규칙 | `/sys/numbering` | 개발1 | 관리자 Web | F-SYS-11 ~ 12 (2) |
| 49 | SYS-06 | sys | 시스템 | 백업 · 이관 | `/sys/backup` | 개발1 | 관리자 Web | F-SYS-13 ~ 16 (4) |
| 50 | IFC-01 | ifc | 인터페이스 | 수집 수신 현황 | `/ifc/collect` | 개발3 | 관리자 Web | F-IFC-01 ~ 02 (2) |
| 51 | IFC-02 | ifc | 인터페이스 | ERP 연계 로그 | `/ifc/erp` | 개발3 | 관리자 Web | F-IFC-03 ~ 04 (2) |
<!-- END:generated screens -->

모듈별 화면 9 · 4 · 3 · 5 · 4 · 4 · 4 · 4 · 3 · 3 · 6 · 2 = **51**. 기능 36 · 10 · 7 · 11 · 8 · 11 · 8 · 10 · 3 · 8 · 16 · 4 = **132**.

## 2. 공통 화면 5

| 화면 ID | 화면 | 경로 | 담당 | 비고 |
|---|---|---|---|---|
| CMN-01 | 로그인 | `/login` | 아키텍트 → 개발1 | `device` 선택(web · pop · mobile · board). 실패 401 재렌더 |
| CMN-02 | 메인 (IA) | `/` | 개발1 | 모듈 카드를 **일하는 순서**로. 팩 `menus.order` 반영 |
| CMN-03 | 오류 | `/error` · `_error.html` | 아키텍트 | 상태코드별. 현황판 채널은 자동 새로고침 유지 |
| CMN-04 | 대시보드 | `/dashboard` | 개발3 | 로그인 직후 역할별 요약(지시 · 실적 · 검사 · 출하 건수). `kpi` 집계를 읽기만 |
| CMN-05 | 팝업 | `/popup/{kind}` | 아키텍트 | 품목 · 거래처 · 설비 · LOT 찾기 공용 팝업(`kind` = item · partner · equipment · lot · worker). JSON 도 준다 |

## 3. 파일 소유권 (한 파일은 한 사람만)

| 경로 | 소유자 |
|---|---|
| `src/mescore/core.yaml` · `app/{main,settings,packs,nav,contracts,rbac,auth,templating,audit}.py` · `app/util/` · `templates/{base,_error,home/*}.html` · `static/` · `db/{conn.py,schema.sql,views.sql,seed_core.py}` · `tools/` · `packs/_template/` | 아키텍트 |
| `app/numbering.py` · `app/routers/{home,bas,job,sys}.py` · `templates/{bas,job,sys,login}/` · `db/seed_dev1.py` · `packs/foodservice/` | 개발1 |
| `app/{lineage,printing,collect}.py` · `app/routers/{mat,pop,qua,eqp}.py` · `templates/{mat,pop,qua,eqp,print/label_*}.html` · `templates/home/_measure.html` · `db/seed_dev2.py` · `packs/printfilm/` | 개발2 |
| `app/{stats,erp}.py` · `app/routers/{ord,shp,trc,kpi,ifc,dashboard}.py` · `templates/{ord,shp,trc,kpi,ifc,dashboard,print/document_*}.html` · `migrate/` · `db/seed_dev3.py` · `packs/kimchi/` | 개발3 |
| `tests/test_arch_*.py` | 아키텍트 · `tests/test_<모듈>_*.py` 는 그 모듈 소유자 · `tools/check_{screens,data,schema,security}.py` 는 QA |

## 4. 팩 화면 (렌더본 — `make contracts` 가 `MES_PACK` 별로 붙인다)

<!-- BEGIN:generated pack screens -->
(아직 없음 — 웨이브 B 에서 채워진다. 형식은 §1 과 같고 화면 ID 는 `X-<모듈>-nn`, 담당은 그 팩 담당.)
<!-- END:generated pack screens -->
