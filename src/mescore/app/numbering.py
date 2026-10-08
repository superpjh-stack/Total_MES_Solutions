"""채번 — 작업지시 · LOT 3종 · 출하 · 성적서 · 수주 · 생산계획 번호를 내는 **한 곳** (`contracts/interfaces.md` §3 · G-C08).

담당 **개발1**. 형식은 코드에 박지 않는다 — `sys_number_rule`(접두어 · 날짜 형식 · 자릿수) 행이 형식이고 `sys_number_seq` 가 카운터다.
종류(`kind`)는 `core.yaml: numbering`(+ 팩 `pack.yaml: numbering`) 의 키 — 시드가 `sys_number_rule` 을 채운다. 가설 형식은 D-10 · D-16,
공표는 `progress-dev1.md` §1.

    번호 = prefix + to_char(기준 시각, date_format) + 일련번호(seq_digits 자리, 0 채움)

- 구분 기호는 따로 두지 않는다 — 필요하면 `prefix` 나 `date_format` 안에 글자로 넣는다(예: `YYMMDD-`).
- 카운터 범위(`seq_scope`)는 **날짜 부분의 값**이다 — 날짜가 바뀌면 1 부터 다시 센다. 날짜 형식이 비면 범위는 빈 글자(통산).
- 카운터 행은 `insert … on conflict do update … returning` 한 문장으로 올린다 — 같은 (종류, 범위)를 동시에 부르면 뒤에 온 쪽이
  앞 트랜잭션의 커밋/되돌림을 기다린다(행 잠금). `cur=` 로 받은 커서 안에서 발번하면 업무 행과 함께 되돌려진다.
- 일련번호가 자릿수를 넘으면 자르지 않고 자릿수를 늘린다(같은 번호가 두 번 나오지 않는 것이 먼저다).
- 번호는 바코드로 찍히므로 **영문 대문자 · 숫자 · `-`** 만 — 규칙이 다른 글자를 만들면 `RuntimeError`.
- 형식 행이 없는 종류를 `next` 하면 `RuntimeError`(500) — 번호를 지어내지 않는다. 화면은 `rule()` 이 None 일 때 `미확정 (D-10)`.
- **다른 모듈은 번호의 첫 글자로 종류를 판정하지 않는다** — `lineage.resolve` 가 테이블에서 찾는다.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from ..db import conn
from . import packs

BARCODE_RE = re.compile(r"^[A-Z0-9-]+$")
SEEDED_BY = "numbering"

# 형식 행과 그 시각의 날짜 부분을 한 번에 읽는다. 날짜 부분은 DB 의 to_char 가 만든다(형식 열이 to_char 형식이다)
_RULE_SQL = """
select kind, prefix, date_format, seq_digits, use_yn,
       case when date_format = '' then '' else to_char(coalesce(%(at)s::timestamptz, now()), date_format) end as date_part
  from sys_number_rule
 where kind = %(kind)s and use_yn = 'Y'
"""

# 카운터 행을 잠그고 올린다 — 한 문장. 같은 (종류, 범위)의 동시 호출은 여기서 줄을 선다
_BUMP_SQL = """
insert into sys_number_seq (kind, seq_scope, last_seq, created_by) values (%s, %s, 1, %s)
on conflict (kind, seq_scope) do update set last_seq = sys_number_seq.last_seq + 1, updated_at = now(), updated_by = excluded.created_by
returning last_seq
"""


def kinds() -> list[str]:
    """선언된 번호 종류 — `core.yaml: numbering` + 팩 추가 (E1). 화면 · 시드가 쓴다."""
    return list(packs.current().numbering.keys())


KINDS = kinds


def _missing(kind: str) -> RuntimeError:
    return RuntimeError(f"sys_number_rule 에 {kind!r} 형식 행이 없다 (또는 use_yn=N) — SYS-05 채번 규칙에서 정한다 (D-10)")


def _compose(rule_row: dict, value: int) -> str:
    no = f"{rule_row['prefix']}{rule_row['date_part']}{str(value).zfill(int(rule_row['seq_digits']))}"
    if not BARCODE_RE.match(no):
        raise RuntimeError(f"채번 규칙 {rule_row['kind']!r} 이 바코드에 쓸 수 없는 글자를 만든다: {no!r} — 영문 대문자 · 숫자 · '-' 만 (interfaces.md §3)")
    return no


def _at(at: datetime | date | None):
    if isinstance(at, date) and not isinstance(at, datetime):
        return datetime(at.year, at.month, at.day)
    return at


def _next_in(cur, kind: str, at: datetime | date | None) -> str:
    cur.execute(_RULE_SQL, {"kind": kind, "at": _at(at)})
    rule_row = cur.fetchone()
    if rule_row is None:
        raise _missing(kind)
    cur.execute(_BUMP_SQL, (kind, rule_row["date_part"], SEEDED_BY))
    return _compose(rule_row, cur.fetchone()["last_seq"])


def next(kind: str, *, cur=None, at: datetime | date | None = None) -> str:  # noqa: A001 — 계약상 이름 (interfaces.md §3)
    """다음 번호를 **발번**한다(카운터 +1). 동시에 불러도 같은 번호가 두 번 나오지 않는다(카운터 행 잠금).

    cur  `conn.tx()` 의 커서. 주면 그 트랜잭션 안에서 발번한다 — 업무 행과 함께 되돌려진다. 없으면 자체 트랜잭션.
    at   날짜 부분의 기준 시각. 기본 now().
    형식 행이 없으면 422 가 아니라 **RuntimeError** — 설정 누락은 사용자 입력 오류가 아니다.
    """
    if cur is not None:
        return _next_in(cur, kind, at)
    with conn.tx() as own:
        return _next_in(own, kind, at)


def peek(kind: str, *, at: datetime | date | None = None) -> str:
    """다음에 나올 번호를 **발번하지 않고** 보여 준다(등록 화면 · SYS-05 미리보기). 그 사이 다른 사람이 발번하면 달라진다."""
    rule_row = conn.q1(_RULE_SQL, {"kind": kind, "at": _at(at)})
    if rule_row is None:
        raise _missing(kind)
    seq = conn.q1("select last_seq from sys_number_seq where kind = %s and seq_scope = %s", (kind, rule_row["date_part"]))
    return _compose(rule_row, (int(seq["last_seq"]) if seq else 0) + 1)


def rule(kind: str) -> dict | None:
    """그 종류의 형식 행(`sys_number_rule` · use_yn 무관). 없으면 None — 화면은 `미확정 (D-10)` 을 보여 준다."""
    return conn.q1("""select id, kind, prefix, date_format, seq_digits, use_yn, created_at, created_by, updated_at, updated_by
                        from sys_number_rule where kind = %s""", (kind,))


def counter(kind: str, *, at: datetime | date | None = None) -> int:
    """그 종류의 지금 범위(오늘) 카운터 값 — SYS-05 표시용. 범위 행이 없으면 0."""
    rule_row = conn.q1(_RULE_SQL, {"kind": kind, "at": _at(at)})
    if rule_row is None:
        return 0
    seq = conn.q1("select last_seq from sys_number_seq where kind = %s and seq_scope = %s", (kind, rule_row["date_part"]))
    return int(seq["last_seq"]) if seq else 0
