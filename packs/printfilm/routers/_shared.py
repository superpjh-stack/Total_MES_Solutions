"""printfilm 라우터 공용 — 롤 조회 · 라벨 데이터 · 폼 해석 (`_` 로 시작하므로 로더가 include 하지 않는다). 쓰기 SQL 없음."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from mescore.app import lineage, printing
from mescore.app.packs import t
from mescore.app.routers import _dev2 as f
from mescore.app.util import http
from mescore.db import conn

ROLL = "ROLL"
PRINT, FINISH, SLIT = "인쇄", "후가공", "슬리팅"
RATIO_Q = Decimal("0.001")                       # 엘컴화인 D-209 — 비율은 소수 셋째 자리까지 저장


def roll_row(lot_id: int) -> dict | None:
    """롤 1행 — lot + ext + Job + 상태."""
    return conn.q1("""select l.id, l.lot_no, l.kind, l.kind_base, l.qty, l.unit, l.made_at, l.insp_status, l.attrs, l.work_order_id, l.work_result_id,
                             l.equipment_id as lot_equipment_id, x.process_type, x.slit_seq, x.equipment_id, e.equip_code, e.equip_name,
                             w.work_order_no, w.status as job_status, i.item_code, i.item_name, s.state
                        from lot l
                        join v_lot_state s on s.lot_id = l.id
                        left join x_printfilm_lot_ext x on x.id = l.id
                        left join bas_equipment e on e.id = x.equipment_id
                        left join job_work_order w on w.id = l.work_order_id
                        left join bas_item i on i.id = l.item_id
                       where l.id = %s""", (int(lot_id),))


def rolls_of(process_type: str, limit: int = 200) -> list[dict]:
    """공정 구분별 롤 목록 + 부모 롤 번호(계보 한 단계)."""
    return conn.q("""select l.id, l.lot_no, l.qty, l.unit, l.made_at, l.insp_status, l.attrs, x.slit_seq, e.equip_code, w.work_order_no, s.state,
                            (select string_agg(p.lot_no, ', ' order by g.id) from lot_genealogy g join lot p on p.id = g.parent_lot_id where g.child_lot_id = l.id) as parents
                       from x_printfilm_lot_ext x
                       join lot l on l.id = x.id
                       join v_lot_state s on s.lot_id = l.id
                       left join bas_equipment e on e.id = x.equipment_id
                       left join job_work_order w on w.id = l.work_order_id
                      where x.process_type = %s
                      order by l.made_at desc, l.id desc limit %s""", (process_type, int(limit)))


def roll_label(lot_id: int, size: str = "100x50") -> dict:
    """printing.label_for + 롤 ext(공정 구분 · 분할 순번) — 팩이 덮어쓴 print/label_lot.html 이 kind=ROLL 분기로 그린다."""
    label = printing.label_for(lot_id, size=size)
    r = roll_row(lot_id) or {}
    label.update({"process_type": r.get("process_type"), "slit_seq": r.get("slit_seq"), "equip_code": r.get("equip_code"),
                  "length_m": (r.get("attrs") or {}).get("length_m"), "width_mm": (r.get("attrs") or {}).get("width_mm")})
    return label


def split_nos(text: str | None) -> list[str]:
    """쉼표 · 공백 · 줄바꿈으로 이은 번호 → 목록(순서 유지)."""
    out: list[str] = []
    for part in (text or "").replace("\n", ",").replace(" ", ",").split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


def require_roll(no: str, *, must_stock: bool = True) -> lineage.Node:
    """번호 → 롤(kind=ROLL). 없는 번호 · 롤 아님 · (must_stock) 재고 아님 → 422."""
    n = lineage.resolve(no)
    if n is None:
        raise http.validation_error(t("없는 롤 번호입니다"), fields=[f.field_error("roll_no", "롤", no)])
    if n.kind != ROLL:
        raise http.validation_error(t("롤이 아닌 번호입니다"), fields=[f.field_error("roll_no", "롤", f"{n.no} {n.kind_label}")])
    if must_stock and n.state != lineage.IN_STOCK:
        raise http.validation_error(t("재고가 아닙니다"), fields=[f.field_error("roll_no", "롤", f"{n.no} {lineage.state_label(n.state)}")])
    return n


def equipment(equipment_id: str | None) -> dict | None:
    eid = f.int_id(equipment_id, "equipment_id", "설비")
    if eid is None:
        return None
    e = conn.q1("select id, equip_code, equip_name, process_id from bas_equipment where id = %s and use_yn = 'Y'", (eid,))
    if e is None:
        raise http.validation_error(t("없는 설비입니다"), fields=[f.field_error("equipment_id", "설비", str(eid))])
    return e


def equipment_options() -> list[tuple]:
    """사용 중인 설비 전부 — 공정 구분별 거름은 attrs 를 WHERE 에 쓰게 되므로(D-05) 하지 않는다."""
    rows = conn.q("select id, equip_code, equip_name from bas_equipment where use_yn = 'Y' order by equip_code")
    return f.options(rows, "id", "equip_code", "equip_name")


def ratio(value, name: str, label: str) -> Decimal:
    """비율 % — 0 초과 100 이하 · 소수 셋째 자리로 반올림(저장되는 값)."""
    if value is None or str(value).strip() == "":
        raise http.validation_error(t("필수 항목이 비었습니다"), fields=[f.field_error(name, label, t("필수"))])
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        raise http.validation_error(t("숫자여야 합니다"), fields=[f.field_error(name, label, str(value))]) from None
    d = d.quantize(RATIO_Q, rounding=ROUND_HALF_UP)
    if d <= 0 or d > 100:
        raise http.validation_error(t("비율은 0 초과 100 이하여야 합니다"), fields=[f.field_error(name, label, str(d))])
    return d


def component_lines(form, *, required: bool) -> list[dict]:
    """성분명 · 비율 N줄 (같은 이름의 폼 칸 여러 개). 빈 줄은 건너뛴다."""
    names, ratios = f.list_form(form, "component_name"), f.list_form(form, "ratio_pct")
    lines = []
    for i, name in enumerate(names):
        nm = (name or "").strip()
        rt = ratios[i] if i < len(ratios) else ""
        if not nm and not (rt or "").strip():
            continue
        if not nm:
            raise http.validation_error(t("성분명이 비었습니다"), fields=[f.field_error("component_name", "성분명", f"#{i + 1}")])
        lines.append({"seq_no": len(lines) + 1, "component_name": nm, "input": (rt or "").strip(), "ratio_pct": ratio(rt, "ratio_pct", "비율")})
    if required and not lines:
        raise http.validation_error(t("성분을 한 줄 이상 넣습니다"), fields=[f.field_error("component_name", "성분명", t("필수"))])
    return lines


def lab(form_value, name: str) -> Decimal | None:
    return f.num(form_value, name, "색상값")


def yn(value: str | None, default: str = "Y") -> str:
    v = (value or "").strip().upper()
    if not v:
        return default
    if v not in ("Y", "N"):
        raise http.validation_error(t("사용 여부는 Y 또는 N"), fields=[f.field_error("use_yn", "사용 여부", v)])
    return v
