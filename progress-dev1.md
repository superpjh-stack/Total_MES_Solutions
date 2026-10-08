# progress-dev1 — 개발1 (기준 · 지시 · 시스템 / `bas` `job` `sys` + 로그인 · 메인)

검증된 것만 적는다. 형식 `| 항목 | 실측 | 검증 방법 |`. 비밀번호 값은 적지 않는다.

## §1 공표 — 채번 (`app/numbering.py` · R1 · 2026-10-09)

**시그니처 (`interfaces.md` §3 그대로)**

```python
from mescore.app import numbering
numbering.next(kind, *, cur=None, at=None) -> str   # 발번 (카운터 +1). cur 를 주면 그 트랜잭션 안 — 되돌리면 번호도 돌아온다
numbering.peek(kind, *, at=None) -> str             # 발번하지 않고 다음 번호
numbering.rule(kind) -> dict | None                 # sys_number_rule 행 (id kind prefix date_format seq_digits use_yn …). 없으면 None → 화면 `미확정 (D-10)`
numbering.kinds() -> list[str]                      # core.yaml: numbering + 팩 numbering 의 키 (표시 · 시드용)
numbering.counter(kind, *, at=None) -> int          # 지금 범위(오늘)의 카운터 값 — SYS-05 표시용
```

**형식 (가설 — D-10 · D-16 · 행은 `core.yaml: numbering` → 시드 `sys_number_rule`)**

`번호 = prefix + to_char(기준 시각, date_format) + 일련번호(seq_digits 자리 0 채움)` — 구분 기호는 `date_format` 끝의 `-` 가 전부.

| kind | prefix | date_format | digits | 예 (2026-10-09) | 쓰는 곳 |
|---|---|---|---|---|---|
| `WORK_ORDER` | `W` | `YYMMDD-` | 3 | `W261009-001` | 개발1 F-JOB-01 |
| `LOT_MATERIAL` | `M` | `YYMMDD-` | 4 | `M261009-0001` | 개발2 F-MAT-01 |
| `LOT_PRODUCT` | `P` | `YYMMDD-` | 4 | `P261009-0001` | 개발2 `lineage.make_product_lot` · split · merge |
| `LOT_SHIPMENT` | `X` | `YYMMDD-` | 4 | `X261009-0001` | 개발2 `lineage.ship` |
| `SHIPMENT` | `S` | `YYMMDD-` | 3 | `S261009-001` | 개발3 F-SHP-01 |
| `DOCUMENT` | `C` | `YYMMDD-` | 3 | `C261009-001` | 개발3 F-SHP-09 |
| `ORDER` | `O` | `YYMMDD-` | 3 | `O261009-001` | 개발3 F-ORD-01 |
| `PLAN` | `N` | `YYMMDD-` | 3 | `N261009-001` | 개발3 F-ORD-08 |

규칙
- 카운터 범위 = 날짜 부분 값(`seq_scope`). 날짜가 바뀌면 1 부터. `date_format` 이 비면 통산.
- 자릿수를 넘으면 자르지 않고 늘린다(`W261009-1000`). 글자는 `^[A-Z0-9-]+$` 만 — 아니면 `RuntimeError`(규칙 오류).
- 형식 행이 없거나 `use_yn=N` 이면 `RuntimeError`(500) — 번호를 지어내지 않는다. 다른 모듈은 **첫 글자로 종류를 판정하지 않는다**.
- 카운터 행 잠금은 `insert … on conflict do update … returning` 한 문장 — 동시 호출은 행 잠금에서 줄을 선다. 한 트랜잭션의 잠금 순서는 `실적/LOT 행 → 지시 행 → 채번 카운터`(interfaces.md §1).
- 팩은 `pack.yaml: numbering` 으로 접두어 · 형식 · 자릿수 · 종류(예 `BATCH`)를 더한다. 시드가 행을 넣는다 — 코드 변경 없음.

| 항목 | 실측 | 검증 방법 |
|---|---|---|
| 채번 | 동시 8스레드 × 5 = 40 발번 중복 0 · 되돌림 뒤 `peek` 복귀 · 날짜 바뀌면 001 · 자릿수 초과 비절단 · 규칙 없음 RuntimeError · 금지 글자 RuntimeError | `uv run pytest -q tests/test_numbering.py` 9 passed |

## §2 실측

(R2 진행 중 — 아래에 채운다)

## §3 요청

(R2 진행 중 — 아래에 채운다)
