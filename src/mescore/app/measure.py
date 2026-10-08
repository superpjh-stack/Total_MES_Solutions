"""측정값 (E3 · G-C24) — `bas_process_param` 선언 → 폼 칸(`home/_measure.html` 의 `measure_fields`) → `pop_measure` 기록 → 집계(`stats.measure_series` · 개발3).

담당 **개발2**. 공정별 값을 위해 테이블을 만들지 않는다(D-04). 선언 한 행 = 칸 하나 = `pop_measure` 한 행(실적 1건 · 키당 1행).

    params_for(process_id) -> list[dict]                  # use_yn=Y · seq 순. 각 행에 field(폼 이름 m_<key>) · required(bool) 가 붙는다
    parse_form(params, form) -> (values, missing)         # manual 칸만 읽는다. 필수 누락은 missing (라우터가 422)
    record(cur, work_result_id, params, values, *, by)    # 수동 칸 저장 — 범위 이탈은 저장 + deviated (422 아님)
    fill_collect(cur, result, params, *, by)              # collect 칸 — 구간(시작~종료 · 같은 설비)의 eqp_collect 대표값(agg). 수신 0 이면 value NULL(미수집)
    values_of(work_result_id) -> dict[param_key, row]     # 재렌더 · 조회
    deviated(param, value_num) -> bool

검사 항목(`qua_insp_plan`)도 같은 모양으로 그린다 — `plan_fields(plan_rows)` 가 같은 키(param_key · label · value_type …)로 바꿔 준다.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from ..db import conn
from . import collect
from .packs import t

FIELD_PREFIX = "m_"
INSP_PREFIX = "i_"
VALUE_TYPES: tuple[str, ...] = ("number", "text", "bool", "select")


def _decorate(p: dict, prefix: str) -> dict:
    p = dict(p)
    p["field"] = f"{prefix}{p['param_key']}"
    p["required"] = (p.get("required_yn") or "N") == "Y"
    p["is_collect"] = (p.get("source") or "manual") == "collect"
    p["tag"] = p.get("collect_tag") or p["param_key"]
    choices = p.get("choices")
    p["choices"] = list(choices) if isinstance(choices, list) else []
    p["min_value"] = None if p.get("min_value") is None else float(p["min_value"])
    p["max_value"] = None if p.get("max_value") is None else float(p["max_value"])
    p["range_text"] = range_text(p["min_value"], p["max_value"])
    return p


def range_text(lo, hi) -> str:
    if lo is None and hi is None:
        return ""
    if lo is not None and hi is not None:
        return f"{lo:g} ~ {hi:g}"
    return f"{lo:g} {t('이상')}" if lo is not None else f"{hi:g} {t('이하')}"


def params_for(process_id: int | None, cur=None) -> list[dict]:
    """공정의 측정값 선언 (use_yn=Y · seq). 공정이 없으면 []."""
    if process_id is None:
        return []
    sql = "select * from bas_process_param where process_id = %s and use_yn = 'Y' order by seq, id"
    if cur is None:
        rows = conn.q(sql, (int(process_id),))
    else:
        cur.execute(sql, (int(process_id),))
        rows = [dict(r) for r in cur.fetchall()]
    return [_decorate(r, FIELD_PREFIX) for r in rows]


def plan_fields(plan_rows: list[dict]) -> list[dict]:
    """`qua_insp_plan` 항목 → 측정값 칸과 같은 모양 (item_key → param_key · 필수 아님 · 수동)."""
    out = []
    for r in plan_rows:
        out.append(_decorate({"id": r["id"], "param_key": r["item_key"], "label": r["label"], "unit": r.get("unit"), "value_type": r.get("value_type") or "number",
                              "choices": r.get("choices") if isinstance(r.get("choices"), list) else [], "min_value": r.get("min_value"),
                              "max_value": r.get("max_value"), "required_yn": "N", "source": "manual", "standard": r.get("standard"), "seq": r.get("seq")},
                             INSP_PREFIX))
    return out


def deviated(param: Mapping, value_num) -> bool:
    """하한만 · 상한만 · 둘 다 — 있는 쪽만 본다. 값이 없으면 이탈 아님."""
    if value_num is None:
        return False
    v = float(value_num)
    lo, hi = param.get("min_value"), param.get("max_value")
    if lo is not None and v < float(lo):
        return True
    if hi is not None and v > float(hi):
        return True
    return False


def _num(raw: str, p: dict, errs: list[dict]) -> Decimal | None:
    try:
        return Decimal(str(raw).strip())
    except InvalidOperation:
        errs.append({"name": p["field"], "label": t(p["label"]), "reason": t("숫자여야 합니다")})
        return None


def parse_form(params: list[dict], form: Mapping[str, Any]) -> tuple[dict[str, dict], list[dict]]:
    """폼 → {param_key: {"value_num", "value_text"}}. 비운 칸은 행을 만들지 않는다. 필수 누락 · 형식 오류는 둘째 값(라우터가 422).
    collect 칸은 사람이 넣는 값이 아니므로 읽지 않는다."""
    values: dict[str, dict] = {}
    errs: list[dict] = []
    for p in params:
        if p["is_collect"]:
            continue
        raw = form.get(p["field"])
        blank = raw is None or str(raw).strip() == ""
        if blank:
            if p["required"]:
                errs.append({"name": p["field"], "label": t(p["label"]), "reason": t("필수")})
            continue
        vt = p.get("value_type") or "number"
        if vt == "number":
            n = _num(raw, p, errs)
            if n is not None:
                values[p["param_key"]] = {"value_num": n, "value_text": None}
        elif vt == "bool":
            s = str(raw).strip().lower()
            if s not in ("1", "0", "true", "false", "y", "n", "yes", "no", "on", "off"):
                errs.append({"name": p["field"], "label": t(p["label"]), "reason": t("예/아니오 값이어야 합니다")})
                continue
            values[p["param_key"]] = {"value_num": Decimal(1) if s in ("1", "true", "y", "yes", "on") else Decimal(0), "value_text": None}
        elif vt == "select":
            s = str(raw).strip()
            if p["choices"] and s not in [str(c) for c in p["choices"]]:
                errs.append({"name": p["field"], "label": t(p["label"]), "reason": t("선택지에 없는 값입니다")})
                continue
            values[p["param_key"]] = {"value_num": None, "value_text": s}
        else:
            values[p["param_key"]] = {"value_num": None, "value_text": str(raw).strip()}
    return values, errs


def _upsert(cur, work_result_id: int, p: dict, value_num, value_text, source: str, by: str) -> dict:
    dev = deviated(p, value_num)
    cur.execute("""insert into pop_measure (work_result_id, param_id, param_key, value_num, value_text, unit, source, deviated, measured_at, created_by)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
                   on conflict (work_result_id, param_key) do update set param_id = excluded.param_id, value_num = excluded.value_num,
                       value_text = excluded.value_text, unit = excluded.unit, source = excluded.source, deviated = excluded.deviated,
                       measured_at = now(), updated_at = now(), updated_by = excluded.created_by
                   returning *""",
                (int(work_result_id), p.get("id"), p["param_key"], value_num, value_text, p.get("unit"), source, dev, by))
    return dict(cur.fetchone())


def record(cur, work_result_id: int, params: list[dict], values: Mapping[str, Mapping], *, by: str) -> list[dict]:
    """수동 칸 저장 — 실적 1건 · 키당 1행(같은 키는 덮어쓴다). 범위 이탈은 저장하고 `deviated=true`."""
    by_key = {p["param_key"]: p for p in params}
    out = []
    for key, v in values.items():
        p = by_key.get(key)
        if p is None or p["is_collect"]:
            continue
        out.append(_upsert(cur, work_result_id, p, v.get("value_num"), v.get("value_text"), "manual", by))
    return out


def fill_collect(cur, result: Mapping, params: list[dict], *, by: str) -> list[dict]:
    """collect 칸 — 실적 구간(시작~종료)에 같은 설비의 `eqp_collect` 대표값(`agg`). 설비가 없거나 수신 0 이면 value NULL 행(`미수집`) — 필수여도 422 아님."""
    out = []
    equip = result.get("equipment_id")
    frm, to = result.get("started_at"), result.get("ended_at")
    for p in params:
        if not p["is_collect"]:
            continue
        value = None
        if equip is not None and frm is not None and to is not None:
            value = collect.aggregate(equip, p["tag"], frm, to, p.get("agg") or "last")
        out.append(_upsert(cur, result["id"], p, None if value is None else Decimal(str(value)), None, "collect", by))
    return out


def values_of(work_result_id: int, cur=None) -> dict[str, dict]:
    sql = "select * from pop_measure where work_result_id = %s order by id"
    if cur is None:
        rows = conn.q(sql, (int(work_result_id),))
    else:
        cur.execute(sql, (int(work_result_id),))
        rows = [dict(r) for r in cur.fetchall()]
    return {r["param_key"]: r for r in rows}


def display_value(row: Mapping | None) -> str:
    """화면 표시 — 값이 없으면 `미수집`."""
    if row is None:
        return t("미수집")
    if row.get("value_num") is not None:
        v = float(row["value_num"])
        return f"{v:g}"
    return row.get("value_text") or t("미수집")
