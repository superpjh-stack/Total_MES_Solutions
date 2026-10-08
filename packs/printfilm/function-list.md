# printfilm 팩 기능 목록 — 팩 화면 기능 24줄 (기획자2 · 2026-10-09)

> 코어 `contracts/function-list.md` 와 같은 열. `app/contracts.py` 가 이 표를 코어 표에 **더해** 읽고, `rbac.require_fn("F-X-…")` · `check_trace`(G-P02 · G-P03)가 쓴다.
> 엘컴화인 `contracts/function-list.md` 의 F-PRT-01~12 · F-CLR-01~05 · F-RLL-01~07(24줄)을 코어 열 형식으로 옮기고, API 경로 · 쓰는 테이블을 팩 규칙(`x_printfilm_*` · `lineage` 경유)에 맞췄다. **코어로 간 기능(README §1.2 의 1:1 · 용어)은 여기 없다.**
> 담당은 팩 담당 **개발2**(코어 `screen-map.md` §3: `packs/printfilm/` 은 개발2). 채널 · 권한은 `pack.yaml: channels` · `seed/permissions.csv` 의 팩 메뉴 행(prt: 관리자 · 생산 입력 / clr: 품질 · 현장 입력 / rll: 생산 · 현장 입력).

## 1. 읽는 법

열은 코어와 같다 — ID · 모듈 · 화면 · 기능명 · 유형 · 쓰는 테이블 · 채널 · 권한 · 범위 · API · 훅 · 담당 · 계약. 공통 규칙도 같다: 쓰기는 `rbac.require_fn`, 쓰기 뒤 `audit.log_change`, 번호는 `numbering`, 계보는 `lineage`, 문구는 `t()`, 0건은 `미수집`. 팩 테이블은 `schema_ext.md`.

## 2. 기능 24줄

| ID | 모듈 | 화면 | 기능명 | 유형 | 쓰는 테이블 | 채널 | 권한 | 범위 | API | 훅 | 담당 | 계약 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-X-PRT-01 | prt | X-PRT-01 | 판사양 등록 | 등록 | x_printfilm_plate | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/plates` | - | 개발2 | 판 코드 · 판명 · 품목(제품 · `bas_item`) · 도수 · 사양 메모 → 한 행. 코드 중복 · 필수 누락 422. 미사용(`use_yn=N`) 품목은 고를 수 없다. 규격 값은 `(예시)` 외에 지어내지 않는다 |
| F-X-PRT-02 | prt | X-PRT-01 | 판사양 수정 | 수정 | x_printfilm_plate | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/plates/{id}` | - | 개발2 | 코드는 못 바꾼다. 사용 여부 변경 포함. 없는 ID 404 |
| F-X-PRT-03 | prt | X-PRT-01 | 판사양 삭제 | 삭제 | x_printfilm_plate | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/plates/{id}/delete` | - | 개발2 | Job(`x_printfilm_job_work_order_ext.plate_id`)이 참조하면 422 `사용 중이라 삭제할 수 없습니다`, 아니면 지운다. 막는 참조는 FK 에서 읽는다(엘컴화인 D-102) |
| F-X-PRT-04 | prt | X-PRT-01 | 판사양 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /prt/plates` | - | 개발2 | 코드 · 이름 · 품목 · 사용 여부로 검색. 0건 `미수집` |
| F-X-PRT-05 | prt | X-PRT-02 | 아니록스 등록 | 등록 | x_printfilm_anilox | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/anilox` | - | 개발2 | 아니록스 코드 · 명칭 · 선수 · 셀 용적 · 비고 → 한 행. 코드 중복 422. 규격 값은 지어내지 않는다 |
| F-X-PRT-06 | prt | X-PRT-02 | 아니록스 수정 | 수정 | x_printfilm_anilox | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/anilox/{id}` | - | 개발2 | 코드는 못 바꾼다. 사용 여부 변경 포함 |
| F-X-PRT-07 | prt | X-PRT-02 | 아니록스 삭제 | 삭제 | x_printfilm_anilox | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/anilox/{id}/delete` | - | 개발2 | Job(ext `anilox_id`)이 참조하면 422, 아니면 지운다 |
| F-X-PRT-08 | prt | X-PRT-02 | 아니록스 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /prt/anilox` | - | 개발2 | 코드 · 이름 · 사용 여부로 검색. 0건 `미수집` |
| F-X-PRT-09 | prt | X-PRT-03 | 잉크조성 등록 | 등록 | x_printfilm_ink_formula, x_printfilm_ink_formula_component | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/inks` | - | 개발2 | 잉크 코드 · 잉크명 · 색 이름 · 기준 색상값(L · a · b) + 조성 행(성분명 · 비율 %) N줄 → `tx` 하나. 코드 중복 422. 비율은 0 초과 100 이하, 소수 셋째 자리까지(엘컴화인 D-209). 조성 행 합이 100 이 아니어도 등록은 된다(기준 조성은 합을 강제하지 않는다 — 배합비 F-X-CLR-02 만 100 을 강제) |
| F-X-PRT-10 | prt | X-PRT-03 | 잉크조성 수정 | 수정 | x_printfilm_ink_formula, x_printfilm_ink_formula_component | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/inks/{id}` | - | 개발2 | 코드는 못 바꾼다. 조성 행은 통째로 바꿔 넣는다(`delete` 후 `insert`, 같은 `tx`) |
| F-X-PRT-11 | prt | X-PRT-03 | 잉크조성 삭제 | 삭제 | x_printfilm_ink_formula, x_printfilm_ink_formula_component | 관리자 Web | 관리자 · 생산 | 일반 | `POST /prt/inks/{id}/delete` | - | 개발2 | Job(ext `ink_formula_id`) · 조색 기록(`x_printfilm_color_record.ink_formula_id`)이 참조하면 422, 아니면 조성 행과 함께 지운다 |
| F-X-PRT-12 | prt | X-PRT-03 | 잉크조성 조회 | 조회 | - | 관리자 Web | 조회 이상 | - | `GET /prt/inks` | - | 개발2 | 코드 · 이름 · 색 이름 · 사용 여부로 검색. 한 건을 열면 조성 행. 0건 `미수집` |
| F-X-CLR-01 | clr | X-CLR-01 | 조색 기록 등록 | 등록 | x_printfilm_color_record | 현장 POP | 품질 · 현장 | 일반 | `POST /clr/records` | - | 개발2 | Job 번호(스캔 · `job_work_order.work_order_no`) · 색 이름 · 차수 · 색상값(L · a · b) · 기준 잉크조성(선택) → 한 행. **Job 참조 필수** — 없는 Job · 취소된 Job 422(스캔 진입 `?no=` 없는 번호는 그 화면 422 재렌더). 차수는 같은 Job · 색 이름 안에서 유니크(`(work_order_id, color_name, seq_no)`), 비우면 마지막 + 1 |
| F-X-CLR-02 | clr | X-CLR-01 | 배합비 등록 | 등록 | x_printfilm_color_record_mix | 현장 POP | 품질 · 현장 | 일반 | `POST /clr/records/{id}/mix` | - | 개발2 | 그 조색 기록의 배합비 행(성분명 · 비율 %)을 통째로 바꿔 넣는다(`tx`). **비율 합이 100 이 아니면 422** — 비율은 소수 셋째 자리까지 저장(넘는 자리는 반올림)하고 합은 저장되는 값으로 센다. 422 사유에 그 규칙과 「입력 → 저장되는 값」 이 보인다(엘컴화인 D-209) |
| F-X-CLR-03 | clr | X-CLR-01 | 조색 기록 수정 | 수정 | x_printfilm_color_record | 현장 POP | 품질 · 현장 | 일반 | `POST /clr/records/{id}` | - | 개발2 | 색상값 · 색 이름 · 기준 잉크조성 · 비고를 고친다. **Job 은 못 바꾼다.** 없는 ID 404 |
| F-X-CLR-04 | clr | X-CLR-01 | 조색 기록 삭제 | 삭제 | x_printfilm_color_record, x_printfilm_color_record_mix | 현장 POP | 품질 · 현장 | 일반 | `POST /clr/records/{id}/delete` | - | 개발2 | 조색 기록과 그 배합비 행을 지운다(`on delete cascade` 또는 같은 `tx`) |
| F-X-CLR-05 | clr | X-CLR-01 | 조색 기록 조회 | 조회 | - | 현장 POP | 조회 이상 | - | `GET /clr/records` | - | 개발2 | Job 번호 · 기간으로 검색. 차수 순으로 색상값과 배합비. `?no=<Job 번호>` 스캔 진입 — 스캔칸(`data-scan`)이 포커스를 잡는다. 0건 `미수집` |
| F-X-RLL-01 | rll | X-RLL-01 | 후가공 실적 등록 | 등록 | lot, lot_genealogy, x_printfilm_lot_ext | 현장 POP | 생산 · 현장 | 일반 | `POST /rll/finishing` | on_lot_created | 개발2 | 부모 롤 **1개** 스캔 + 설비 · 길이 · 폭 → `lineage.merge(parent_ids=[1], relation="후가공", kind="ROLL")` 후가공 롤 1 + 계보 `후가공` 1줄 + ext(`process_type=후가공`, `equipment_id`) + `attrs(length_m, width_mm)`(D-514). 부모는 `재고`(소진 · 출하 롤 422 — `lineage.assert_usable`). 롤 번호를 2개 이상 주면 422 「splice 로 등록하세요」(엘컴화인 D-203). 부모의 Job 이 `마감` · `취소` 면 422(엘컴화인 D-208). 응답에 롤 번호와 라벨 링크 |
| F-X-RLL-02 | rll | X-RLL-01 | splice 등록 | 등록 | lot, lot_genealogy, x_printfilm_lot_ext | 현장 POP | 생산 · 현장 | 일반 | `POST /rll/finishing/splice` | on_lot_created | 개발2 | 부모 롤 **N개(2 이상)** 스캔 → `lineage.merge(parent_ids=N, relation="splice", kind="ROLL")` 후가공 롤 1 + 계보 `splice` N줄. 같은 롤 중복 · 자기 자신 · 소진 · 출하 롤 422. 한 `tx`. 부모들의 Job 이 서로 다르면 후가공 롤의 Job 을 `work_order_no` 로 받아야 한다(없으면 422) — **부모 롤의 Job 중 하나**여야 하고 `마감` · `취소` 면 422(G-C08 · 엘컴화인 D-203 · D-208). `roll_no` 는 반복 필드, 쉼표 · 공백으로 이은 번호도 받는다 |
| F-X-RLL-03 | rll | X-RLL-01 | 후가공 조회 | 조회 | - | 현장 POP | 조회 이상 | - | `GET /rll/finishing` | - | 개발2 | 후가공 롤 목록(`x_printfilm_lot_ext.process_type='후가공'` — 부모 롤 · 설비 · 길이 · 상태 `v_lot_state`). 부모 롤을 하나씩 스캔해 쌓는다(`?rolls=R…,R…` — 어디에도 저장하지 않는다 · 엘컴화인 D-203). 1개면 F-X-RLL-01, 2개 이상이면 F-X-RLL-02 로. 스캔할 때마다 없는 롤 · 중복 · `재고` 아님을 바로 알린다(422 재렌더). 스캔칸 포커스 |
| F-X-RLL-04 | rll | X-RLL-02 | 슬리팅 분할 등록 | 등록 | lot, lot_genealogy, x_printfilm_lot_ext | 현장 POP | 생산 · 현장 | 일반 | `POST /rll/slitting` | on_lot_created | 개발2 | 부모 롤 1개 스캔 + 분할 수 N(+ 폭 N개 `widths_mm` 쉼표 · 길이) → `lineage.split(parent_id, count=N, relation="슬리팅", kind="ROLL")` 슬리팅 롤 N + 계보 `슬리팅` N줄 + ext(`process_type=슬리팅`, `slit_seq=1..N`, `equipment_id`) + `attrs`. N < 1 · 부모가 `재고` 아님 422. 상한은 `(미확정)`(엘컴화인 D-409). 응답 뒤 `/rll/slitting?parent=<부모 롤>` 에 라벨 N장을 늘어놓고 한 번에 인쇄(엔드포인트를 더 만들지 않는다) |
| F-X-RLL-05 | rll | X-RLL-02 | 슬리팅 조회 | 조회 | - | 현장 POP | 조회 이상 | - | `GET /rll/slitting` | - | 개발2 | 슬리팅 롤 목록(`process_type='슬리팅'` — 부모 롤 · 분할 순번 · 폭 · 상태). `?parent=` 로 그 부모의 자식 N + 라벨. 스캔칸 포커스 |
| F-X-RLL-06 | rll | X-RLL-03 | 롤 이력 조회 | 조회 | - | 현장 POP | 조회 이상 | - | `GET /rll/history` | - | 개발2 | `?no=<롤 번호>`(스캔) → 그 롤의 공정 구분(ext) · Job · 상태(`lineage.state`) · 부모 · 자식 한 단계(`lineage.parents_of/children_of`). 없는 롤 · 롤이 아닌 번호(원재료 LOT · 출하 LOT) 422 재렌더. 후가공 · 슬리팅 롤은 `lineage.trace_backward` 로 닿은 **조상 인쇄 롤의 작업 실적**(`lot.work_result_id → pop_work_result` · 측정값 · 정지 · 폐기 · 투입)을 함께 보여 준다 — 롤 번호 하나로 실적에 닿는 길은 이 화면의 책임(G-C08 · 엘컴화인 D-210). **쓰지 않는다** |
| F-X-RLL-07 | rll | X-RLL-03 | 롤 라벨 출력 | 출력 | - | 현장 POP | 조회 이상 | - | `GET /rll/history/{lot_no}/label` | - | 개발2 | `printing.render_print("label_lot", printing.label_for(lot_id))` — 팩이 덮어쓴 `print/label_lot.html` 이 kind=ROLL 이면 롤 라벨(롤 번호 바코드 · 공정 구분(분할 순번) · Job · 품목 · 길이 · 폭 · 생산 일시)을 그린다. 인쇄 롤도 같은 양식으로 재출력. 바코드 = `lot_no` 글자 그대로 — 스캔칸에 넣으면 그 롤이 열린다(G-C14). 없는 번호 404(경로 키) |

## 3. 모듈별 수 (G-P02 기대값 — `gates.yaml: functions: 24`)

| 모듈 | prt | clr | rll | 합 |
|---|---|---|---|---|
| 화면 | 3 | 1 | 3 | **7** |
| 기능 | 12 | 5 | 7 | **24** |
| 쓰기 | 9 | 4 | 3 | 16 |
| 읽기 | 3 | 1 | 4 | 8 |

- 계보에 닿는 팩 기능은 **F-X-RLL-01 · 02 · 04** 뿐이고 전부 `lineage.merge/split` 을 거친다. `lot_genealogy` 직접 INSERT 0(R8). 테스트 `@pytest.mark.fn("F-X-RLL-02")` 등 기능마다 하나 이상.
- 팩 라우터 3: `routers/prt.py` · `routers/clr.py` · `routers/rll.py` — 각 `router = APIRouter()`, 경로는 `nav.path_of("X-PRT-01")` 등.
