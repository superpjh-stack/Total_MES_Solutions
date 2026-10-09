# printfilm 팩 — 인쇄필름 MES (기획자2 · 2026-10-09 · 기획 산출물)

> **한 줄**: 엘컴화인 인쇄필름 MES(대메뉴 12 · 중메뉴 32 · 기능 94 + 이관 6 · 테이블 30 + EXT 1)를 표준 코어 위에 **코어 수정 0** 으로 올리는 참조 팩. 핵심 시나리오는 엘컴화인 설계도 §3 의 Job-Lot-Roll 계보 = `lot_genealogy` **10행**(G-P04).
> **근거**: `../lcomFine MES/` — `goal.md`(§2.2 G-06 · §6 권한 표) · `contracts/`(7종) · `decisions.md` · `src/lcomfine/app/nav.py` · `db/schema.sql` · `db/seed*.py` · 설계도 `엘컴화인_MES_설계도 복사본.html`. 전부 **읽기만** 했다.
> **정본**: 표준 쪽은 `spec.md`(§2.4 · §3 · §4 · §8.3 · §12) · `contracts/pack-contract.md`. 둘이 어긋나면 `spec.md` 가 맞고 이 문서 끝 §6 "결정 후보" 에 적었다.
> **코드는 없다.** 이 폴더의 파일은 개발2 가 웨이브 B 에서 그대로 구현하는 기획 산출물이다 — `pack.yaml` · `seed/*.csv` · `gates.yaml` · `migrate.yaml` 은 그대로 쓰고, `function-list.md` · `hooks.md` · `schema_ext.md` · `scenarios.md` 는 `routers/` · `hooks.py` · `schema_ext.sql` · `tests/` 의 설계서다.

## 0. 이 폴더

| 파일 | 뜻 | 개발2 가 만드는 것 |
|---|---|---|
| `pack.yaml` | `pack-contract.md` §2 의 키 전부. 용어 · 메뉴 · 화면 7 · 역할 4 · 채번 · 채널 · 속성 · 측정값 · 계보 · 쓰기 범위 · 훅 · 어댑터 · 시드 · 게이트 | 그대로 |
| `seed/permissions.csv` | 메뉴 15(코어 12 + 팩 3) × 역할 4 = **60칸** (엘컴화인 48칸 + 팩 메뉴 · 코어 전용 메뉴 12칸) | 그대로 |
| `seed/process_params.csv` · `inspection_items.csv` · `codes.csv` · `*_example.csv` | E3 측정값 · 검사 항목 · 공통코드 · `(예시)` 기준정보 | 그대로 |
| `function-list.md` | 팩 기능 **24줄**(`F-X-PRT-01~12` · `F-X-CLR-01~05` · `F-X-RLL-01~07`) | `routers/{prt,clr,rll}.py` · `templates/{prt,clr,rll}/` |
| `hooks.md` | 훅 6 사양 | `hooks.py` |
| `schema_ext.md` | 팩 테이블 **8** 컬럼 설계 | `schema_ext.sql` |
| `gates.yaml` | 화면 7 · 테이블 8 · 기능 24 · 시나리오 S1~S3 | `tests/test_scenario_*.py` |
| `scenarios.md` | QA 화면 조작 한 바퀴(엘컴화인 G-22) · 역할별 권한 케이스 | — (QA3 · QA1 이 쓴다) |
| `migrate.yaml` | 엘컴화인 테이블 30(+1) → 표준 Import 4종 매핑 | `migrate_export.py`(이관 단계) |
| 템플릿 덮어쓰기(R10) | `templates/print/label_lot.html`(롤 라벨 — kind 로 원재료 LOT · 인쇄 롤 · 후가공/슬리팅 롤 3종 분기) · `templates/print/document.html`(COA) · `templates/print/work_order.html`(작업지시서에 판사양 · 아니록스 · 잉크조성) — `check_pack` WARN 목록과 이 줄이 같아야 한다 | `templates/print/*.html` |

규모(`gates.yaml` 과 같다): 팩 화면 **7** · 팩 테이블 **8** · 팩 기능 **24** · 추가 메뉴 3(`prt` `clr` `rll`) · 숨긴 메뉴 1(`eqp`) · 계보 kind 1(`ROLL`) · 관계 3(`splice` · `슬리팅` · `후가공`) · 훅 6 · 어댑터 1(`printing`).

---

## 1. 코어 매핑표 — 엘컴화인 중메뉴 32 · 기능 100(+ 확장 6) 은 어디로 가는가

판정 기호: **1:1** = 코어 기능이 그대로 한다 · **용어** = 코어 기능 + `terms`/`rename`/양식 덮어쓰기만 · **팩** = 팩 화면 `X-` · **밖** = 코어 변경 요청 후보(§3) 또는 1차 범위 밖(이관 단계).

### 1.1 중메뉴 32 → 코어/팩 화면

| # | 엘컴화인 화면 | 대메뉴 | 코어/팩 화면 | 판정 | 비고 |
|---|---|---|---|---|---|
| 1 | BAS-01 품목 관리 | 기준정보 관리 | BAS-01 품목 | 1:1 | `item_type` 제품/원재료 ⊂ 코어 4종 |
| 2 | BAS-02 고객 관리 | 〃 | BAS-06 거래처 | 용어 | `terms: 거래처 → 고객` · `partner_type=고객`. 공급처(입고)도 같은 화면 — 엘컴화인은 공급처 마스터가 없었다(글자) |
| 3 | BAS-03 공정 관리 | 〃 | BAS-03 공정 | 1:1 | 공정 구분(인쇄/후가공/슬리팅/기타)은 `bas_process.attrs.process_type`(E2 표시용) |
| 4 | BAS-04 설비 관리 | 〃 | BAS-05 설비 | 1:1 | `collect_yn=N` 고정(엘컴화인 G-12 — 수집 없음) |
| 5 | BAS-05 불량코드 관리 | 〃 | BAS-08 불량코드 | 1:1 | 분류(`defect_group`)는 `attrs.defect_group` |
| 6 | PRT-01 판사양 관리 | 인쇄 기준 관리 | **X-PRT-01** | 팩 | `/prt/plates` · 관리자 Web · 기능 4 |
| 7 | PRT-02 아니록스 관리 | 〃 | **X-PRT-02** | 팩 | `/prt/anilox` · 관리자 Web · 기능 4 |
| 8 | PRT-03 잉크조성 관리 | 〃 | **X-PRT-03** | 팩 | `/prt/inks` · 관리자 Web · 기능 4 |
| 9 | JOB-01 작업지시 | 작업지시 관리 | JOB-01 작업지시 | 용어 | `terms: 작업지시 → Job`. 판사양 · 아니록스 · 잉크조성은 `attrs`(E2) + 훅이 `x_printfilm_job_work_order_ext` 에 FK 로 옮긴다(`hooks.md` §2) |
| 10 | JOB-02 Job-Lot-Roll 매핑 | 〃 | — | **밖** | 코어 `job_lot` 은 "지시 ↔ 소요 품목/LOT"(BOM 소요 줄)이지 엘컴화인의 **생산 LOT(`L…` 채번 · 계획 롤 수 · 계획 길이)** 이 아니다 → §3 CR-1. 조회 쪽은 X-RLL-03 롤 이력 + TRC-01/02 가 Job → Roll → 출하 LOT 을 보여 준다 |
| 11 | POP-01 작업 실적 | 생산 실적 (POP) | POP-01 작업 목록 · POP-02 작업 시작 · 종료 | 용어 | 종료 시 훅 `on_result_closed` 가 생산 LOT 을 `ROLL` kind 로 바꾼다 |
| 12 | POP-02 정지 · 폐기 | 〃 | POP-02 (정지 · 폐기 블록) | 1:1 | 코어는 별도 화면이 없고 POP-02 안에 정지 · 폐기 · 목록이 있다 |
| 13 | POP-03 롤 라벨 | 〃 | POP-04 LOT 라벨 | 용어 | 양식 `print/label_lot.html` 덮어쓰기(인쇄 롤 라벨) |
| 14 | MAT-01 입고 | 자재 · 입고 | MAT-01 입고 | 1:1 | 공급처 = `bas_partner(partner_type=공급)` — 엘컴화인 `supplier_name` 글자 → 마스터 필요(§6 D-507) |
| 15 | MAT-02 입고검사 | 〃 | MAT-02 입고검사 | 1:1 | 범위 `입고검사` 는 품질만(엘컴화인 D-14 그대로 `permissions.csv`) |
| 16 | MAT-03 원재료 LOT | 〃 | MAT-03 원재료 LOT | 1:1 | 잔량 `v_lot_stock` = 엘컴화인 `v_material_lot_stock` |
| 17 | MAT-04 자재 투입 | 〃 | POP-03 투입 스캔 | 용어 | 엘컴화인도 P5 였다(D-13). 메뉴 위치만 자재 → 생산실적으로 옮겨진다 |
| 18 | CLR-01 조색 기록 | 조색 기록 | **X-CLR-01** | 팩 | `/clr/records` · 현장 POP · 기능 5 |
| 19 | RLL-01 후가공 | 후가공 · 슬리팅 롤 이력 | **X-RLL-01** | 팩 | `/rll/finishing` · 현장 POP · 기능 3 · `lineage.merge(relation=splice|후가공)` |
| 20 | RLL-02 슬리팅 | 〃 | **X-RLL-02** | 팩 | `/rll/slitting` · 현장 POP · 기능 2 · `lineage.split(relation=슬리팅)` |
| 21 | RLL-03 롤 이력 | 〃 | **X-RLL-03** | 팩 | `/rll/history` · 현장 POP · 기능 2 |
| 22 | QUA-01 검사 결과 | 품질 검사 기록 | QUA-02 검사 결과 | 용어 | 코어는 등록(F-QUA-04) → 판정(F-QUA-05) 2단계. ΔE · 불량 위치는 `inspection_items.csv`, 불량 유형은 `qua_defect` |
| 23 | QUA-02 불량 집계 | 〃 | QUA-03 불량 집계 | 1:1 | `stats.quality(by=defect)` |
| 24 | SHP-01 출하 | 출하 | SHP-01 출하 등록 + SHP-02 LOT 스캔 | 용어 | 엘컴화인은 한 화면, 코어는 둘. 흐름은 같다 |
| 25 | SHP-02 출하 승인 | 〃 | SHP-02 LOT 스캔 · 승인 | 1:1 | 범위 `승인` 은 관리자만. 훅 `validate_shipment` |
| 26 | SHP-03 COA | 〃 | SHP-04 성적서 | 용어 | `terms: 성적서 → COA` · 양식 `print/document.html` 덮어쓰기. 엘컴화인은 "승인 = COA 발행", 코어는 승인 뒤 발행(F-SHP-09) 2단계(§6 D-505) |
| 27 | TRC-01 추적 | LOT 추적 | TRC-01 · TRC-02 · TRC-03 | 1:1 | 엘컴화인 한 화면 → 코어 셋. 모바일 |
| 28 | STA-01 집계 | 실적 현황 | KPI-02 집계 | 용어 | `rename: kpi → 실적 현황`. 평균 ΔE 는 `measure_series`/`kpi_extra` |
| 29 | STA-02 현황판 | 〃 | KPI-01 현황판 | 1:1 | |
| 30 | SYS-01 사용자 | 시스템 관리 | SYS-01 사용자 | 1:1 | 삭제 = 중지(F-SYS-03 toggle) |
| 31 | SYS-02 권한 | 〃 | SYS-03 권한 표 | 1:1 | |
| 32 | SYS-03 로그 | 〃 | SYS-04 접근 로그 | 1:1 | |
| 확장 | SAL-01 수주 관리 | 영업관리(D-418) | ORD-01 수주 | 용어 | `rename: ord → 영업관리`. `ord` 를 숨기지 않는다 |
| 확장 | SAL-02 수주 현황 | 〃 | ORD-01 (상세별 지시 · 출하 수량) | 용어 | 진행 단계(미지시 → … → 출하 완료) 표시는 코어 F-ORD-04 계약 범위 안에서 — 부족하면 §6 D-509 |
| 확장 | SAL-03 거래처 이력 | 〃 | — | 밖 | 코어에 거래처별 수주 · 출하 집계 화면이 없다. 이관 단계에 `kpi_extra` 또는 팩 화면으로 |

중메뉴 32 판정: 1:1 **15** · 용어 **9** · 팩 **7** · 밖 **1**(JOB-02 매핑). 확장 3: 용어 2 · 밖 1.

코어에는 있고 엘컴화인에는 없는 화면(메뉴 단위로만 숨길 수 있어 그대로 보인다): BAS-02 BOM · BAS-04 공정 측정값 · BAS-07 작업자 · BAS-09 공통코드 · ORD-02~04 · JOB-02 지시 현황 · JOB-03 작업지시서 출력(엘컴화인 F-JOB-05 가 여기로) · MAT-04 재고 · MAT-05 소요량 · QUA-01 검사 계획 · QUA-04 이상 · KPI-03 지표 정의 · SYS-02 역할 · SYS-05 채번 규칙 · SYS-06 백업 · 이관 · IFC-01~02. `eqp` 메뉴만 숨긴다(엘컴화인 G-12: 설비는 기준정보까지).

### 1.2 기능 100 + 확장 6 → 코어/팩 기능

| 엘컴화인 | 기능명 | 코어/팩 | 판정 | 비고 |
|---|---|---|---|---|
| F-BAS-01~04 | 품목 등록 · 수정 · 삭제 · 조회 | F-BAS-01~04 | 1:1 | 삭제 참조 422 는 코어 계약과 같다 |
| F-BAS-05~08 | 고객 등록 · 수정 · 삭제 · 조회 | F-BAS-21~24 | 용어 | 거래처 → 고객 |
| F-BAS-09~12 | 공정 등록 · 수정 · 삭제 · 조회 | F-BAS-09~12 | 1:1 | 공정 구분은 attrs |
| F-BAS-13~16 | 설비 등록 · 수정 · 삭제 · 조회 | F-BAS-17~20 | 1:1 | |
| F-BAS-17~20 | 불량코드 등록 · 수정 · 삭제 · 조회 | F-BAS-29~32 | 1:1 | |
| F-PRT-01~04 | 판사양 등록 · 수정 · 삭제 · 조회 | **F-X-PRT-01~04** | 팩 | |
| F-PRT-05~08 | 아니록스 등록 · 수정 · 삭제 · 조회 | **F-X-PRT-05~08** | 팩 | |
| F-PRT-09~12 | 잉크조성 등록 · 수정 · 삭제 · 조회 | **F-X-PRT-09~12** | 팩 | 조성 행 `x_printfilm_ink_formula_component` |
| F-JOB-01 | 작업지시 등록 | F-JOB-01 | 용어 | + `attrs`(판사양 · 아니록스 · 잉크조성 코드) + 훅 `validate_job_work_order`/`on_work_order_created` → ext. 고객 · 납기는 수주 상세(`order_dtl_id`)에서 — 수주 없는 Job 은 §6 D-506 |
| F-JOB-02 | 작업지시 수정(마감 포함) | F-JOB-02 + F-JOB-03 마감 | 용어 | 엘컴화인 `완료` = 코어 `마감`. 되돌리기(완료 → 등록)는 코어에 없다(§6 D-508) |
| F-JOB-03 | 작업지시 취소 | F-JOB-04 | 1:1 | 실적 있으면 422 같다 |
| F-JOB-04 | 작업지시 조회 | F-JOB-05 | 1:1 | `?no=` 스캔 진입 |
| F-JOB-05 | 작업지시서 출력 | F-JOB-07 | 용어 | 양식 `print/work_order.html` 덮어쓰기(판사양 · 아니록스 · 잉크조성 표시) |
| F-JOB-06 | Job-Lot-Roll 매핑 등록 | — | **밖** | §3 CR-1 (코어 `job_lot` 에 생산 LOT 번호 · 계획값이 없다). 채번 `JOB_LOT`(`L`) 은 `pack.yaml` 에 선언만 |
| F-JOB-07 | Job-Lot-Roll 매핑 조회 | X-RLL-03 + TRC-01 | 밖(부분) | Job → Roll → 출하는 보인다. 생산 LOT 단은 CR-1 뒤 |
| F-POP-01 | 작업 시작 | F-POP-02 | 1:1 | Job 행 `for share` 잠금은 코어에 내장(엘컴화인 D-211 계열) |
| F-POP-02 | 작업 종료(인쇄 롤 생성) | F-POP-03 | 용어 | `lineage.make_product_lot` + 훅 `on_result_closed` 가 `ROLL` 로 retag · `x_printfilm_lot_ext(process_type=인쇄)`. 길이 · 폭은 `attrs`(E2) |
| F-POP-03 | 작업 실적 조회 | F-POP-01 | 1:1 | |
| F-POP-04 | 정지 등록 | F-POP-04 | 1:1 | 사유는 공통코드 `STOP_REASON`(엘컴화인은 글자 — `codes.csv` 에 `(예시)` 1건) |
| F-POP-05 | 재개 등록 | F-POP-04 | 용어 | 코어는 같은 엔드포인트가 열린 정지를 닫는다 |
| F-POP-06 | 폐기 등록 | F-POP-05 | 1:1 | |
| F-POP-07 | 정지 · 폐기 조회 | F-POP-01 / POP-02 표시 | 1:1 | 별도 기능 없음 — 화면 안 목록 |
| F-POP-08 | 인쇄 롤 라벨 출력 | F-POP-08 | 용어 | 양식 덮어쓰기 |
| F-MAT-01 | 입고 등록 | F-MAT-01 | 1:1 | `kind=MATERIAL` · 번호 `LOT_MATERIAL`(`M`) |
| F-MAT-02 | 입고 조회 | F-MAT-03 | 1:1 | |
| F-MAT-03 | 입고검사 결과 등록 | F-MAT-04 | 1:1 | 범위 `입고검사` · 검사 항목은 `inspection_items.csv` 입고 유형(비고 1건) |
| F-MAT-04 | 입고검사 조회 | F-MAT-05 | 1:1 | |
| F-MAT-05 | 원재료 LOT 조회 | F-MAT-06 | 1:1 | |
| F-MAT-06 | 원재료 LOT 라벨 출력 | F-MAT-07 | 용어 | 양식 덮어쓰기(같은 `label_lot.html` 의 MATERIAL 분기) |
| F-MAT-07 | 자재 투입 스캔 | F-POP-06 | 1:1 | 합격 LOT 만 — 코어 계약과 같다 |
| F-MAT-08 | 자재 투입 조회 | F-POP-06 / POP-03 표시 | 1:1 | |
| F-CLR-01~05 | 조색 기록 등록 · 배합비 · 수정 · 삭제 · 조회 | **F-X-CLR-01~05** | 팩 | |
| F-RLL-01~07 | 후가공 · splice · 후가공 조회 · 슬리팅 · 슬리팅 조회 · 롤 이력 · 롤 라벨 | **F-X-RLL-01~07** | 팩 | |
| F-QUA-01 | 검사 결과 등록(ΔE · 판정 · 불량) | F-QUA-04 + F-QUA-05 | 용어 | 코어는 등록 → 판정. 출하 승인된 롤 422 는 코어 "출하된 LOT 422" 가 한다 |
| F-QUA-02 | 검사 결과 수정 | F-QUA-04 (새 검사) | 용어 | 코어: 판정 뒤 수정은 새 검사로 — 롤의 판정은 최신 검사(둘 다 같다) |
| F-QUA-03 | 검사 결과 삭제 | — | 밖 | 코어에 검사 삭제가 없다(새 검사로 덮는다). 이관 단계에 필요하면 D-번호 |
| F-QUA-04 | 검사 결과 조회 | F-QUA-06 | 1:1 | |
| F-QUA-05 | 불량 유형별 집계 | F-QUA-07 | 1:1 | |
| F-QUA-06 | 불량 롤 조회(집계 내역) | F-QUA-07 | 용어(부분) | 코어 F-QUA-07 계약에 내역 드릴다운이 명시되지 않았다 — 개발3 확인, 없으면 §6 D-509 |
| F-SHP-01 | 출하 등록 | F-SHP-01 | 1:1 | 번호 `SHIPMENT`(`S`) |
| F-SHP-02 | 출하 롤 스캔 | F-SHP-05 | 1:1 | `lineage.ship`. 다른 Job 의 롤 422(D-16)는 코어 스캔에 없다 → `validate_shipment` 가 승인 때 막는다 + §3 CR-3 |
| F-SHP-03 | 출하 취소 | F-SHP-03 | 1:1 | |
| F-SHP-04 | 출하 조회 | F-SHP-04 | 1:1 | |
| F-SHP-05 | 출하 승인(= COA 번호) | F-SHP-07 (+ F-SHP-09) | 용어 | 범위 `승인` 관리자만. COA 발행은 F-SHP-09(`DOCUMENT` = `C`) — §6 D-505 |
| F-SHP-06 | COA 조회 | F-SHP-09/10 화면 SHP-04 | 용어 | |
| F-SHP-07 | COA 출력 | F-SHP-10 | 용어 | 양식 덮어쓰기. 바코드 = 출하 LOT 번호(엘컴화인 D-305) |
| F-TRC-01~03 | 정방향 · 역방향 · LOT 검색 | F-TRC-01~03 | 1:1 | |
| F-STA-01 | 생산 집계 | F-KPI-02 | 1:1 | |
| F-STA-02 | 품질 집계(평균 ΔE) | F-KPI-03 | 용어 | `measure_series("delta_e")` 는 `pop_measure` 만 본다 — 검사 ΔE(`qua_insp_item`) 평균은 `kpi_extra`(`hooks.md` §6) |
| F-STA-03 | 납기 집계 | F-KPI-04 | 1:1 | 산식은 코어 `stats.delivery`(엘컴화인 D-25 와 대조는 QA2) |
| F-STA-04 | 현황판 | F-KPI-01 | 1:1 | |
| F-SYS-01~04 | 사용자 등록 · 수정 · 삭제 · 조회 | F-SYS-01~04 | 1:1 | 삭제 = 중지(toggle) |
| F-SYS-05 | 권한 조회 | F-SYS-09 | 1:1 | |
| F-SYS-06 | 권한 수정 | F-SYS-08 | 1:1 | |
| F-SYS-07 | 로그 조회 | F-SYS-10 | 1:1 | |
| B-MIG-01 | Import 파일 검증 | B-MIG-01~04 `--dry-run` | 1:1 | |
| B-MIG-02 | 기준정보 적재 | B-MIG-01 `basics` | 1:1 | `migrate.yaml: rename` |
| B-MIG-03 | 인쇄 기준 적재(판사양 · 아니록스 · 잉크조성) | — | **밖** | 표준 Import 4종에 팩 테이블 파일이 없다 → 팩 `migrate_export.py`/적재 스크립트(이관 단계 · `migrate.yaml: pack_files`) · §3 CR-6 |
| B-MIG-04 | 작업지시 적재 | B-MIG-02 `orders` | 1:1 | 판사양 등은 `ext` 매핑 |
| B-MIG-05 | 과거 이력 적재 | B-MIG-03 `lots` + B-MIG-04 `history` | 1:1 | 엘컴화인도 적재 보류(D-01) |
| B-MIG-06 | 이관 결과 리포트 | F-SYS-16 | 1:1 | `sys_migration_log` |
| X-SAL-01~04 | 수주 등록 · 수정 · 취소 · 조회 | F-ORD-01~04 | 용어 | |
| X-SAL-05 | 수주 현황 | F-ORD-04 | 용어(부분) | |
| X-SAL-06 | 거래처 이력 | — | 밖 | |

기능 100 판정: 1:1 **54** · 용어 **18** · 팩 **24**(= 팩 `function-list.md` 24줄) · 밖 **4**(F-JOB-06 · F-JOB-07 · F-QUA-03 · B-MIG-03). 확장 6: 용어 5 · 밖 1. (F-JOB-07 · F-QUA-06 · X-SAL-05 처럼 "부분" 은 주 판정에 셌다.)

---

## 2. 확장 지점 분류표 — 엘컴화인 고유 기능 전부 (`spec.md` §3.8 의 기대값)

| 고유 기능 | 확장 지점 | 어디에 | 비고 |
|---|---|---|---|
| Job-Lot-Roll 계보 (`ROLL` · 재귀 추적) | **E6** | `pack.yaml: lineage.lot_kinds[ROLL base PRODUCT]` | 추적 · 상태는 코어 `relation_base` 로 — 같은 쿼리 |
| 용어 Job · Roll · COA · 슬리팅 · splice · 고객 | **E1** | `pack.yaml: terms` | 키는 `spec.md` §12 중립어 26 안에서만 |
| 메뉴 인쇄 기준 · 조색 기록 · 후가공 · 슬리팅 롤 이력 · 영업관리(rename) · 일하는 순서(D-417) · `eqp` 숨김 | **E1** | `pack.yaml: menus` | |
| 권한 48칸(괄호 조건 2: 입고검사 · 승인) | **E1** | `seed/permissions.csv` (`scopes`) | |
| 채번 J · L · M · R · S · C · SO (D-101) | **E1** | `pack.yaml: numbering` | `ROLL` 은 `LOT_PRODUCT` 형식(`R` 4자리) |
| 채널(POP 14 · 모바일 4 · 현황판 1) | **E1** | `pack.yaml: channels` | |
| 판사양 · 아니록스 · 잉크조성(+조성 행) | **E4** | `x_printfilm_plate` `x_printfilm_anilox` `x_printfilm_ink_formula` `x_printfilm_ink_formula_component` · X-PRT-01~03 | |
| Job 의 판사양 · 아니록스 · 잉크조성 FK | **E2** + **E5** | `job_work_order.attrs`(입력칸) → `validate_job_work_order` 가 코드 검증 → `x_printfilm_job_work_order_ext`(FK · 삭제 422 판정용) | attrs 를 WHERE 에 쓰지 않는다(D-05) |
| 조색 기록 · 배합비 | **E4** | `x_printfilm_color_record` `x_printfilm_color_record_mix` · X-CLR-01 | Job 참조 필수 — 팩 라우터가 검사 |
| ΔE (검사) · 불량 위치 | **E3** | `seed/inspection_items.csv` → `qua_insp_plan` → `qua_insp_item` | COA · 품질 집계의 원천 |
| ΔE (인쇄 중) · 인쇄 속도 | **E3** | `seed/process_params.csv` → `bas_process_param` → `pop_measure` | 인쇄 속도는 설계도에 없다(`spec.md` §8.3 에서) — 단위 `(미확정)` |
| 롤 길이 · 폭 · 슬리팅 분할 폭 | **E2** | `lot.attrs.length_m` · `width_mm`(표시용 — 라벨 · COA · 조회) | 집계에 쓰지 않는다. 쓰게 되면 E3 로(§6 D-502) |
| 롤 공정 구분(인쇄/후가공/슬리팅) · 분할 순번 · 가공 설비 | **E2** | `x_printfilm_lot_ext(process_type, slit_seq, equipment_id)` | 후가공 · 슬리팅 조회의 WHERE 에 쓴다 → ext |
| 후가공(1:1) · splice(N:1) · 슬리팅(1:N) | **E6** + **E4** | `relations: 후가공(base 합병) · splice(base 합병) · 슬리팅(base 분할)` · X-RLL-01/02 → `lineage.merge/split(relation=…)` | `lot_genealogy` 직접 SQL 0 |
| 롤 이력(부모 · 자식 한 단계 + 조상 인쇄 롤의 실적) | **E4** | X-RLL-03 → `lineage.parents_of/children_of/trace_backward` + `lot.work_result_id` | 읽기만 |
| 인쇄 롤 생성(작업 종료) | **E5** | `on_result_closed` → `lineage.retag(ROLL)` + ext 행 | |
| 불합격 롤 출하 금지 · 다른 Job 롤 금지 · 미검사 허용(D-17) | **E5** | `validate_shipment` | 미검사 허용은 코어 스캔(F-SHP-05 미검사 422)이 더 엄격 — 코어를 따른다(§6 D-504) |
| COA | 코어 `shp_document` + **E7** | `templates/print/document.html` 덮어쓰기 | 스냅샷에 롤별 ΔE · 판정 · 불량 · 길이 · 폭 |
| 롤 라벨 3종(원재료 LOT · 인쇄 롤 · 롤) | **E7** | `templates/print/label_lot.html`(kind · process_type 분기) + `adapters/label_html.py`(브라우저 인쇄 · D-04) | 바코드 = 번호 글자 그대로(G-C14) |
| 평균 ΔE · 불합격 롤 수 · 재고 롤 수 | **E5** | `kpi_extra` | |
| 영업관리 확장(수주 → 작업지시 · 수주 현황) | 코어 `ord` + **E1** | `rename: ord → 영업관리` · 권한 칸 = 작업지시 관리 칸(D-418) | 거래처 이력은 §1.2 밖 |
| 이관 배치 6 | 코어 B-MIG-01~04 + `migrate.yaml` | §1.2 | 인쇄 기준 3 테이블은 CR-6 |
| 작업지시서 · 라벨 · COA 양식 | **E7** | `templates/print/` | |

**들어가지 않는 것** → §3.

---

## 3. 코어 변경 요청 후보 — 확장 지점 7 밖이거나 코어 계약이 모자란 것 (`decisions.md` 에 `코어 변경 요청` 으로 올릴 초안)

| # | 무엇 | 왜 모자란가 | 코어의 어디를 어떻게 — 다른 팩도 쓰는가 | 팩의 임시 처리 |
|---|---|---|---|---|
| **CR-1** | **`job_lot` 과 Job-Lot-Roll 매핑 화면** | `spec.md` §2.2 는 `job_lot` 을 "지시 ↔ LOT 매핑(엘컴화인 D-10)" 이라 했지만 `db-schema.md` 의 `job_lot` 은 `item_id · required_qty · lot_id(지정 투입)` = BOM 소요 줄이다. 엘컴화인 `job_lot` 은 **생산 LOT**(`lot_no` 채번 `JOB_LOT` · `planned_roll_count` · `planned_length_m`, Job 1:N)이고 `roll.job_lot_id` 가 가리킨다. 코어 JOB-01 에는 "지시 LOT 등록" 기능(F-JOB-06 에 해당)이 없다 | `job_lot` 에 `lot_no`(채번 `JOB_LOT`) · `plan_qty` · `plan_count` 를 두고 F-JOB-01 안에 "지시 LOT 추가" 를 주거나, 별도 F-JOB-08 "지시 LOT 등록" 을 더한다. `lot.job_lot_id`(선택 FK). 김치(배치 계획 N) · 급식(솥 N) 도 같은 자리가 필요하다 | 1차 범위 밖. `numbering.JOB_LOT` 만 선언. 조회는 X-RLL-03 + TRC |
| **CR-2** | **`lineage.split/merge` 에 `process_id` · `equipment_id` · `attrs` 인자** | `make_product_lot` 은 `attrs=` 를 받지만 `split/merge` 는 `(parent_ids, by, qty, relation, kind)` 뿐. 후가공 · 슬리팅 롤의 가공 설비 · 공정 · 길이 · 폭을 적을 길이 없다 | `split(..., process_id=None, equipment_id=None, attrs=None)` · `merge(...)` 같게. 김치 혼합(설비) · 급식 소분도 쓴다 | `rll` 라우터가 `lineage.split/merge` 직후 **같은 `tx` 에서** `update lot set process_id, equipment_id, attrs where id = …`(write_scope `lot` 안 · R8 위반 아님). 설비는 ext 에도 둔다(`x_printfilm_lot_ext.equipment_id`) |
| **CR-3** | **출하 스캔 시점 훅 `validate_lot_ship(cur, shipment, lot, user)`** | 훅은 `validate_shipment`(승인 직전)뿐. 엘컴화인 D-16 "다른 Job 의 롤은 스캔 때 422" 를 스캔 때 못 막고 승인 때만 막는다 | `lineage.ship` 직전에 훅 한 자리. 김치 "금속검출 미통과 스캔 거부" 도 같은 자리 | `validate_shipment` 에서 승인 때 일괄 판정(S2) |
| **CR-4** | **`attrs` 형식 `lookup`(팩 테이블 참조)** | `attrs[].type` 은 `number|text|bool|date|select(choices 고정)`. 판사양 · 아니록스 · 잉크조성은 팩 테이블에서 골라야 하는데 `select` 는 고정 목록이다 | `type: lookup, table: x_printfilm_plate, key: plate_code, label: plate_name` 을 `ui.attrs_fields` 가 `/popup/{kind}` 처럼 그린다. 급식 레시피 · 김치 절임통도 쓴다 | `type: text`(코드 입력) + `validate_job_work_order` 가 없는 코드 422 |
| **CR-5** | **`on_work_order_updated` 훅** | 수정(F-JOB-02)에는 `on_*` 훅이 없고 `validate_job_work_order` 만 있다. ext 행 갱신을 validate 안에서 해야 한다 | `on_work_order_updated(cur, wo, user)` 를 F-JOB-02 저장 후에 | `validate_job_work_order` 가 `x_printfilm_job_work_order_ext` upsert(팩 테이블이라 write_scope 불필요). 검증 훅이 쓰기를 하는 점을 `hooks.md` 에 명시 |
| **CR-6** | **표준 Import 에 팩 테이블 파일** | `migration-files.md` 4종(기준 · 수주/지시 · LOT/계보 · 이력)에 `x_<팩>_*` 파일이 없다. 엘컴화인 B-MIG-03 인쇄 기준 3 테이블을 표준 배치로 못 넣는다 | `migrate.yaml: pack_files: [{file, table, key}]` 를 `migrate basics` 가 코어 파일 뒤에 같은 규칙(멱등 · 오류 리포트)으로 적재 | 이관 단계에 팩 스크립트 |
| CR-7 | `lot` 의 종류별 "공정 구분" | `lot.process_id` 가 있지만 `split/merge` 가 채우지 않는다(CR-2 와 같은 뿌리). 공정 구분을 ext 에 중복 저장한다 | CR-2 가 받아들여지면 `x_printfilm_lot_ext.process_type` 은 `lot.process_id → bas_process.attrs.process_type` 로 대체 가능 | ext 유지 |
| CR-8 | 성적서 발행본이 `qty · unit` 외에 `attrs` 를 스냅샷에 담는가 | F-SHP-09 계약은 "최신 검사 항목 값" 스냅샷. 길이 · 폭(attrs) · 공정 구분(ext)이 들어가는지 명시되지 않았다 | 스냅샷에 `lot.attrs` 와 `packs.hook("snapshot_extra")` 를 더한다 | 양식(`document.html`)이 스냅샷 + `x_printfilm_lot_ext` 를 읽는다 — 발행 뒤 ext 가 바뀌면 양식이 바뀐다(스냅샷 불변 위반 위험 → `scenarios.md` S3 에 검증) |

**`lot` 단일 테이블(D-03) 판단**: 엘컴화인 `roll` 의 컬럼은 전부 들어갈 자리가 있다 — `roll_no → lot.lot_no` · `process_type → x_printfilm_lot_ext.process_type`(WHERE 용) · `job_id → lot.work_order_id` · `job_lot_id → (CR-1)` · `work_result_id → lot.work_result_id` · `equipment_id → lot.equipment_id`(CR-2 전까지 ext 에도) · `length_m · width_mm → lot.attrs`(표시용) · `slit_seq → ext` · `produced_at → lot.made_at` · `produced_by → created_by`. 단일 테이블로 **충분하다**. 모자란 것은 테이블이 아니라 `lineage.split/merge` 의 인자(CR-2)다.

**`job_lot` 매핑 화면이 코어 JOB-01 안에서 되는가**: **안 된다**(CR-1). 코어 `job_lot` 의 뜻이 다르고 등록 기능이 없다. 1차 팩은 생산 LOT 단 없이 Job → Roll 로 간다(G-P04 10행에는 생산 LOT 이 필요 없다).

---

## 4. 테이블 매핑표 — 엘컴화인 30(+ `sales_order`) → 코어 / `x_printfilm_*` / `attrs`

| 엘컴화인 | 저장소 | 간다 | 방식 | 컬럼 메모 |
|---|---|---|---|---|
| `item` | D1 | `bas_item` | 코어 | `item_type` 제품/원재료 |
| `customer` | D1 | `bas_partner(partner_type=고객)` | 코어 | `note → attrs.note` 또는 코어 `contact` |
| `process` | D1 | `bas_process` | 코어 + attrs | `process_type → attrs.process_type` · `sort_no → seq` |
| `equipment` | D1 | `bas_equipment` | 코어 | `collect_yn=N` |
| `defect_code` | D1 | `bas_defect_code` | 코어 + attrs | `defect_group → attrs.defect_group` |
| `plate_spec` | D1 | **`x_printfilm_plate`** | 팩 E4 | `schema_ext.md` §1 |
| `anilox` | D1 | **`x_printfilm_anilox`** | 팩 E4 | |
| `ink_formula` | D1 | **`x_printfilm_ink_formula`** | 팩 E4 | |
| `ink_formula_component` | D1 | **`x_printfilm_ink_formula_component`** | 팩 E4 | |
| `job` | D2 | `job_work_order` + **`x_printfilm_job_work_order_ext`** | 코어 + 팩 E2 | `job_no → work_order_no` · `item_id` · `equipment_id` · `order_qty/qty_unit → plan_qty/unit` · `due_date → ord_order.due_date`(수주 경유) · `customer_id → ord_order.partner_id` · `status 등록/완료/취소 → 대기/마감/취소` · `plate_spec_id · anilox_id · ink_formula_id → ext` · `sales_order_id → order_dtl_id` |
| `job_lot` | D2 | — (CR-1) | 밖 | 코어 `job_lot` 과 뜻이 다르다 |
| `material_lot` | D3 | `lot(kind=MATERIAL)` + `mat_receipt` | 코어 | `lot_no` · `item_id` · `received_qty → qty` · `received_at → made_at`/`mat_receipt.receipt_date` · `insp_status 대기/합격/불합격 → 미검사/합격/불합격` · `supplier_name → bas_partner(공급)`(§6 D-507) · `supplier_lot_no → attrs.supplier_lot_no` · `insp_at/by/note → qua_inspection(insp_type=입고)` |
| `color_record` | D4 | **`x_printfilm_color_record`** | 팩 E4 | `job_id → work_order_id` |
| `color_record_mix` | D4 | **`x_printfilm_color_record_mix`** | 팩 E4 | |
| `work_result` | D5 | `pop_work_result` | 코어 | `status 진행/정지/완료 → started_at/ended_at + pop_stop 열림` · `output_qty → good_qty` · `worker → worker_id`(§6 D-507) · `job_lot_id → (CR-1)` |
| `work_stop` | D5 | `pop_stop` | 코어 | `stop_reason(글자) → reason_code(STOP_REASON)` |
| `work_scrap` | D5 | `pop_scrap` | 코어 | |
| `material_input` | D5 | `pop_input` | 코어 | |
| `roll` | D6 | `lot(kind=ROLL)` + **`x_printfilm_lot_ext`** + `attrs` | 코어 + 팩 E2/E6 | §3 "lot 단일 테이블 판단" |
| `roll_genealogy` | D6 | `lot_genealogy` | 코어 | `parent_material_lot_id/parent_roll_id → parent_lot_id` · `child_roll_id/child_shipment_id → child_lot_id` · `relation 투입/후가공/splice/슬리팅/출하 → 같은 이름`(`relation_base` 투입/합병/합병/분할/출하) |
| `inspection` | D7 | `qua_inspection` + `qua_insp_item(delta_e)` | 코어 + E3 | `result 합격/불합격 → judgement` · `delta_e → qua_insp_item.item_key=delta_e` · `roll_id → lot_id` · `job_id → (lot 경유)` |
| `inspection_defect` | D7 | `qua_defect` + `qua_insp_item(defect_position)` | 코어 + E3 | `defect_code_id` · `position → qua_defect.position` |
| `shipment` | D8 | `shp_shipment` + `lot(kind=SHIPMENT)` + `shp_document` | 코어 | `shipment_no → shp_shipment.shipment_no`(출하 LOT 번호는 코어 `LOT_SHIPMENT` 별도 — §6 D-501) · `customer_id → partner_id` · `job_id → (계보 경유)` · `status 등록/승인/취소 → 같다` · `coa_no · coa_issued_at → shp_document(document_no, issued_at)` |
| `sys_role` | SYS | `sys_role` | 코어 | ADMIN · PROD · QC · FIELD |
| `sys_user` | SYS | `sys_user` + `sys_session` | 코어 | `session_epoch/revoked_sessions → sys_session` |
| `sys_permission` | SYS | `sys_permission` | 코어 | `write_scope → scopes[]` |
| `sys_access_log` | SYS | `sys_access_log` | 코어 | |
| `sys_number_rule` · `sys_number_seq` | SYS | 같은 이름 | 코어 | `seq_kind → kind`(종류명은 §5 매핑) |
| `sys_migration_log` | SYS | `sys_migration_log` | 코어 | |
| `sales_order` (EXT) | EXT | `ord_order` + `ord_order_dtl` | 코어 | 수주 1 = 헤더 1 + 상세 1줄 |
| `v_roll_state` · `v_material_lot_stock` | 뷰 | `v_lot_state` · `v_lot_stock` | 코어 | |

30 + 1 → 코어 **22**(뷰 2 제외) · 팩 테이블 **8** · 밖 **1**(`job_lot`). 팩 테이블 8 = `x_printfilm_plate` · `anilox` · `ink_formula` · `ink_formula_component` · `color_record` · `color_record_mix` · `lot_ext` · `job_work_order_ext`(= `gates.yaml: tables: 8`).

---

## 5. 채번 종류 매핑 (엘컴화인 D-101 → 코어 종류명)

| 엘컴화인 | 접두 · 형식 | 코어 종류 | 비고 |
|---|---|---|---|
| `JOB` | `J` + `YYMMDD-` + 3 | `WORK_ORDER` | |
| `JOB_LOT` | `L` + `YYMMDD-` + 3 | `JOB_LOT`(팩 추가 종류) | CR-1 전까지 발번하는 기능이 없다 |
| `MAT_LOT` | `M` + `YYMMDD-` + 3 | `LOT_MATERIAL` | |
| `ROLL` | `R` + `YYMMDD-` + **4** | `LOT_PRODUCT` | `ROLL` kind 의 base 가 PRODUCT 라 같은 종류 |
| `SHIPMENT` | `S` + `YYMMDD-` + 3 | `SHIPMENT` | 코어 `LOT_SHIPMENT`(출하 LOT 번호)는 별도 — `(미확정)` 코어 기본 형식(§6 D-501) |
| `COA` | `C` + `YYMMDD-` + 3 | `DOCUMENT` | |
| `SALES_ORDER` | `SO` + `YYMMDD-` + 3 | `ORDER` | |
| — | — | `PLAN` | 엘컴화인 없음 — 코어 기본 |

형식은 전부 **가설**(엘컴화인 D-05 · D-101 — 현업 번호 체계 미수령).

---

## 6. 결정 후보 D-5nn — 이 팩이 정한 것 (아키텍트가 `decisions.md` 에 옮긴다)

| # | 제목 | 내용 · 상태 |
|---|---|---|
| **D-501** | 출하 LOT 번호 | 엘컴화인은 출하 = 출하 LOT 한 번호(`S…`). 코어는 `shp_shipment.shipment_no`(`SHIPMENT`)와 `lot(kind=SHIPMENT).lot_no`(`LOT_SHIPMENT`)가 따로다. `SHIPMENT` 에 `S` 를 주고 `LOT_SHIPMENT` 는 **코어 기본값 그대로** 둔다 — 같은 `S` 를 주면 번호가 겹칠 수 있다. 라벨 · COA 바코드는 출하 LOT 번호(`lot_no`). 가설 · 현업 확인 |
| **D-502** | 롤 길이 · 폭은 attrs | `length_m` · `width_mm` 는 라벨 · COA · 조회 표시용 → `lot.attrs`(E2). 집계 · 검색에 쓰지 않는다(엘컴화인 D-25 생산 집계도 실적 수량 기준). 집계가 필요해지면 `bas_process_param` 으로 옮긴다(E3). `lot.qty/unit` = 작업 종료의 양품 수량(품목 단위 — 시드 예시 `m`) |
| **D-503** | 생산 LOT(Job-Lot-Roll 매핑) 1차 보류 | CR-1 전까지 팩에 생산 LOT 이 없다. 키 계층은 Job → Roll. `numbering.JOB_LOT` 은 선언만 |
| **D-504** | 미검사 롤 출하 | 엘컴화인 D-17 은 미검사 롤 스캔을 허용(COA 에 `미수집`). 코어 F-SHP-05 는 미검사 422. **코어를 따른다**(팩이 코어 검증을 풀 수 없다 — 게이트를 낮추는 것). 현업 확인 |
| **D-505** | 승인과 COA 발행 2단계 | 엘컴화인 "승인 = COA 번호 채번". 코어는 F-SHP-07 승인 → F-SHP-09 발행(`DOCUMENT`). 2단계로 간다. `after_commit_shipment_approved` 로 자동 발행하지 않는다(트랜잭션 밖 쓰기 · 재발행 번호 규칙 충돌) |
| **D-506** | Job 의 고객 · 납기는 수주에서 | 코어 `job_work_order` 에 거래처 · 납기가 없다(수주 상세 → `ord_order`). 엘컴화인 F-JOB-01 은 수주 없이도 고객 · 납기 필수. 팩은 `validate_job_work_order` 로 **수주 상세 없는 Job 을 422** 로 막는다(영업관리 확장 D-418 의 "수주 → 작업지시" 흐름을 기본으로). 수주 없는 긴급 Job 을 허용할지 현업 확인 |
| **D-507** | 글자로 받던 것 → 마스터 | 공급처(`supplier_name`) → `bas_partner(공급)` · 작업자(`worker` login_id) → `bas_worker` · 정지 사유(글자) → `STOP_REASON` 코드. 시드에 `(예시)` 1건씩 |
| **D-508** | 마감 되돌리기 없음 | 엘컴화인 F-JOB-02 "완료 → 등록 되돌리기" 는 코어 F-JOB-03 마감에 없다. 되돌리기 요구가 오면 코어 변경 요청 |
| **D-509** | 조회의 "부분" 매핑 | 수주 현황 진행 단계 · 불량 롤 내역 · 거래처 이력은 코어 조회 계약 범위에서 되는 만큼만. 모자라면 이관 단계에 `kpi_extra` 또는 팩 화면 |
| **D-510** | 권한 — 코어 전용 메뉴 칸 | 엘컴화인 48칸 밖의 코어 메뉴: `ord` = 작업지시 관리 칸(D-418) · `eqp` = 없음 ×4(숨김) · `ifc` = 관리자 `입력:재전송` · 나머지 없음 · `kpi` 는 엘컴화인대로 **조회 ×4** → KPI-03 지표 등록은 아무도 못 한다(지표는 시드로). 관리자에게 `입력:지표` 를 줄지 현업 확인 |
| **D-511** | 후가공 1:1 의 관계명 | 엘컴화인 `후가공`(부모 1) · `splice`(부모 N≥2) 둘 다 코어 base `합병`. 이름을 둘 다 등록한다 — 추적 · 상태는 base 로 같다 |
| **D-512** | 검사 ΔE 와 공정 ΔE | 검사 ΔE(`qua_insp_item.delta_e`)가 COA · 품질 집계의 원천(엘컴화인 P7). 공정 측정 ΔE(`pop_measure.delta_e`)는 인쇄 중 자가 측정 — 선택(`required_yn=N`). `kpi_extra.avg_delta_e` 는 검사 ΔE 로 센다 |
| **D-513** | 입고검사 항목 | 엘컴화인 F-MAT-03 은 판정 + 비고뿐. 코어 F-MAT-04 가 항목 0건을 허용하는지 개발2 확인 — 허용 안 하면 `inspection_items.csv` 의 입고 `insp_note`(비고 · text) 1건을 쓴다 |
| **D-514** | `rll` 라우터의 `lot` UPDATE | CR-2 전까지 `lineage.split/merge` 직후 같은 `tx` 에서 `update lot set process_id, equipment_id, attrs`. `write_scope.rll` 에 `lot` 이 있으므로 R7 안이고 R8(`lot_genealogy` · `sys_number_seq`) 밖이다. `check_pack` 이 이것을 잡으면 CR-2 를 앞당긴다 |

미확정 값 요약 — 채번 형식 7종(가설) · `LOT_SHIPMENT` 형식 · 인쇄 속도 단위 · ΔE 상한 · 판사양 도수 · 아니록스 선수 · 셀 용적 · 잉크 기준 Lab · 불량 위치 형식 · 정지 사유 목록 · 슬리팅 분할 수 상한(엘컴화인 D-409) · COA 양식 항목 · 라벨 크기 · 심벌(D-04) · 실 고객 · 품목 · 규격값 전부.

---

## 구현 메모 (개발2 · 웨이브 B · 2026-10-09)

기획 문서(§0~§6)는 그대로 두고 코드 · 테스트를 더했다. 아래는 **문서와 코드가 다른 곳**과 그 이유 — 코드가 맞다(CLAUDE.md).

### 만든 것

| 파일 | 내용 |
|---|---|
| `schema_ext.sql` | 테이블 8 = `schema_ext.md`. 1:1 ext 의 PK 겸 FK 컬럼명은 `_template` · `check_schema`(공통 컬럼 6) 규약대로 **`id`**(문서의 `lot_id` · `work_order_id` 와 같은 뜻). 코어 ALTER · 트리거 · 뷰 0 |
| `hooks.py` | 훅 6 + 코어가 실제로 부르는 자리 2: `after_save_job_work_order`(D-504 — 등록 · 수정 모두 ext upsert · CR-5 대체) · `validate_shp_document`(스냅샷 보강 — CR-8 임시) |
| `routers/{prt,clr,rll}.py` · `routers/_shared.py` | 기능 24 = 엔드포인트 24(`function-list.md` API 열 그대로). `rll` 의 계보는 `lineage.merge(relation="후가공"\|"splice", kind="ROLL", process_id=, equipment_id=, attrs=)` · `lineage.split(relation="슬리팅", …)` 만(D-503) — `lot_genealogy` 직접 SQL 0. `update lot` 은 둘(슬리팅 자식별 폭 attrs · splice 의 Job 지정 — D-514 · write_scope `lot`) |
| `templates/{prt,clr,rll}/*.html` 7 · `templates/print/{label_lot,document,work_order}.html` 3(R10 덮어쓰기 — 위 §0 표와 같다) | 최소 템플릿 · `base.html` + `ui` 매크로 · 문구 `t()`. 롤 라벨은 kind=ROLL 분기(공정 구분 · 분할 순번 · Job · 길이 · 폭), COA 는 롤별 ΔE · 판정 · 불량 · 길이 · 폭 + 바코드 = 출하 LOT 번호, 작업지시서에 판사양 · 아니록스 · 잉크조성 |
| `adapters/label_html.py` | `PrintAdapter`(코어 상속) — 브라우저 인쇄 `sent=False` + 양식 이름 검증(모르는 양식 ValueError) |
| `seed/*.csv` · `pack.yaml: seeds[]` | 기획 10 파일 + 지표 4(`kpi_indicators_example.csv`) — 코어 `seed_core`(CR-9 · 6c77eb9)가 공정 → 품목 → 설비 → `process_params` → `inspection_items` → 나머지 순서로 멱등 적재. 팩 테이블 4 는 `{file, table, key}`(`ink_code` → `ink_formula_id` FK 풀기) · `attrs.process_type` · `attrs.defect_group` · 역할별 계정(`qc` 포함). 웨이브 B 의 `seed/seed_pack.sql` 우회는 **지웠다**(회전 4). `MES_PACK=printfilm make db-reset` 한 번이면 끝 · 2회 행 수 diff 0 실측 |
| `tests/` 9 파일 · 39 테스트 | `gates.yaml` S1~S3 + 훅 + 기능 24 마다 `@pytest.mark.fn` + 용어(G-P05) |

### pack.yaml 에서 고친 것 (기획 값 → 동작하는 값)

| 키 | 기획 | 고침 | 이유 |
|---|---|---|---|
| `screens[].channels` | `[web]` · `[pop]` | **기획값으로 되돌림**(회전 4) | 웨이브 B 에는 `[관리자 Web]` · `[현장 POP]` 로 우회했다 — 아키텍트 `733074f` 가 `packs.load` 에서 코드 → 라벨로 정규화 |
| `menus.add[].owner` | 없음 | `개발2` | 팩 `function-list.md` 의 담당(개발2)과 모듈 owner 가 같아야 `contracts` 가 읽는다 — `pack-contract.md` §2 서식에 들어갔다(733074f) |
| `terms` | `실적: 작업 실적` · `추적: LOT 추적` | **기획값으로 되돌림**(회전 4) | 웨이브 B 에는 겹말("LOT 추적" → "LOT LOT 추적") 때문에 뺐다 — `packs.t` 겹말 방지(733074f)로 `LOT 추적` · `작업 실적` 은 그대로. 남는 어색함: 메뉴 rename `생산 실적 (POP)` → 「생산 작업 실적 (POP)」 · `실적 현황` → 「작업 실적 현황」 · 「역추적」 → 「역LOT 추적」(기획 판단 — rename 을 최종 이름으로 쓰면 해소) |
| `seeds[]` | 10 파일 | **기획값으로 되돌림**(회전 4) + `kpi_indicators_example.csv` | 웨이브 B 에는 5 파일 + `seed_pack.sql` 로 우회했다 — 코어 CR-9(6c77eb9)가 `{file, table, key}` · `attrs.*` · 적재 순서를 받는다. 지표 4 는 SQL 안 값에서 CSV 로 옮겼다 |

### 코어와 다른 점 · 임시 처리 (progress-dev2.md §3 의 코어 변경 요청)

- **CR-2 · D-503** 해결됨 — `lineage.split/merge` 가 `process_id · equipment_id · attrs` 를 받는다. D-514 의 `update lot` 은 "자식별 폭(슬리팅)" 과 "splice 의 Job 지정" 둘만 남았다(설비 · 공정 · 길이는 인자로).
- **CR-5** — `after_save_job_work_order`(D-504) 가 코어 `job.py` 에 이미 있어 `on_work_order_updated` 없이 등록 · 수정 모두 ext 를 쓴다. `validate_job_work_order` 는 검증만 한다(문서 §2 의 "검증 훅이 쓴다" 예외를 쓰지 않았다).
- **CR-8** — 스냅샷 보강 훅이 없어 `validate_shp_document(cur, row, user)` 가 `row["snapshot"]`(코어가 같은 객체를 저장)을 제자리에서 보강한다. 발행 뒤 ext 가 바뀌어도 발행본은 불변(S3 재발행 바이트 대조).
- **CR-3** — 출하 스캔 시점 훅 없음 → 다른 Job 의 롤은 승인 때 422(`validate_shipment`). 그대로.
- **S2 6단계** — "스캔 뒤 재검사 불합격" 은 코어 F-QUA-04 가 스캔된 LOT(상태 `출하`)의 새 검사를 422 로 막는다(D-304). 테스트는 **스캔 전에 등록해 둔 검사를 스캔 뒤 불합격 판정**(F-QUA-05 는 출하 상태를 보지 않는다)으로 같은 상태를 만든다.
- **계정 `qc`** — 코어 `seed_core.USERS` 가 역할 코드 `QA` 로 고정돼 팩 역할 `QC` 의 계정을 만들지 않는다. 테스트 · 화면 캡처는 관리자가 F-SYS-01 로 `qc` 를 만든다.
- **G-P03** — `check_trace` 는 `design_source` 가 있으면 `import_design` 출력을 기다리며 `미검증`, `import_design.py` 는 `design.json` 만 읽는다(설계도 HTML · README §1 매핑표 미지원 · `--pack` 없음). 매핑표 자체는 §1.1(32행 · 고아 0 · 밖 1 = JOB-02/CR-1) 에 있다.
- **R9(코어 테스트를 팩을 올린 채로)** — `MES_PACK=printfilm uv run pytest tests/` 는 57 failed · 6 errors. 원인은 팩이 선언한 업종 규칙이 코어 테스트의 전제와 다른 것: 역할 `QA`→`QC`(계정 `qa` 없음) · 권한 표(관리자 `pop` 조회 · `eqp` 숨김 403) · `on_result_closed` 가 인쇄 공정(`attrs.process_type=인쇄`)이 아닌 코어 예시 공정의 종료를 422 · `bas_process.attrs.process_type` 필수. 코어 수정 없이 팩이 풀 수 없다 — §3 요청.
