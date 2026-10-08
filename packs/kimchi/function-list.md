# 기능 목록 — `kimchi` 팩 화면 8 · 기능 24 (기획자3 · 2026-10-09 · 기획 초안)

> 열은 코어 `contracts/function-list.md` §1 과 같다. 코어로 간 기능(품목 · 작업지시 · 실적 · 검사 · 출하 · 추적 …)은 여기 적지 않는다 — README §1 매핑표가 가리키는 코어 기능을 그대로 쓴다.
> 공통 규칙: 쓰기는 `rbac.require_fn("F-X-…")` · 저장 뒤 `audit.log_change` · 번호는 `numbering.next` · 계보는 `lineage` 만 · 문구는 `t()`. 0건 `미수집`. 쓰기 대상은 `x_kimchi_*` + `pack.yaml: write_scope` 만(R7).
> 권한의 역할명은 `pack.yaml: roles`(PM · PROD · QA · FIELD · ADMIN · VENDOR). 범위는 `permissions.csv` 의 `scopes`.

| ID | 모듈 | 화면 | 기능명 | 유형 | 쓰는 테이블 | 채널 | 권한 | 범위 | API | 훅 | 담당 | 계약 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-X-COND-01 | cond | X-COND-01 | 품목별 공정 조건 등록 | 등록 | x_kimchi_item_std | 관리자 Web | PROD · ADMIN | 일반 | `POST /cond/item-standards` | - | 개발3 | 공정(P03 세척/절임) · 품목 · 크기구분(선택) · 키(`salinity_pct` `salting_hours` `wash_time_min` `wash_volume_l` `wash_weight_kg` `sanitizer_ppm` `aging_days`) · 기준값 · 하한 · 상한 · 허용편차 · 적용시작일 → 한 행. 키는 `bas_process_param.param_key` 에 있어야 한다(없으면 422). `(process, item, size_type, param_key, valid_from)` 중복 422. 기준값 없이 저장하면 `미확정` 표시 |
| F-X-COND-02 | cond | X-COND-01 | 품목별 공정 조건 수정 | 수정 | x_kimchi_item_std | 관리자 Web | PROD · ADMIN | 일반 | `POST /cond/item-standards/{id}` | - | 개발3 | 기준값 · 범위 · 편차 · 사용 여부. 키 · 품목은 못 바꾼다. 변경은 접근 로그(`change`)에 전후값 |
| F-X-COND-03 | cond | X-COND-01 | 품목별 공정 조건 사용중지 | 삭제 | x_kimchi_item_std | 관리자 Web | PROD · ADMIN | 일반 | `POST /cond/item-standards/{id}/delete` | - | 개발3 | 진행 중 절임통 배치(`x_kimchi_tank.std_id`)가 참조하면 422. 삭제 대신 `use_yn=N` |
| F-X-COND-04 | cond | X-COND-01 | 품목별 공정 조건 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /cond/item-standards` | - | 개발3 | 공정 · 품목 · 키 검색. 그리드: 품목 · 크기구분 · 키 · 기준값 · 하한 · 상한 · 허용편차 · 사용여부(TD3 020 · 023 열). 정본 값(9% 48h · 13% 24h · 소독수 10ppm)은 시드가 아니라 **화면에서 입력**한다(임진강 D-08 — 품목 연결이 예시이므로) |
| F-X-WSH-01 | wsh | X-WSH-01 | 소독수 농도 수기 기록 | 등록 | x_kimchi_sanitizer_log | 관리자 Web, 현장 POP | PROD · FIELD · ADMIN | 일반 | `POST /wsh/sanitizer` | - | 개발3 | 설비(소독수 공급장치) · 작업지시(선택) · 측정 농도(ppm) · 접촉시간(분) · 투입비율 · 측정 시각 → 한 행(`source=manual`). 농도 < `bas_process_param(P03, sanitizer_ppm).min_value`(10) 이면 `deviated=Y` + `x_kimchi_env_alarm` 1행(종류 `소독수 10ppm 미달`, 훅과 같은 함수 `alarm.raise_env`). 센서 연동 구간의 자동 수집은 이 기능이 아니라 `on_collect`(hooks.md §3) |
| F-X-WSH-02 | wsh | X-WSH-01 | 소독수 기록 취소 | 취소 | x_kimchi_sanitizer_log | 관리자 Web | PROD · ADMIN | 일반 | `POST /wsh/sanitizer/{id}/cancel` | - | 개발3 | `source=manual` 만. `canceled_yn=Y`(행 삭제 안 함). collect 행은 422 |
| F-X-WSH-03 | wsh | X-WSH-01 | 소독수 농도 로그 조회 | 조회 | - | 관리자 Web, 현장 POP | 조회 이상 | - | `GET /wsh/sanitizer` | - | 개발3 | 설비 · 작업지시 · 기간 · 이탈 여부. 수기(`x_kimchi_sanitizer_log`)와 센서(`collect.series(SW-01, sanitizer_ppm)`)를 **한 목록**에 `수집방식` 열로 합친다. 이탈 행 색상 + '알람 이력' 링크(X-ALM-01). 0건 `미수집` |
| F-X-TANK-01 | tank | X-TANK-01 | 절임통 투입 등록 | 등록 | x_kimchi_tank | 관리자 Web, 현장 POP | PROD · FIELD · ADMIN | 일반 | `POST /tank/operations` | - | 개발3 | 진행 중 실적(`pop_work_result` 공정 P03 · 설비 = 절임통 · `ended_at` NULL) 선택 + 품목별 절임 조건(`x_kimchi_item_std` 염도 · 시간) + 투입 중량 → `x_kimchi_tank` 1행(`work_result_id` PK · `plan_end_at = started_at + salting_hours`). 같은 절임통에 미완료 배치가 있으면 422. 실적 자체는 코어 F-POP-02 가 만든다(D-501) — 이 기능은 실적을 만들지 않는다 |
| F-X-TANK-02 | tank | X-TANK-01 | 절임통 투입 취소 | 취소 | x_kimchi_tank | 관리자 Web | PROD · ADMIN | 일반 | `POST /tank/operations/{id}/cancel` | - | 개발3 | 실적이 종료되지 않았을 때만. 종료 후 422. 행 삭제(ext 만 — 실적은 그대로) |
| F-X-TANK-03 | tank | X-TANK-01 | 절임 완료 처리 | 승인 | x_kimchi_tank | 관리자 Web, 현장 POP | PROD · FIELD · ADMIN | 일반 | `POST /tank/operations/{id}/complete` | - | 개발3 | `status=완료` · `completed_at` · 완료 시 염도(센서 최종값 `collect.aggregate(센서, salinity_pct, started_at, now, last)` 또는 수기) 기록. 실적 종료(F-POP-03)는 **따로** POP-02 에서 하며, 종료 훅 `on_result_closed` 가 LOT 을 `TANK` 로 바꾼다. 완료 전 실적 종료는 422 가 아니다(순서 자유) — 둘 다 끝나야 역추적 노드에 `완료` 가 보인다 |
| F-X-TANK-04 | tank | X-TANK-01 | 절임통 운영 조회 | 조회 | - | 관리자 Web, 현장 POP, 현황판 | 조회 이상 | - | `GET /tank/operations` | - | 개발3 | 절임통 8 × 현재 배치(작업지시 · 품목 · 투입 시각 · 경과 시간 · 예정 완료 · 측정 염도 · 상태) — TD3 024 그리드. 현황판(`?device=board`)은 8칸 타일 + 5초 폴링 JSON(`Accept: application/json`). 염도 센서가 매핑되지 않은 절임통은 `미확정 (D-206)` |
| F-X-TANK-05 | tank | X-TANK-02 | 염도 추이 조회 | 조회 | - | 관리자 Web, 현황판 | 조회 이상 | - | `GET /tank/salinity` | - | 개발3 | 절임통(또는 센서) · 기간 → `collect.series(equip, salinity_pct, from, to)` 표 + 추이. 진행 중 배치의 목표 염도 · 허용편차(`x_kimchi_item_std`)를 기준선으로. 0건 `미수집`. **쓰기 0** |
| F-X-PKG-01 | pkg | X-PKG-01 | 테이핑 실적 수기 등록 | 등록 | x_kimchi_taping_log | 관리자 Web | PROD · FIELD · ADMIN | 일반 | `POST /pkg/taping` | - | 개발3 | 작업지시 · 설비(자동포장기) · 포장 수량(박스) · 가동 분 · 기록 시각 → 한 행(`source=manual`). 자동 수집분은 `on_collect` 가 같은 표에 `source=collect` 로 쌓는다 |
| F-X-PKG-02 | pkg | X-PKG-01 | 테이핑 실적 조회 | 조회 | - | 관리자 Web, 현황판 | 조회 이상 | - | `GET /pkg/taping` | - | 개발3 | 설비 · 작업지시 · 기간 · 가동상태. 그리드: 수집일시 · 작업지시 · 포장수량(박스) · 가동상태 · 누적가동(분) · 수집방식(TD3 030). 작업지시별 누계는 화면 집계(저장 안 함). 가동 상태는 `eqp_run_log` 를 읽는다 |
| F-X-AGE-01 | age | X-AGE-01 | 숙성 투입 | 등록 | lot, lot_genealogy, x_kimchi_lot_ext | 관리자 Web, 모바일 | PROD · FIELD · ADMIN | 일반 | `POST /age/stock` | on_lot_created | 개발3 | 포장 LOT(`kind_base=PRODUCT` · 재고 · 합격) 스캔 + 숙성 수량 + 숙성 냉장고 → **`lineage.split(cur, parent_lot_id, [{qty}], relation="숙성", kind="AGING")`** 1회 → 새 LOT 에 `x_kimchi_lot_ext(aging_start_date=today · aging_due_date=+aging_days · location_equipment_id=냉장고)`. `aging_days` 는 `x_kimchi_item_std(aging_days)` → 없으면 21(D-511). 불합격 · 미검사 · 소진 LOT 422. **`lot_genealogy` 직접 SQL 금지** |
| F-X-AGE-02 | age | X-AGE-01 | 숙성 완료(출하 가능) 처리 | 승인 | x_kimchi_lot_ext | 관리자 Web, 모바일 | PROD · ADMIN | 일반 | `POST /age/stock/{lot_id}/complete` | - | 개발3 | `shippable_yn=Y` · `aging_end_date`. 예정일 전 완료는 422 가 아니라 허용 + 접근 로그(사유 필수). 출하 자체는 SHP-02 |
| F-X-AGE-03 | age | X-AGE-01 | 숙성 재고 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /age/stock` | - | 개발3 | `lot.kind=AGING` × `v_lot_state=재고` × ext. 그리드: 품목 · 로트 · 숙성 투입일 · 경과일수 · 완료 예정일 · 숙성수량(kg) · 출하가능(TD3 032). FIFO 안내 = 투입일 오름차순 상단 고정. 390px |
| F-X-AGE-04 | age | X-AGE-01 | 숙성 배치 라벨 출력 | 출력 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /age/stock/{lot_id}/label` | - | 개발3 | 코어 `print/label_lot` 재사용(바코드 = `lot_no`). 스캔 왕복(G-C14) |
| F-X-AGE-05 | age | X-AGE-02 | 냉장고 입고 | 등록 | x_kimchi_cold_move, x_kimchi_lot_ext | 관리자 Web, 모바일 | PROD · FIELD · ADMIN | 일반 | `POST /age/cold-moves/in` | - | 개발3 | LOT 스캔(PRODUCT · AGING) + 냉장고 + 수량 → `x_kimchi_cold_move(trx_type=입고)` 1행 + `x_kimchi_lot_ext.location_equipment_id` 갱신(없으면 생성). 출하된 LOT 422 |
| F-X-AGE-06 | age | X-AGE-02 | 냉장고 출고 | 등록 | x_kimchi_cold_move, x_kimchi_lot_ext | 관리자 Web, 모바일 | PROD · FIELD · ADMIN | 일반 | `POST /age/cold-moves/out` | - | 개발3 | LOT 스캔 + 수량 → `trx_type=출고` 1행 · 잔량(입고 합 − 출고 합) 0 이면 `location_equipment_id=NULL`. 잔량 초과 422. 출하는 여기서 하지 않는다(SHP-02) |
| F-X-AGE-07 | age | X-AGE-02 | 냉장고 입출고 이력 조회 | 조회 | - | 관리자 Web, 모바일 | 조회 이상 | - | `GET /age/cold-moves` | - | 개발3 | 냉장고 · 품목 · 로트 · 기간 · 구분. 그리드: 처리일시 · 냉장고 · 품목 · 로트번호 · 구분 · 수량(TD3 031). 냉장고별 현재 잔량 요약 상단 |
| F-X-ALM-01 | alm | X-ALM-01 | 알람 확인 | 수정 | x_kimchi_env_alarm | 관리자 Web, 현장 POP | QA · ADMIN | 일반 | `POST /alm/alarms/{id}/ack` | - | 개발3 | `status=확인` · `acked_at/by`. 이미 해제면 422 |
| F-X-ALM-02 | alm | X-ALM-01 | 알람 해제(조치) | 승인 | x_kimchi_env_alarm | 관리자 Web, 현장 POP | QA · ADMIN | 일반 | `POST /alm/alarms/{id}/clear` | - | 개발3 | 조치 내용 필수 → `status=해제` · `cleared_at/by`. 해제 뒤 같은 설비 · 태그 이탈이 다시 오면 **새 알람**(D-512 는 미해제일 때만 합침) |
| F-X-ALM-03 | alm | X-ALM-01 | 알람 이력 조회 | 조회 | - | 관리자 Web, 현장 POP, 현황판 | 조회 이상 | - | `GET /alm/alarms` | - | 개발3 | 종류 · 설비 · 기간 · 상태. 그리드: 발생일시 · 종류 · 설비 · 태그 · 값 · 기준 · 횟수 · 상태. `qua_issue(source=hook)` 로 간 검사 · 측정값 이탈(손실률 · 금속 · CCP · 중량)은 이 목록에 **읽기 전용 행**으로 합쳐 보인다(QUA-04 링크) — 임진강 "알람 이력 6종 한 화면"(TD3 standard_note 3) 재현. 현황판은 미해제 건수 + 최근 5건 |

## 모듈별 수 (G-P02 기대값)

| 모듈 | cond | wsh | tank | pkg | age | alm | 합 |
|---|---|---|---|---|---|---|---|
| 화면 | 1 | 1 | 2 | 1 | 2 | 1 | **8** |
| 기능 | 4 | 3 | 5 | 2 | 7 | 3 | **24** |

계보에 닿는 팩 기능은 **F-X-AGE-01 뿐**이고 `lineage.split` 을 거친다. 절임통 `TANK` 는 훅 `on_result_closed` 의 `lineage.retag` 이 한다(hooks.md §4). 혼합 `혼합` relation 은 코어 F-POP-03 의 합병 옵션이 받는다(D-502) — 팩 기능이 아니다.
