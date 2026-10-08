"""kpi 라우터 — 현황판 · 집계 · 지표 정의 (기능 8 · F-KPI-01~08) · 담당 개발3.

쓰는 테이블: **`kpi_indicator` 만**(F-KPI-06 · 07). 집계 SQL 은 이 파일에 없다 — 전부 `app/stats.py`(G-C10). `kpi_snapshot` 은 배치만 쓴다
(`uv run python -m mescore.app.stats snapshot` — Makefile `kpi-snapshot` 요청은 progress-dev3.md §3). 집계 결과를 저장하는 테이블은 없다.
현황판(KPI-01)은 같은 경로가 `Accept: application/json` 이면 **`stats.board()` 그대로**(JSON 폴링 · 접근 로그를 남기지 않는다), 브라우저면 템플릿.
`?device=board` 가 현황판 채널 — 5초 폴링 + 마지막 갱신 시각 · 폴링 실패에도 마지막 값 유지 (api-contract.md §2 · D-602).
CMN-04 대시보드(`routers/dashboard.py`)는 `home` 라우터 목록(13)에 없어 여기서 include 한다 — 읽기만.

  KPI-01 현황판   GET /kpi/board                 F-KPI-01  stats.board
  KPI-02 집계     GET /kpi/summary?kind=         F-KPI-02 production · 03 quality · 04 delivery · 05 equipment (모바일 390px)
  KPI-03 지표 정의 GET/POST /kpi/indicators · POST /kpi/indicators/{id}   F-KPI-06 · 07 · 08
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ...db import conn
from .. import nav, packs, rbac, stats, templating
from ..packs import t
from ..util import audit, http
from . import dashboard

router = APIRouter()
router.include_router(dashboard.router)

CALC_PREFIXES = ("core:", "pack:")


def _period(frm: str, to: str) -> tuple[date, date]:
    try:
        return stats.period(frm, to)
    except ValueError as exc:
        raise http.validation_error(str(exc), fields=[{"name": "frm", "label": t("기간"), "reason": f"{frm} ~ {to}"}]) from None


# ── KPI-01 현황판 ──────────────────────────────────────────────────────
@router.get(nav.path_of("KPI-01"), response_class=HTMLResponse)                     # F-KPI-01 현황판 조회
def board(request: Request, user: rbac.User = rbac.require_fn("F-KPI-01")):
    data = stats.board()
    if not http.wants_html(request):
        return JSONResponse(templating.jsonable(data), headers={"Cache-Control": "no-store"})
    return templating.render(request, "kpi/board.html", {"board": data, "poll_url": f"{nav.path_of('KPI-01')}?device=board"}, screen_id="KPI-01")


# ── KPI-02 집계 ────────────────────────────────────────────────────────
@router.get(nav.path_of("KPI-02"), response_class=HTMLResponse)                     # F-KPI-02~05 집계 조회 (?kind=)
def summary(request: Request, kind: str = "production", frm: str = "", to: str = "", by: str = "", param_key: str = "", agg: str = "avg",
            user: rbac.User = rbac.require_screen("KPI-02")):
    k = stats.KINDS.get(kind)
    if k is None:
        raise http.validation_error(t("집계 종류가 올바르지 않습니다"), fields=[{"name": "kind", "label": t("종류"), "reason": kind}])
    if not user.can(k.fn_id):                                                           # 기능별 권한 — 읽기 기능 4 가 한 경로를 나눠 쓴다
        raise http.forbidden(function_id=k.fn_id)
    d1, d2 = _period(frm, to)
    try:
        section = stats.summary(kind, d1, d2, by=by or None)
        series = stats.measure_series(param_key, d1, d2, by="day", agg=agg) if (kind == "quality" and param_key.strip()) else None
    except ValueError as exc:
        raise http.validation_error(str(exc), fields=[{"name": "by", "label": t("기준"), "reason": by or agg}]) from None
    return templating.render(request, "kpi/summary.html", {
        "kind": kind, "kinds": [{"code": c, "name": v.name, "fn_id": v.fn_id, "by_options": v.by_options, "allowed": user.can(v.fn_id)} for c, v in stats.KINDS.items()],
        "section": section, "by": section["by"], "by_options": k.by_options, "frm": d1, "to": d2, "today": date.today(),
        "param_key": param_key.strip(), "agg": agg, "series": series, "measure_keys": stats.measure_keys() if kind == "quality" else [],
        "aggs": stats.MEASURE_AGG,
    }, screen_id="KPI-02")


# ── KPI-03 지표 정의 ───────────────────────────────────────────────────
def _target(text: str | None) -> Decimal | None:
    if text is None or not str(text).strip():
        return None
    try:
        return Decimal(str(text).strip())
    except InvalidOperation:
        raise http.validation_error(t("목표값은 숫자여야 합니다"), fields=[{"name": "target_value", "label": t("목표값"), "reason": text}]) from None


def _calc_kind(text: str) -> str:
    calc = (text or "").strip()
    if not calc.startswith(CALC_PREFIXES):
        raise http.validation_error(t("산식 종류는 core:<집계 키> 또는 pack:<kpi_extra 키> 입니다"), fields=[{"name": "calc_kind", "label": t("산식"), "reason": calc}])
    kind, _, key = calc.partition(":")
    if kind == "core" and key not in stats.CORE_METRIC_KEYS:
        raise http.validation_error(t("코어 집계 키가 아닙니다") + f": {' · '.join(stats.CORE_METRIC_KEYS)}", fields=[{"name": "calc_kind", "label": t("산식"), "reason": calc}])
    if kind == "pack" and not packs.has_hook("kpi_extra"):
        raise http.validation_error(t("이 팩에는 kpi_extra 훅이 없습니다"), fields=[{"name": "calc_kind", "label": t("산식"), "reason": calc}])
    return calc


def _indicator(indicator_id: int) -> dict:
    row = conn.q1("select * from kpi_indicator where id = %s", (indicator_id,))
    if row is None:
        raise http.not_found()
    return row


@router.get(nav.path_of("KPI-03"), response_class=HTMLResponse)                     # F-KPI-08 지표 조회
def indicators(request: Request, frm: str = "", to: str = "", id: str = "", user: rbac.User = rbac.require_fn("F-KPI-08")):
    d1, d2 = _period(frm, to) if (frm or to) else (date.today(), date.today())
    rows = stats.indicators(d1, d2)
    opened = None
    if id.strip():
        if not id.strip().isdigit():
            raise http.not_found()
        opened = _indicator(int(id))
    pack_keys = [m["key"] for m in stats.kpi_extra(d1, d2)]
    return templating.render(request, "kpi/indicators.html", {
        "rows": rows, "opened": opened, "frm": d1, "to": d2, "core_keys": stats.CORE_METRIC_KEYS, "pack_keys": pack_keys,
        "can_write": user.can("F-KPI-06"),
    }, screen_id="KPI-03")


@router.post(nav.path_of("KPI-03"))                                                  # F-KPI-06 지표 등록 (관리자 · 범위 지표)
def create_indicator(request: Request, indicator_key: str = Form(""), name: str = Form(""), unit: str = Form(""), target_value: str = Form(""),
                     calc_kind: str = Form(""), visible_yn: str = Form("Y"), seq: str = Form("0"), user: rbac.User = rbac.require_fn("F-KPI-06")):
    key, nm = indicator_key.strip(), name.strip()
    missing = [{"name": n, "label": t(l), "reason": t("비어 있음")} for n, l, v in (("indicator_key", "지표 키", key), ("name", "이름", nm)) if not v]
    if missing:
        raise http.validation_error(t("필수값을 입력해 주세요"), fields=missing)
    if conn.q1("select 1 from kpi_indicator where indicator_key = %s", (key,)):
        raise http.validation_error(t("이미 있는 지표 키입니다"), fields=[{"name": "indicator_key", "label": t("지표 키"), "reason": key}])
    calc = _calc_kind(calc_kind)
    target = _target(target_value)
    row = {"indicator_key": key, "name": nm, "unit": unit.strip() or None, "target_value": target, "calc_kind": calc,
           "visible_yn": "Y" if (visible_yn or "Y").upper() == "Y" else "N", "seq": int(seq) if str(seq).strip().lstrip("-").isdigit() else 0}
    with conn.tx() as cur:
        packs.hook("validate_kpi_indicator")(cur, row, user)
        cur.execute("""insert into kpi_indicator (indicator_key, name, unit, target_value, calc_kind, visible_yn, seq, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                    (key, nm, row["unit"], target, calc, row["visible_yn"], row["seq"], user.login_id))
        row["id"] = cur.fetchone()["id"]
        packs.hook("after_save_kpi_indicator")(cur, row, user)
    audit.log_change(request, user, "F-KPI-06", f"kpi_indicator:{key}")
    return http.saved(request, t("지표를 등록했습니다"), back=f"{nav.path_of('KPI-03')}?id={row['id']}", data={"id": row["id"], "indicator_key": key})


@router.post(nav.path_of("KPI-03") + "/{indicator_id}")                               # F-KPI-07 지표 수정 — 목표값 · 표시 여부 (+ 이름 · 단위 · 순서)
def update_indicator(request: Request, indicator_id: int, target_value: str = Form(None), clear_target: str = Form(""), visible_yn: str = Form(None),
                     name: str = Form(None), unit: str = Form(None), seq: str = Form(None), user: rbac.User = rbac.require_fn("F-KPI-07")):
    """빈 폼 값은 "바꾸지 않음"(FastAPI 가 빈 문자열을 None 으로 준다). 목표값을 지워 `미확정` 으로 되돌리려면 `clear_target=1`."""
    ind = _indicator(indicator_id)
    row = {**ind,
           "target_value": None if clear_target.strip() in ("1", "Y", "y", "true") else (_target(target_value) if target_value is not None else ind["target_value"]),
           "visible_yn": ("Y" if visible_yn.upper() == "Y" else "N") if visible_yn is not None and visible_yn.strip() else ind["visible_yn"],
           "name": name.strip() if name is not None and name.strip() else ind["name"],
           "unit": (unit.strip() or None) if unit is not None else ind["unit"],
           "seq": int(seq) if seq is not None and str(seq).strip().lstrip("-").isdigit() else ind["seq"]}
    with conn.tx() as cur:
        packs.hook("validate_kpi_indicator")(cur, row, user)
        cur.execute("""update kpi_indicator set target_value = %s, visible_yn = %s, name = %s, unit = %s, seq = %s, updated_at = now(), updated_by = %s where id = %s""",
                    (row["target_value"], row["visible_yn"], row["name"], row["unit"], row["seq"], user.login_id, indicator_id))
        packs.hook("after_save_kpi_indicator")(cur, row, user)
    audit.log_change(request, user, "F-KPI-07", f"kpi_indicator:{ind['indicator_key']}")
    return http.saved(request, t("지표를 수정했습니다"), back=f"{nav.path_of('KPI-03')}?id={indicator_id}",
                      data={"id": indicator_id, "indicator_key": ind["indicator_key"], "visible_yn": row["visible_yn"],
                            "target_value": float(row["target_value"]) if row["target_value"] is not None else None})
