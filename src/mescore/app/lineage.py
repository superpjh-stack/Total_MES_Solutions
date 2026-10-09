"""계보 — `lot` · `lot_genealogy` 에 쓰고(화살표 한 줄 = 부모 LOT → 자식 LOT) 그 기록을 따라 읽는 **한 곳** (G-C06 · G-C07).

담당 **개발2**. 시그니처 공표는 `progress-dev2.md` §1. 개발3 의 출하(`ship` · `unship`) · 추적(`trace_*`) 은 여기 함수만 부른다.
**다른 모듈은 `lot_genealogy` 에 직접 쓰지 않는다.** 생산 LOT · 출하 LOT 도 여기서만 만든다(번호는 `numbering` 뿐).

지킬 것
  · 추적은 조회 하나다(`with recursive` 한 문장). 경로 · 결과를 어디에도 저장하지 않는다. 깊이 · 분기를 가정하지 않는다.
  · 쓰기 함수는 전부 `cur`(`conn.tx()` 의 커서)를 받는다. LOT 생성과 계보 행이 한 트랜잭션이어야 한다.
  · 검증 실패는 `http.validation_error`(422). DB 지킴이 트리거(순환 · 자기참조 · 유니크)는 마지막 방어선이다.
  · 관계 · 종류는 `core.yaml` + 팩 등록(`packs.current().lineage`) — 팩 관계는 `base` 로 동작한다(`relation_base` 컬럼 저장).
  · LOT 상태(재고 · 소진 · 출하) · 잔량은 저장하지 않는다 — `v_lot_state` · `v_lot_stock`.
  · 훅: LOT 행 생성 전 `validate_lot(cur, row, user)` · 후 `after_save_lot` · `on_lot_created`. `user` 는 라우터가 넘긴 `rbac.User`(없으면 None).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..db import conn
from . import packs
from .packs import t
from .util import http

#: 코어 관계 5 (core.yaml: lineage.relations) — 팩 관계는 relation(name).base 로 이 다섯 중 하나에 귀속된다
INPUT, PRODUCE, SPLIT, MERGE, SHIP = "투입", "생산", "분할", "합병", "출하"
CORE_RELATIONS: tuple[str, ...] = (INPUT, PRODUCE, SPLIT, MERGE, SHIP)
#: 코어 LOT 종류 3 (lot.kind_base)
MATERIAL, PRODUCT, SHIPMENT = "MATERIAL", "PRODUCT", "SHIPMENT"
#: 상태 — v_lot_state.state 의 값. 표시어는 packs.current().lineage["states"]
IN_STOCK, CONSUMED, SHIPPED = "재고", "소진", "출하"
FORWARD, BACKWARD = "forward", "backward"
#: kind_base → 채번 종류 (interfaces.md §3). 팩 kind(예: ROLL · base PRODUCT) 도 base 의 종류를 쓴다
NUMBERING_KIND = {MATERIAL: "LOT_MATERIAL", PRODUCT: "LOT_PRODUCT", SHIPMENT: "LOT_SHIPMENT"}
USABLE_INSP = ("합격", "조건부")


@dataclass(frozen=True)
class Relation:
    name: str
    base: str


@dataclass(frozen=True)
class LotKind:
    kind: str
    base: str
    label: str


@dataclass(frozen=True)
class Node:
    id: int
    no: str
    kind: str
    kind_label: str
    item: str | None               # 품목명 (SHIPMENT 는 None)
    state: str                     # 재고 | 소진 | 출하
    work_order_no: str | None
    qty: float | None
    unit: str | None
    kind_base: str = PRODUCT
    item_id: int | None = None
    item_code: str | None = None
    insp_status: str | None = None
    work_order_id: int | None = None
    shipment_id: int | None = None
    remain_qty: float | None = None
    made_at: Any = None


@dataclass(frozen=True)
class Edge:
    genealogy_id: int
    parent: Node
    child: Node
    relation: str
    relation_base: str
    qty: float | None
    depth: int                     # 출발점에서 몇 번째 화살표인가 (1부터 · 최단)


@dataclass(frozen=True)
class Trace:
    start: Node
    direction: str                 # forward | backward
    edges: list[Edge] = field(default_factory=list)   # 중복 없음 · 출발점에서 가까운 순

    def nodes(self) -> list[Node]:
        """출발점 포함 지나간 노드 전부(중복 없음). 출발점이 맨 앞."""
        seen: dict[int, Node] = {self.start.id: self.start}
        for e in self.edges:
            near, far = (e.parent, e.child) if self.direction == FORWARD else (e.child, e.parent)
            seen.setdefault(near.id, near)
            seen.setdefault(far.id, far)
        return list(seen.values())

    def by_kind(self, kind: str) -> list[Node]:
        """kind 또는 kind_base 가 같은 노드."""
        return [n for n in self.nodes() if n.kind == kind or n.kind_base == kind]

    def materials(self) -> list[Node]:
        return [n for n in self.nodes() if n.kind_base == MATERIAL]

    def shipments(self) -> list[Node]:
        return [n for n in self.nodes() if n.kind_base == SHIPMENT]

    def stock(self) -> list[Node]:
        """재고로 남은 생산 LOT (정방향 추적에서 자식 없이 끝난 것)."""
        return [n for n in self.nodes() if n.kind_base == PRODUCT and n.state == IN_STOCK]

    def products(self) -> list[Node]:
        return [n for n in self.nodes() if n.kind_base == PRODUCT]


# ── 관계 · 종류 (매니페스트) ────────────────────────────────────────────
def relations() -> dict[str, Relation]:
    return {r["name"]: Relation(r["name"], r["base"]) for r in packs.current().lineage["relations"]}


def relation(name: str) -> Relation:
    rel = relations().get(name)
    if rel is None:
        raise http.validation_error(t("모르는 계보 관계입니다"), fields=[{"name": "relation", "label": t("관계"), "reason": str(name)}])
    return rel


def lot_kinds() -> dict[str, LotKind]:
    return {k["kind"]: LotKind(k["kind"], k["base"], k["label"]) for k in packs.current().lineage["lot_kinds"]}


def lot_kind(kind: str) -> LotKind:
    lk = lot_kinds().get(kind)
    if lk is None:
        raise http.validation_error(t("모르는 LOT 종류입니다"), fields=[{"name": "kind", "label": t("LOT 종류"), "reason": str(kind)}])
    return lk


def kind_label(kind: str) -> str:
    lk = lot_kinds().get(kind)
    return t(lk.label) if lk else kind


def state_label(state: str) -> str:
    return packs.current().lineage["states"].get({IN_STOCK: "IN_STOCK", CONSUMED: "CONSUMED", SHIPPED: "SHIPPED"}.get(state, ""), state)


# ── 내부: 번호 · 조회 ──────────────────────────────────────────────────
def _numbering():
    """채번은 개발1 의 `app/numbering.py` 뿐. 파일이 아직 없으면 지어내지 않고 그대로 실패한다."""
    from . import numbering  # noqa: PLC0415 — 개발1 모듈. 기동 시점이 아니라 쓰는 시점에 찾는다 (D-26 과 같은 취급)
    return numbering


def next_no(kind: str, cur) -> str:
    return _numbering().next(kind, cur=cur)


def _rows(cur, sql: str, params=None) -> list[dict]:
    if cur is None:
        return conn.q(sql, params)
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def _one(cur, sql: str, params=None) -> dict | None:
    rows = _rows(cur, sql, params)
    return rows[0] if rows else None


def _num(v) -> float | None:
    return None if v is None else float(v)


#: 노드 한 모양 — lot ⋈ v_lot_state ⋈ v_lot_stock ⋈ bas_item ⋈ job_work_order
_NODE_SQL = """
select l.id, l.lot_no as no, l.kind, l.kind_base, l.item_id, i.item_code, i.item_name, s.state, k.remain_qty,
       w.work_order_no, l.work_order_id, l.qty, l.unit, l.insp_status, l.shipment_id, l.made_at
  from lot l
  join v_lot_state s on s.lot_id = l.id
  join v_lot_stock k on k.lot_id = l.id
  left join bas_item i on i.id = l.item_id
  left join job_work_order w on w.id = l.work_order_id
"""


def _node_of(r: dict) -> Node:
    return Node(id=r["id"], no=r["no"], kind=r["kind"], kind_label=kind_label(r["kind"]), item=r["item_name"], state=r["state"],
                work_order_no=r["work_order_no"], qty=_num(r["qty"]), unit=r["unit"], kind_base=r["kind_base"], item_id=r["item_id"],
                item_code=r["item_code"], insp_status=r["insp_status"], work_order_id=r["work_order_id"], shipment_id=r["shipment_id"],
                remain_qty=_num(r["remain_qty"]), made_at=r["made_at"])


def node(lot_id: int, cur=None) -> Node | None:
    r = _one(cur, _NODE_SQL + " where l.id = %s", (int(lot_id),))
    return _node_of(r) if r else None


def nodes(lot_ids: list[int], cur=None) -> dict[int, Node]:
    if not lot_ids:
        return {}
    return {r["id"]: _node_of(r) for r in _rows(cur, _NODE_SQL + " where l.id = any(%s)", ([int(x) for x in lot_ids],))}


def _require_node(cur, lot_id, label: str = "LOT") -> Node:
    try:
        lid = int(lot_id)
    except (TypeError, ValueError):
        raise http.validation_error(t("LOT 을 가리키는 값이 아닙니다"), fields=[{"name": "lot_id", "label": t(label), "reason": repr(lot_id)}]) from None
    n = node(lid, cur)
    if n is None:
        raise http.validation_error(t("없는 LOT 입니다"), fields=[{"name": "lot_id", "label": t(label), "reason": str(lid)}])
    return n


# ── 쓰기 ────────────────────────────────────────────────────────────────
def link(cur, parent_id: int, child_id: int, relation_name: str, *, by: str, qty=None, at=None) -> int:
    """화살표 한 줄. 자기 참조 · 순환 · 모르는 relation · 없는 LOT 은 422. `relation_base` 를 채운다. genealogy_id 를 돌려준다.
    `at` 은 연결 시각(`linked_at` — 이관 22 의 원본 시각). 없으면 now()."""
    rel = relation(relation_name)
    p, c = _require_node(cur, parent_id, "부모 LOT"), _require_node(cur, child_id, "자식 LOT")
    if p.id == c.id:
        raise http.validation_error(t("자기 자신을 부모로 하는 계보는 만들 수 없습니다"), fields=[{"name": "lot_id", "label": t("LOT"), "reason": p.no}])
    hit = _one(cur, """with recursive down (lot_id) as (
                           select %(child)s::bigint
                           union
                           select g.child_lot_id from lot_genealogy g join down d on g.parent_lot_id = d.lot_id)
                       select 1 as hit from down where lot_id = %(parent)s limit 1""", {"child": c.id, "parent": p.id})
    if hit:
        raise http.validation_error(t("계보 순환 — 자손 LOT 을 부모로 쓸 수 없습니다"),
                                    fields=[{"name": "lot_id", "label": t("LOT"), "reason": f"{p.no} 은 {c.no} 의 자손"}])
    if _one(cur, "select 1 as x from lot_genealogy where parent_lot_id = %s and child_lot_id = %s and relation = %s", (p.id, c.id, rel.name)):
        raise http.validation_error(t("이미 있는 계보입니다"), fields=[{"name": "relation", "label": t("관계"), "reason": f"{p.no} → {c.no} ({rel.name})"}])
    row = _one(cur, """insert into lot_genealogy (parent_lot_id, child_lot_id, relation, relation_base, qty, linked_at, linked_by, created_by)
                       values (%s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s) returning id""",
               (p.id, c.id, rel.name, rel.base, qty, at, by, by))
    return int(row["id"])


def assert_usable(cur, lot_ids) -> None:
    """투입 · 분할 · 합병 · 출하에 쓸 수 있는가 — PRODUCT 는 `재고`, MATERIAL 은 합격(또는 조건부)이고 소진 전. 아니면 422."""
    ids = [int(x) for x in (lot_ids if isinstance(lot_ids, (list, tuple, set)) else [lot_ids])]
    found = nodes(ids, cur)
    for lid in ids:
        n = found.get(lid)
        if n is None:
            raise http.validation_error(t("없는 LOT 입니다"), fields=[{"name": "lot_id", "label": t("LOT"), "reason": str(lid)}])
        if n.kind_base == SHIPMENT:
            raise http.validation_error(t("출하 LOT 은 쓸 수 없습니다"), fields=[{"name": "lot_id", "label": t("출하 LOT"), "reason": n.no}])
        if n.kind_base == MATERIAL:
            if n.insp_status not in USABLE_INSP:
                raise http.validation_error(t("검사에 통과하지 않은 원재료 LOT 입니다"),
                                            fields=[{"name": "lot_id", "label": t("원재료 LOT"), "reason": f"{n.no} {n.insp_status}"}])
            if n.state == CONSUMED:
                raise http.validation_error(t("소진된 원재료 LOT 입니다"), fields=[{"name": "lot_id", "label": t("원재료 LOT"), "reason": n.no}])
        elif n.state != IN_STOCK:
            raise http.validation_error(t("재고 상태가 아닌 LOT 입니다"),
                                        fields=[{"name": "lot_id", "label": t("생산 LOT"), "reason": f"{n.no} {state_label(n.state)}"}])


def _insert_lot(cur, row: dict, *, by: str, user=None) -> dict:
    """lot 한 행 — validate_lot → insert → after_save_lot · on_lot_created. 번호는 numbering(없으면 row["lot_no"])."""
    lk = lot_kind(row["kind"])
    row = dict(row, kind_base=lk.base, attrs=row.get("attrs") or {})
    if not row.get("lot_no"):
        row["lot_no"] = next_no(NUMBERING_KIND[lk.base], cur)
    packs.hook("validate_lot")(cur, row, user)
    import json  # noqa: PLC0415

    saved = _one(cur, """insert into lot (lot_no, kind, kind_base, item_id, work_order_id, process_id, equipment_id, work_result_id, partner_id,
                                          shipment_id, qty, unit, insp_status, made_at, note, attrs, created_by)
                         values (%(lot_no)s, %(kind)s, %(kind_base)s, %(item_id)s, %(work_order_id)s, %(process_id)s, %(equipment_id)s,
                                 %(work_result_id)s, %(partner_id)s, %(shipment_id)s, %(qty)s, %(unit)s, %(insp_status)s,
                                 coalesce(%(made_at)s, now()), %(note)s, %(attrs)s::jsonb, %(by)s)
                         returning *""",
                 {"lot_no": row["lot_no"], "kind": row["kind"], "kind_base": row["kind_base"], "item_id": row.get("item_id"),
                  "work_order_id": row.get("work_order_id"), "process_id": row.get("process_id"), "equipment_id": row.get("equipment_id"),
                  "work_result_id": row.get("work_result_id"), "partner_id": row.get("partner_id"), "shipment_id": row.get("shipment_id"),
                  "qty": row.get("qty"), "unit": row.get("unit"), "insp_status": row.get("insp_status") or "미검사",
                  "made_at": row.get("made_at"), "note": row.get("note"), "attrs": json.dumps(row["attrs"], ensure_ascii=False, default=str), "by": by})
    packs.hook("after_save_lot")(cur, saved, user)
    packs.hook("on_lot_created")(cur, saved, user)
    return saved


def make_material_lot(cur, *, item_id: int, qty, unit: str | None, by: str, partner_id: int | None = None, lot_no: str | None = None,
                      made_at=None, attrs: dict | None = None, insp_status: str = "미검사", note: str | None = None, kind: str = MATERIAL,
                      user=None) -> dict:
    """원재료 LOT (F-MAT-01 · 이관 B-MIG-03). `lot_no` 를 주면 그 번호(이관 · 시드), 없으면 `LOT_MATERIAL` 채번."""
    if lot_kind(kind).base != MATERIAL:
        raise http.validation_error(t("원재료 LOT 종류가 아닙니다"), fields=[{"name": "kind", "label": t("LOT 종류"), "reason": kind}])
    return _insert_lot(cur, {"lot_no": lot_no, "kind": kind, "item_id": item_id, "partner_id": partner_id, "qty": qty, "unit": unit,
                             "insp_status": insp_status, "made_at": made_at, "note": note, "attrs": attrs}, by=by, user=user)


def _lock_work_order(cur, work_order_id: int | None) -> dict | None:
    """지시에 무엇을 붙이는 쪽은 `for share` (interfaces.md §1). 마감 · 취소된 지시에는 붙이지 않는다."""
    if work_order_id is None:
        return None
    wo = _one(cur, "select * from job_work_order where id = %s for share", (int(work_order_id),))
    if wo is None:
        raise http.validation_error(t("없는 작업지시입니다"), fields=[{"name": "work_order_id", "label": t("작업지시"), "reason": str(work_order_id)}])
    if wo["status"] in ("마감", "취소"):
        raise http.validation_error(t("마감 · 취소된 작업지시에는 LOT 을 붙일 수 없습니다"),
                                    fields=[{"name": "work_order_id", "label": t("작업지시"), "reason": f"{wo['work_order_no']} {wo['status']}"}])
    return wo


def make_product_lot(cur, *, work_result_id: int, by: str, kind: str = PRODUCT, qty=None, unit: str | None = None, attrs: dict | None = None,
                     parent_id: int | None = None, merge_parent_ids=None, merge_relation: str = MERGE, user=None) -> dict:
    """F-POP-03 종료 — 생산 LOT 1 + 그 실적의 `pop_input`(취소 제외) 마다 `투입` 계보 한 줄. `parent_id` 를 주면 앞 공정 LOT 과 `생산` 1:1.
    `merge_parent_ids` 를 주면 그 LOT 들(재고인 생산 LOT · 1 개 이상)을 새 LOT 에 `merge_relation`(base 합병) 으로 잇는다 — 별도 합병 LOT 없이
    "투입 + 합병 → 이 실적의 한 LOT". 실적에 이미 생산 LOT 이 있으면 422. 수량은 `qty` → 실적 양품 수량 순."""
    if lot_kind(kind).base != PRODUCT:
        raise http.validation_error(t("생산 LOT 종류가 아닙니다"), fields=[{"name": "kind", "label": t("LOT 종류"), "reason": kind}])
    r = _one(cur, "select * from pop_work_result where id = %s for update", (int(work_result_id),))
    if r is None:
        raise http.validation_error(t("없는 실적입니다"), fields=[{"name": "work_result_id", "label": t("실적"), "reason": str(work_result_id)}])
    if r["product_lot_id"] is not None:
        raise http.validation_error(t("이미 생산 LOT 이 있는 실적입니다"), fields=[{"name": "work_result_id", "label": t("실적"), "reason": str(r["id"])}])
    wo = _lock_work_order(cur, r["work_order_id"])
    inputs = _rows(cur, """select material_lot_id, sum(qty) as qty from pop_input
                            where work_result_id = %s and canceled_yn = 'N' group by material_lot_id order by material_lot_id""", (r["id"],))
    if inputs:
        assert_usable_inputs = [i["material_lot_id"] for i in inputs]
        # 투입 LOT 은 스캔 때 검사했다. 여기서는 존재만 다시 본다(소진 LOT 도 이 실적이 쓴 것이면 계보에 남아야 한다).
        found = nodes(assert_usable_inputs, cur)
        missing = [x for x in assert_usable_inputs if x not in found]
        if missing:
            raise http.validation_error(t("없는 LOT 입니다"), fields=[{"name": "material_lot_id", "label": t("원재료 LOT"), "reason": str(missing)}])
    parent = _require_node(cur, parent_id, "앞 공정 LOT") if parent_id is not None else None
    if parent is not None:
        assert_usable(cur, [parent.id])
    merge_parents = _merge_parents(cur, merge_parent_ids, merge_relation) if merge_parent_ids else []
    lot = _insert_lot(cur, {"kind": kind, "item_id": wo["item_id"] if wo else None, "work_order_id": r["work_order_id"], "process_id": r["process_id"],
                            "equipment_id": r["equipment_id"], "work_result_id": r["id"], "qty": qty if qty is not None else r["good_qty"],
                            "unit": unit or r["unit"] or (wo["unit"] if wo else None), "insp_status": "미검사", "attrs": attrs}, by=by, user=user)
    for i in inputs:
        link(cur, i["material_lot_id"], lot["id"], INPUT, by=by, qty=i["qty"])
    if parent is not None:
        link(cur, parent.id, lot["id"], PRODUCE, by=by, qty=parent.remain_qty)
    for m in merge_parents:
        link(cur, m.id, lot["id"], merge_relation, by=by, qty=m.remain_qty)
    cur.execute("update pop_work_result set product_lot_id = %s, updated_at = now(), updated_by = %s where id = %s", (lot["id"], by, r["id"]))
    return lot


def inherit_insp(statuses) -> str:
    """분할 · 합병 자식의 `insp_status` — 부모가 **전부 합격** → 합격 · **불합격이 하나라도** → 불합격 · 미검사가 하나라도 → 미검사 ·
    그 밖(합격 + 조건부) → 조건부. 부모가 하나면 그 값 그대로."""
    vals = [s or "미검사" for s in statuses]
    if not vals:
        return "미검사"
    if "불합격" in vals:
        return "불합격"
    if all(v == "합격" for v in vals):
        return "합격"
    if "미검사" in vals:
        return "미검사"
    return "조건부"


def _merge_parents(cur, parent_ids, relation_name: str) -> list[Node]:
    """make_product_lot 의 합병 부모 — base 합병 관계 · 중복 없음 · 전부 재고인 생산 LOT."""
    relation_of_base(relation_name, MERGE)
    ids: list[int] = []
    for x in parent_ids:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            raise http.validation_error(t("LOT 을 가리키는 값이 아닙니다"), fields=[{"name": "merge_lot_ids", "label": t("합병 LOT"), "reason": repr(x)}]) from None
    if len(set(ids)) != len(ids):
        raise http.validation_error(t("같은 LOT 이 두 번 들어 있습니다"), fields=[{"name": "merge_lot_ids", "label": t("합병 LOT"), "reason": str(ids)}])
    found = nodes(ids, cur)
    missing = [i for i in ids if i not in found]
    if missing:
        raise http.validation_error(t("없는 LOT 입니다"), fields=[{"name": "merge_lot_ids", "label": t("합병 LOT"), "reason": str(missing)}])
    bad = [found[i].no for i in ids if found[i].kind_base != PRODUCT]
    if bad:
        raise http.validation_error(t("생산 LOT 만 합병할 수 있습니다"), fields=[{"name": "merge_lot_ids", "label": t("합병 LOT"), "reason": str(bad)}])
    assert_usable(cur, ids)
    return [found[i] for i in ids]


def _qty_list(qtys, count: int) -> list:
    if qtys is None:
        return [None] * count
    vals = [None if q in (None, "") else Decimal(str(q)) for q in qtys]
    if len(vals) != count:
        raise http.validation_error(t("분할 수량의 개수가 분할 수와 다릅니다"), fields=[{"name": "qtys", "label": t("분할 수량"), "reason": f"{len(vals)} ≠ {count}"}])
    if any(q is not None and q <= 0 for q in vals):
        raise http.validation_error(t("분할 수량은 0 보다 커야 합니다"), fields=[{"name": "qtys", "label": t("분할 수량"), "reason": str(qtys)}])
    return vals


def split(cur, *, parent_id: int, count: int, by: str, qtys=None, relation: str = SPLIT, kind: str | None = None,
          process_id: int | None = None, equipment_id: int | None = None, attrs: dict | None = None, user=None) -> list[dict]:
    """1 → N. 코어 `분할` 은 N ≥ 2, 팩이 등록한 분할 계열 관계는 N ≥ 1(부분 분할 — merge 와 대칭). 부모는 재고인 생산 LOT.
    `relation` 은 base 가 `분할` 인 관계. `process_id · equipment_id · attrs` 는 D-503. 자식 `insp_status` 는 부모 값을 잇는다(`inherit_insp`)."""
    rel = relation_of_base(relation, SPLIT)
    try:
        n = int(count)
    except (TypeError, ValueError):
        raise http.validation_error(t("분할 수는 정수여야 합니다"), fields=[{"name": "count", "label": t("분할 수"), "reason": repr(count)}]) from None
    least = 2 if rel.name == SPLIT else 1
    if n < least:
        raise http.validation_error(t("분할은 2 이상으로 나눕니다") if least == 2 else t("분할 수는 1 이상입니다"),
                                    fields=[{"name": "count", "label": t("분할 수"), "reason": f"{n} < {least}"}])
    parent = _require_node(cur, parent_id, "부모 LOT")
    if parent.kind_base != PRODUCT:
        raise http.validation_error(t("생산 LOT 만 분할할 수 있습니다"), fields=[{"name": "parent_id", "label": t("LOT"), "reason": f"{parent.no} {parent.kind}"}])
    assert_usable(cur, [parent.id])
    vals = _qty_list(qtys, n)
    given = [q for q in vals if q is not None]
    if given and parent.remain_qty is not None and sum(given) > Decimal(str(parent.remain_qty)) + Decimal("0.0005"):
        raise http.validation_error(t("분할 수량의 합이 잔량을 넘습니다"),
                                    fields=[{"name": "qtys", "label": t("분할 수량"), "reason": f"{sum(given)} > {parent.remain_qty}"}])
    _lock_work_order(cur, parent.work_order_id)
    base = _one(cur, "select * from lot where id = %s", (parent.id,))
    children: list[dict] = []
    for i in range(n):
        child = _insert_lot(cur, {"kind": kind or base["kind"], "item_id": base["item_id"], "work_order_id": base["work_order_id"],
                                  "process_id": process_id if process_id is not None else base["process_id"],
                                  "equipment_id": equipment_id if equipment_id is not None else base["equipment_id"],
                                  "work_result_id": base["work_result_id"], "qty": vals[i], "unit": base["unit"], "insp_status": inherit_insp([parent.insp_status]),
                                  "attrs": attrs if attrs is not None else {}}, by=by, user=user)
        link(cur, parent.id, child["id"], rel.name, by=by, qty=vals[i])
        children.append(child)
    return children


def relation_of_base(name: str, base: str) -> Relation:
    rel = relation(name)
    if rel.base != base:
        raise http.validation_error(t("이 작업에 쓸 수 없는 관계입니다"), fields=[{"name": "relation", "label": t("관계"), "reason": f"{name} (base {rel.base} ≠ {base})"}])
    return rel


def merge(cur, *, parent_ids, by: str, qty=None, relation: str = MERGE, kind: str | None = None,
          process_id: int | None = None, equipment_id: int | None = None, attrs: dict | None = None, user=None) -> dict:
    """N → 1. 코어 `합병` 은 N ≥ 2, 팩이 등록한 합병 계열 관계(1:1 이어붙임 포함)는 N ≥ 1. 부모는 전부 재고인 생산 LOT. 수량은 `qty` → 부모 잔량 합.
    자식 `insp_status` 는 부모들에서 잇는다(`inherit_insp`)."""
    rel = relation_of_base(relation, MERGE)
    ids: list[int] = []
    for x in (parent_ids or []):
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            raise http.validation_error(t("LOT 을 가리키는 값이 아닙니다"), fields=[{"name": "parent_ids", "label": t("LOT"), "reason": repr(x)}]) from None
    if len(set(ids)) != len(ids):
        raise http.validation_error(t("같은 LOT 이 두 번 들어 있습니다"), fields=[{"name": "parent_ids", "label": t("LOT"), "reason": str(ids)}])
    least = 2 if rel.name == MERGE else 1
    if len(ids) < least:
        raise http.validation_error(t("합병할 LOT 이 모자랍니다"), fields=[{"name": "parent_ids", "label": t("LOT"), "reason": f"{len(ids)} < {least}"}])
    found = nodes(ids, cur)
    parents = [found[i] for i in ids if i in found]
    if len(parents) != len(ids):
        raise http.validation_error(t("없는 LOT 입니다"), fields=[{"name": "parent_ids", "label": t("LOT"), "reason": str([i for i in ids if i not in found])}])
    bad = [p.no for p in parents if p.kind_base != PRODUCT]
    if bad:
        raise http.validation_error(t("생산 LOT 만 합병할 수 있습니다"), fields=[{"name": "parent_ids", "label": t("LOT"), "reason": str(bad)}])
    assert_usable(cur, ids)
    wo_ids = {p.work_order_id for p in parents}
    work_order_id = parents[0].work_order_id if len(wo_ids) == 1 else None
    _lock_work_order(cur, work_order_id)
    first = _one(cur, "select * from lot where id = %s", (parents[0].id,))
    total = qty
    if total is None and all(p.remain_qty is not None for p in parents):
        total = sum(Decimal(str(p.remain_qty)) for p in parents)
    child = _insert_lot(cur, {"kind": kind or first["kind"], "item_id": first["item_id"], "work_order_id": work_order_id,
                              "process_id": process_id if process_id is not None else first["process_id"],
                              "equipment_id": equipment_id if equipment_id is not None else first["equipment_id"],
                              "qty": total, "unit": first["unit"], "insp_status": inherit_insp([p.insp_status for p in parents]),
                              "attrs": attrs if attrs is not None else {}}, by=by, user=user)
    for p in parents:
        link(cur, p.id, child["id"], rel.name, by=by, qty=p.remain_qty)
    return child


def _shipment(cur, shipment_id) -> dict:
    s = _one(cur, "select * from shp_shipment where id = %s for update", (int(shipment_id),))
    if s is None:
        raise http.validation_error(t("없는 출하입니다"), fields=[{"name": "shipment_id", "label": t("출하"), "reason": str(shipment_id)}])
    if s["status"] != "등록":
        raise http.validation_error(t("등록 상태의 출하에만 LOT 을 담거나 뺄 수 있습니다"),
                                    fields=[{"name": "shipment_id", "label": t("출하"), "reason": f"{s['shipment_no']} {s['status']}"}])
    return s


def shipment_lot(cur, shipment_id: int) -> dict | None:
    """출하 헤더의 출하 LOT 행(kind_base SHIPMENT) — 없으면 None. 읽기만."""
    return _one(cur, "select * from lot where shipment_id = %s and kind_base = %s order by id limit 1", (int(shipment_id), SHIPMENT))


def ship(cur, *, shipment_id: int, lot_id: int, by: str, user=None) -> int:
    """F-SHP-05 (개발3). 출하 LOT 이 없으면 만든다(`LOT_SHIPMENT` 채번 · 거래처는 출하 헤더). 생산 LOT → 출하 LOT `출하` 한 줄.
    이미 출하된 · 소진된 · 불합격 LOT 은 422."""
    s = _shipment(cur, shipment_id)
    n = _require_node(cur, lot_id, "LOT")
    if n.kind_base != PRODUCT:
        raise http.validation_error(t("생산 LOT 만 출하할 수 있습니다"), fields=[{"name": "lot_id", "label": t("LOT"), "reason": f"{n.no} {n.kind}"}])
    if n.state == SHIPPED:
        raise http.validation_error(t("이미 출하된 LOT 입니다"), fields=[{"name": "lot_id", "label": t("생산 LOT"), "reason": n.no}])
    if n.state == CONSUMED:
        raise http.validation_error(t("다음 공정에 쓰인(소진) LOT 은 출하할 수 없습니다"), fields=[{"name": "lot_id", "label": t("생산 LOT"), "reason": n.no}])
    if n.insp_status == "불합격":
        raise http.validation_error(t("최신 검사가 불합격인 LOT 은 출하할 수 없습니다"), fields=[{"name": "lot_id", "label": t("생산 LOT"), "reason": n.no}])
    x = shipment_lot(cur, s["id"])
    if x is None:
        x = _insert_lot(cur, {"kind": SHIPMENT, "shipment_id": s["id"], "partner_id": s["partner_id"], "unit": n.unit, "insp_status": "미검사",
                              "note": s["shipment_no"]}, by=by, user=user)
    return link(cur, n.id, x["id"], SHIP, by=by, qty=n.remain_qty)


def unship(cur, *, shipment_id: int, lot_id: int, by: str, user=None) -> int:
    """F-SHP-06 (개발3). 그 출하의 출하 LOT 으로 가는 `출하` 화살표를 지운다. 없으면 422. 지운 행 수."""
    s = _shipment(cur, shipment_id)
    n = _require_node(cur, lot_id, "LOT")
    x = shipment_lot(cur, s["id"])
    if x is None:
        raise http.validation_error(t("이 출하에 담긴 LOT 이 없습니다"), fields=[{"name": "shipment_id", "label": t("출하"), "reason": s["shipment_no"]}])
    cur.execute("delete from lot_genealogy where parent_lot_id = %s and child_lot_id = %s and relation_base = %s", (n.id, x["id"], SHIP))
    if cur.rowcount == 0:
        raise http.validation_error(t("이 출하에 담기지 않은 LOT 입니다"), fields=[{"name": "lot_id", "label": t("생산 LOT"), "reason": n.no}])
    return cur.rowcount


def _stock_move(cur, *, item_id: int, lot_id: int, qty, unit: str | None, trx_type: str, ref_table: str, ref_id: int, reason: str | None, by: str) -> None:
    """투입 소비 · 취소의 재고 거래 + 현재고 — mat_stock* 은 lineage 와 mat 라우터만 쓴다."""
    cur.execute("""insert into mat_stock_trx (item_id, lot_id, trx_type, qty, unit, ref_table, ref_id, reason, created_by)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""", (item_id, lot_id, trx_type, qty, unit, ref_table, ref_id, reason, by))
    cur.execute("""insert into mat_stock (item_id, qty, unit, created_by) values (%s, %s, %s, %s)
                   on conflict (item_id) do update set qty = mat_stock.qty + excluded.qty, unit = coalesce(mat_stock.unit, excluded.unit),
                                                       updated_at = now(), updated_by = excluded.created_by""", (item_id, qty, unit, by))


def consume_material(cur, *, work_result_id: int, material_lot_id: int, qty, by: str, unit: str | None = None) -> int:
    """F-POP-06 투입 스캔 → `pop_input` 한 행(계보는 종료 때). 불합격 · 미검사 · 소진 LOT · 잔량 부족 · 종료된 실적은 422.
    원재료(MATERIAL)면 재고 거래 `투입` −qty + 현재고 갱신. 반제품(PRODUCT 재고) 투입도 받는다. pop_input.id 를 돌려준다."""
    r = _one(cur, "select * from pop_work_result where id = %s for update", (int(work_result_id),))
    if r is None:
        raise http.validation_error(t("없는 실적입니다"), fields=[{"name": "work_result_id", "label": t("실적"), "reason": str(work_result_id)}])
    if r["ended_at"] is not None:
        raise http.validation_error(t("종료된 실적에는 투입할 수 없습니다"), fields=[{"name": "work_result_id", "label": t("실적"), "reason": str(r["id"])}])
    n = _require_node(cur, material_lot_id, "원재료 LOT")
    assert_usable(cur, [n.id])
    q = None if qty in (None, "") else Decimal(str(qty))
    if q is not None and q <= 0:
        raise http.validation_error(t("투입량은 0 보다 커야 합니다"), fields=[{"name": "qty", "label": t("투입량"), "reason": str(qty)}])
    if q is not None and n.remain_qty is not None and q > Decimal(str(n.remain_qty)) + Decimal("0.0005"):
        raise http.validation_error(t("투입량이 LOT 잔량을 넘습니다"), fields=[{"name": "qty", "label": t("투입량"), "reason": f"{q} > {n.remain_qty}"}])
    row = _one(cur, """insert into pop_input (work_result_id, material_lot_id, qty, unit, created_by) values (%s, %s, %s, %s, %s) returning id""",
               (r["id"], n.id, q, unit or n.unit, by))
    if q is not None and n.kind_base == MATERIAL and n.item_id is not None:
        _stock_move(cur, item_id=n.item_id, lot_id=n.id, qty=-q, unit=unit or n.unit, trx_type="투입", ref_table="pop_input", ref_id=row["id"],
                    reason=None, by=by)
    return int(row["id"])


def cancel_consume(cur, *, input_id: int, by: str) -> int:
    """F-POP-07 투입 취소 — 실적 종료 전만. 취소 표시 + 재고 거래 되돌림(원재료). 취소한 pop_input.id."""
    i = _one(cur, "select i.*, r.ended_at from pop_input i join pop_work_result r on r.id = i.work_result_id where i.id = %s for update of i", (int(input_id),))
    if i is None:
        raise http.not_found(t("없는 투입입니다"))
    if i["ended_at"] is not None:
        raise http.validation_error(t("종료된 실적의 투입은 취소할 수 없습니다"), fields=[{"name": "input_id", "label": t("투입"), "reason": str(i["id"])}])
    if i["canceled_yn"] == "Y":
        raise http.validation_error(t("이미 취소한 투입입니다"), fields=[{"name": "input_id", "label": t("투입"), "reason": str(i["id"])}])
    cur.execute("update pop_input set canceled_yn = 'Y', updated_at = now(), updated_by = %s where id = %s", (by, i["id"]))
    n = node(i["material_lot_id"], cur)
    if i["qty"] is not None and n is not None and n.kind_base == MATERIAL and n.item_id is not None:
        _stock_move(cur, item_id=n.item_id, lot_id=n.id, qty=i["qty"], unit=i["unit"], trx_type="투입", ref_table="pop_input", ref_id=i["id"],
                    reason=t("투입 취소"), by=by)
    return int(i["id"])


def retag(cur, lot_id: int, kind: str, *, by: str | None = None) -> dict:
    """팩이 LOT 종류를 바꾼다(예: PRODUCT → ROLL · pack-contract.md §5 on_result_closed). base 는 등록된 kind 의 base 로."""
    lk = lot_kind(kind)
    row = _one(cur, "update lot set kind = %s, kind_base = %s, updated_at = now(), updated_by = %s where id = %s returning *", (lk.kind, lk.base, by, int(lot_id)))
    if row is None:
        raise http.validation_error(t("없는 LOT 입니다"), fields=[{"name": "lot_id", "label": t("LOT"), "reason": str(lot_id)}])
    return row


# ── 읽기 — 어떤 테이블에도 쓰지 않는다 ────────────────────────────────
def resolve(no: str, cur=None) -> Node | None:
    """번호(스캔값) → LOT. 앞뒤 공백만 벗긴다 — 글자는 바꾸지 않는다. 없으면 None (라우터가 422 로)."""
    if no is None or str(no).strip() == "":
        return None
    r = _one(cur, _NODE_SQL + " where l.lot_no = %s", (str(no).strip(),))
    return _node_of(r) if r else None


def search(text: str, limit: int = 50) -> list[Node]:
    """F-TRC-03 — LOT 번호 · 품목 코드 · 품목명 · 지시 번호 부분 일치. 최근 생성 순."""
    q = (text or "").strip()
    if not q:
        return []
    rows = conn.q(_NODE_SQL + """ where l.lot_no ilike %(p)s or i.item_code ilike %(p)s or i.item_name ilike %(p)s or w.work_order_no ilike %(p)s
                                  order by l.made_at desc, l.id desc limit %(n)s""", {"p": f"%{q}%", "n": int(limit)})
    return [_node_of(r) for r in rows]


def state(lot_id: int) -> str:
    r = conn.q1("select state from v_lot_state where lot_id = %s", (int(lot_id),))
    if r is None:
        raise http.not_found(t("없는 LOT 입니다"))
    return r["state"]


_WALK = """
with recursive walk (gid, next_id, depth) as (
    select g.id, g.{next_col}, 1 from lot_genealogy g where g.{start_col} = %(id)s
    union
    select g.id, g.{next_col}, w.depth + 1 from lot_genealogy g join walk w on g.{join_col} = w.next_id
), hit as (
    select gid, min(depth) as depth from walk group by gid
), n as (""" + _NODE_SQL + """
)
select g.id as genealogy_id, g.relation, g.relation_base, g.qty, h.depth,
       row_to_json(p) as parent, row_to_json(c) as child
  from hit h
  join lot_genealogy g on g.id = h.gid
  join n p on p.id = g.parent_lot_id
  join n c on c.id = g.child_lot_id
 order by h.depth, g.id
"""


def _edges(rows: list[dict]) -> list[Edge]:
    out = []
    for r in rows:
        out.append(Edge(genealogy_id=r["genealogy_id"], parent=_node_of(r["parent"]), child=_node_of(r["child"]), relation=r["relation"],
                        relation_base=r["relation_base"], qty=_num(r["qty"]), depth=int(r["depth"])))
    return out


def _walk(lot_id: int, direction: str, cur=None) -> list[Edge]:
    if direction == FORWARD:
        sql = _WALK.format(next_col="child_lot_id", start_col="parent_lot_id", join_col="parent_lot_id")
    else:
        sql = _WALK.format(next_col="parent_lot_id", start_col="child_lot_id", join_col="child_lot_id")
    return _edges(_rows(cur, sql, {"id": int(lot_id)}))


def _start(lot_id: int, cur=None) -> Node:
    n = node(lot_id, cur)
    if n is None:
        raise http.not_found(t("없는 LOT 입니다"))
    return n


def trace_forward(lot_id: int, cur=None) -> Trace:
    """F-TRC-01 — 이 LOT 에서 자손 쪽으로. 재귀 조회 하나, 경로 저장 0."""
    return Trace(_start(lot_id, cur), FORWARD, _walk(lot_id, FORWARD, cur))


def trace_backward(lot_id: int, cur=None) -> Trace:
    """F-TRC-02 — 이 LOT 에서 조상 쪽으로(출하 LOT → 원재료 LOT)."""
    return Trace(_start(lot_id, cur), BACKWARD, _walk(lot_id, BACKWARD, cur))


def parents_of(lot_id: int, cur=None) -> list[Edge]:
    return [e for e in _walk(lot_id, BACKWARD, cur) if e.depth == 1]


def children_of(lot_id: int, cur=None) -> list[Edge]:
    return [e for e in _walk(lot_id, FORWARD, cur) if e.depth == 1]


def genealogy_rows(lot_ids: list[int], cur=None) -> list[dict]:
    """이 LOT 들이 부모 또는 자식인 계보 행 — 검사 · 화면용 (G-C06 행 수 세기)."""
    if not lot_ids:
        return []
    return _rows(cur, """select g.id, g.parent_lot_id, g.child_lot_id, g.relation, g.relation_base, g.qty, g.linked_at
                           from lot_genealogy g where g.parent_lot_id = any(%(ids)s) or g.child_lot_id = any(%(ids)s) order by g.id""",
                 {"ids": [int(x) for x in lot_ids]})
