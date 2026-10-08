"""훅 단위 — 코어 폼이 attrs 를 아직 넘기지 않는 자리(ord_order · qua_issue · 코어 버그 progress-dev1.md §3 ①)를 dict 로 직접 검증 + 코어 중립 흐름(R9) 통과."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from mescore.app.util.http import HookError
from mescore.db import conn

from _helpers import MENU, PORK, item_id

from packs.foodservice import hooks


class _User:
    login_id = "unit"
    device = "web"


class _Rollback(Exception):
    pass


def _tx():
    return conn.tx()


def test_validate_qua_issue_claim_requires_partner():
    """S8-b — 클레임 이슈는 고객사 필수."""
    with pytest.raises(HookError) as exc:
        hooks.validate_qua_issue(None, {"content": "x", "attrs": {"issue_type": "클레임"}}, _User())
    assert "고객사" in exc.value.message and exc.value.fields[0]["name"] == "attr_partner_code"
    hooks.validate_qua_issue(None, {"content": "x", "attrs": {"issue_type": "클레임", "partner_code": "CUS-001"}}, _User())
    hooks.validate_qua_issue(None, {"content": "x", "attrs": {"issue_type": "이물"}}, _User())
    hooks.validate_qua_issue(None, {"content": "x"}, _User())


def test_after_save_ord_order_copies_due_time_and_service_type():
    order = conn.q1("select id from ord_order order by id desc limit 1")
    assert order, "수주가 하나는 있어야 한다 (seed_dev3)"
    try:
        with _tx() as cur:
            hooks.after_save_ord_order(cur, {"id": order["id"], "attrs": {"due_time": "11:30", "service_type": "위탁급식"}}, _User())
            cur.execute("select due_time, service_type from x_foodservice_order_ext where id = %s", (order["id"],))
            row = cur.fetchone()
            assert str(row["due_time"]) == "11:30:00" and row["service_type"] == "위탁급식"
            with pytest.raises(HookError):
                hooks.after_save_ord_order(cur, {"id": order["id"], "attrs": {"due_time": "11시30분"}}, _User())
            with pytest.raises(HookError):
                hooks.after_save_ord_order(cur, {"id": order["id"], "attrs": {"service_type": "학교급식"}}, _User())
            raise _Rollback
    except _Rollback:
        pass
    assert conn.q1("select 1 as hit from x_foodservice_order_ext where id = %s", (order["id"],)) is None   # 되돌아갔다


def test_after_save_qua_insp_plan_parses_sampling_freq():
    plan = conn.q1("select id from qua_insp_plan where insp_type = '최종' order by id limit 1")
    try:
        with _tx() as cur:
            hooks.after_save_qua_insp_plan(cur, {"id": plan["id"], "attrs": {"sample_freq": "10솥당 1솥", "apply_from": "2026-08-01"}}, _User())
            cur.execute("select * from x_foodservice_insp_plan_ext where id = %s", (plan["id"],))
            row = cur.fetchone()
            assert row["sample_n"] == 10 and row["sample_k"] == 1 and row["apply_from"] == date(2026, 8, 1)
            raise _Rollback
    except _Rollback:
        pass


def test_per_serving_and_core_neutral_items():
    """D-502 1인량 = 배합량 ÷ 배치 기준인분 · 코어 예시 품목(-EX-) 은 급식 규칙 밖(R9)."""
    assert hooks._per_serving(Decimal("12.000"), Decimal("100")) == Decimal("0.12")
    with pytest.raises(HookError):
        hooks._per_serving(Decimal("12.000"), 0)
    with _tx() as cur:
        assert hooks._pack_item(cur, item_id(MENU)) is not None and hooks._pack_item(cur, item_id(PORK)) is not None
        ex = cur.execute("select id from bas_item where item_code = 'PRD-EX-01'").fetchone()
        assert ex and hooks._pack_item(cur, ex["id"]) is None
        hooks.validate_job_work_order(cur, {"item_id": ex["id"], "process_id": None, "unit": "EA"}, _User())      # 통과 — 코어 중립
        hooks.validate_bas_bom(cur, {"item_id": ex["id"], "version": "9", "use_yn": "Y", "attrs": {}}, _User())  # 통과
