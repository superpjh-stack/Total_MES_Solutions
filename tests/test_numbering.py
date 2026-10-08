"""채번 `app/numbering.py` (개발1 · interfaces.md §3 · G-C08) — 동시 발번 중복 0 · 되돌림 때 번호가 되돌아감 · 날짜가 바뀌면 1 · 규칙 없으면 RuntimeError.

공통 시드(`make db-seed`)의 `sys_number_rule` 8행이 있어야 한다. 카운터는 실제 DB 의 것을 올린다(번호는 예약되지 않는다).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from mescore.app import numbering, packs
from mescore.db import conn

KIND = "WORK_ORDER"
OLD_AT = datetime(1999, 12, 31, 9, 0, 0)       # 다른 날짜의 범위 — 카운터가 1 부터 시작하는지 본다
OLD_SCOPE = "991231-"


def _rule() -> dict:
    r = numbering.rule(KIND)
    assert r is not None, "공통 시드의 sys_number_rule WORK_ORDER 행이 없다 — make db-seed"
    return r


def test_kinds_come_from_manifest():
    assert set(numbering.kinds()) == set(packs.current().numbering.keys())
    assert "WORK_ORDER" in numbering.kinds() and len(numbering.kinds()) >= 8


def test_format_is_prefix_date_seq():
    r = _rule()
    no = numbering.peek(KIND)
    assert no.startswith(r["prefix"]) and numbering.BARCODE_RE.match(no)
    assert len(no) == len(r["prefix"]) + len(datetime.now().strftime("%y%m%d")) + 1 + r["seq_digits"]   # 'YYMMDD-' = 7 글자


def test_next_is_peek_then_increments():
    before = numbering.peek(KIND)
    got = numbering.next(KIND)
    assert got == before
    after = numbering.peek(KIND)
    assert int(after.rsplit("-", 1)[1]) == int(got.rsplit("-", 1)[1]) + 1


def test_scope_resets_when_date_changes():
    conn.x("delete from sys_number_seq where kind = %s and seq_scope = %s", (KIND, OLD_SCOPE))
    r = _rule()
    assert numbering.peek(KIND, at=OLD_AT) == f"{r['prefix']}{OLD_SCOPE}{'1'.zfill(r['seq_digits'])}"
    assert numbering.next(KIND, at=OLD_AT) == f"{r['prefix']}{OLD_SCOPE}{'1'.zfill(r['seq_digits'])}"
    assert numbering.next(KIND, at=OLD_AT) == f"{r['prefix']}{OLD_SCOPE}{'2'.zfill(r['seq_digits'])}"
    assert numbering.counter(KIND, at=OLD_AT) == 2
    conn.x("delete from sys_number_seq where kind = %s and seq_scope = %s", (KIND, OLD_SCOPE))


def test_rollback_returns_the_number():
    before = numbering.peek(KIND)
    with pytest.raises(ZeroDivisionError):
        with conn.tx() as cur:
            issued = numbering.next(KIND, cur=cur)
            assert issued == before
            _ = 1 / 0           # 업무 행 저장이 실패한 셈 — 트랜잭션이 되돌려진다
    assert numbering.peek(KIND) == before, "되돌린 트랜잭션의 번호가 돌아오지 않았다"
    assert numbering.next(KIND) == before


def test_concurrent_next_has_no_duplicates():
    n_threads, per_thread = 8, 5
    conn.x("delete from sys_number_seq where kind = %s and seq_scope = %s", (KIND, OLD_SCOPE))

    def work(_i: int) -> list[str]:
        out = []
        for _ in range(per_thread):
            with conn.tx() as cur:
                out.append(numbering.next(KIND, cur=cur, at=OLD_AT))
        return out

    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        got = [no for part in ex.map(work, range(n_threads)) for no in part]
    assert len(got) == n_threads * per_thread
    assert len(set(got)) == len(got), "동시 발번에서 같은 번호가 나왔다"
    seqs = sorted(int(no.rsplit("-", 1)[1]) for no in got)
    assert seqs == list(range(1, n_threads * per_thread + 1))
    conn.x("delete from sys_number_seq where kind = %s and seq_scope = %s", (KIND, OLD_SCOPE))


def test_missing_rule_is_runtime_error_not_invented():
    with pytest.raises(RuntimeError):
        numbering.next("없는-종류-X")
    with pytest.raises(RuntimeError):
        numbering.peek("없는-종류-X")
    assert numbering.rule("없는-종류-X") is None


def test_seq_wider_than_digits_is_not_truncated():
    conn.x("delete from sys_number_seq where kind = %s and seq_scope = %s", (KIND, OLD_SCOPE))
    r = _rule()
    conn.x("insert into sys_number_seq (kind, seq_scope, last_seq, created_by) values (%s, %s, %s, 'test')",
           (KIND, OLD_SCOPE, 10 ** r["seq_digits"] - 1))
    assert numbering.next(KIND, at=OLD_AT) == f"{r['prefix']}{OLD_SCOPE}{10 ** r['seq_digits']}"
    conn.x("delete from sys_number_seq where kind = %s and seq_scope = %s", (KIND, OLD_SCOPE))


def test_rule_with_bad_characters_is_refused():
    conn.x("""insert into sys_number_rule (kind, prefix, date_format, seq_digits, created_by) values ('TEST_BAD', 'tb/', 'YYMMDD', 3, 'test')
              on conflict (kind) do update set prefix = 'tb/', date_format = 'YYMMDD', use_yn = 'Y'""")
    try:
        with pytest.raises(RuntimeError):
            numbering.peek("TEST_BAD")
    finally:
        conn.x("delete from sys_number_seq where kind = 'TEST_BAD'")
        conn.x("delete from sys_number_rule where kind = 'TEST_BAD'")
