# 기능 목록 — 코어 화면 기능 132 + 이관 배치 4 = 136줄 (아키텍트 · 2026-10-09 · 초안)

> **이 표가 기능의 원본이다.** `src/mescore/app/contracts.py` 가 §2 의 표를 그대로 파싱해 placeholder 화면, `rbac.require_fn`, `tools/check_trace.py`(G-C02) 에 준다. 표를 고치면 앱이 다음 기동부터 그 값을 쓴다 — 다른 곳에 같은 목록을 또 적지 않는다.
> **전개 전체가 `가설` 이다(D-11).** `spec.md` §6.1 은 화면 51 만 주었다. 화면 × 단위 기능(등록 · 수정 · 삭제/취소 · 조회 · 출력 · 승인 · 스캔)으로 전개했고, 근거 사업 셋 중 둘 이상에 있는 기능만 넣었다.
> 팩 기능은 `packs/<팩>/function-list.md` 에 `F-X-<MOD>-nn` 으로 따로 적는다(`pack-contract.md` §6).

## 1. 읽는 법

| 열 | 뜻 |
|---|---|
| ID | `F-<모듈>-nn`(화면 기능) · `B-MIG-nn`(이관 배치). 테스트에 `@pytest.mark.fn("F-BAS-01")` 을 붙여야 이어진 것으로 센다 |
| 화면 | `screen-map.md` 의 화면 ID |
| 유형 | `등록` `수정` `삭제` `취소` `판정` `승인` `스캔` `실행` = 쓰기 · `조회` `출력` = 읽기 · `배치` |
| 쓰는 테이블 | 그 기능이 **쓰는** 곳. 읽기 기능은 `-`. 모듈의 쓰기 경계(`db-schema.md` §2) 밖에는 쓰지 않는다(G-C05) |
| 채널 | 그 화면의 채널(`screen-map.md`). 팩이 `channels` 로 바꿀 수 있다 |
| 권한 | 쓰기 기능: 입력할 수 있는 역할(`goal.md` §6 기본 권한 표). 읽기 기능: `조회 이상` |
| 범위 | 쓰기 기능의 `scope`. `일반` · `입고검사` · `승인` · `지표` · `재전송`. 권한 칸의 `scopes` 에 있어야 쓸 수 있다 |
| API | 엔드포인트 하나. 경로 앞부분은 `nav.path_of(...)`. `cli <명령>` = `uv run python -m mescore.migrate <명령> --dir <폴더>` |
| 훅 | 그 기능이 부르는 팩 훅(`interfaces.md` §9). `-` 는 `validate_<table>` 만 |
| 담당 | 개발1(기준 · 지시 · 시스템) · 개발2(현장 실행) · 개발3(수주 · 출하 · 조회 · 연계) |
| 계약 | 지켜야 할 문장. 오류 코드는 `api-contract.md`. 문구는 중립어 — 화면은 `t()` 로 바꾼다 |

공통 규칙 — 쓰기는 `rbac.require_fn("<ID>")`, 쓰기 뒤에는 `audit.log_change(...)`(G-C18), 번호는 `numbering.next(...)` 한 곳, 계보는 `lineage` 한 곳, 측정값 폼은 `ui.measure_fields`, 팩 속성 폼은 `ui.attrs_fields`. 조회 화면은 0건일 때 `미수집`(G-C11). 모든 등록 · 수정은 저장 직전 `packs.hook("validate_<table>")`.

## 2. 기능 136줄

| ID | 모듈 | 화면 | 기능명 | 유형 | 쓰는 테이블 | 채널 | 권한 | 범위 | API | 훅 | 담당 | 계약 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-BAS-01 | bas | BAS-01 | 품목 등록 | 등록 | bas_item | 관리자 Web | 관리자 | 일반 | `POST /bas/items` | - | 개발1 | 품목 코드 · 품목명 · 구분(제품/반제품/원재료/부자재) · 규격 · 단위 → 한 행. 코드 중복 · 필수 누락 422. `attrs` 는 팩 선언대로 |
| F-BAS-02 | bas | BAS-01 | 품목 수정 | 수정 | bas_item | 관리자 Web | 관리자 | 일반 | `POST /bas/items/{id}` | - | 개발1 | 코드는 못 바꾼다. 사용 여부 변경 포함. 없는 ID 404 |
| F-BAS-03 | bas | BAS-01 | 품목 삭제 | 삭제 | bas_item | 관리자 Web | 관리자 | 일반 | `POST /bas/items/{id}/delete` | - | 개발1 | 참조(LOT · BOM · 수주 · 지시)가 있으면 삭제 대신 `use_yn=N` 안내 422 |
| F-BAS-04 | bas | BAS-01 | 품목 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/items` | - | 개발1 | 코드 · 이름 · 구분 검색. 0건 `미수집` |
| F-BAS-05 | bas | BAS-02 | BOM 등록 | 등록 | bas_bom, bas_bom_dtl | 관리자 Web | 관리자 | 일반 | `POST /bas/bom` | - | 개발1 | 상위 품목 + 버전 + 구성품(품목 · 소요량 · 단위 · 손실률) N줄 → `tx` 하나. 자기 자신 구성품 422 |
| F-BAS-06 | bas | BAS-02 | BOM 수정 | 수정 | bas_bom, bas_bom_dtl | 관리자 Web | 관리자 | 일반 | `POST /bas/bom/{id}` | - | 개발1 | 구성품 줄 추가 · 삭제 · 수량 변경. 지시가 참조하는 버전은 새 버전으로만 |
| F-BAS-07 | bas | BAS-02 | BOM 삭제 | 삭제 | bas_bom, bas_bom_dtl | 관리자 Web | 관리자 | 일반 | `POST /bas/bom/{id}/delete` | - | 개발1 | 지시가 참조하면 422 |
| F-BAS-08 | bas | BAS-02 | BOM 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/bom` | - | 개발1 | 상위 품목별 버전 · 구성품 트리 |
| F-BAS-09 | bas | BAS-03 | 공정 등록 | 등록 | bas_process | 관리자 Web | 관리자 | 일반 | `POST /bas/processes` | - | 개발1 | 공정 코드 · 이름 · 순서. 코드 중복 422 |
| F-BAS-10 | bas | BAS-03 | 공정 수정 | 수정 | bas_process | 관리자 Web | 관리자 | 일반 | `POST /bas/processes/{id}` | - | 개발1 | 순서 · 이름 · 사용 여부 |
| F-BAS-11 | bas | BAS-03 | 공정 삭제 | 삭제 | bas_process | 관리자 Web | 관리자 | 일반 | `POST /bas/processes/{id}/delete` | - | 개발1 | 측정값 정의 · 설비 · 실적이 참조하면 422 |
| F-BAS-12 | bas | BAS-03 | 공정 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/processes` | - | 개발1 | 순서대로. 공정별 측정값 수 · 설비 수 표시 |
| F-BAS-13 | bas | BAS-04 | 공정 측정값 등록 | 등록 | bas_process_param | 관리자 Web | 관리자 | 일반 | `POST /bas/process-params` | - | 개발1 | 공정 · 키 · 라벨 · 단위 · 형식 · 하한 · 상한 · 필수 · 수집원(manual/collect) · 대표값(agg). `(공정, 키)` 중복 422. **이 행이 POP 종료 폼을 만든다(G-C24)** |
| F-BAS-14 | bas | BAS-04 | 공정 측정값 수정 | 수정 | bas_process_param | 관리자 Web | 관리자 | 일반 | `POST /bas/process-params/{id}` | - | 개발1 | 키는 못 바꾼다(기록이 키로 이어진다). 범위 · 필수 · 수집원 변경 |
| F-BAS-15 | bas | BAS-04 | 공정 측정값 삭제 | 삭제 | bas_process_param | 관리자 Web | 관리자 | 일반 | `POST /bas/process-params/{id}/delete` | - | 개발1 | 기록(`pop_measure`)이 있으면 `use_yn=N` 안내 422 |
| F-BAS-16 | bas | BAS-04 | 공정 측정값 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/process-params` | - | 개발1 | 공정별 그룹. 수집원 collect 는 태그 이름 표시 |
| F-BAS-17 | bas | BAS-05 | 설비 등록 | 등록 | bas_equipment | 관리자 Web | 관리자 | 일반 | `POST /bas/equipment` | - | 개발1 | 설비 코드 · 이름 · 공정 · 수집 여부. 코드 중복 422. **수집 코드는 `collect` 의 `equip_code` 와 1:1** |
| F-BAS-18 | bas | BAS-05 | 설비 수정 | 수정 | bas_equipment | 관리자 Web | 관리자 | 일반 | `POST /bas/equipment/{id}` | - | 개발1 | 코드는 못 바꾼다 |
| F-BAS-19 | bas | BAS-05 | 설비 삭제 | 삭제 | bas_equipment | 관리자 Web | 관리자 | 일반 | `POST /bas/equipment/{id}/delete` | - | 개발1 | 실적 · 수집값이 참조하면 422 |
| F-BAS-20 | bas | BAS-05 | 설비 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/equipment` | - | 개발1 | 공정별. 수집 설비는 마지막 수신 시각 |
| F-BAS-21 | bas | BAS-06 | 거래처 등록 | 등록 | bas_partner | 관리자 Web | 관리자 | 일반 | `POST /bas/partners` | - | 개발1 | 코드 · 이름 · 구분(고객/공급/외주) · 연락처 |
| F-BAS-22 | bas | BAS-06 | 거래처 수정 | 수정 | bas_partner | 관리자 Web | 관리자 | 일반 | `POST /bas/partners/{id}` | - | 개발1 | 코드는 못 바꾼다 |
| F-BAS-23 | bas | BAS-06 | 거래처 삭제 | 삭제 | bas_partner | 관리자 Web | 관리자 | 일반 | `POST /bas/partners/{id}/delete` | - | 개발1 | 수주 · 입고 · 출하가 참조하면 422 |
| F-BAS-24 | bas | BAS-06 | 거래처 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/partners` | - | 개발1 | 구분 · 이름 검색 |
| F-BAS-25 | bas | BAS-07 | 작업자 등록 | 등록 | bas_worker | 관리자 Web | 관리자 | 일반 | `POST /bas/workers` | - | 개발1 | 코드 · 이름 · 담당 공정. 사용자 계정(`sys_user`)과는 별개 — 연결은 선택 |
| F-BAS-26 | bas | BAS-07 | 작업자 수정 | 수정 | bas_worker | 관리자 Web | 관리자 | 일반 | `POST /bas/workers/{id}` | - | 개발1 | |
| F-BAS-27 | bas | BAS-07 | 작업자 삭제 | 삭제 | bas_worker | 관리자 Web | 관리자 | 일반 | `POST /bas/workers/{id}/delete` | - | 개발1 | 실적이 참조하면 422 |
| F-BAS-28 | bas | BAS-07 | 작업자 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/workers` | - | 개발1 | 공정별 |
| F-BAS-29 | bas | BAS-08 | 불량코드 등록 | 등록 | bas_defect_code | 관리자 Web | 관리자 | 일반 | `POST /bas/defect-codes` | - | 개발1 | 코드 · 이름 · 공정(선택). 중복 422 |
| F-BAS-30 | bas | BAS-08 | 불량코드 수정 | 수정 | bas_defect_code | 관리자 Web | 관리자 | 일반 | `POST /bas/defect-codes/{id}` | - | 개발1 | |
| F-BAS-31 | bas | BAS-08 | 불량코드 삭제 | 삭제 | bas_defect_code | 관리자 Web | 관리자 | 일반 | `POST /bas/defect-codes/{id}/delete` | - | 개발1 | 불량 기록이 참조하면 422 |
| F-BAS-32 | bas | BAS-08 | 불량코드 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/defect-codes` | - | 개발1 | |
| F-BAS-33 | bas | BAS-09 | 공통코드 등록 | 등록 | bas_code | 관리자 Web | 관리자 | 일반 | `POST /bas/codes` | - | 개발1 | 그룹 · 코드 · 이름 · 순서. `(그룹, 코드)` 중복 422. 코어 예약 그룹(`ITEM_TYPE` 등)은 코드 추가만 |
| F-BAS-34 | bas | BAS-09 | 공통코드 수정 | 수정 | bas_code | 관리자 Web | 관리자 | 일반 | `POST /bas/codes/{id}` | - | 개발1 | |
| F-BAS-35 | bas | BAS-09 | 공통코드 삭제 | 삭제 | bas_code | 관리자 Web | 관리자 | 일반 | `POST /bas/codes/{id}/delete` | - | 개발1 | 코어 예약 그룹의 코어 코드는 422 |
| F-BAS-36 | bas | BAS-09 | 공통코드 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /bas/codes` | - | 개발1 | 그룹별 |
| F-ORD-01 | ord | ORD-01 | 수주 등록 | 등록 | ord_order, ord_order_dtl, ord_order_hist | 관리자 Web | 관리자 · 생산 | 일반 | `POST /ord/orders` | on_order_created | 개발3 | 거래처 · 수주일 · 납기 + 상세(품목 · 수량 · 단위) N줄 → `tx`. 번호 `numbering.next("ORDER")`. 이력 1행 |
| F-ORD-02 | ord | ORD-01 | 수주 수정 | 수정 | ord_order, ord_order_dtl, ord_order_hist | 관리자 Web | 관리자 · 생산 | 일반 | `POST /ord/orders/{id}` | - | 개발3 | 납기 · 수량 변경은 이력에 전후값. 지시가 붙은 상세의 품목은 못 바꾼다 |
| F-ORD-03 | ord | ORD-01 | 수주 취소 | 취소 | ord_order, ord_order_hist | 관리자 Web | 관리자 · 생산 | 일반 | `POST /ord/orders/{id}/cancel` | - | 개발3 | 진행 중 지시가 있으면 422. `status=취소` |
| F-ORD-04 | ord | ORD-01 | 수주 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /ord/orders` | - | 개발3 | 기간 · 거래처 · 상태. 상세별 지시 · 출하 수량 |
| F-ORD-05 | ord | ORD-02 | 수주 이력 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /ord/order-history` | - | 개발3 | `ord_order_hist` 전후값 · 누가 · 언제 |
| F-ORD-06 | ord | ORD-03 | 납기 달력 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /ord/delivery-calendar` | - | 개발3 | 월 단위. 날짜별 납기 건수 · 출하 완료 표시. 390px 에서 주 단위로 접힘 |
| F-ORD-07 | ord | ORD-04 | 생산계획 등록 | 등록 | ord_plan | 관리자 Web | 관리자 · 생산 | 일반 | `POST /ord/plans` | - | 개발3 | 수주 상세(선택) · 품목 · 계획일 · 계획 수량. 번호 `PLAN` |
| F-ORD-08 | ord | ORD-04 | 생산계획 수정 | 수정 | ord_plan | 관리자 Web | 관리자 · 생산 | 일반 | `POST /ord/plans/{id}` | - | 개발3 | 확정 후에는 수량만 |
| F-ORD-09 | ord | ORD-04 | 생산계획 확정 | 승인 | ord_plan | 관리자 Web | 관리자 · 생산 | 일반 | `POST /ord/plans/{id}/confirm` | - | 개발3 | `status=확정`. 확정된 계획만 지시로 이어진다 |
| F-ORD-10 | ord | ORD-04 | 생산계획 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /ord/plans` | - | 개발3 | 기간 · 품목 · 상태. 계획 대비 지시 · 실적 수량 |
| F-JOB-01 | job | JOB-01 | 작업지시 등록 | 등록 | job_work_order, job_lot | 관리자 Web | 관리자 · 생산 | 일반 | `POST /job/work-orders` | on_work_order_created | 개발1 | 품목 · 공정 · 설비(선택) · 계획 수량 · 계획일 · 생산계획/수주 상세(선택). 번호 `WORK_ORDER`. `status=대기`. BOM 이 있으면 `job_lot` 에 소요 원재료 품목 줄(LOT 은 비움) |
| F-JOB-02 | job | JOB-01 | 작업지시 수정 | 수정 | job_work_order | 관리자 Web | 관리자 · 생산 | 일반 | `POST /job/work-orders/{id}` | - | 개발1 | `for update` 잠금. 진행 중이면 수량 · 설비만. 마감 · 취소는 422 |
| F-JOB-03 | job | JOB-01 | 작업지시 마감 | 승인 | job_work_order | 관리자 Web | 관리자 · 생산 | 일반 | `POST /job/work-orders/{id}/close` | on_work_order_closed | 개발1 | 진행 중 실적(종료 안 된)이 있으면 422. `status=마감` |
| F-JOB-04 | job | JOB-01 | 작업지시 취소 | 취소 | job_work_order | 관리자 Web | 관리자 · 생산 | 일반 | `POST /job/work-orders/{id}/cancel` | - | 개발1 | 실적이 하나라도 있으면 422 |
| F-JOB-05 | job | JOB-01 | 작업지시 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /job/work-orders` | - | 개발1 | 기간 · 품목 · 공정 · 상태. 진행 여부는 실적 유무로 계산(저장 안 함) |
| F-JOB-06 | job | JOB-02 | 지시 현황 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /job/status` | - | 개발1 | 오늘 · 이번 주 지시별 계획 대비 실적 · 상태. 390px |
| F-JOB-07 | job | JOB-03 | 작업지시서 출력 | 출력 | - | 관리자 Web | 조회 이상 | - | `GET /job/print?id=` | - | 개발1 | `printing.render_print("work_order")`. 지시 번호 바코드. 없는 ID 404 |
| F-MAT-01 | mat | MAT-01 | 입고 등록 | 등록 | mat_receipt, lot, mat_stock_trx | 현장 POP, 관리자 Web | 생산 · 현장 | 일반 | `POST /mat/receipts` | on_lot_created | 개발2 | 품목 · 공급처 · 수량 · 단위 · 입고일 → `mat_receipt` + 원재료 LOT(`kind=MATERIAL`, 번호 `LOT_MATERIAL`, `insp_status=미검사`) + 재고 거래 1행. `tx` 하나 |
| F-MAT-02 | mat | MAT-01 | 입고 수정 | 수정 | mat_receipt, lot, mat_stock_trx | 현장 POP, 관리자 Web | 생산 · 현장 | 일반 | `POST /mat/receipts/{id}` | - | 개발2 | 수량 변경은 거래 보정 1행. 투입된 LOT 은 422 |
| F-MAT-03 | mat | MAT-01 | 입고 조회 | 조회 | - | 현장 POP, 관리자 Web | 조회 이상 | - | `GET /mat/receipts` | - | 개발2 | 기간 · 품목 · 공급처. LOT 번호 · 검사 상태 |
| F-MAT-04 | mat | MAT-02 | 입고검사 판정 | 판정 | lot, qua_inspection, qua_insp_item | 현장 POP, 관리자 Web | 품질 | 입고검사 | `POST /mat/inspections` | on_inspection_judged | 개발2 | LOT 스캔 → 검사 항목(`qua_insp_plan` 입고 유형) 값 입력 → 합격/불합격/조건부 → `lot.insp_status`. 이미 투입된 LOT 은 422. 검사 기록은 `qua_inspection(insp_type=입고)` |
| F-MAT-05 | mat | MAT-02 | 입고검사 조회 | 조회 | - | 현장 POP, 관리자 Web | 조회 이상 | - | `GET /mat/inspections` | - | 개발2 | 미검사 LOT 우선. 스캔 진입 `?no=` 없는 번호 422 재렌더 |
| F-MAT-06 | mat | MAT-03 | 원재료 LOT 조회 | 조회 | - | 관리자 Web, 현장 POP | 조회 이상 | - | `GET /mat/lots` | - | 개발2 | `kind=MATERIAL`. 잔량은 `v_lot_stock`. 상태 · 검사 · 투입처 |
| F-MAT-07 | mat | MAT-03 | 원재료 LOT 라벨 출력 | 출력 | - | 관리자 Web, 현장 POP | 조회 이상 | - | `GET /mat/lots/{id}/label` | - | 개발2 | `print/label_lot`. 바코드 = `lot_no`. 스캔칸에 넣으면 그 LOT 이 열린다(G-C14) |
| F-MAT-08 | mat | MAT-04 | 재고 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /mat/stock` | - | 개발2 | 품목별 현재고(`mat_stock`) + LOT 별 잔량. 390px |
| F-MAT-09 | mat | MAT-04 | 재고 조정 | 수정 | mat_stock, mat_stock_trx | 관리자 Web | 생산 | 일반 | `POST /mat/stock/adjust` | - | 개발2 | 품목 · 조정 수량 · 사유 → 거래 1행 + 현재고 갱신. 사유 필수 |
| F-MAT-10 | mat | MAT-05 | 소요량 계산 | 실행 | mat_requirement | 관리자 Web | 생산 | 일반 | `POST /mat/requirements/calc` | - | 개발2 | 기간의 확정 계획 · 대기 지시 × BOM → 품목별 소요 · 현재고 · 부족. 재실행 멱등(기간 키로 갱신). 팩 훅이 만든 행(`source=hook`)은 덮지 않는다 |
| F-MAT-11 | mat | MAT-05 | 소요량 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /mat/requirements` | - | 개발2 | 기간별. 부족 품목 강조 |
| F-POP-01 | pop | POP-01 | 작업 목록 조회 (스캔) | 조회 | - | 현장 POP | 조회 이상 | - | `GET /pop/work` | - | 개발2 | 오늘 지시(대기 · 진행). 지시 번호 스캔 `?no=` → POP-02 로. 없는 번호 422 재렌더. 터치 확대 |
| F-POP-02 | pop | POP-02 | 작업 시작 | 등록 | pop_work_result | 현장 POP | 생산 · 현장 | 일반 | `POST /pop/result/start` | on_result_started | 개발2 | 지시 · 설비 · 작업자 → 실적 행(`started_at`). 지시 `for share` · 대기/진행만 · 같은 지시의 미종료 실적이 있으면 422 |
| F-POP-03 | pop | POP-02 | 작업 종료 | 등록 | pop_work_result, pop_measure, lot, lot_genealogy | 현장 POP | 생산 · 현장 | 일반 | `POST /pop/result/{id}/end` | on_result_closed | 개발2 | 양품 · 불량 수량 + **측정값(`ui.measure_fields` 가 만든 칸)** → `pop_measure` N행(필수 누락 422 · 범위 이탈 저장 + `deviated`) → `lineage.make_product_lot`(번호 `LOT_PRODUCT`, `pop_input` → `투입` 계보) → collect 소스 측정값 채움 → 훅. `tx` 하나. 라벨 출력 안내 |
| F-POP-04 | pop | POP-02 | 정지 기록 | 등록 | pop_stop | 현장 POP | 생산 · 현장 | 일반 | `POST /pop/result/{id}/stop` | - | 개발2 | 사유(공통코드 `STOP_REASON`) · 시작 · 종료. 종료 안 된 정지가 있으면 그것을 닫는다 |
| F-POP-05 | pop | POP-02 | 폐기 기록 | 등록 | pop_scrap | 현장 POP | 생산 · 현장 | 일반 | `POST /pop/result/{id}/scrap` | - | 개발2 | 수량 · 불량코드. 종료 후에도 가능(불량 수량과 별개) |
| F-POP-06 | pop | POP-03 | 투입 스캔 | 스캔 | pop_input | 현장 POP | 생산 · 현장 | 일반 | `POST /pop/inputs` | - | 개발2 | 실적 + 원재료 LOT 바코드 + 투입량 → `lineage.consume_material`. 불합격 · 미검사 · 소진 LOT 422(스캔칸 유지). 한 번 스캔 = 한 건 |
| F-POP-07 | pop | POP-03 | 투입 취소 | 취소 | pop_input | 현장 POP | 생산 · 현장 | 일반 | `POST /pop/inputs/{id}/cancel` | - | 개발2 | 실적 종료 전만. 종료 후 422 |
| F-POP-08 | pop | POP-04 | 생산 LOT 라벨 출력 | 출력 | - | 현장 POP | 조회 이상 | - | `GET /pop/labels?lot=` | - | 개발2 | `print/label_lot`. 분할 · 합병 LOT 도 같은 양식. 바코드 스캔 왕복(G-C14) |
| F-QUA-01 | qua | QUA-01 | 검사 계획 등록 | 등록 | qua_insp_plan | 관리자 Web | 품질 | 일반 | `POST /qua/plans` | - | 개발2 | 검사 유형(입고/공정/최종) · 품목 또는 공정 · 항목(키 · 라벨 · 기준 · 하한 · 상한 · 형식) N줄. 팩 시드 `inspection_items` 와 같은 모양 |
| F-QUA-02 | qua | QUA-01 | 검사 계획 수정 | 수정 | qua_insp_plan | 관리자 Web | 품질 | 일반 | `POST /qua/plans/{id}` | - | 개발2 | 항목 추가 · 기준 변경. 기록된 항목 키는 못 지운다 |
| F-QUA-03 | qua | QUA-01 | 검사 계획 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /qua/plans` | - | 개발2 | 유형 · 품목 · 공정별 |
| F-QUA-04 | qua | QUA-02 | 검사 결과 등록 | 등록 | qua_inspection, qua_insp_item | 관리자 Web, 현장 POP | 품질 | 일반 | `POST /qua/inspections` | - | 개발2 | LOT 스캔 → 해당 계획의 항목 값 입력 → 저장(판정 전 `judgement=NULL`). 출하된 LOT 422 |
| F-QUA-05 | qua | QUA-02 | 검사 판정 | 판정 | qua_inspection, lot, qua_defect | 관리자 Web, 현장 POP | 품질 | 일반 | `POST /qua/inspections/{id}/judge` | on_inspection_judged | 개발2 | 합격/불합격/조건부 → `lot.insp_status`(최신 검사 기준). 불합격이면 불량코드 · 수량 N줄(`qua_defect`). 판정 뒤 수정은 새 검사로 |
| F-QUA-06 | qua | QUA-02 | 검사 결과 조회 | 조회 | - | 관리자 Web, 현장 POP | 조회 이상 | - | `GET /qua/inspections` | - | 개발2 | 기간 · 유형 · 판정 · LOT. 항목별 값 · 기준 이탈 표시 |
| F-QUA-07 | qua | QUA-03 | 불량 집계 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /qua/defect-stats` | - | 개발2 | `stats.quality(by=defect)`. 기간 · 품목 · 공정 · 불량코드별 건수 · 수량. QA2 재계산 대상 |
| F-QUA-08 | qua | QUA-04 | 이상 등록 | 등록 | qua_issue | 관리자 Web | 품질 | 일반 | `POST /qua/issues` | - | 개발2 | 발생일 · 공정 · LOT(선택) · 내용 · 원인. `status=발생`. 팩 훅이 자동 생성한 행은 `source=hook` |
| F-QUA-09 | qua | QUA-04 | 시정 조치 등록 | 수정 | qua_issue | 관리자 Web | 품질 | 일반 | `POST /qua/issues/{id}/action` | - | 개발2 | 조치 내용 · 담당 · 일자 → `status=조치` |
| F-QUA-10 | qua | QUA-04 | 이상 종결 | 승인 | qua_issue | 관리자 Web | 품질 | 일반 | `POST /qua/issues/{id}/close` | - | 개발2 | 조치가 없으면 422. `status=종결` |
| F-QUA-11 | qua | QUA-04 | 이상 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /qua/issues` | - | 개발2 | 상태 · 기간 · 공정 |
| F-EQP-01 | eqp | EQP-01 | 가동 현황 조회 | 조회 | - | 현장 POP, 관리자 Web | 조회 이상 | - | `GET /eqp/status` | - | 개발2 | 설비별 현재 상태(가동/정지/점검/고장) · 수집 설비는 `collect.latest` · 마지막 수신. 수집 없으면 `미수집` |
| F-EQP-02 | eqp | EQP-01 | 가동 상태 기록 | 등록 | eqp_run_log | 현장 POP, 관리자 Web | 생산 · 현장 | 일반 | `POST /eqp/status` | - | 개발2 | 설비 · 상태 · 시각 → 로그 1행(이전 구간 닫기). **상태 기록이지 제어가 아니다** |
| F-EQP-03 | eqp | EQP-02 | 점검 등록 | 등록 | eqp_check | 현장 POP, 관리자 Web | 생산 · 현장 | 일반 | `POST /eqp/checks` | - | 개발2 | 설비 · 점검일 · 항목 · 결과 · 점검자 |
| F-EQP-04 | eqp | EQP-02 | 점검 조회 | 조회 | - | 현장 POP, 관리자 Web | 조회 이상 | - | `GET /eqp/checks` | - | 개발2 | 설비 · 기간 |
| F-EQP-05 | eqp | EQP-03 | 고장 등록 | 등록 | eqp_fault, eqp_run_log | 현장 POP, 관리자 Web | 생산 · 현장 | 일반 | `POST /eqp/faults` | - | 개발2 | 설비 · 발생 시각 · 증상 → 고장 행 + 가동 로그 `고장` 구간 시작 |
| F-EQP-06 | eqp | EQP-03 | 고장 조치 | 수정 | eqp_fault, eqp_run_log | 현장 POP, 관리자 Web | 생산 · 현장 | 일반 | `POST /eqp/faults/{id}/fix` | - | 개발2 | 조치 내용 · 복구 시각 → 고장 구간 닫기 |
| F-EQP-07 | eqp | EQP-03 | 고장 조회 | 조회 | - | 현장 POP, 관리자 Web | 조회 이상 | - | `GET /eqp/faults` | - | 개발2 | 설비 · 기간 · 복구 여부. MTTR 은 `stats.equipment` |
| F-EQP-08 | eqp | EQP-04 | 수집값 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /eqp/collect` | - | 개발2 | 설비 · 태그 · 기간 → `collect.series`. 표 + 간단 추이. 0건 `미수집` |
| F-SHP-01 | shp | SHP-01 | 출하 등록 | 등록 | shp_shipment | 현장 POP, 관리자 Web | 관리자 · 생산 · 현장 | 일반 | `POST /shp/shipments` | - | 개발3 | 거래처 · 출하일 · 수주(선택) → 번호 `SHIPMENT` · `status=등록`. LOT 은 아직 없다 |
| F-SHP-02 | shp | SHP-01 | 출하 수정 | 수정 | shp_shipment | 현장 POP, 관리자 Web | 관리자 · 생산 · 현장 | 일반 | `POST /shp/shipments/{id}` | - | 개발3 | 승인 전만. 승인 후 422 |
| F-SHP-03 | shp | SHP-01 | 출하 취소 | 취소 | shp_shipment, lot, lot_genealogy | 현장 POP, 관리자 Web | 관리자 · 생산 · 현장 | 일반 | `POST /shp/shipments/{id}/cancel` | - | 개발3 | 승인 전만. 스캔된 LOT 은 전부 `lineage.unship` 으로 되돌린다 |
| F-SHP-04 | shp | SHP-01 | 출하 조회 | 조회 | - | 현장 POP, 관리자 Web | 조회 이상 | - | `GET /shp/shipments` | - | 개발3 | 기간 · 거래처 · 상태. LOT 수 · 수량 |
| F-SHP-05 | shp | SHP-02 | 출하 LOT 스캔 | 스캔 | lot, lot_genealogy | 현장 POP, 관리자 Web | 관리자 · 생산 · 현장 | 일반 | `POST /shp/scan` | - | 개발3 | 출하 + 생산 LOT 바코드 → `lineage.ship`(출하 LOT 이 없으면 `kind=SHIPMENT` 생성, `출하` 계보 1줄). 재고 아님 · 불합격 · 미검사 · 이미 출하 422(스캔칸 유지) |
| F-SHP-06 | shp | SHP-02 | 출하 LOT 스캔 취소 | 취소 | lot, lot_genealogy | 현장 POP, 관리자 Web | 관리자 · 생산 · 현장 | 일반 | `POST /shp/scan/cancel` | - | 개발3 | 승인 전만. `lineage.unship` |
| F-SHP-07 | shp | SHP-02 | 출하 승인 | 승인 | shp_shipment | 현장 POP, 관리자 Web | 관리자 | 승인 | `POST /shp/shipments/{id}/approve` | validate_shipment, after_commit_shipment_approved | 개발3 | LOT 0건 422 → 훅(`HookError` 422) → `status=승인` · `approved_at/by`. 승인 후 스캔 · 취소 불가. `after_commit` 으로 ERP 큐 |
| F-SHP-08 | shp | SHP-03 | 출하 현황 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /shp/status` | - | 개발3 | 오늘 · 이번 주 출하 · 납기 대비. 390px |
| F-SHP-09 | shp | SHP-04 | 성적서 발행 | 등록 | shp_document | 관리자 Web | 관리자 · 생산 | 일반 | `POST /shp/documents` | - | 개발3 | 승인된 출하 → 그 LOT 들의 **최신 검사 항목 값**으로 성적서 행(번호 `DOCUMENT`, 내용 스냅샷 JSON). 미승인 422. 같은 출하에 재발행은 새 번호 |
| F-SHP-10 | shp | SHP-04 | 성적서 출력 | 출력 | - | 관리자 Web | 조회 이상 | - | `GET /shp/documents/{id}/print` | - | 개발3 | `print/document`. 스냅샷을 그린다(검사가 나중에 바뀌어도 발행본 불변). 팩이 양식 덮어쓰기(COA 등) |
| F-TRC-01 | trc | TRC-01 | 정방향 추적 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /trc/forward?no=` | - | 개발3 | `lineage.trace_forward`. 원재료 LOT → … → 출하 LOT. 재고 LOT 은 `재고` 표시. 없는 번호 422 재렌더. **쓰기 0** |
| F-TRC-02 | trc | TRC-02 | 역방향 추적 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /trc/backward?no=` | - | 개발3 | `lineage.trace_backward`. 출하 LOT → 원재료 LOT 전부. 각 노드에서 지시 · 실적 · 측정값 · 검사로 링크(G-C08) |
| F-TRC-03 | trc | TRC-03 | 번호 검색 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /trc/search?q=` | - | 개발3 | `lineage.search`. 번호 일부 · 품목으로. 결과에서 정/역방향으로 |
| F-KPI-01 | kpi | KPI-01 | 현황판 조회 | 조회 | - | 현황판 | 조회 이상 | - | `GET /kpi/board` | - | 개발3 | `stats.board`. `?device=board` 자동 새로고침(5초 폴링 JSON) + 마지막 갱신 시각. 오류 중에도 새로고침 유지 |
| F-KPI-02 | kpi | KPI-02 | 생산 집계 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /kpi/summary?kind=production` | - | 개발3 | `stats.production`. 기간 · 품목/공정/설비별 계획 대비 실적 · 양품률. QA2 재계산 |
| F-KPI-03 | kpi | KPI-02 | 품질 집계 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /kpi/summary?kind=quality` | - | 개발3 | `stats.quality`. 검사 합격률 · 불량률 + `measure_series` 선택 키 |
| F-KPI-04 | kpi | KPI-02 | 납기 집계 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /kpi/summary?kind=delivery` | - | 개발3 | `stats.delivery`. 납기 준수율 · 지연 건 |
| F-KPI-05 | kpi | KPI-02 | 설비 집계 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /kpi/summary?kind=equipment` | - | 개발3 | `stats.equipment`. 가동률 · 정지 · 고장 · MTTR |
| F-KPI-06 | kpi | KPI-03 | 지표 등록 | 등록 | kpi_indicator | 관리자 Web | 관리자 | 지표 | `POST /kpi/indicators` | - | 개발3 | 키 · 이름 · 단위 · 목표값 · 산식 종류(코어 집계 키 또는 팩 `kpi_extra` 키) |
| F-KPI-07 | kpi | KPI-03 | 지표 수정 | 수정 | kpi_indicator | 관리자 Web | 관리자 | 지표 | `POST /kpi/indicators/{id}` | - | 개발3 | 목표값 · 표시 여부 |
| F-KPI-08 | kpi | KPI-03 | 지표 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /kpi/indicators` | kpi_extra | 개발3 | `stats.indicators` — 정의 + 현재값 + 목표 대비 |
| F-SYS-01 | sys | SYS-01 | 사용자 등록 | 등록 | sys_user | 관리자 Web | 관리자 | 일반 | `POST /sys/users` | - | 개발1 | 로그인 ID · 이름 · 역할 · 초기 비밀번호(해시) · 작업자 연결(선택). ID 중복 422 |
| F-SYS-02 | sys | SYS-01 | 사용자 수정 | 수정 | sys_user | 관리자 Web | 관리자 | 일반 | `POST /sys/users/{id}` | - | 개발1 | 역할 변경은 **다음 요청부터** 반영(요청마다 DB). 비밀번호 재설정 포함 |
| F-SYS-03 | sys | SYS-01 | 사용자 중지 · 해제 | 수정 | sys_user, sys_session | 관리자 Web | 관리자 | 일반 | `POST /sys/users/{id}/toggle` | - | 개발1 | 중지하면 그 사용자의 세션 전부 무효 → 다음 요청 401. 자기 자신 중지 422 |
| F-SYS-04 | sys | SYS-01 | 사용자 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /sys/users` | - | 개발1 | 역할 · 상태 · 마지막 로그인 |
| F-SYS-05 | sys | SYS-02 | 역할 등록 | 등록 | sys_role, sys_permission | 관리자 Web | 관리자 | 일반 | `POST /sys/roles` | - | 개발1 | 코드 · 이름. 모든 메뉴 칸을 `없음` 으로 만든다(칸 수 = 메뉴 수). `rbac.invalidate()` |
| F-SYS-06 | sys | SYS-02 | 역할 수정 | 수정 | sys_role | 관리자 Web | 관리자 | 일반 | `POST /sys/roles/{id}` | - | 개발1 | 이름 · 사용 여부. `ADMIN` 은 중지 불가. `rbac.invalidate()` |
| F-SYS-07 | sys | SYS-02 | 역할 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /sys/roles` | - | 개발1 | 역할별 사용자 수 |
| F-SYS-08 | sys | SYS-03 | 권한 표 수정 | 수정 | sys_permission | 관리자 Web | 관리자 | 일반 | `POST /sys/permissions` | - | 개발1 | 메뉴 × 역할 칸 `없음 · 조회 · 입력` + `scopes`. `ADMIN` 의 `sys` 칸은 `입력` 고정(잠그지 못한다). 저장 즉시 `rbac.invalidate()` → 다음 요청부터 반영(G-C17) |
| F-SYS-09 | sys | SYS-03 | 권한 표 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /sys/permissions` | - | 개발1 | 코어 + 팩 메뉴 × 역할 전 칸. 빈 칸(시드 누락)은 `미확정` 로 표시하고 `check_security` 가 FAIL |
| F-SYS-10 | sys | SYS-04 | 접근 로그 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /sys/logs` | - | 개발1 | 기간 · 사용자 · 종류(로그인/조회/변경) · 화면 · 기능 · 대상. 비밀번호 · 세션 ID 는 없다 |
| F-SYS-11 | sys | SYS-05 | 채번 규칙 수정 | 수정 | sys_number_rule | 관리자 Web | 관리자 | 일반 | `POST /sys/numbering` | - | 개발1 | 종류별 접두어 · 날짜 형식 · 자릿수. 바꾼 뒤 `numbering.peek` 미리보기. 이미 발번된 번호는 바뀌지 않는다 |
| F-SYS-12 | sys | SYS-05 | 채번 규칙 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /sys/numbering` | - | 개발1 | 종류별 규칙 · 오늘 카운터 · 다음 번호(`peek`). 규칙 없는 종류는 `미확정 (D-10)` |
| F-SYS-13 | sys | SYS-06 | 백업 실행 | 실행 | sys_backup_hist | 관리자 Web | 관리자 | 일반 | `POST /sys/backup` | - | 개발1 | `pg_dump` → `backups/` + 테이블별 행 수 JSON + 이력 1행. 실패는 이력에 남고 500 아님(422 사유) |
| F-SYS-14 | sys | SYS-06 | 복구 확인 | 실행 | sys_backup_hist | 관리자 Web | 관리자 | 일반 | `POST /sys/backup/{id}/verify` | - | 개발1 | 임시 DB 에 복구해 행 수 대조 → 결과를 이력에. 운영 DB 는 건드리지 않는다(G-C20) |
| F-SYS-15 | sys | SYS-06 | 이관 실행 | 실행 | sys_migration_log | 관리자 Web | 관리자 | 일반 | `POST /sys/migrate` | - | 개발1 | 서버의 지정 폴더(`MES_MIGRATE_DIR`) 에 대해 `migrate.run(command, dry_run)` 호출 → 리포트. 파일 업로드는 없다(폴더 경로만). 개발3 의 `migrate` 를 부른다 |
| F-SYS-16 | sys | SYS-06 | 백업 · 이관 이력 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /sys/backup` | - | 개발1 | 백업 이력 · 이관 로그 |
| F-IFC-01 | ifc | IFC-01 | 수집 메시지 수신 | 등록 | ifc_collect_raw, eqp_collect | - (API) | 토큰 | - | `POST /ifc/collect` | on_collect | 개발3 | `api-contract.md` §4. `collect.receive`. 인증은 `X-Collect-Token`. 멱등 · 모르는 설비 422 + 거부 기록 |
| F-IFC-02 | ifc | IFC-01 | 수집 수신 현황 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /ifc/collect` | - | 개발3 | 설비별 마지막 수신 · 건수 · 거부 · 모르는 태그. 수신 없으면 `미수집` |
| F-IFC-03 | ifc | IFC-02 | ERP 연계 로그 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /ifc/erp` | - | 개발3 | `ifc_outbox` · `ifc_erp_link`. 어댑터가 없으면 전부 `대기 — 미확정 (D-02)` |
| F-IFC-04 | ifc | IFC-02 | ERP 재전송 | 실행 | ifc_outbox, ifc_erp_link | 관리자 Web | 관리자 | 재전송 | `POST /ifc/erp/{id}/retry` | - | 개발3 | `erp.flush` 한 건. 어댑터 501 이면 501 그대로(조용한 폴백 0, G-C16) |
| B-MIG-01 | migrate | - | 기준정보 이관 | 배치 | bas_item, bas_partner, bas_process, bas_process_param, bas_equipment, bas_bom, bas_bom_dtl, bas_worker, bas_defect_code, bas_code, sys_migration_log | - | - | - | `cli basics` | - | 개발3 | `migration-files.md` §2. 멱등 · 건수 · 오류 리포트 · 종료 코드 |
| B-MIG-02 | migrate | - | 수주 · 작업지시 이관 | 배치 | ord_order, ord_order_dtl, job_work_order, sys_migration_log | - | - | - | `cli orders` | - | 개발3 | §3. 번호는 파일 값 그대로(채번 안 함) |
| B-MIG-03 | migrate | - | LOT · 계보 이관 | 배치 | lot, lot_genealogy, sys_migration_log | - | - | - | `cli lots` | - | 개발3 | §4. 계보는 `lineage.link` 로만. 순환 · 모르는 관계는 그 줄 오류 |
| B-MIG-04 | migrate | - | 실적 · 검사 이력 이관 | 배치 | pop_work_result, pop_measure, qua_inspection, qua_insp_item, lot, shp_shipment, sys_migration_log | - | - | - | `cli history` | - | 개발3 | §5. 검사 판정이 `lot.insp_status` 갱신(최신 기준) |

## 3. 모듈별 수 (G-C02 기대값)

| 모듈 | bas | ord | job | mat | pop | qua | eqp | shp | trc | kpi | sys | ifc | 합 | 배치 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 기능 | 36 | 10 | 7 | 11 | 8 | 11 | 8 | 10 | 3 | 8 | 16 | 4 | **132** | **4** |
| 담당 | 개발1 | 개발3 | 개발1 | 개발2 | 개발2 | 개발2 | 개발2 | 개발3 | 개발3 | 개발3 | 개발1 | 개발3 | 59 / 38 / 35 | 개발3 |

쓰기 기능 중 **계보에 닿는 것은 F-POP-03 · F-SHP-03 · F-SHP-05 · F-SHP-06 · B-MIG-03 뿐**이고 전부 `lineage` 를 거친다. 분할 · 합병은 코어 화면이 없다 — `lineage.split/merge` 는 API 로만 있고(`POST /pop/result/{id}/split` · `/merge` 는 **F-POP-03 의 계약 안**에서 LOT 생성 옵션으로 제공, G-C06 테스트가 부른다) 화면은 팩이 만든다(`printfilm` 의 후가공 · 슬리팅). 코어 단독 E2E(G-C22)는 그 API 를 POP-02 의 "분할/합병" 버튼(`ui.write_button`)으로 연다 — 이 버튼은 코어 화면 기능에 세지 않는다(D-12).
