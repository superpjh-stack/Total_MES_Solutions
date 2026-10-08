"""kimchi 팩 공용 — 라우터 6 · 훅이 같이 쓰는 조회 · 판정 헬퍼 (개발3 · 2026-10-09). **쓰기는 `x_kimchi_lot_ext` 만**(ensure_lot_ext).

임계값 · 기준은 전부 데이터에서 읽는다 — `bas_process_param` · `x_kimchi_item_std` · `qua_insp_plan`. 값이 없으면 None 을 돌려주고 호출자가 판정하지 않는다.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mescore.app.packs import t  # noqa: E402
from mescore.app.routers import _dev2 as f  # noqa: E402 — 폼 값 해석 · 스캔 422 재렌더 (코어 공용 헬퍼 · 읽기만)
from mescore.app.util import http  # noqa: E402
from mescore.db import conn  # noqa: E402

from packs.kimchi.adapters import collect_tags as tags  # noqa: E402

DEFAULT_AGING_DAYS = 21          # 임진강 "3주" — x_kimchi_item_std(aging_days) 가 없을 때만 (D-511)
AGING_DAYS_KEY = "aging_days"
SALTING_PROCESS, AGING_PROCESS, PRETREAT_PROCESS, MIX_PROCESS, METAL_PROCESS, PACK_PROCESS = "P03", "P09", "P02", "P06", "P07", "P08"
CCP_KEYS: tuple[str, ...] = ("metal_detect", "mix_ccp", "pack_weight_kg")
UNDECIDED_SENSOR = "미확정 (D-206)"


# ── DB (cur 가 있으면 그 트랜잭션 안에서) ────────────────────────────────
def rows(cur, sql: str, params=None) -> list[dict]:
    if cur is None:
        return conn.q(sql, params)
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def one(cur, sql: str, params=None) -> dict | None:
    out = rows(cur, sql, params)
    return out[0] if out else None


def dec(v) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def num(v) -> float | None:
    return None if v is None else float(v)


# ── 기준정보 ───────────────────────────────────────────────────────────
def process(cur, code: str) -> dict | None:
    return one(cur, "select id, process_code, process_name from bas_process where process_code = %s", (code,))


def process_id(cur, code: str) -> int | None:
    p = process(cur, code)
    return p["id"] if p else None


def process_code_of(cur, process_id_: int | None) -> str | None:
    if process_id_ is None:
        return None
    r = one(cur, "select process_code from bas_process where id = %s", (int(process_id_),))
    return r["process_code"] if r else None


def equipment(cur, equipment_id: int | None) -> dict | None:
    if equipment_id is None:
        return None
    return one(cur, "select * from bas_equipment where id = %s", (int(equipment_id),))


def equipment_by_code(cur, code: str) -> dict | None:
    return one(cur, "select * from bas_equipment where equip_code = %s", (code,))


def equipment_of_type(cur, kind: str, *, collect: str | None = None) -> list[dict]:
    """종류별 설비 — `attrs.equip_type` 또는 (예시) CSV 표. attrs 는 WHERE 에 쓰지 않는다(D-05) — 파이썬에서 거른다."""
    out = []
    for e in rows(cur, "select * from bas_equipment where use_yn = 'Y' order by equip_code"):
        if tags.is_type(e["equip_code"], kind, e.get("attrs") or {}) and (collect is None or e["collect_yn"] == collect):
            out.append(e)
    return out


def item_of_work_order(cur, work_order_id: int | None) -> dict | None:
    if work_order_id is None:
        return None
    return one(cur, "select i.* from job_work_order w join bas_item i on i.id = w.item_id where w.id = %s", (int(work_order_id),))


# ── 품목별 공정 조건 (x_kimchi_item_std) ─────────────────────────────────
def std_for(cur, item_id: int | None, param_key: str, *, size_type: str | None = None, process_code: str = SALTING_PROCESS, at: date | None = None) -> dict | None:
    """품목 × 키 (× 크기구분) 의 기준 — 적용 시작일이 지난 것 중 최신. 크기구분 행이 없으면 전체(NULL) 행. 없으면 None (미확정)."""
    if item_id is None:
        return None
    day = at or date.today()
    r = rows(cur, """select s.* from x_kimchi_item_std s join bas_process p on p.id = s.process_id
                      where s.item_id = %s and s.param_key = %s and p.process_code = %s and s.use_yn = 'Y' and s.valid_from <= %s
                        and (s.size_type is null or s.size_type = %s)
                      order by (s.size_type is not null) desc, s.valid_from desc, s.id desc limit 1""",
             (int(item_id), param_key, process_code, day, size_type))
    return r[0] if r else None


def aging_days(cur, item_id: int | None) -> tuple[int, str]:
    """(일수, 출처) — 품목 기준(aging_days) 이 있으면 그것, 없으면 21 (D-511)."""
    s = std_for(cur, item_id, AGING_DAYS_KEY, process_code=AGING_PROCESS)
    if s and s["std_value"] is not None:
        return int(s["std_value"]), f"x_kimchi_item_std:{s['id']}"
    return DEFAULT_AGING_DAYS, "D-511"


def param_for(cur, equipment_id: int | None, tag: str) -> dict | None:
    """설비의 공정에 선언된 collect 측정값 정의 (collect_tag 또는 param_key = 태그). 없으면 None."""
    if equipment_id is None:
        return None
    return one(cur, """select p.* from bas_process_param p join bas_equipment e on e.process_id = p.process_id
                        where e.id = %s and p.source = 'collect' and p.use_yn = 'Y' and coalesce(p.collect_tag, p.param_key) = %s
                        order by p.seq, p.id limit 1""", (int(equipment_id), tag))


def param_by_code(cur, process_code: str, param_key: str) -> dict | None:
    return one(cur, "select p.* from bas_process_param p join bas_process c on c.id = p.process_id where c.process_code = %s and p.param_key = %s",
               (process_code, param_key))


def out_of_range(value, lo, hi) -> bool:
    """하한 · 상한 중 있는 쪽만 본다. 둘 다 없으면 판정하지 않는다(False)."""
    if value is None or (lo is None and hi is None):
        return False
    v = Decimal(str(value))
    if lo is not None and v < Decimal(str(lo)):
        return True
    if hi is not None and v > Decimal(str(hi)):
        return True
    return False


def limit_text(lo, hi, unit: str | None = None) -> str:
    u = f" {unit}" if unit else ""
    if lo is not None and hi is not None:
        return f"{num(lo):g} ~ {num(hi):g}{u}"
    if lo is not None:
        return f"min {num(lo):g}{u}"
    if hi is not None:
        return f"max {num(hi):g}{u}"
    return t("미확정")


# ── 절임통 배치 ────────────────────────────────────────────────────────
def tank_row(cur, work_result_id: int) -> dict | None:
    return one(cur, """select k.*, r.started_at, r.ended_at, r.product_lot_id, r.work_order_id, r.process_id
                        from x_kimchi_tank k join pop_work_result r on r.id = k.id where k.id = %s""", (int(work_result_id),))


def open_tank_for_sensor(cur, sensor_equipment_id: int, sensor_code: str) -> dict | None:
    """센서에 연결된 미완료 절임통 배치 — (1) 배치의 sensor_equipment_id, (2) 고정 매핑 표(미확정이면 빈 표). 없으면 None."""
    r = one(cur, """select k.*, r.started_at, r.ended_at, r.product_lot_id, r.work_order_id from x_kimchi_tank k join pop_work_result r on r.id = k.id
                     where k.sensor_equipment_id = %s and k.status <> '완료' order by k.created_at desc limit 1""", (int(sensor_equipment_id),))
    if r:
        return r
    code = tags.tank_code_for(sensor_code)
    if not code:
        return None
    return one(cur, """select k.*, r.started_at, r.ended_at, r.product_lot_id, r.work_order_id from x_kimchi_tank k join pop_work_result r on r.id = k.id
                        join bas_equipment e on e.id = k.equipment_id where e.equip_code = %s and k.status <> '완료' order by k.created_at desc limit 1""", (code,))


def tank_tolerance(cur, tank: dict) -> Decimal | None:
    """배치가 적용한 절임 조건의 허용편차 — NULL 이면 판정하지 않는다(미확정 임진강 D-08)."""
    if tank.get("std_id") is None:
        return None
    s = one(cur, "select tolerance from x_kimchi_item_std where id = %s", (tank["std_id"],))
    return dec(s["tolerance"]) if s else None


# ── LOT 확장 (유일한 쓰기) ─────────────────────────────────────────────
def ensure_lot_ext(cur, lot_id: int, by: str, **cols) -> dict:
    """`x_kimchi_lot_ext` upsert — 준 컬럼만 바꾼다. 행이 없으면 만든다."""
    allowed = ("aging_start_date", "aging_due_date", "aging_end_date", "shippable_yn", "location_equipment_id", "tank_equipment_id")
    bad = [k for k in cols if k not in allowed]
    if bad:
        raise ValueError(f"x_kimchi_lot_ext 에 없는 컬럼 {bad}")
    cur.execute("insert into x_kimchi_lot_ext (id, created_by) values (%s, %s) on conflict (id) do nothing", (int(lot_id), by))
    if cols:
        sets = ", ".join(f"{k} = %({k})s" for k in cols)
        cur.execute(f"update x_kimchi_lot_ext set {sets}, updated_at = now(), updated_by = %(by)s where id = %(id)s", {**cols, "by": by, "id": int(lot_id)})
    cur.execute("select * from x_kimchi_lot_ext where id = %s", (int(lot_id),))
    return dict(cur.fetchone())


def lot_ext(cur, lot_id: int) -> dict | None:
    return one(cur, "select * from x_kimchi_lot_ext where id = %s", (int(lot_id),))


def resolve_lot(no: str | None, lot_id: str | None, label: str = "생산 LOT"):
    """스캔값(번호) 또는 id → lineage.Node. 없으면 422."""
    from mescore.app import lineage

    n = lineage.resolve(no) if f.opt_text(no) else lineage.node(f.int_id(lot_id, "lot_id", label, required=True))
    if n is None:
        raise http.validation_error(t("없는 LOT 번호입니다"), fields=[f.field_error("lot_no", label, no or lot_id or "")])
    return n
