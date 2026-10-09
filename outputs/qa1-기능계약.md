# QA1 리포트 — 기능 · 계약 · 용어 (회전 8 재확인 · 2026-10-09)

> 담당 QA1. 회전 8 은 **재확인** — DEF-QA1-011 을 그 재현 절차 그대로 다시 돌리고, 검사기를 코어 단독 + 팩 3 으로 다시 돌리고, 회전 7 의 폼 422 입력값 유지 14곳을 `api-contract.md` §2 에 대조했다. **고치지 않았다** — 고친 것은 내 검사기 `src/mescore/tools/check_screens.py` 와 이 리포트뿐.
> 기준 커밋 **`d46d441`** (그 앞 `2f39590` 에서 gate-full 42/42 PASS · `outputs/gate-r8-final.txt`). DB `mes_qa_db`(쓰기 · `--reset-db`) · 팩은 `mes_<팩>_db` 읽기 · 호출만(422 · 403 · 404 · GET 만). 서버는 띄우지 않았다(TestClient — 포트 8051 안 씀).

## 회전 8 재확인

### R8-1. 결함 표

| ID | 등급 | 판정 | 고친 커밋 | 실측 (회전 8) | 검증 명령 |
|---|---|---|---|---|---|
| DEF-QA1-011 kimchi rename `품질이상` 에 terms 키 `이상` | 경미 | **해결** | `200b3dd` (기획자3 · D-516) · `4d351f0` (개발3 확인) | `packs/kimchi/pack.yaml:49` `qua: 품질 이슈 관리` — 최종 꼴(terms `이상: 품질 이슈` 를 쓴 꼴). 검사기 행 `G-P05 팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①)` **FAIL → PASS** `[kimchi] rename 값 10 · 키 든 값 0`. 화면 실측: kimchi 관리자 `/qua/issues` HTML 에 `품질 이슈 관리` 2곳 · `품질이상` 0. 화면 글 G-P05 도 PASS(화면 64 · 노출 0) | `MES_PACK=kimchi uv run python src/mescore/tools/check_screens.py` |

새 결함: **없음**.

- 지나간 것(결함 아님): 첫 코어 실행 중 `G-C23 코어 파일 금지어 0 (정적)` 이 한 번 FAIL(`src/mescore/tools/check_data.py:2019 \`숙성\``) — QA2 가 같은 시각 `check_data.py` 를 고치던 중의 작업본을 읽은 것. QA2 커밋 `d46d441` 뒤 다시 돌린 결과 `check_terms.py` · `check_screens` 모두 **파일 160 · 위반 0 PASS**. 남은 것 없음.
- 관찰(결함 아님 · 회전 7 범위 밖): 디자이너2 README 가 「되채우지 않는 것」으로 적은 폼 — SHP-02 · POP-01 · POP-04 · MAT-03(스캔칸뿐 · S-05 대로) · EQP-01 상태 · QUA-04 조치 · EQP-03 조치 · QUA-01 행 수정(행마다 반복되는 인라인 폼 — 값으로 어느 행인지 못 가름) · QUA-02 판정(대기 판정 여럿일 때). `api-contract.md` §2 는 예외를 적지 않았다 — **아키텍트가 §2 에 「행 인라인 폼 · 가를 수 없는 같은 이름 폼은 되채우지 않음」을 한 줄 적으면** 계약과 구현이 맞는다(제안).

**남은 수 — 치명 0 · 중대 0 · 경미 0** (QA1 결함 001~011 전부 해결).

### R8-2. 회전 7 — 폼 422 입력값 유지 14곳 계약 대조 (검사기 ⑦ `round7_echo` · 새 행 `G-C03 회전 7 계약`)

계약(`api-contract.md` §2 33행): 422 폼 POST → **303** → 원래 화면 + 알림 `values` → 폼이 `flash.values[이름]` 으로 다시 채움 · 비밀 칸은 싣지 않음 · JSON 422 는 `{code, message, fields}` 뿐. 스캔칸은 S-05(docs/design/README) 대로 비움.
각 곳마다 그 기능의 **입력 칸 역할**(권한 표에서 고름 · POP 화면은 `device=pop` 세션)로 틀린 값을 보내고 다섯 가지를 본다: ① 303 이 **보낸 화면 그대로**(쿼리까지) ② 보낸 값이 **그 폼의 칸**에 되채워짐(input value · select selected · radio checked) ③ 화면의 모든 `data-scan` 칸 · `password` 칸 값이 비어 있음 ④ 고유 표지값이 **그 폼 밖**(조회 조건 · 다른 폼 · 행 인라인 폼)에 없음 — 알림 자체(`<script id="flash-data">`)는 뺌 ⑤ 같은 본문의 JSON 호출이 422 이고 `values` 키 없음. 쓰기 없음(422 만). 코어 QA DB 에서만 전제 데이터(열린 실적 1 · 대기 판정 1건)를 정상 호출로 만든다.

| 곳 (README 표) | 역할 (코어) | 보낸 틀린 값 → 422 원인 | 되채움 확인 | 안 덮음 확인 | 코어 | kimchi | foodservice | printfilm |
|---|---|---|---|---|---|---|---|---|
| POP-03 투입 | FIELD · pop | 없는 LOT 바코드 + 투입량 3.25 | `qty` 3.25 (직전 저장값보다 앞섬) | 스캔칸 `barcode` 빈 값 · 보낸 바코드가 어느 input 값에도 없음 | PASS | PASS | PASS | PASS |
| POP-02 시작 | FIELD · pop | 없는 설비 id | 작업자 radio checked · 비고 | 표지값 시작 폼 밖 0 | PASS | PASS | PASS | PASS |
| POP-02 종료 | FIELD · pop | 양품 −12 | 양품 −12 · 불량 1 · `merge_lot_ids` · 측정값 `m_<key>` 7.25 (코어 `m_qa_req` · `m_qa_rng` / kimchi `m_pack_weight_kg`) | 폐기 `qty` · 정지 `note` · 합병 `lot_ids` 빈 값 | PASS | PASS | PASS | PASS |
| POP-02 정지 | FIELD · pop | 없는 정지 사유 코드 | 비고 | 종료 폼 `note` 안 덮음 | PASS | PASS | PASS | PASS |
| POP-02 폐기 | FIELD · pop | 수량 −3.5 | 폐기 수량 | 합병 `qty` · 종료 `good_qty` 안 덮음(이름 `qty` 겹침) | PASS | PASS | PASS | PASS |
| POP-02 분할 | FIELD · pop (종료 + 재고 생산 LOT 실적) | 분할 수 `x9` | 분할 수 · 분할 수량 | 표지값 분할 폼 밖 0 | PASS | PASS | PASS | PASS |
| POP-02 합병 | FIELD · pop (같은 실적) | 없는 LOT 번호 | 합병 LOT · 수량 4.75 | 폐기 `qty` 안 덮음 | PASS | PASS | PASS | PASS |
| MAT-01 입고 | FIELD · web | 수량 −5 | 품목(입고 선택지) · 수량 · 단위 · 비고 · 입고일 | 조회 조건 · 다른 폼에 표지값 0 | PASS | PASS | PASS | PASS |
| MAT-02 입고검사 | QA · pop | 판정 `QA1_NOPE` | 판정 폼 비고 (`lot_id` = 이 LOT) | 스캔칸 빈 값 | PASS | PASS | PASS | PASS |
| MAT-04 재고 조정 | FIELD · web | 수량 `abc` | 품목 · 수량 · 사유 | 조회 조건 안 덮음 | PASS | PASS | PASS | PASS |
| QUA-01 검사 계획 | QA · web | 유형 `QA1_NOPE` | 품목 · 항목 키 3줄(줄 번호대로) | 행 수정 인라인 폼에 표지값 0 | PASS | PASS | PASS | PASS |
| QUA-02 검사 결과 · 판정 | QA · web | 유형 · 판정 `QA1_NOPE` | 항목 저장 폼 비고 / 판정 폼 비고(대기 1건일 때) | 서로 안 덮음 | PASS · PASS | PASS · 대상 없음¹ | PASS · PASS | PASS · 대상 없음¹ |
| QUA-04 품질이상 | QA · web | 내용 비움 | 원인 · LOT · 발생 시각 | 조치 · 종결 인라인 폼 안 덮음 | PASS | PASS | PASS | PASS |
| EQP-02 점검 · EQP-03 고장 | FIELD · web | 점검 항목 · 증상 비움 | 설비 · 결과 · 점검자 · 비고 / 설비 · 발생 시각 | 조치 인라인 폼 안 덮음 | PASS · PASS | PASS · PASS | PASS · PASS | 숨김² |
| SHP-01 등록 · 수정 | FIELD · web (`?id=` 등록 상태 출하 — 두 폼 다 그려짐) | 없는 거래처 | 등록 폼 출하일 · 비고 / 수정 폼(`shipment_edit=1`) 출하일 · 비고 | 등록 ↔ 수정 서로 안 덮음 | PASS · PASS | PASS · PASS | PASS · PASS | PASS · PASS |
| SHP-04 성적서 | FIELD · web | 종류 `QA1_NOPE` | 출하 select (승인 출하) | 표지값 폼 밖 0 | PASS | PASS | PASS | PASS |

¹ 대기 판정이 정확히 1건인 LOT 이 그 팩 DB 에 없다(읽기 전용이라 만들지 않음 · README 의 설계 한계 — 여럿이면 되채우지 않는다). 코어 · foodservice 에서 확인.  ² printfilm 은 eqp 메뉴를 숨김(403 · G-C13 · G-C17 이 본다).
**JSON 422 에 입력값 없음**: 19 호출 모두 같은 본문의 JSON 호출이 422 · `values` 키 0 (계약 모양 `code · message · fields` 는 G-C03 응답 모양 행이 따로 본다). 비밀 칸: 이 14곳에 `password` 류 칸 없음 · 회전 5 행(`/sys/users`)이 그대로 PASS(비밀 값 화면 · 쿠키 0).

### R8-3. 검사기 원문 판정 줄 (`d46d441` + 이 회전 검사기)

코어 단독 — `MES_PACK= uv run python src/mescore/tools/check_screens.py --reset-db` (종료 0 · 소요 25s)
```
G-C02  기능 136 계약 호출 (정상 + 오류 계약)                                                 PASS  PASS 136/136 · FAIL 0 [] · 미검증 0 [] · 검사 677건 · DB mes_qa_db
G-C17  권한 칸 데이터 = core.yaml                                                      PASS  칸 48 (입력 19 · 조회 22 · 없음 7) · DB 불일치 0
G-C17  역할 × 기능 전부 (없음 · 조회 쓰기 403 · 입력 통과)                                       PASS  역할 4 ['ADMIN', 'FIELD', 'PROD', 'QA'] · 호출 522 (허용 281 · 거부 241) · 위반 0 []
G-C17  칸별 판정 (화면 GET + 기능)                                                       PASS  48/48 칸 PASS · FAIL []
G-C17  범위(scopes) 4종 — 입고검사 · 승인 · 지표 · 재전송                                      PASS  8 조합 · 어긋남 0 (호출 판정은 위 전수에 포함)
G-C03  화면 51 + 공통 200 · placeholder 0                                            PASS  200 54 · placeholder 0 · 문제 0
G-C03  응답 모양 · 인증 없는 경로 · 503 (api-contract §2)                                  PASS  검사 31 · 통과 못한 0 []
G-C02  회전 5 계약 — ?sort= (D-37) · JOB-02 ?wo= (D-604)                             PASS  검사 7 · 통과 못한 0 []
G-C03  회전 5 계약 — 422 입력값 유지 · POST /logout · /login/as · role_summary            PASS  검사 8 · 통과 못한 0 []
G-C03  회전 7 계약 — 폼 422 입력값 유지 14곳 (되채움 · 스캔칸 비움 · 다른 폼 안 덮음 · JSON 에 values 없음)  PASS  곳 19 · 통과 못한 0 []
G-C13  채널 밖 화면 403 (core.yaml: channels)                                         PASS  호출 155 · 위반 0 []
G-C23  화면 HTML 금지어 0 (DB · 시드 값 포함)                                              PASS  화면 60 · 금지어 44개 · 노출 0 []
G-C23  코어 파일 금지어 0 (정적)                                                          PASS  파일 160 · 위반 0 []
G-C23  날것 중립어 0 — 용어 표지 치환 후 화면 글 (t() 누락)                                       PASS  화면 60 · 표지 뒤에도 남은 곳 0 [] · (정적 템플릿 스캔 0)
```

팩 3 — `MES_PACK=<팩> uv run python src/mescore/tools/check_screens.py` (종료 0 · 3팩 모두 · G-C02 · G-C17 · G-C13 · 회전 7 · G-P05 행만 · 나머지 G-C03 · 회전 5 행도 전부 PASS · G-C23 팩 배포 화면 금지어는 참고 WARN — 팩 용어)
```
G-C02  기능 156 계약 호출 (정상 + 오류 계약)                                                 PASS  [kimchi] PASS 156/156 · FAIL 0 [] · 미검증 0 [] · 검사 314건 · DB mes_kimchi_db
G-C02  팩 기능 F-X 읽기 · 호출                                                          PASS  [kimchi] 팩 기능 24 · 통과 못한 0 []
G-C17  칸별 판정 (화면 GET + 기능)                                                       PASS  [kimchi] 108/108 칸 PASS · FAIL []
G-C02  회전 5 계약 — ?sort= (D-37) · JOB-02 ?wo= (D-604)                             PASS  [kimchi] 검사 7 · 통과 못한 0 []
G-C03  회전 7 계약 — 폼 422 입력값 유지 14곳 (되채움 · 스캔칸 비움 · 다른 폼 안 덮음 · JSON 에 values 없음)  PASS  [kimchi] 곳 19 · 통과 못한 0 []
G-C13  채널 밖 화면 403 (core.yaml: channels)                                         PASS  [kimchi] 호출 179 · 위반 0 []
G-P05  팩 용어 — JSON 오류 message · fields.label 치환                                  PASS  [kimchi] 오류 응답 91 · 치환 안 된 0 []
G-P05  팩 용어 — 치환 안 된 terms 키 노출 0 (화면 글)                                         PASS  [kimchi] 화면 64 · 바뀌는 키 12 · 노출 0 []
G-P05  팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①)                          PASS  [kimchi] rename 값 10 · 키 든 값 0 []
G-C02  기능 132 계약 호출 (정상 + 오류 계약)                                                 PASS  [foodservice] PASS 132/132 · FAIL 0 [] · 미검증 0 [] · 검사 265건 · DB mes_foodservice_db
G-C17  칸별 판정 (화면 GET + 기능)                                                       PASS  [foodservice] 72/72 칸 PASS · FAIL []
G-C02  회전 5 계약 — ?sort= (D-37) · JOB-02 ?wo= (D-604)                             PASS  [foodservice] 검사 7 · 통과 못한 0 []
G-C03  회전 7 계약 — 폼 422 입력값 유지 14곳 (되채움 · 스캔칸 비움 · 다른 폼 안 덮음 · JSON 에 values 없음)  PASS  [foodservice] 곳 19 · 통과 못한 0 []
G-C13  채널 밖 화면 403 (core.yaml: channels)                                         PASS  [foodservice] 호출 155 · 위반 0 []
G-P05  팩 용어 — JSON 오류 message · fields.label 치환                                  PASS  [foodservice] 오류 응답 76 · 치환 안 된 0 []
G-P05  팩 용어 — 치환 안 된 terms 키 노출 0 (화면 글)                                         PASS  [foodservice] 화면 56 · 바뀌는 키 16 · 노출 0 []
G-P05  팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①)                          PASS  [foodservice] rename 값 12 · 키 든 값 0 []
G-C02  기능 156 계약 호출 (정상 + 오류 계약)                                                 PASS  [printfilm] PASS 156/156 · FAIL 0 [] · 미검증 0 [] · 검사 314건 · DB mes_printfilm_db
G-C02  팩 기능 F-X 읽기 · 호출                                                          PASS  [printfilm] 팩 기능 24 · 통과 못한 0 []
G-C17  칸별 판정 (화면 GET + 기능)                                                       PASS  [printfilm] 60/60 칸 PASS · FAIL []
G-C02  회전 5 계약 — ?sort= (D-37) · JOB-02 ?wo= (D-604)                             PASS  [printfilm] 검사 7 · 통과 못한 0 []
G-C03  회전 7 계약 — 폼 422 입력값 유지 14곳 (되채움 · 스캔칸 비움 · 다른 폼 안 덮음 · JSON 에 values 없음)  PASS  [printfilm] 곳 17 · 통과 못한 0 []
G-C13  채널 밖 화면 403 (core.yaml: channels)                                         PASS  [printfilm] 호출 164 · 위반 0 []
G-P05  팩 용어 — JSON 오류 message · fields.label 치환                                  PASS  [printfilm] 오류 응답 88 · 치환 안 된 0 []
G-P05  팩 용어 — 치환 안 된 terms 키 노출 0 (화면 글)                                         PASS  [printfilm] 화면 59 · 바뀌는 키 9 · 노출 0 []
G-P05  팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①)                          PASS  [printfilm] rename 값 10 · 키 든 값 0 []
```

- 기능 136 **136/136** · 팩 기능 F-X kimchi 24 · printfilm 24 통과(foodservice 는 팩 기능 선언 없음 — 행 없음) · 권한 48칸(코어) · kimchi 108 · foodservice 72 · printfilm 60 칸 전부 PASS · 채널 위반 0 · G-P05 3팩 × 3행 PASS · rename 값 검사 3팩 PASS.
- `make gate` 영향: 새 행은 `G-C03` 이라 `gate.per_gate` 가 읽는 G-C03 판정(나쁜 쪽 우선)에 들어간다 — 지금 PASS. `check_screens.py` 는 `outputs/core.sha256` 대상이므로 **아키텍트가 `make core-hash` 를 다시 찍어야** 코어 무변경 검사가 이 수정을 코어 변경으로 세지 않는다.

### R8-4. 이 회전에 검사기에서 바꾼 것 (`check_screens.py`)
- ⑦ `round7_echo()` 새로 — 회전 7 폼 422 입력값 유지 14곳(19 검사). 도우미 `_forms` · `_form_of` · `_val`(input · textarea · select · radio) · `_scan_values`. 역할은 `rbac.can_do` 로 그 기능의 입력 역할을 고른다(코어 ADMIN 은 mat · pop · qua · eqp 가 조회라 403 — 하드코딩하지 않음). 전제 데이터가 없으면 `미검증` 으로 FAIL(조용히 넘기지 않음) · 코어 QA DB 에서만 정상 호출로 전제(열린 실적 · 대기 판정 1건)를 만든다. 팩에서는 쓰기 없음.
- 출력 행 `G-C03  회전 7 계약 — 폼 422 입력값 유지 14곳 (…)` · `--json` 의 `shapes` 에 19 행 포함.

---

# (회전 6 원문) QA1 리포트 — 기능 · 계약 · 용어 (회전 6 재판정 · 2026-10-09)


> 담당 QA1. 회전 6 은 **재판정** — 회전 4 결함 10건을 그 재현 절차 그대로 다시 돌리고, 코어 단독 + 팩 3 으로 검사기를 다시 돌리고, 회전 5 새 기능을 계약에 대조했다. **고치지 않았다** — 고친 것은 내 검사기 `src/mescore/tools/check_screens.py` 와 이 리포트뿐.
> 기준 커밋 **`967021f`** (gate-full 42/42 PASS · `outputs/gate-r5-final.txt`). DB `mes_qa_db`(쓰기) · 팩은 `mes_<팩>_db` 읽기 · 호출만 · 서버 포트 8051(재현 때만 띄우고 내렸다).

## 회전 6 재판정

### R6-1. 결함 표 (회전 4 의 10건 + 새 1건)

| ID | 등급(회전 4) | 판정 | 고친 커밋 | 실측 (회전 6) | 검증 명령 |
|---|---|---|---|---|---|
| DEF-QA1-001 `POST /login/as` 비밀번호 없는 로그인 | 중대 | **해결** | `de9feba` · `f6afe88` · `02d6d16` | 8051 서버(.env `MES_ENV=dev`): 루프백 `curl localhost` → 200 · 그 세션 `/sys/users` 200 (**D-605 확정 · api-contract §2 44행이 허용한 조합**) / 같은 서버를 LAN 주소 `192.168.219.101` 로 → **404** · `/sys/users` 401 / `MES_ENV=prod` → 루프백도 **404**. `MES_ENV=` (빈 값) → `prod`. TestClient 6조합(dev×127.0.0.1 · ::1 = 200 · dev×10.1.2.3 · dev×`testclient` · prod · 빈 값 = 404) 전부 계약대로 · 로그인 화면 개발용 버튼도 같은 조건 | `MES_ENV=dev\|prod … uvicorn … --host 0.0.0.0 --port 8051` → `curl -X POST <주소>:8051/login/as -d role=ADMIN` · `check_screens` ⑥ |
| DEF-QA1-002 `check_terms --pack` 거짓 PASS | 중대 | **해결** | `b2761d4` | `scan_pack` 이 화면 글 조각 · 키마다 판정(`exposed_keys`) — 덮어쓰기 버그 없음. 3팩 `check_terms --pack` PASS 와 `check_screens` G-P05(화면 글) PASS 가 일치(kimchi 64 · foodservice 56 · printfilm 59 화면 노출 0). 단 두 도구 모두 rename 값을 통째로 빼므로 rename 값 안의 키는 못 본다 → 새 행으로 보강(R6-3 · DEF-QA1-011) | `MES_PACK=<팩> uv run python src/mescore/tools/check_terms.py --pack` |
| DEF-QA1-003 G-P05 FAIL 3팩 (rename · attrs 라벨) | 중대 | **부분** | `9dda6ac` · `8e5710c`(printfilm) · `c547a59`(foodservice) · `3c01d38`(kimchi) | 화면 글 노출 **3팩 0** (회전 4: printfilm 180 · foodservice 61 · kimchi 1) · attrs 라벨 `t()` 정상(`설비구분` · `조리공정구분` 사라짐). printfilm rename `Job 관리` · `작업 실적 (POP)` · `작업 실적 현황` · foodservice `조리 실적 (POP)` 최종 꼴. **남은 것**: kimchi `menus.rename.qua = 품질이상` 이 terms 키 `이상`(→`품질 이슈`)을 담는다 — D-38 ① 위반, 사이드바 64 화면 전부 → **DEF-QA1-011 로 분리** | `MES_PACK=<팩> uv run python src/mescore/tools/check_screens.py` |
| DEF-QA1-004 숫자 아닌 경로 키 422 | 경미 | **해결** | `e484766` | 기능 136 **136/136 PASS**(회전 4: 115 · FAIL 21) · 8051 서버 관리자 `POST /ord/orders/abc` → **404** `{"code":"not_found"}` · `GET /mat/lots/abc/label` → 404. 팩 3 도 FAIL 0 (kimchi F-X-AGE-04 포함) | `check_screens --reset-db` · `curl -b jar -X POST localhost:8051/ord/orders/abc` |
| DEF-QA1-005 채널 배지 `현황판` t() 누락 | 경미 | **해결** | `d7f91b6` · `02d6d16` · `9de6316` | 용어 표지 치환 뒤 화면 60 날것 중립어 **0** (회전 4: 58 화면 `현황판`) · 정적 템플릿 스캔 0 · `check_terms` `템플릿 t() 누락 0 PASS` | `check_screens` ③ · `uv run python src/mescore/tools/check_terms.py` |
| DEF-QA1-006 코어 금지어 (QA 도구) | 중대 | **해결** | (QA2 `5d9c581` · QA3 `f5a19b7` 상태) | `check_terms.py` → `G-C23 코어 금지어 0 PASS 파일 160 · 위반 0` · check_screens 정적 행도 0 | `uv run python src/mescore/tools/check_terms.py` |
| DEF-QA1-007 F-SHP-07 코어 단독 ERP 큐 0 | 경미 | **해결** | `2d051e5` (D-39) | 승인 전후 `ifc_outbox` **1 → 2**, 마지막 행 `shipment_approved · 대기`. 검사기의 메모를 **검사 항목으로 올렸다**(F-SHP-07 9 항목 PASS) | `check_screens --reset-db` (F-SHP-07) · `psql -d mes_qa_db -c "select event,status,count(*) from ifc_outbox group by 1,2"` |
| DEF-QA1-008 `make db-schema` 가 DSN 무시 | 중대 | **해결** | `14bd28f` | `MES_PG_DSN=postgresql:///mes_qa_db make -n db-schema` → `db-schema → mes_qa_db (drop schema public cascade)` · `psql -d "dbname=mes_qa_db …"` — `mes_core_db` 안 건드림. `db-create` · `backup` 도 같은 DB | `MES_PG_DSN=postgresql:///mes_qa_db make -n db-schema db-create backup` |
| DEF-QA1-009 printfilm 지표 정의 쓸 역할 0 | 경미 | **해결** | `8e5710c` | `packs/printfilm/seed/permissions.csv:46` `kpi,ADMIN,입력,지표` · `check_screens` printfilm G-C17 60/60 칸 · DB = 병합본 | `MES_PACK=printfilm … check_screens.py` |
| DEF-QA1-010 gate 가 QA1 의 G-C13 · G-C23 · 팩 G-P05 를 안 읽음 | 경미 | **해결** | `b2761d4` | `gate.py:623` `check_screens` → G-C02 · G-C03 · G-C13 · G-C17 · G-C23 (나쁜 쪽 우선) · `gate.py:700` 팩 G-P05 를 `check_screens` 행과 합침. 남은 틈: 팩 게이트는 check_screens 의 **G-P05 만** 읽는다(팩 G-C02 · G-C03 행은 판정표에 안 들어감 — 지금 모두 PASS라 영향 없음 · 참고) | `grep -n check_screens src/mescore/tools/gate.py` |
| **DEF-QA1-011 (새)** kimchi rename `품질이상` 에 terms 키 `이상` | **경미** | **미해결(새)** | — | `packs/kimchi/pack.yaml:49` `qua: 품질이상` · `:32` `이상: 품질 이슈`. rename 값은 `t()` 를 거치지 않으므로(D-38 ①) 사이드바 · 메뉴 이름에 `이상` 이 그대로 — 다른 화면은 `품질 이슈`. 회전 4 에 없던 값(`3c01d38` 개발3 「rename.qua 품질이상」). 화면 글 G-P05 는 rename 값을 빼서(아키텍트 `0fdfde7`) 이것을 못 봤다 | `MES_PACK=kimchi uv run python src/mescore/tools/check_screens.py` → `G-P05 팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①) FAIL [kimchi] rename 값 10 · 키 든 값 1 ['`품질이상` 에 `이상`(→`품질 이슈`)']` |

- **기대(DEF-QA1-011)**: D-38 ① "rename 값은 terms 키를 담지 않게 **최종 꼴로** 쓴다" — kimchi 는 치환어를 쓴 최종 꼴(예: `품질 이슈`)로 쓰거나, 아키텍트가 D-38(가설)에 "붙여 쓴 합성어는 예외" 를 적는다. 담당: 개발3(kimchi `pack.yaml`) · 아키텍트(D-38 판정).

**남은 수 — 치명 0 · 중대 0 · 경미 1** (DEF-QA1-011). 회전 4 결함 10건: 해결 9 · 부분 1(003 — 남은 몫을 011 로 분리).

### R6-2. 아키텍트의 검사기 수정 2곳 검토 (`git show 0fdfde7 e3819c5 -- src/mescore/tools/check_screens.py`)

| 커밋 | 바꾼 것 | 계약 대조 | 결론 |
|---|---|---|---|
| `e3819c5` G-C03 | 인증 없는 경로 전수에서 `POST /login/as → 404` 를 위반으로 세지 않음 | `api-contract.md` §2 44행 · D-605(확정): dev + 루프백 아니면 **404**(경로 없음) — 인증 없이 "열리는" 경로가 아니다. 404 **만** 면제하고 200 · 422 등은 여전히 위반으로 센다. 비밀번호 없는 로그인 행(`/login/as` 200 → `/sys/users` 200 이면 FAIL)도 그대로 | **유지** — 기대값을 낮추지 않았다. 다만 TestClient 기본 주소(`testclient`)만 보던 것을 보강: dev/prod/빈 값 × 루프백(127.0.0.1 · ::1)/비루프백 6조합과 로그인 화면 버튼을 따로 검사(R6-3) |
| `0fdfde7` 팩 G-P05 | 화면 글에서 terms 값과 함께 `pack.verbatim`(= `menus.rename` 값)도 지운 뒤 키를 찾음 | D-38 ③(판정 단위) · `check_terms --pack` 과 같은 규칙이라 화면 글 판정으로는 맞다. 그러나 D-38 ① 은 "rename 값은 terms 키를 담지 않게 최종 꼴로" 를 **요구**한다 — 이 면제만 두면 rename 값 안의 날것 키(회전 4 printfilm `작업지시 관리` 같은 것)가 통째로 사라진다. 실제로 kimchi `품질이상` 이 이 면제로 가려졌다 | **기대값을 낮춘 부분이 있다** → 면제는 두되(같은 노출을 64 번 세지 않게) **rename 값 자체를 검사하는 행을 새로 넣어 기대값을 되돌렸다**: `G-P05 팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①)`. 코드 `rename_values_terms()` |

### R6-3. 회전 5 새 기능 — 계약 대조 (검사기 ⑥ `round5_contracts` · 코어 + 팩 3 모두 PASS)

| 기능 | 계약 | 실측 (코어 `mes_qa_db`) |
|---|---|---|
| `?sort=` 정렬 | D-37 · interfaces §8 `http.sort_clause` — 허용 열만 · 모르는 열 422 · 비면 기본 | `sort` 를 받는 목록 **17** (BAS 마스터 8 · BOM · JOB-01 · MAT 입고 · LOT · QUA 검사 · 이상 · EQP 점검 · 고장 · SYS-01) — 라우트가 `sort` 를 선언한 것 전부 포함. 모르는 열 → **422** `fields[name=sort]` (사유에 공개 이름만 · SQL 식 없음). 허용 열 오름 · 내림 · 여럿 · SQL 조각(`x;drop table x` · `x desc` · `(select 1)` · `1`) **305 호출 어긋남 0**. 브라우저 GET → 422 오류 화면(api-contract §2). SYS-01 `login_id` 오름/내림 실제 순서 일치. printfilm 은 숨긴 eqp 2 목록 제외(403) |
| JOB-02 `?wo=` 드릴다운 | D-604 확정 — id 또는 지시 번호 · 없으면 404 · 실적별 측정값 | `?wo=5` 와 `?wo=W-EX-0001` → 같은 지시 · 실적 2 = DB 2 · 실적마다 `measures`. 없는 번호 · `999999999` → **404 · 404**. 측정값 4(이탈 1 표시 · 기록 없는 선언 키 `미수집` 1). 팩 3(팩 접두 번호) 도 PASS |
| 422 입력값 유지 | api-contract §2 — 303 + 알림 `values` · 비밀 칸은 싣지 않음 · JSON 422 에는 없음 | `POST /sys/users`(없는 역할) 브라우저 → 303 → 폼에 `login_id` · 이름 다시 채움 · **`<input type="password" name="password" value="">`** · 비밀 값은 화면 · Set-Cookie 어디에도 없음 · 다음 GET 에는 사라짐(알림 한 번) · JSON 422 키 `code fields message` 뿐 · 행 생성 0 |
| `POST /logout` 전용 | api-contract §2 — GET 405 | `GET /logout` **405** (세션 유지 200) · `POST /logout` 303 `/login` → 그 세션 **401**. 8051 서버 `curl localhost:8051/logout` → 405 |
| 로그인 `dev_login` · `role_summary` | D-605 · api-contract §2 · 세션 쿠키 | 개발용 역할 버튼은 dev + 루프백일 때만(6조합 일치) · prod 로 만든 앱의 세션 쿠키 `httponly; samesite=lax; secure` · `role_summary` = DB 역할 × 입력 칸 메뉴 그대로(어긋남 0) · 비밀번호 · `password` 글자 없음 |

### R6-4. 검사기 원문 판정 줄 (`967021f` + 이 회전 검사기 · 소요 코어 23s)

코어 단독 — `MES_PACK= uv run python src/mescore/tools/check_screens.py --reset-db` (종료 0)
```
G-C02  기능 136 계약 호출 (정상 + 오류 계약)                                       PASS  PASS 136/136 · FAIL 0 [] · 미검증 0 [] · 검사 677건 · DB mes_qa_db
G-C17  권한 칸 데이터 = core.yaml                                            PASS  칸 48 (입력 19 · 조회 22 · 없음 7) · DB 불일치 0
G-C17  역할 × 기능 전부 (없음 · 조회 쓰기 403 · 입력 통과)                             PASS  역할 4 ['ADMIN', 'FIELD', 'PROD', 'QA'] · 호출 522 (허용 281 · 거부 241) · 위반 0 []
G-C17  칸별 판정 (화면 GET + 기능)                                             PASS  48/48 칸 PASS · FAIL []
G-C17  범위(scopes) 4종 — 입고검사 · 승인 · 지표 · 재전송                            PASS  8 조합 · 어긋남 0 (호출 판정은 위 전수에 포함)
G-C03  화면 51 + 공통 200 · placeholder 0                                  PASS  200 54 · placeholder 0 · 문제 0
G-C03  응답 모양 · 인증 없는 경로 · 503 (api-contract §2)                        PASS  검사 31 · 통과 못한 0 []
G-C02  회전 5 계약 — ?sort= (D-37) · JOB-02 ?wo= (D-604)                   PASS  검사 7 · 통과 못한 0 []
G-C03  회전 5 계약 — 422 입력값 유지 · POST /logout · /login/as · role_summary  PASS  검사 8 · 통과 못한 0 []
G-C13  채널 밖 화면 403 (core.yaml: channels)                               PASS  호출 155 · 위반 0 []
G-C23  화면 HTML 금지어 0 (DB · 시드 값 포함)                                    PASS  화면 60 · 금지어 44개 · 노출 0 []
G-C23  코어 파일 금지어 0 (정적)                                                PASS  파일 160 · 위반 0 []
G-C23  날것 중립어 0 — 용어 표지 치환 후 화면 글 (t() 누락)                             PASS  화면 60 · 표지 뒤에도 남은 곳 0 [] · (정적 템플릿 스캔 0)
```

팩 3 — `MES_PACK=<팩> uv run python src/mescore/tools/check_screens.py` (G-P05 · 회전 5 · 응답 모양 행만 · 나머지 G-C02 · G-C17 · G-C13 전부 PASS — kimchi 156/156 · 108칸 · foodservice 132/132 · 72칸 · printfilm 156/156 · 60칸)
```
G-C03  응답 모양 · 인증 없는 경로 · 503 (api-contract §2)                        PASS  [kimchi] 검사 27 · 통과 못한 0 []
G-C02  회전 5 계약 — ?sort= (D-37) · JOB-02 ?wo= (D-604)                   PASS  [kimchi] 검사 7 · 통과 못한 0 []
G-C03  회전 5 계약 — 422 입력값 유지 · POST /logout · /login/as · role_summary  PASS  [kimchi] 검사 8 · 통과 못한 0 []
G-P05  팩 용어 — JSON 오류 message · fields.label 치환                        PASS  [kimchi] 오류 응답 91 · 치환 안 된 0 []
G-P05  팩 용어 — 치환 안 된 terms 키 노출 0 (화면 글)                               PASS  [kimchi] 화면 64 · 바뀌는 키 12 · 노출 0 []
G-P05  팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①)                FAIL  [kimchi] rename 값 10 · 키 든 값 1 ['`품질이상` 에 `이상`(→`품질 이슈`)']
G-C03  응답 모양 · 인증 없는 경로 · 503 (api-contract §2)                        PASS  [foodservice] 검사 27 · 통과 못한 0 []
G-C02  회전 5 계약 — ?sort= (D-37) · JOB-02 ?wo= (D-604)                   PASS  [foodservice] 검사 7 · 통과 못한 0 []
G-C03  회전 5 계약 — 422 입력값 유지 · POST /logout · /login/as · role_summary  PASS  [foodservice] 검사 8 · 통과 못한 0 []
G-P05  팩 용어 — JSON 오류 message · fields.label 치환                        PASS  [foodservice] 오류 응답 76 · 치환 안 된 0 []
G-P05  팩 용어 — 치환 안 된 terms 키 노출 0 (화면 글)                               PASS  [foodservice] 화면 56 · 바뀌는 키 16 · 노출 0 []
G-P05  팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①)                PASS  [foodservice] rename 값 12 · 키 든 값 0 []
G-C03  응답 모양 · 인증 없는 경로 · 503 (api-contract §2)                        PASS  [printfilm] 검사 27 · 통과 못한 0 []
G-C02  회전 5 계약 — ?sort= (D-37) · JOB-02 ?wo= (D-604)                   PASS  [printfilm] 검사 7 · 통과 못한 0 []
G-C03  회전 5 계약 — 422 입력값 유지 · POST /logout · /login/as · role_summary  PASS  [printfilm] 검사 8 · 통과 못한 0 []
G-P05  팩 용어 — JSON 오류 message · fields.label 치환                        PASS  [printfilm] 오류 응답 88 · 치환 안 된 0 []
G-P05  팩 용어 — 치환 안 된 terms 키 노출 0 (화면 글)                               PASS  [printfilm] 화면 59 · 바뀌는 키 9 · 노출 0 []
G-P05  팩 용어 — menus.rename 값에 치환 안 된 terms 키 0 (D-38 ①)                PASS  [printfilm] rename 값 10 · 키 든 값 0 []
```

`gate.per_gate` 로 읽은 값: 코어 G-C02 · G-C03 · G-C13 · G-C17 · G-C23 **PASS** / kimchi **G-P05 FAIL**(DEF-QA1-011) · G-C23 WARN(팩 용어 참고) / foodservice · printfilm G-P05 **PASS**.
→ 다음 `make gate-full` 은 kimchi G-P05 가 FAIL 로 바뀐다(검사기가 기대값을 되돌린 결과 · 의도). 또 `check_screens.py` 는 `outputs/core.sha256` 대상이라 **아키텍트가 `make core-hash` 를 다시 찍어야** 코어 무변경 검사가 이 수정을 코어 변경으로 세지 않는다.

### R6-5. 이 회전에 검사기에서 바꾼 것 (`check_screens.py`)
- F-SHP-07: `ifc_outbox` 메모 → 검사 항목(승인 뒤 `shipment_approved · 대기` 1행 · D-39).
- 팩 G-P05: `rename_values_terms()` — rename 값 안의 terms 키(D-38 ①) 새 행. 아키텍트의 화면 글 면제는 주석에 검토 결과를 적고 유지.
- ⑥ `round5_contracts()` — `?sort=` · JOB-02 `?wo=` · 422 입력값 유지 · `POST /logout` · `/login/as` 6조합 · prod 세션 쿠키 · `role_summary` (G-C02 · G-C03 행 1개씩 · 쓰기 없음 · 팩에서도 돈다). `MES_ENV` 는 바꿨다가 원래 값으로 되돌린다.
- G-C03 `/login/as` 404 면제는 검토 주석만 더함.

---

# (회전 4 원문) QA1 리포트 — 기능 · 계약 · 용어 (회전 4 · 2026-10-09)

> 담당 QA1 (`goal.md` §3.3). 범위: G-C01~G-C03 · 기능 136 의 1:1 · §2.5 오류 계약 · G-C17 48칸 전수 · G-C23 금지어 전수 · G-P05.
> **고치지 않았다 — 결함만 적는다.** 기대값은 `contracts/function-list.md` · `contracts/api-contract.md` · `src/mescore/core.yaml` · 팩 `pack.yaml`/`gates.yaml` 에서만 끌어왔다.
> 검사기: `src/mescore/tools/check_screens.py` (gate 가 부른다 · 출력 `G-nn  항목  PASS|FAIL|WARN|미검증  실측`).

## 0. 판정 요약

| 범위 | 결과 | 검증 명령 |
|---|---|---|
| 기능 136 (코어 132 + 배치 4) | **PASS 115 · FAIL 21 · 미검증 0** — FAIL 21 은 전부 같은 원인(숫자 아닌 경로 키 → 422, 계약은 404 · DEF-QA1-004). 그 밖 계약 문장 · 오류 계약 676 건 통과 | `MES_PACK= uv run python src/mescore/tools/check_screens.py --reset-db` |
| G-C17 권한 48칸 | **48/48 PASS** — DB = core.yaml (입력 19 · 조회 22 · 없음 7) · 역할 4 × 기능 전부 522 호출(허용 281 · 거부 241) 위반 0 · 범위 4종 8 조합 어긋남 0 | 〃 |
| G-C03 화면 · 응답 모양 | 화면 54 (코어 51 + 공통 3) 200 · placeholder 0 **PASS** / 응답 모양 31 검사 중 **FAIL 2** — 인증 없이 열리는 `POST /login/as` (DEF-QA1-001) | 〃 |
| 채널(⑤) | 채널 밖 화면 403 — 155 호출 위반 0 **PASS** (세션 device=pop 포함) | 〃 |
| G-C23 용어 | 화면 HTML 60 금지어 노출 0 **PASS** · 코어 파일 정적 **FAIL** (전부 QA 검사 도구 — QA2 `check_data.py` 4 → 재측정 시 QA3 `check_security.py` 1 · DEF-QA1-006) · 날것 중립어 **FAIL** — 채널 배지 `현황판` (DEF-QA1-005) | 〃 |
| 팩 3 (읽기 · 호출만) | G-C17 3팩 **PASS**(kimchi 108칸 · foodservice 72칸 · printfilm 60칸) · 채널 **PASS** · **G-P05 FAIL 3팩**(DEF-QA1-003) · `check_terms --pack` 은 3팩 거짓 PASS (DEF-QA1-002) | `MES_PACK=<팩> uv run python src/mescore/tools/check_screens.py` |

결함 **10건** — 치명 0 · **중대 5**(001 · 002 · 003 · 006 · 008) · 경미 5(004 · 005 · 007 · 009 · 010). 담당(공동 포함): 아키텍트 001 · 002 · 003 · 007 · 008 · 010 / 개발1 001 · 003(foodservice) / 개발2 004 · 003(printfilm) · 009 / 개발3 004 · 007 · 003(kimchi) / 디자이너1 005 / QA2 · QA3 006.

## 1. 실행 환경 · 방법

- **전용 DB `mes_qa_db`** — 쓰기 검사는 여기서만. 스키마 · 코어 시드 · 개발 시드는 `psql -f schema.sql · views.sql` + `MES_PACK= MES_PG_DSN=postgresql:///mes_qa_db uv run python -m mescore.db.seed_core` 로 올렸다(검사기 `--reset-db` 가 같은 일을 한다 — DB 이름에 `qa` 가 없으면 거부).
  **`make db-schema` 는 쓰지 않았다** — `MES_PG_DSN` 을 무시하고 `mes_core_db` 를 지운다(DEF-QA1-008 · `make -n` 으로 확인). `make db-seed` 는 `MES_PG_DSN` 을 존중한다(seed_core → `conn.dsn()`).
- 검사기는 코어 단독(MES_PACK 비움)이면 **`MES_QA_DSN` 또는 `postgresql:///mes_qa_db`** 에 붙는다 — gate 가 불러도 `mes_core_db` 에 쓰지 않는다. 팩은 `mes_<팩>_db` 에 **읽기 · 호출만**(정상 쓰기 호출 없음 · 401/403/404/422 만 · F-MAT-10 · F-SYS-13 · F-SYS-15 는 빈 폼으로도 쓰기가 일어나 호출 생략).
- 비밀번호는 `.env` 의 `MES_SEED_PASSWORD` 로만(값을 어디에도 적지 않았다). 새로 만든 QA 사용자 비밀번호는 실행마다 난수.
- 서버 포트 **8051** — DEF-QA1-001 재현에만 띄웠다가 내렸다(`uvicorn … --port 8051`, `MES_PG_DSN=postgresql:///mes_qa_db`).
- 흐름: 기준정보 9 화면 등록 · 수정 · 삭제 → 수주 → 생산계획 → 확정 → 작업지시 → 입고(원재료 LOT 3: 합격 · 불합격 · 미검사) → 입고검사 → POP 시작 · 투입 · 정지 · 종료(측정값 필수 1 · 범위 1) · 폐기 → 마감 → 검사 계획 · 결과 · 판정 · 이상/시정 → 설비 → 출하 등록 · 스캔 · 취소 · 승인 · 성적서 → 추적 → KPI → 시스템(역할 · 사용자 · 권한 칸 · 중지 · 비밀번호 재설정 · 채번 · 백업/복구 확인 · 이관) → 수집 수신 · ERP 재전송. 기능마다 정상 + 오류 계약(필수 누락 · 중복 · 경로 키 404(큰 숫자 · 숫자 아님) · 스캔 번호 422 JSON/HTML 재렌더 · 미로그인 401 · 권한 403 · 501) + 계약 문장의 422 조건.

## 2. 결함 (치명 · 중대 먼저)

### DEF-QA1-001 · 중대 · 비밀번호 없이 관리자로 로그인되는 `POST /login/as` (인증 없이 열리는 경로 계약 위반)
- **재현**: 서버 `MES_PG_DSN=postgresql:///mes_qa_db uv run uvicorn mescore.app.main:app --app-dir src --port 8051` →
  `curl -c jar -X POST localhost:8051/login/as -d role=ADMIN` → `{"ok":true,"login_id":"admin","role_code":"ADMIN",…}` → `curl -b jar localhost:8051/sys/users` → **200**.
  TestClient 도 같다(`check_screens` ④ — 4 배포 전부: 코어 · kimchi · foodservice · printfilm).
- **실측**: 인증 없이 열리는 라우트 139(팩 163) 전수 중 계약 밖 1 — `POST /login/as`. 역할 코드만 주면 시드 계정으로 세션이 열린다(D-605 · `routers/home.py`). `MES_ENV` 가 없으면 `settings.py` 기본값이 **`dev`** 라 운영에서도 켜진다.
- **기대**: `api-contract.md` §2 — 인증 없이 열리는 것은 `/health` · `/static/*` · `/login` · `/error` · `POST /ifc/collect` 뿐. 비밀번호 없는 로그인 경로 0.
- **담당**: 개발1(`routers/home.py` · D-605) + 아키텍트(`settings.py` 의 `MES_ENV` 기본값 · `api-contract.md` 목록 · D-605 를 `가설` 에서 판정). QA3(보안) 공유.

### DEF-QA1-002 · 중대 · `check_terms.py --pack`(G-P05) 이 거짓 PASS — gate 의 팩 G-P05 판정이 믿을 수 없다
- **재현**: `MES_PACK=printfilm uv run python src/mescore/tools/check_terms.py --pack` → `PASS … 치환 안 된 노출 0` (foodservice · kimchi 도 PASS). 같은 DB 에서 `MES_PACK=printfilm uv run python src/mescore/tools/check_screens.py` → G-P05 **노출 180**(foodservice 61 · kimchi 1).
- **원인(코드 읽기)**: `scan_pack()` 에서 `plain = re.sub(r"<[^>]*>", …)` 바로 다음 줄이 `plain = re.sub(r"<code>.*?</code>", " ", resp.text)` 로 **덮어써** 태그 제거가 사라지고, 판정 조건 `k in plain and terms[k] not in plain` 은 그 화면 어딘가에 치환어가 한 번이라도 있으면(예: 메뉴 `Job`) 같은 화면의 날것 키(`작업지시 관리`)를 통과시킨다.
- **기대**: G-P05 — 화면 · 메뉴 · 라벨에 terms 키가 치환되지 않은 채 노출 0. 키 하나하나의 노출 위치로 판정.
- **담당**: 아키텍트(`check_terms.py` · `gate.py pack_gates` 는 G-P05 를 check_terms 에서만 읽는다 — check_screens 의 팩 G-P05 행도 읽게 하는 것을 함께 제안).

### DEF-QA1-003 · 중대 · G-P05 FAIL 3팩 — 팩 메뉴 이름(`menus.rename`) · 팩 속성 라벨이 `t()` 를 거치지 않아 terms 키가 그대로 보인다
- **재현**: `MES_PACK=<팩> uv run python src/mescore/tools/check_screens.py` → `G-P05 팩 용어 — 치환 안 된 terms 키 노출 0 (화면 글) FAIL`.
- **실측** (표 본문 · 선택지 · 숫자/`(예시)` 가 든 DB 값은 뺀 화면 글):
  - printfilm — 사이드바 **57 화면 전부** `작업지시 관리`(작업지시→Job) · `실적 현황` · `생산 실적 (POP)`(실적→작업 실적) — `pack.yaml: menus.rename` 값이 그대로 렌더.
  - foodservice — 54 화면 `실적 (POP)`(실적→조리 실적). `pack.yaml` 주석은 "코어가 메뉴 이름에도 t() 를 적용" 한다고 적고 일부러 치환 전 꼴로 두었는데 **코어는 rename 값에 t() 를 적용하지 않는다** — 팩과 코어의 가정이 어긋남. + 메인 `입력 (+입고검사)`(검사→검식) · 속성 라벨 `조리공정구분`(공정→조리 공정).
  - kimchi — BAS-05 속성 라벨 `설비구분`(설비→설비·탱크).
  - JSON 오류 응답의 `message` · `fields[].label` 은 3팩 모두 치환 정상(kimchi 91 · foodservice 76 · printfilm 86 응답 · 치환 안 된 0).
- **기대**: G-P05 노출 0 (`goal.md` §2.7).
- **담당**: 아키텍트(메뉴 rename · 속성 라벨에 `t()` 를 적용할지 결정 — 진행 중인 코어 변경 요청 「menus.rename 이중 치환」과 같은 뿌리) + 팩 담당(printfilm 개발2 · foodservice 개발1 · kimchi 개발3 — rename 값 · attrs label).

### DEF-QA1-006 · 중대 · 코어 금지어 — QA 검사 도구(`src/mescore/tools/check_data.py` · `check_security.py`) 안의 업종어 (G-C23 FAIL 원인)
- **재현**: `uv run python src/mescore/tools/check_terms.py` → `G-C23 코어 금지어 0 FAIL … 위반 4`.
- **실측**: 검사기 실행 때 `check_data.py:1529` `슬리팅` · `splice` · `:1533` `슬리팅` · `:1598` `양념` (QA2 작업 중 파일). 리포트를 쓰는 사이 다시 재니 `check_data.py` 는 0 이 되고 **`check_security.py:781` `롤`(인쇄필름 — 「스크롤」 같은 낱말 속 부분 문자열로 보인다 · QA3) 1건**이 새로 잡힌다. 내 파일(`check_screens.py`) 위반 0. 다른 QA 도구가 고쳐지는 중이라 숫자는 움직인다 — 최종 판정은 `uv run python src/mescore/tools/check_terms.py` 재실행으로.
- **기대**: `src/mescore/` 전체 금지어 0 — 검사 도구도 `src/mescore/tools/` 안이라 대상이다(팩 시나리오 단어는 `packs/` 쪽 기대값 파일이나 `core.yaml: forbidden_terms` 에서 읽어 와야 한다).
- **담당**: QA2 (`check_data.py`) · QA3 (`check_security.py`).

### DEF-QA1-008 · 중대 · `make db-schema` 가 `MES_PG_DSN` 을 무시하고 `mes_core_db` 를 지운다
- **재현**: `MES_PG_DSN=postgresql:///mes_qa_db make -n db-schema` → `psql -q -h /tmp -d mes_core_db … drop schema public cascade` (`DB := mes_$(PACK)_db | mes_core_db` — DSN 을 보지 않는다). `make -n db-seed` → `uv run python -m mescore.db.seed_core` (이쪽은 DSN 존중).
- **실측**: QA 가 지시대로 `MES_PG_DSN=…/mes_qa_db make db-schema db-seed` 를 쳤다면 **다른 사람이 쓰는 `mes_core_db` 의 스키마가 지워지고** 시드만 `mes_qa_db` 로 갔을 것. (이번에는 `make -n` 으로 확인하고 psql 직접 실행.)
- **기대**: `db-schema` · `db-create` · `backup` 대상이 `MES_PG_DSN` 의 DB 이름을 따른다(또는 `MES_PG_DSN` 이 있으면 거부).
- **담당**: 아키텍트(`Makefile`).

### DEF-QA1-004 · 경미 · 숫자가 아닌 경로 키가 404 가 아니라 422 (기능 21 · 팩 1)
- **재현**: 관리자/입력 역할로 `POST /ord/orders/abc` · `GET /mat/lots/abc/label` · `GET /shp/documents/abc/print` … → **422** `{"code":"validation_error","fields":[{"name":"order_id","reason":"정수여야 합니다"}]}` (8051 서버에서도 `POST /ord/orders/abc` → 422).
- **원인**: 경로 변수를 `id: int` 로 선언 → FastAPI `RequestValidationError` → 422. 개발1 라우터(`bas` · `job` · `sys`)는 `id_of_path()` 로 404 — 맞다.
- **기대**: `api-contract.md` §1 — "경로 키가 숫자여야 하는데 아닌 것도 404". 큰 숫자(999999999)는 21 기능 모두 404 로 맞다.
- **대상**: 개발3 — F-ORD-02 · 03 · 08 · 09 · F-SHP-02 · 03 · 07 · 10 · F-KPI-07 · F-IFC-04 · (kimchi) F-X-AGE-04 / 개발2 — F-MAT-02 · 07 · F-POP-03 · 04 · 05 · 07 · F-QUA-02 · 05 · 09 · 10 · F-EQP-06. (D-12 extra 라우트 `/pop/result/{id}/split|merge` · `/shp/shipments/{id}/label` 도 같은 꼴.)
- **담당**: 개발2 · 개발3.

### DEF-QA1-005 · 경미 · 채널 배지 `현황판` 이 `t()` 를 거치지 않는다 (날것 중립어)
- **재현**: `check_screens` ③ — terms_keys 26 개를 표지(§n§)로 바꾼 뒤 화면 60 을 그리면 58 화면에 `<i class="ch" title="주로 쓰는 채널: 현황판">현황판</i>` 와 메인 `· 관리자 Web · 현황판 · 모바일` 이 남는다.
- **실측**: 다른 terms_keys(메뉴 · 화면명 · 라벨 · 오류 메시지)는 전부 표지로 바뀌었다(정적 템플릿 스캔 `t()` 누락 0 은 Jinja 식 안의 채널명을 보지 못한다).
- **기대**: G-C23 "t() 누락 0" — `현황판` 은 terms_keys 의 중립어다. 팩이 `현황판` 을 바꾸면 채널 배지만 옛 이름으로 남는다(지금 3팩 중 바꾸는 팩은 없다).
- **담당**: 디자이너1(사이드바 · 메인 채널 배지 — `base.html`/`_macros.html`) — 채널명을 용어 밖으로 둘지는 아키텍트 결정.

### DEF-QA1-007 · 경미 · F-SHP-07 "after_commit 으로 ERP 큐" — 코어 단독은 승인해도 `ifc_outbox` 행 0
- **재현**: 코어 단독에서 F-SHP-07 승인 전후 `select count(*) from ifc_outbox` → 같다(검사기 실행 메모).
- **실측**: 라우터는 `http.after_commit(request, "shipment_approved", …)` 를 부르지만 `after_commit_shipment_approved` 훅은 팩에만 있다 → 코어 단독은 큐가 비고, F-IFC-03 · 04 · G-C16 의 `ifc_outbox` 는 시드(`seed_dev3`) 행으로만 검증된다.
- **기대**: 계약 문장(`function-list.md` F-SHP-07)과 코드 중 하나로 맞춘다 — 코어가 기본 `erp.enqueue` 를 하거나, 계약을 "팩의 after_commit 훅이 큐에 넣는다" 로.
- **담당**: 아키텍트(계약) · 개발3(`shp.py` · `erp.py`).

### DEF-QA1-009 · 경미 · printfilm 에서 지표 정의(F-KPI-06 · 07)를 아무 역할도 못 쓴다
- **실측**: `mes_printfilm_db` 의 `kpi` 칸이 4 역할 모두 `조회`(`packs/printfilm/seed/permissions.csv:46-49`) → `지표` 범위를 가진 역할 0 → KPI-03 의 등록 · 수정이 막혀 있다(검사기: 전 역할 403 확인).
- **기대**: 팩이 칸을 바꿀 수는 있다(G-C17) — 다만 기능을 아무도 못 쓰게 된 것이 의도인지 `pack.yaml`/README 에 적거나 ADMIN 에 `입력 (지표)` 를 둔다.
- **담당**: 개발2(printfilm).

### DEF-QA1-010 · 경미 · gate 가 QA1 검사기의 G-C13 · G-C23 · 팩 G-P05 행을 읽지 않는다
- **실측**: `gate.py` 는 `check_screens` 에서 G-C02 · G-C03 · G-C17 만 읽고(자기 판정이 FAIL 이면 그것을 유지), 팩 게이트는 `check_screens` 를 부르지 않는다. 그래서 DEF-QA1-002/003/005 가 판정표에 드러나지 않는다.
- **기대**: QA 검사기 출력이 우선(`gate.py` 머리말) — G-C23 · 팩 G-P05 도 `check_screens` 행을 합친다.
- **담당**: 아키텍트(`gate.py`).

## 3. 통과한 것 (실측)

- **오류 계약 §2.5 / api-contract §1**: 필수 누락 422 · 코드 중복 422 · 없는 LOT 스캔 422 · 이미 출하 LOT 422 · 불합격/미검사 LOT 투입 422 · 측정값 필수 누락 422 · 범위 이탈은 저장 + `deviated`(오류 아님) · 경로 키(큰 숫자) 404 · 미로그인 401 `{"code":"unauthorized","message":"로그인이 필요합니다"}` · 권한 403 `접근 권한이 없습니다` · ERP 재전송 **501 `decision: D-02`** · DB 끊김 503 `서비스 일시 중단`(`/health` · 화면 · 브라우저 · 현황판 오류 화면에도 새로고침 유지 · 응답에 접속 문자열 · DB 이름 없음).
- **응답 모양 §2**: 브라우저 쓰기 성공 303 + 알림 · 422 폼 POST 303 → Referer · **스캔 진입 GET `?no=` 없는 번호는 그 화면을 422 로 다시 그림(`data-scan` 유지)** — MAT-02 · POP-01 · QUA-02 · TRC-01 · TRC-02 · 미로그인 브라우저 GET 303 `/login?next=` · POST 401 오류 화면 · 로그인 실패 401 재렌더 · `/health` 계약 키 11 정확히(메뉴 12 · 화면 51 · 기능 132 · placeholder 0) · `/docs` `/redoc` 404 · `/openapi.json` 401/403/200 · 화면 GET JSON 에 `screen_id user functions template`.
- **G-C17**: 48칸 DB = core.yaml · 칸별 화면 GET(없음 403 · 그 밖 200) + 기능(쓰기: 입력 칸만 통과, 조회 · 없음 칸 403) 전부 PASS · 범위 4종(QA×F-MAT-04 만 · ADMIN×F-SHP-07 만 · ADMIN×F-KPI-06 · ADMIN×F-IFC-04) · **SYS-03 으로 새 역할 칸을 `조회` 로 바꾸면 다음 요청 403 → 200(코드 변경 0)** · 사용자 중지 → 그 세션 다음 요청 401 · 비밀번호 재설정 → 이전 세션 401 · 역할 변경 다음 요청부터 반영 · 자기 자신 중지 422 · ADMIN×sys 잠금 422.
- **계보 · 측정값 접점(①에서 본 것)**: 종료 시 생산 LOT `P…` + 투입 계보 · `pop_measure` 2행 · 출하 스캔 계보 1줄 · 정방향(원재료 → 출하 LOT) · 역방향(출하 LOT → 원재료) 도달 · 추적 3 화면 조회 전후 행 수 diff 0(접근 로그 밖).
- **번호 형식**: ORDER `O\d{6}-\d{3}` · WORK_ORDER `W…` · SHIPMENT `S…` · LOT_MATERIAL `M…` · LOT_PRODUCT `P…` — `core.yaml: numbering` 과 같다.
- **이관 배치 4**: `--dry-run` 종료 0 · 리포트 열(파일 읽음 적재 갱신 건너뜀 오류) · 실적재 2회째 적재 0 · 없는 폴더 종료 코드 ≠ 0.
- **채널**: pop · mobile · board × 화면 51 = 153 + 로그인 device=pop 세션 2 — `core.yaml: channels` 밖 403 · 안 200, 위반 0. 팩 3 도 위반 0.

## 4. 팩 3 — 읽기 · 호출만 (`mes_<팩>_db`)

| 팩 | 기능 (코어 + F-X) | G-C17 | 채널 | G-P05 화면 글 | G-P05 오류 응답 | G-C03 응답 모양 |
|---|---|---|---|---|---|---|
| kimchi | 156 중 PASS 153 · FAIL 3 (F-MAT-07 · F-SHP-10 · F-X-AGE-04 — 전부 DEF-004) · F-X 24 중 23 | 6 역할(ADMIN FIELD PM PROD QA VENDOR) · 108칸 PASS · 호출 925 위반 0 | 179 위반 0 | **FAIL 1** (`설비구분`) | PASS (91) | FAIL 2 (DEF-001) |
| foodservice | 132 중 PASS 130 · FAIL 2 (DEF-004) · F-X 0 (gates.yaml functions 0) | 6 역할(ADMIN NUTRITIONIST PRODUCTION SHIPPING VENDOR WORKER) · 72칸 PASS · 호출 780 위반 0 | 155 위반 0 | **FAIL 61** (`실적 (POP)` 등) | PASS (76) | FAIL 2 (DEF-001) |
| printfilm | 156 중 PASS 154 · FAIL 2 (DEF-004) · F-X 24 전부 PASS · 숨긴 eqp 8 기능 403 확인 | 4 역할(ADMIN FIELD PROD QC) · 60칸 PASS · 호출 615 위반 0 | 164 위반 0 | **FAIL 180** (`작업지시 관리` · `실적 현황` · `생산 실적 (POP)`) | PASS (86) | FAIL 2 (DEF-001) |

- 팩 역할 계정은 `sys_user` 에서 그 역할의 사용 중 계정 중 시드 비밀번호로 열리는 것을 골랐다(foodservice 는 시드 계정이 `admin` 하나뿐이라 팩 `seed/users` 계정). 팩 금지어 노출(kimchi 553 · foodservice 288 · printfilm 523)은 팩 terms · 팩 화면의 업종어라 정상(WARN 참고).

## 5. `make gate` 에 읽히는 판정 줄 (`gate.per_gate` 로 이 검사기 출력을 읽은 값 · 코어 단독)

```
G-C02  FAIL  기능 136 계약 호출 (정상 + 오류 계약): PASS 115/136 · FAIL 21 [F-ORD-02 … F-IFC-04] · 미검증 0 · 검사 676건 · DB mes_qa_db
G-C03  FAIL  검사 2 · 통과 못한 1 — 응답 모양 · 인증 없는 경로 · 503: 검사 31 · 통과 못한 2 [POST /login/as → 422 · /login/as 200 → 그 세션 /sys/users 200 · MES_ENV=dev]
G-C17  PASS  검사 4 전부 PASS
(G-C13 PASS · G-C23 FAIL 은 출력하지만 gate 는 읽지 않는다 — DEF-QA1-010)
```
gate 규칙상 gate 자신의 판정이 이미 FAIL 이면 그것을 유지하고, 아니면 위 값으로 바뀐다 → G-C02 · G-C03 은 **FAIL**, G-C17 은 **PASS**.

## 6. 기능 136 판정 표 (코어 단독 · `mes_qa_db`)

| ID | 기능명 | API | 담당 | 판정 | 검사 | 실측 — 통과 못한 항목 (없으면 대표 정상 호출) |
|---|---|---|---|---|---|---|
| F-BAS-01 | 품목 등록 | `POST /bas/items` | 개발1 | **PASS** | 5 | 등록 200 (200 등록했습니다 — 품목 QA-IT-1009092430983) |
| F-BAS-02 | 품목 수정 | `POST /bas/items/{id}` | 개발1 | **PASS** | 6 | 수정 200 (200 수정했습니다 — 품목 QA-IT-1009092430983) |
| F-BAS-03 | 품목 삭제 | `POST /bas/items/{id}/delete` | 개발1 | **PASS** | 7 | 삭제 200 (200 삭제했습니다 — 품목 QA-IT-1009092430983_D) |
| F-BAS-04 | 품목 조회 | `GET /bas/items` | 개발1 | **PASS** | 5 | 조회 200 JSON (200 /bas/items?q=QA-IT-1009092430983) |
| F-BAS-05 | BOM 등록 | `POST /bas/bom` | 개발1 | **PASS** | 6 | BOM 등록 200 (헤더 + 구성품 tx) (200 BOM을 등록했습니다) |
| F-BAS-06 | BOM 수정 | `POST /bas/bom/{id}` | 개발1 | **PASS** | 6 | BOM 수정 200 (구성품 수량) (200 BOM을 수정했습니다) |
| F-BAS-07 | BOM 삭제 | `POST /bas/bom/{id}/delete` | 개발1 | **PASS** | 6 | BOM 삭제 200 (200 BOM을 삭제했습니다) |
| F-BAS-08 | BOM 조회 | `GET /bas/bom` | 개발1 | **PASS** | 4 | 조회 200 JSON (200 /bas/bom?item_id=39) |
| F-BAS-09 | 공정 등록 | `POST /bas/processes` | 개발1 | **PASS** | 5 | 등록 200 (200 등록했습니다 — 공정 QA-PRC-1009092430983) |
| F-BAS-10 | 공정 수정 | `POST /bas/processes/{id}` | 개발1 | **PASS** | 6 | 수정 200 (200 수정했습니다 — 공정 QA-PRC-1009092430983) |
| F-BAS-11 | 공정 삭제 | `POST /bas/processes/{id}/delete` | 개발1 | **PASS** | 7 | 삭제 200 (200 삭제했습니다 — 공정 QA-PRC-1009092430983_D) |
| F-BAS-12 | 공정 조회 | `GET /bas/processes` | 개발1 | **PASS** | 5 | 조회 200 JSON (200 /bas/processes?q=QA-PRC-1009092430983) |
| F-BAS-13 | 공정 측정값 등록 | `POST /bas/process-params` | 개발1 | **PASS** | 6 | 등록 200 (200 등록했습니다 — 공정 측정값 qa_req) |
| F-BAS-14 | 공정 측정값 수정 | `POST /bas/process-params/{id}` | 개발1 | **PASS** | 7 | 수정 200 (200 수정했습니다 — 공정 측정값 qa_req) |
| F-BAS-15 | 공정 측정값 삭제 | `POST /bas/process-params/{id}/delete` | 개발1 | **PASS** | 6 | 삭제 200 (200 삭제했습니다 — 공정 측정값 qa_req_D) |
| F-BAS-16 | 공정 측정값 조회 | `GET /bas/process-params` | 개발1 | **PASS** | 5 | 조회 200 JSON (200 /bas/process-params?q=qa_req) |
| F-BAS-17 | 설비 등록 | `POST /bas/equipment` | 개발1 | **PASS** | 5 | 등록 200 (200 등록했습니다 — 설비 QA-EQ-1009092430983) |
| F-BAS-18 | 설비 수정 | `POST /bas/equipment/{id}` | 개발1 | **PASS** | 6 | 수정 200 (200 수정했습니다 — 설비 QA-EQ-1009092430983) |
| F-BAS-19 | 설비 삭제 | `POST /bas/equipment/{id}/delete` | 개발1 | **PASS** | 6 | 삭제 200 (200 삭제했습니다 — 설비 QA-EQ-1009092430983_D) |
| F-BAS-20 | 설비 조회 | `GET /bas/equipment` | 개발1 | **PASS** | 5 | 조회 200 JSON (200 /bas/equipment?q=QA-EQ-1009092430983) |
| F-BAS-21 | 거래처 등록 | `POST /bas/partners` | 개발1 | **PASS** | 5 | 등록 200 (200 등록했습니다 — 거래처 QA-CU-1009092430983) |
| F-BAS-22 | 거래처 수정 | `POST /bas/partners/{id}` | 개발1 | **PASS** | 6 | 수정 200 (200 수정했습니다 — 거래처 QA-CU-1009092430983) |
| F-BAS-23 | 거래처 삭제 | `POST /bas/partners/{id}/delete` | 개발1 | **PASS** | 6 | 삭제 200 (200 삭제했습니다 — 거래처 QA-CU-1009092430983_D) |
| F-BAS-24 | 거래처 조회 | `GET /bas/partners` | 개발1 | **PASS** | 5 | 조회 200 JSON (200 /bas/partners?q=QA-CU-1009092430983) |
| F-BAS-25 | 작업자 등록 | `POST /bas/workers` | 개발1 | **PASS** | 5 | 등록 200 (200 등록했습니다 — 작업자 QA-WK-1009092430983) |
| F-BAS-26 | 작업자 수정 | `POST /bas/workers/{id}` | 개발1 | **PASS** | 6 | 수정 200 (200 수정했습니다 — 작업자 QA-WK-1009092430983) |
| F-BAS-27 | 작업자 삭제 | `POST /bas/workers/{id}/delete` | 개발1 | **PASS** | 6 | 삭제 200 (200 삭제했습니다 — 작업자 QA-WK-1009092430983_D) |
| F-BAS-28 | 작업자 조회 | `GET /bas/workers` | 개발1 | **PASS** | 5 | 조회 200 JSON (200 /bas/workers?q=QA-WK-1009092430983) |
| F-BAS-29 | 불량코드 등록 | `POST /bas/defect-codes` | 개발1 | **PASS** | 5 | 등록 200 (200 등록했습니다 — 불량코드 QA-DF-1009092430983) |
| F-BAS-30 | 불량코드 수정 | `POST /bas/defect-codes/{id}` | 개발1 | **PASS** | 6 | 수정 200 (200 수정했습니다 — 불량코드 QA-DF-1009092430983) |
| F-BAS-31 | 불량코드 삭제 | `POST /bas/defect-codes/{id}/delete` | 개발1 | **PASS** | 6 | 삭제 200 (200 삭제했습니다 — 불량코드 QA-DF-1009092430983_D) |
| F-BAS-32 | 불량코드 조회 | `GET /bas/defect-codes` | 개발1 | **PASS** | 5 | 조회 200 JSON (200 /bas/defect-codes?q=QA-DF-1009092430983) |
| F-BAS-33 | 공통코드 등록 | `POST /bas/codes` | 개발1 | **PASS** | 6 | 등록 200 (200 등록했습니다 — 공통코드 C1009092430983) |
| F-BAS-34 | 공통코드 수정 | `POST /bas/codes/{id}` | 개발1 | **PASS** | 6 | 수정 200 (200 수정했습니다 — 공통코드 C1009092430983) |
| F-BAS-35 | 공통코드 삭제 | `POST /bas/codes/{id}/delete` | 개발1 | **PASS** | 7 | 삭제 200 (200 삭제했습니다 — 공통코드 C1009092430983_D) |
| F-BAS-36 | 공통코드 조회 | `GET /bas/codes` | 개발1 | **PASS** | 5 | 조회 200 JSON (200 /bas/codes?q=C1009092430983) |
| F-ORD-01 | 수주 등록 | `POST /ord/orders` | 개발3 | **PASS** | 8 | 수주 등록 200 (번호 ORDER) (200 수주를 등록했습니다 — O261009-005) |
| F-ORD-02 | 수주 수정 | `POST /ord/orders/{id}` | 개발3 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[order_id] POST /ord/orders/abc |
| F-ORD-03 | 수주 취소 | `POST /ord/orders/{id}/cancel` | 개발3 | **FAIL** | 7 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[order_id] POST /ord/orders/abc/cancel |
| F-ORD-04 | 수주 조회 | `GET /ord/orders` | 개발3 | **PASS** | 2 | 조회 200 (현장 조회 칸) (200 /ord/orders) |
| F-ORD-05 | 수주 이력 조회 | `GET /ord/order-history` | 개발3 | **PASS** | 3 | 조회 200 JSON (200 /ord/order-history?order_no=O261009-005) |
| F-ORD-06 | 납기 달력 조회 | `GET /ord/delivery-calendar` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /ord/delivery-calendar) |
| F-ORD-07 | 생산계획 등록 | `POST /ord/plans` | 개발3 | **PASS** | 4 | 생산계획 등록 200 (번호 PLAN) (200 생산계획을 등록했습니다 — N261009-005) |
| F-ORD-08 | 생산계획 수정 | `POST /ord/plans/{id}` | 개발3 | **FAIL** | 7 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[plan_id] POST /ord/plans/abc |
| F-ORD-09 | 생산계획 확정 | `POST /ord/plans/{id}/confirm` | 개발3 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[plan_id] POST /ord/plans/abc/confirm |
| F-ORD-10 | 생산계획 조회 | `GET /ord/plans` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /ord/plans) |
| F-JOB-01 | 작업지시 등록 | `POST /job/work-orders` | 개발1 | **PASS** | 7 | 작업지시 등록 200 (번호 WORK_ORDER · 대기) (200 작업지시를 등록했습니다 — W261009-007) |
| F-JOB-02 | 작업지시 수정 | `POST /job/work-orders/{id}` | 개발1 | **PASS** | 7 | 수정 200 (수량) (200 작업지시를 수정했습니다 — W261009-007) |
| F-JOB-03 | 작업지시 마감 | `POST /job/work-orders/{id}/close` | 개발1 | **PASS** | 7 | 종료 안 된 실적 → 마감 422 (422 종료되지 않은 실적이 있어 마감할 수 없습니다[open_count] (기대 422)) |
| F-JOB-04 | 작업지시 취소 | `POST /job/work-orders/{id}/cancel` | 개발1 | **PASS** | 6 | 실적 없는 지시 취소 200 (200 작업지시를 취소했습니다 — W261009-008) |
| F-JOB-05 | 작업지시 조회 | `GET /job/work-orders` | 개발1 | **PASS** | 3 | 조회 200 JSON (200 /job/work-orders) |
| F-JOB-06 | 지시 현황 조회 | `GET /job/status` | 개발1 | **PASS** | 2 | 조회 200 JSON (200 /job/status) |
| F-JOB-07 | 작업지시서 출력 | `GET /job/print?id=` | 개발1 | **PASS** | 5 | 작업지시서 200 · SVG · 지시 번호 바코드 (200) |
| F-MAT-01 | 입고 등록 | `POST /mat/receipts` | 개발2 | **PASS** | 8 | 입고 등록 200 (원재료 LOT · 미검사 · 거래 1행) (200 입고를 등록했습니다 — 원재료 LOT M261009-0007) |
| F-MAT-02 | 입고 수정 | `POST /mat/receipts/{id}` | 개발2 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /mat/receipts/abc |
| F-MAT-03 | 입고 조회 | `GET /mat/receipts` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /mat/receipts) |
| F-MAT-04 | 입고검사 판정 | `POST /mat/inspections` | 개발2 | **PASS** | 7 | 입고검사 합격 200 (200 M261009-0007 입고검사 합격) |
| F-MAT-05 | 입고검사 조회 | `GET /mat/inspections` | 개발2 | **PASS** | 4 | 스캔 진입 ?no= 200 (200 /mat/inspections?no=M261009-0007) |
| F-MAT-06 | 원재료 LOT 조회 | `GET /mat/lots` | 개발2 | **PASS** | 3 | 조회 200 JSON (200 /mat/lots) |
| F-MAT-07 | 원재료 LOT 라벨 출력 | `GET /mat/lots/{id}/label` | 개발2 | **FAIL** | 5 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] GET /mat/lots/abc/label |
| F-MAT-08 | 재고 조회 | `GET /mat/stock` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /mat/stock) |
| F-MAT-09 | 재고 조정 | `POST /mat/stock/adjust` | 개발2 | **PASS** | 4 | 재고 조정 200 (200 재고를 조정했습니다) |
| F-MAT-10 | 소요량 계산 | `POST /mat/requirements/calc` | 개발2 | **PASS** | 4 | 소요량 계산 200 (200 소요량을 계산했습니다 — 3) |
| F-MAT-11 | 소요량 조회 | `GET /mat/requirements` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /mat/requirements) |
| F-POP-01 | 작업 목록 조회 (스캔) | `GET /pop/work` | 개발2 | **PASS** | 5 | 지시 번호 스캔 → POP-02 로 (200/303) (200 http://testserver/pop/work?no=W261009-007) |
| F-POP-02 | 작업 시작 | `POST /pop/result/start` | 개발2 | **PASS** | 6 | 작업 시작 200 (실적 행) (200 W261009-007 작업 시작) |
| F-POP-03 | 작업 종료 | `POST /pop/result/{id}/end` | 개발2 | **FAIL** | 13 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /pop/result/abc/end |
| F-POP-04 | 정지 기록 | `POST /pop/result/{id}/stop` | 개발2 | **FAIL** | 8 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /pop/result/abc/stop |
| F-POP-05 | 폐기 기록 | `POST /pop/result/{id}/scrap` | 개발2 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /pop/result/abc/scrap |
| F-POP-06 | 투입 스캔 | `POST /pop/inputs` | 개발2 | **PASS** | 6 | 투입 스캔 200 (투입 계보 대상) (200 투입 M261009-0007) |
| F-POP-07 | 투입 취소 | `POST /pop/inputs/{id}/cancel` | 개발2 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /pop/inputs/abc/cancel |
| F-POP-08 | 생산 LOT 라벨 출력 | `GET /pop/labels?lot=` | 개발2 | **PASS** | 4 | LOT 라벨 200 · SVG · 바코드 = lot_no (200) |
| F-QUA-01 | 검사 계획 등록 | `POST /qua/plans` | 개발2 | **PASS** | 6 | 검사 계획 등록 200 (200 검사 계획 1) |
| F-QUA-02 | 검사 계획 수정 | `POST /qua/plans/{id}` | 개발2 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /qua/plans/abc |
| F-QUA-03 | 검사 계획 조회 | `GET /qua/plans` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /qua/plans) |
| F-QUA-04 | 검사 결과 등록 | `POST /qua/inspections` | 개발2 | **PASS** | 8 | 검사 결과 등록 200 (판정 전) (200 P261009-0005 검사 등록 — 판정 대기) |
| F-QUA-05 | 검사 판정 | `POST /qua/inspections/{id}/judge` | 개발2 | **FAIL** | 9 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /qua/inspections/abc/judge |
| F-QUA-06 | 검사 결과 조회 | `GET /qua/inspections` | 개발2 | **PASS** | 4 | 스캔 진입 ?no= 200 (200 /qua/inspections?no=P261009-0005) |
| F-QUA-07 | 불량 집계 조회 | `GET /qua/defect-stats` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /qua/defect-stats) |
| F-QUA-08 | 이상 등록 | `POST /qua/issues` | 개발2 | **PASS** | 4 | 이상 등록 200 (발생) (200 이상 Q261009-003) |
| F-QUA-09 | 시정 조치 등록 | `POST /qua/issues/{id}/action` | 개발2 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /qua/issues/abc/action |
| F-QUA-10 | 이상 종결 | `POST /qua/issues/{id}/close` | 개발2 | **FAIL** | 7 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /qua/issues/abc/close |
| F-QUA-11 | 이상 조회 | `GET /qua/issues` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /qua/issues) |
| F-EQP-01 | 가동 현황 조회 | `GET /eqp/status` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /eqp/status) |
| F-EQP-02 | 가동 상태 기록 | `POST /eqp/status` | 개발2 | **PASS** | 5 | 가동 상태 기록 200 (200 QA-EQ-1009092430983 가동) |
| F-EQP-03 | 점검 등록 | `POST /eqp/checks` | 개발2 | **PASS** | 4 | 점검 등록 200 (200 점검을 등록했습니다) |
| F-EQP-04 | 점검 조회 | `GET /eqp/checks` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /eqp/checks) |
| F-EQP-05 | 고장 등록 | `POST /eqp/faults` | 개발2 | **PASS** | 5 | 고장 등록 200 (고장 구간 시작) (200 QA-EQ-1009092430983 고장 등록) |
| F-EQP-06 | 고장 조치 | `POST /eqp/faults/{id}/fix` | 개발2 | **FAIL** | 7 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[id] POST /eqp/faults/abc/fix |
| F-EQP-07 | 고장 조회 | `GET /eqp/faults` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /eqp/faults) |
| F-EQP-08 | 수집값 조회 | `GET /eqp/collect` | 개발2 | **PASS** | 2 | 조회 200 JSON (200 /eqp/collect?equipment_id=16) |
| F-SHP-01 | 출하 등록 | `POST /shp/shipments` | 개발3 | **PASS** | 6 | 출하 등록 200 (번호 SHIPMENT · 등록) (200 출하를 등록했습니다 — S261009-007. 이어서 LOT 을 스캔합니) |
| F-SHP-02 | 출하 수정 | `POST /shp/shipments/{id}` | 개발3 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[shipment_id] POST /shp/shipments/abc |
| F-SHP-03 | 출하 취소 | `POST /shp/shipments/{id}/cancel` | 개발3 | **FAIL** | 6 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[shipment_id] POST /shp/shipments/abc/cancel |
| F-SHP-04 | 출하 조회 | `GET /shp/shipments` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /shp/shipments) |
| F-SHP-05 | 출하 LOT 스캔 | `POST /shp/scan` | 개발3 | **PASS** | 10 | LOT 스캔 200 (출하 계보 1줄) (200 P261009-0005 → S261009-007) |
| F-SHP-06 | 출하 LOT 스캔 취소 | `POST /shp/scan/cancel` | 개발3 | **PASS** | 5 | 스캔 취소 200 (unship) (200 P261009-0005 ← S261009-007) |
| F-SHP-07 | 출하 승인 | `POST /shp/shipments/{id}/approve` | 개발3 | **FAIL** | 8 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[shipment_id] POST /shp/shipments/abc/approve |
| F-SHP-08 | 출하 현황 조회 | `GET /shp/status` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /shp/status) |
| F-SHP-09 | 성적서 발행 | `POST /shp/documents` | 개발3 | **PASS** | 6 | 성적서 발행 200 (번호 DOCUMENT · 스냅샷) (200 성적서를 발행했습니다 — C261009-005) |
| F-SHP-10 | 성적서 출력 | `GET /shp/documents/{id}/print` | 개발3 | **FAIL** | 5 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[document_id] GET /shp/documents/abc/print |
| F-TRC-01 | 정방향 추적 | `GET /trc/forward?no=` | 개발3 | **PASS** | 7 | 조회 200 JSON (200 /trc/forward?no=M261009-0007) |
| F-TRC-02 | 역방향 추적 | `GET /trc/backward?no=` | 개발3 | **PASS** | 6 | 조회 200 JSON (200 /trc/backward?no=X261009-0003) |
| F-TRC-03 | 번호 검색 | `GET /trc/search?q=` | 개발3 | **PASS** | 4 | 조회 200 JSON (200 /trc/search?q=P261009) |
| F-KPI-01 | 현황판 조회 | `GET /kpi/board` | 개발3 | **PASS** | 3 | 현황판 ?device=board 200 JSON (200) |
| F-KPI-02 | 생산 집계 조회 | `GET /kpi/summary?kind=production` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /kpi/summary?kind=production) |
| F-KPI-03 | 품질 집계 조회 | `GET /kpi/summary?kind=quality` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /kpi/summary?kind=quality) |
| F-KPI-04 | 납기 집계 조회 | `GET /kpi/summary?kind=delivery` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /kpi/summary?kind=delivery) |
| F-KPI-05 | 설비 집계 조회 | `GET /kpi/summary?kind=equipment` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /kpi/summary?kind=equipment) |
| F-KPI-06 | 지표 등록 | `POST /kpi/indicators` | 개발3 | **PASS** | 6 | 지표 등록 200 (관리자 · 범위 지표) (200 지표를 등록했습니다) |
| F-KPI-07 | 지표 수정 | `POST /kpi/indicators/{id}` | 개발3 | **FAIL** | 5 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[indicator_id] POST /kpi/indicators/abc |
| F-KPI-08 | 지표 조회 | `GET /kpi/indicators` | 개발3 | **PASS** | 2 | 조회 200 JSON (200 /kpi/indicators) |
| F-SYS-01 | 사용자 등록 | `POST /sys/users` | 개발1 | **PASS** | 5 | 사용자 등록 200 (200 사용자를 등록했습니다 — qa1u1009092430983) |
| F-SYS-02 | 사용자 수정 | `POST /sys/users/{id}` | 개발1 | **PASS** | 8 | 사용자 수정 200 (200 사용자를 수정했습니다 — qa1u1009092430983) |
| F-SYS-03 | 사용자 중지 · 해제 | `POST /sys/users/{id}/toggle` | 개발1 | **PASS** | 8 | 사용자 중지 200 (200 사용자 상태를 바꿨습니다 — qa1u1009092430983: 사용 → ) |
| F-SYS-04 | 사용자 조회 | `GET /sys/users` | 개발1 | **PASS** | 4 | 조회 200 JSON (200 /sys/users) |
| F-SYS-05 | 역할 등록 | `POST /sys/roles` | 개발1 | **PASS** | 6 | 역할 등록 200 (200 역할을 등록했습니다 — QA1009092430983 (메뉴 12칸 없음)) |
| F-SYS-06 | 역할 수정 | `POST /sys/roles/{id}` | 개발1 | **PASS** | 6 | 역할 수정 200 (200 역할을 수정했습니다 — QA1009092430983) |
| F-SYS-07 | 역할 조회 | `GET /sys/roles` | 개발1 | **PASS** | 3 | 조회 200 JSON (200 /sys/roles) |
| F-SYS-08 | 권한 표 수정 | `POST /sys/permissions` | 개발1 | **PASS** | 8 | 권한 칸 수정 200 (새 역할 × bas = 조회) (200 권한 표를 저장했습니다 — 1칸) |
| F-SYS-09 | 권한 표 조회 | `GET /sys/permissions` | 개발1 | **PASS** | 3 | 조회 200 JSON (200 /sys/permissions) |
| F-SYS-10 | 접근 로그 조회 | `GET /sys/logs` | 개발1 | **PASS** | 4 | 조회 200 JSON (200 /sys/logs) |
| F-SYS-11 | 채번 규칙 수정 | `POST /sys/numbering` | 개발1 | **PASS** | 4 | 채번 규칙 수정 200 (같은 값 다시) (200 채번 규칙을 저장했습니다 — ISSUE: 다음 번호 Q261009-004) |
| F-SYS-12 | 채번 규칙 조회 | `GET /sys/numbering` | 개발1 | **PASS** | 3 | 조회 200 JSON (200 /sys/numbering) |
| F-SYS-13 | 백업 실행 | `POST /sys/backup` | 개발1 | **PASS** | 3 | 백업 200 (200 백업을 만들었습니다 — mes_qa_db-20261009-092436.d) |
| F-SYS-14 | 복구 확인 | `POST /sys/backup/{id}/verify` | 개발1 | **PASS** | 5 | 복구 확인 200 (임시 DB) (200 복구 확인을 마쳤습니다 — 판정: PASS — 테이블 52개 전부 복구 ) |
| F-SYS-15 | 이관 실행 | `POST /sys/migrate` | 개발1 | **PASS** | 4 | 이관 실행 200 (examples · dry-run) (200 이관을 실행했습니다 — basics (시험 실행)) |
| F-SYS-16 | 백업 · 이관 이력 조회 | `GET /sys/backup` | 개발1 | **PASS** | 2 | 조회 200 JSON (200 /sys/backup) |
| F-IFC-01 | 수집 메시지 수신 | `POST /ifc/collect` | 개발3 | **PASS** | 6 | 수신 200 (raw_id) (200) |
| F-IFC-02 | 수집 수신 현황 조회 | `GET /ifc/collect` | 개발3 | **PASS** | 3 | 조회 200 JSON (200 /ifc/collect) |
| F-IFC-03 | ERP 연계 로그 조회 | `GET /ifc/erp` | 개발3 | **PASS** | 3 | 조회 200 JSON (200 /ifc/erp) |
| F-IFC-04 | ERP 재전송 | `POST /ifc/erp/{id}/retry` | 개발3 | **FAIL** | 5 | 숫자 아닌 경로 키 404: 422 입력값을 확인해 주세요[outbox_id] POST /ifc/erp/abc/retry |
| B-MIG-01 | 기준정보 이관 | `cli basics` | 개발3 | **PASS** | 3 | dry-run 종료 0 · 리포트 열 (파일 읽음 적재 갱신 건너뜀 오류) (rc=0 합계 읽음 15 · 적재 0 · 갱신 15 · 건너뜀 0 · 오류 0 → 종료 코드 0) |
| B-MIG-02 | 수주 · 작업지시 이관 | `cli orders` | 개발3 | **PASS** | 3 | dry-run 종료 0 · 리포트 열 (파일 읽음 적재 갱신 건너뜀 오류) (rc=0 합계 읽음 3 · 적재 0 · 갱신 3 · 건너뜀 0 · 오류 0 → 종료 코드 0) |
| B-MIG-03 | LOT · 계보 이관 | `cli lots` | 개발3 | **PASS** | 3 | dry-run 종료 0 · 리포트 열 (파일 읽음 적재 갱신 건너뜀 오류) (rc=0 합계 읽음 19 · 적재 0 · 갱신 9 · 건너뜀 10 · 오류 0 → 종료 코드 0) |
| B-MIG-04 | 실적 · 검사 이력 이관 | `cli history` | 개발3 | **PASS** | 3 | dry-run 종료 0 · 리포트 열 (파일 읽음 적재 갱신 건너뜀 오류) (rc=0 합계 읽음 9 · 적재 0 · 갱신 9 · 건너뜀 0 · 오류 0 → 종료 코드 0) |

## 7. 권한 48칸 (모듈 × 역할) — 기대값 core.yaml · DB 대조 · 화면 GET · 기능 호출

칸 = `기대 등급 · DB 일치 · 화면 통과/수 · 기능 통과/수 · 판정`. 기능은 그 모듈의 기능 전부(쓰기는 입력 칸이면 통과 · 아니면 403, 읽기는 없음 칸이면 403). F-SYS-13 · 14 의 허용 호출은 ① 에서 이미 실행(중복 실행 생략).

| 모듈 | ADMIN | PROD | QA | FIELD |
|---|---|---|---|---|
| bas | 입력 · DB = · 화면 9/9 · 기능 36/36 · **PASS** | 조회 · DB = · 화면 9/9 · 기능 36/36 · **PASS** | 조회 · DB = · 화면 9/9 · 기능 36/36 · **PASS** | 없음 · DB = · 화면 9/9 · 기능 36/36 · **PASS** |
| ord | 입력 · DB = · 화면 4/4 · 기능 10/10 · **PASS** | 입력 · DB = · 화면 4/4 · 기능 10/10 · **PASS** | 조회 · DB = · 화면 4/4 · 기능 10/10 · **PASS** | 조회 · DB = · 화면 4/4 · 기능 10/10 · **PASS** |
| job | 입력 · DB = · 화면 3/3 · 기능 7/7 · **PASS** | 입력 · DB = · 화면 3/3 · 기능 7/7 · **PASS** | 조회 · DB = · 화면 3/3 · 기능 7/7 · **PASS** | 조회 · DB = · 화면 3/3 · 기능 7/7 · **PASS** |
| mat | 조회 · DB = · 화면 5/5 · 기능 11/11 · **PASS** | 입력 · DB = · 화면 5/5 · 기능 11/11 · **PASS** | 입력 (입고검사) · DB = · 화면 5/5 · 기능 11/11 · **PASS** | 입력 · DB = · 화면 5/5 · 기능 11/11 · **PASS** |
| pop | 조회 · DB = · 화면 4/4 · 기능 8/8 · **PASS** | 입력 · DB = · 화면 4/4 · 기능 8/8 · **PASS** | 조회 · DB = · 화면 4/4 · 기능 8/8 · **PASS** | 입력 · DB = · 화면 4/4 · 기능 8/8 · **PASS** |
| qua | 조회 · DB = · 화면 4/4 · 기능 11/11 · **PASS** | 조회 · DB = · 화면 4/4 · 기능 11/11 · **PASS** | 입력 · DB = · 화면 4/4 · 기능 11/11 · **PASS** | 조회 · DB = · 화면 4/4 · 기능 11/11 · **PASS** |
| eqp | 조회 · DB = · 화면 4/4 · 기능 8/8 · **PASS** | 입력 · DB = · 화면 4/4 · 기능 8/8 · **PASS** | 조회 · DB = · 화면 4/4 · 기능 8/8 · **PASS** | 입력 · DB = · 화면 4/4 · 기능 8/8 · **PASS** |
| shp | 입력 (승인) · DB = · 화면 4/4 · 기능 10/10 · **PASS** | 입력 · DB = · 화면 4/4 · 기능 10/10 · **PASS** | 조회 · DB = · 화면 4/4 · 기능 10/10 · **PASS** | 입력 · DB = · 화면 4/4 · 기능 10/10 · **PASS** |
| trc | 조회 · DB = · 화면 3/3 · 기능 3/3 · **PASS** | 조회 · DB = · 화면 3/3 · 기능 3/3 · **PASS** | 조회 · DB = · 화면 3/3 · 기능 3/3 · **PASS** | 없음 · DB = · 화면 3/3 · 기능 3/3 · **PASS** |
| kpi | 입력 (지표) · DB = · 화면 3/3 · 기능 8/8 · **PASS** | 조회 · DB = · 화면 3/3 · 기능 8/8 · **PASS** | 조회 · DB = · 화면 3/3 · 기능 8/8 · **PASS** | 조회 · DB = · 화면 3/3 · 기능 8/8 · **PASS** |
| sys | 입력 · DB = · 화면 6/6 · 기능 16/16 · **PASS** | 없음 · DB = · 화면 6/6 · 기능 16/16 · **PASS** | 없음 · DB = · 화면 6/6 · 기능 16/16 · **PASS** | 없음 · DB = · 화면 6/6 · 기능 16/16 · **PASS** |
| ifc | 입력 (재전송) · DB = · 화면 2/2 · 기능 3/3 · **PASS** | 조회 · DB = · 화면 2/2 · 기능 3/3 · **PASS** | 없음 · DB = · 화면 2/2 · 기능 3/3 · **PASS** | 없음 · DB = · 화면 2/2 · 기능 3/3 · **PASS** |

## 8. 검사기 메모

- 출력 행은 `interfaces.md` §10 형식. 종료 코드 1 = FAIL 행이 있다. `--json <파일>` 로 기능별 검사 항목 전부를 남긴다(이 리포트의 §6 · §7 이 그것으로 만든 표).
- 한 번 실행에 코어 약 20초(백업 · 복구 확인 포함) · 팩 약 15~30초. 실행마다 새 코드(`QA-…-<시각>`)로 행을 만들어 `mes_qa_db` 에 쌓인다 — 깨끗한 판정은 `--reset-db`.
- 날것 중립어 검사는 표 본문 · 선택지 · 스크립트 · 숫자나 `(예시)` 가 든 글 조각(DB 값)은 보지 않는다 — DB 값이 화면 문구로 오인되지 않게. 그래서 데이터 영역의 `t()` 누락은 놓칠 수 있다.
- 이 검사기가 다루지 않는 것: 500(처리되지 않은 예외)은 일부러 일으킬 방법이 없어 미검증 · 계보 10행 · 집계 재계산(QA2) · 브라우저 E2E · 390px(QA3).
