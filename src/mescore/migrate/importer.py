"""표준 Import 파일 4종 — 규격 · 리더 · 적재기 (`contracts/migration-files.md` 의 코드 쪽 원본). 담당 개발3.

- 파일은 UTF-8 CSV(BOM 허용), 첫 줄 헤더. 표준 헤더 밖의 열은 `attrs.<헤더>` 로 들어간다. 빈 칸은 NULL.
- 형식이 틀린 행 · 참조 코드가 없는 행 · 같은 파일 안 키 중복은 **그 줄만** 오류로 남기고 계속한다(조용히 고쳐 넣지 않는다).
- 멱등: 파일의 키로 찾아 있으면 갱신, 없으면 적재. `inserted` 는 `xmax = 0`(새 행) 로 센다.
- 번호는 파일 값 그대로(채번 안 함 · `sys_number_seq` 안 올림). 형식 검사만(영문 대문자 · 숫자 · `-`).
- 적재 행은 `created_by = 'migrate'` · `attrs.migrated_from = <파일명>`.
- 계보(22)는 **`lineage.link` 로만** 넣는다 — 이 파일에 `lot_genealogy` 에 쓰는 SQL 은 없다(읽어서 중복만 거른다).
- SHIPMENT 종류의 LOT(21)은 `lot.shipment_id` 가 꼭 있어야 하므로(CHECK) 같은 폴더의 `34_shipments.csv` 에서 그 LOT 의 출하 헤더를 찾아
  먼저 적재한다(D-301). 헤더가 없으면 그 줄 오류.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from ..app import packs

TEXT, INT, DECIMAL, DATE, DATETIME, YN, CHOICE, NO = "text", "int", "decimal", "date", "datetime", "yn", "choice", "no"
LOADED_BY = "migrate"
NO_RE = re.compile(r"^[A-Z0-9-]+$")
INSERTED, UPDATED, SKIPPED = "inserted", "updated", "skipped"
CORE_RELATIONS = ("투입", "생산", "분할", "합병", "출하")


class RowProblem(Exception):
    """적재할 수 없는 줄 — 사유. 그 줄만 오류로 남기고 다음 줄로 간다."""


@dataclass(frozen=True)
class Col:
    name: str
    kind: str = TEXT
    required: bool = False
    choices: tuple[str, ...] = ()
    default: str | None = None
    desc: str = ""


@dataclass(frozen=True)
class FileSpec:
    file: str                         # 01_items.csv
    table: str                        # 대상 테이블(설명용 — 둘 이상이면 첫 것)
    key: tuple[str, ...]              # 같은 파일 안 중복 검사 · upsert 기준
    cols: tuple[Col, ...]
    desc: str = ""

    @property
    def names(self) -> set[str]:
        return {c.name for c in self.cols}


@dataclass
class RowError:
    line: int
    key: str
    reason: str

    def text(self) -> str:
        return f"{self.line}행 [{self.key}] {self.reason}"

    def as_dict(self) -> dict:
        return {"line": self.line, "key": self.key, "reason": self.reason}


@dataclass
class Row:
    line: int
    values: dict[str, Any]
    attrs: dict[str, str] = field(default_factory=dict)

    def key_text(self, spec: FileSpec) -> str:
        return " · ".join(str(self.values.get(k) or "") for k in spec.key)


@dataclass
class FileResult:
    spec: FileSpec
    path: Path | None
    rows: list[Row] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    read: int = 0

    def fail(self, line: int, key: str, reason: str) -> None:
        self.errors.append(RowError(line, key, reason))


# ── 값 변환 ─────────────────────────────────────────────────────────────
def _convert(col: Col, raw: str | None) -> Any:
    text = (raw or "").strip()
    if text == "":
        if col.required:
            raise RowProblem(f"{col.name}: 필수")
        text = col.default if col.default is not None else None
        if text is None:
            return None
    if col.kind == TEXT:
        return text
    if col.kind == NO:
        if not NO_RE.match(text):
            raise RowProblem(f"{col.name}: 번호 형식(영문 대문자 · 숫자 · -)이 아니다 {text!r}")
        return text
    if col.kind == INT:
        try:
            return int(text)
        except ValueError:
            raise RowProblem(f"{col.name}: 정수가 아니다 {text!r}") from None
    if col.kind == DECIMAL:
        try:
            return Decimal(text.replace(",", ""))
        except InvalidOperation:
            raise RowProblem(f"{col.name}: 숫자가 아니다 {text!r}") from None
    if col.kind == DATE:
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise RowProblem(f"{col.name}: 날짜(YYYY-MM-DD)가 아니다 {text!r}") from None
    if col.kind == DATETIME:
        try:
            return datetime.fromisoformat(text.replace("T", " "))
        except ValueError:
            raise RowProblem(f"{col.name}: 일시(YYYY-MM-DD HH:MM:SS)가 아니다 {text!r}") from None
    if col.kind == YN:
        v = text.upper()
        if v not in ("Y", "N"):
            raise RowProblem(f"{col.name}: Y/N 이 아니다 {text!r}")
        return v
    if col.kind == CHOICE:
        if text not in col.choices:
            raise RowProblem(f"{col.name}: {' / '.join(col.choices)} 중 하나가 아니다 {text!r}")
        return text
    raise ValueError(f"모르는 열 형식 {col.kind}")


def read_file(path: Path, spec: FileSpec) -> FileResult:
    """CSV 한 파일을 읽어 형식 검사한다. DB 에는 쓰지 않는다."""
    res = FileResult(spec, path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c.name for c in spec.cols if c.required and c.name not in headers]
        if missing:
            res.fail(1, spec.file, f"필수 헤더 없음: {', '.join(missing)}")
            return res
        seen: dict[tuple, int] = {}
        for i, raw in enumerate(reader, start=2):
            res.read += 1
            raw = {(k or "").strip(): v for k, v in raw.items()}
            values: dict[str, Any] = {}
            try:
                for col in spec.cols:
                    values[col.name] = _convert(col, raw.get(col.name))
            except RowProblem as exc:
                res.fail(i, " · ".join(str(raw.get(k) or "") for k in spec.key), str(exc))
                continue
            key = tuple(values.get(k) for k in spec.key)
            if key in seen:
                res.fail(i, " · ".join(str(k) for k in key), f"같은 파일 안 키 중복 ({seen[key]}행)")
                continue
            seen[key] = i
            attrs = {k: (v or "").strip() for k, v in raw.items() if k and k not in spec.names and (v or "").strip()}
            res.rows.append(Row(i, values, attrs))
    return res


# ── 규격 — 파일 4종 세트 ────────────────────────────────────────────────
_USE = Col("use_yn", YN, default="Y")

SPECS: dict[str, FileSpec] = {s.file: s for s in (
    FileSpec("01_items.csv", "bas_item", ("item_code",), (
        Col("item_code", required=True), Col("item_name", required=True),
        Col("item_type", CHOICE, required=True, choices=("제품", "반제품", "원재료", "부자재")), Col("spec"), Col("unit"), _USE), "품목"),
    FileSpec("02_partners.csv", "bas_partner", ("partner_code",), (
        Col("partner_code", required=True), Col("partner_name", required=True),
        Col("partner_type", CHOICE, required=True, choices=("고객", "공급", "외주")), Col("contact"), _USE), "거래처"),
    FileSpec("03_processes.csv", "bas_process", ("process_code",), (
        Col("process_code", required=True), Col("process_name", required=True), Col("seq", INT, default="0"), _USE), "공정"),
    FileSpec("04_process_params.csv", "bas_process_param", ("process_code", "param_key"), (
        Col("process_code", required=True), Col("param_key", required=True), Col("label", required=True), Col("unit"),
        Col("value_type", CHOICE, choices=("number", "text", "bool", "select"), default="number"),
        Col("min_value", DECIMAL), Col("max_value", DECIMAL), Col("required_yn", YN, default="N"),
        Col("source", CHOICE, choices=("manual", "collect"), default="manual"),
        Col("agg", CHOICE, choices=("last", "avg", "max", "min"), default="last"), Col("seq", INT, default="0")), "공정 측정값 정의"),
    FileSpec("05_equipment.csv", "bas_equipment", ("equip_code",), (
        Col("equip_code", required=True), Col("equip_name", required=True), Col("process_code"), Col("collect_yn", YN, default="N"), _USE), "설비"),
    FileSpec("06_bom.csv", "bas_bom", ("item_code", "component_code"), (
        Col("item_code", required=True), Col("version", default="1"), Col("component_code", required=True),
        Col("qty", DECIMAL, required=True), Col("unit"), Col("loss_rate", DECIMAL, default="0")), "BOM"),
    FileSpec("07_workers.csv", "bas_worker", ("worker_code",), (
        Col("worker_code", required=True), Col("worker_name", required=True), Col("process_code"), _USE), "작업자"),
    FileSpec("08_defect_codes.csv", "bas_defect_code", ("defect_code",), (
        Col("defect_code", required=True), Col("defect_name", required=True), Col("process_code"), _USE), "불량코드"),
    FileSpec("09_codes.csv", "bas_code", ("group_code", "code"), (
        Col("group_code", required=True), Col("code", required=True), Col("code_name", required=True), Col("seq", INT, default="0"), _USE), "공통코드"),
    FileSpec("11_orders.csv", "ord_order", ("order_no", "line_no"), (
        Col("order_no", NO, required=True), Col("partner_code", required=True), Col("order_date", DATE, required=True), Col("due_date", DATE),
        Col("line_no", INT, required=True), Col("item_code", required=True), Col("qty", DECIMAL, required=True), Col("unit"),
        Col("status", CHOICE, choices=("등록", "진행", "완료", "취소"), default="등록")), "수주 + 상세"),
    FileSpec("12_work_orders.csv", "job_work_order", ("work_order_no",), (
        Col("work_order_no", NO, required=True), Col("item_code", required=True), Col("process_code", required=True), Col("equip_code"),
        Col("plan_qty", DECIMAL, required=True), Col("unit"), Col("plan_date", DATE), Col("order_no", NO), Col("line_no", INT),
        Col("status", CHOICE, choices=("대기", "진행", "마감", "취소"), default="대기")), "작업지시"),
    FileSpec("21_lots.csv", "lot", ("lot_no",), (
        Col("lot_no", NO, required=True), Col("kind", required=True), Col("item_code"), Col("work_order_no", NO), Col("process_code"),
        Col("equip_code"), Col("qty", DECIMAL), Col("unit"), Col("insp_status", CHOICE, choices=("미검사", "합격", "불합격", "조건부"), default="미검사"),
        Col("made_at", DATETIME), Col("partner_code")), "LOT"),
    FileSpec("22_genealogy.csv", "lot_genealogy", ("parent_lot_no", "child_lot_no", "relation"), (
        Col("parent_lot_no", NO, required=True), Col("child_lot_no", NO, required=True), Col("relation", required=True),
        Col("qty", DECIMAL), Col("linked_at", DATETIME)), "계보"),
    FileSpec("31_work_results.csv", "pop_work_result", ("work_order_no", "started_at"), (
        Col("work_order_no", NO, required=True), Col("process_code", required=True), Col("equip_code"), Col("worker_code"),
        Col("started_at", DATETIME, required=True), Col("ended_at", DATETIME), Col("good_qty", DECIMAL), Col("scrap_qty", DECIMAL), Col("unit"),
        Col("product_lot_no", NO)), "실적"),
    FileSpec("32_measures.csv", "pop_measure", ("work_order_no", "started_at", "param_key"), (
        Col("work_order_no", NO, required=True), Col("started_at", DATETIME, required=True), Col("param_key", required=True),
        Col("value"), Col("unit")), "측정값"),
    FileSpec("33_inspections.csv", "qua_inspection", ("lot_no", "inspected_at", "item_key"), (
        Col("lot_no", NO, required=True), Col("insp_type", CHOICE, required=True, choices=("입고", "공정", "최종")),
        Col("inspected_at", DATETIME, required=True), Col("inspector"), Col("judgement", CHOICE, choices=("합격", "불합격", "조건부")),
        Col("item_key", required=True), Col("item_value"), Col("item_judgement")), "검사 + 항목"),
    FileSpec("34_shipments.csv", "shp_shipment", ("shipment_no",), (
        Col("shipment_no", NO, required=True), Col("partner_code", required=True), Col("ship_date", DATE, required=True), Col("order_no", NO),
        Col("status", CHOICE, choices=("등록", "승인", "취소"), default="등록"), Col("approved_at", DATETIME), Col("approved_by"),
        Col("ship_lot_no", NO)), "출하"),
)}

COMMAND_FILES: dict[str, tuple[str, ...]] = {
    "basics": ("01_items.csv", "02_partners.csv", "03_processes.csv", "04_process_params.csv", "05_equipment.csv", "06_bom.csv",
               "07_workers.csv", "08_defect_codes.csv", "09_codes.csv"),
    "orders": ("11_orders.csv", "12_work_orders.csv"),
    "lots": ("21_lots.csv", "22_genealogy.csv"),
    "history": ("31_work_results.csv", "32_measures.csv", "33_inspections.csv", "34_shipments.csv"),
}


# ── 적재 문맥 ─────────────────────────────────────────────────────────────
class Ctx:
    """한 명령의 적재 문맥 — 커서 · 폴더 · 참조 찾기. 참조는 매번 커서로 찾는다(같은 실행에서 방금 넣은 행도 보인다)."""

    def __init__(self, cur, dir: Path, file: str):
        self.cur, self.dir, self.file = cur, dir, file

    def one(self, sql: str, params: tuple) -> dict | None:
        self.cur.execute(sql, params)
        return self.cur.fetchone()

    def ref(self, table: str, code_col: str, code: str | None, *, what: str, required: bool = False) -> int | None:
        if code is None or code == "":
            if required:
                raise RowProblem(f"{what}: 필수")
            return None
        row = self.one(f"select id from {table} where {code_col} = %s", (code,))
        if row is None:
            raise RowProblem(f"{what}: 없는 코드 {code!r}")
        return row["id"]

    def attrs(self, row: Row) -> str:
        return json.dumps({**row.attrs, "migrated_from": self.file}, ensure_ascii=False)

    def upsert(self, sql: str, params: tuple) -> str:
        """`insert … on conflict … do update … returning (xmax = 0) as inserted` 꼴의 SQL 을 돌려 inserted/updated 를 돌려준다."""
        self.cur.execute(sql, params)
        got = self.cur.fetchone()
        return INSERTED if got and got.get("inserted") else UPDATED


def _lineage():
    try:
        from ..app import lineage
    except ModuleNotFoundError:
        raise NotImplementedError("app/lineage.py 가 아직 없다 (개발2 R1) — 계보 이관은 lineage.link 로만 한다") from None
    return lineage


def _kind_base(kind: str) -> str:
    for k in packs.current().lineage.get("lot_kinds", []):
        if k.get("kind") == kind:
            return str(k.get("base"))
    raise RowProblem(f"kind: 코어 종류(MATERIAL/PRODUCT/SHIPMENT)나 팩 등록 종류가 아니다 {kind!r}")


def _known_relation(name: str) -> bool:
    return any(r.get("name") == name for r in packs.current().lineage.get("relations", [])) or name in CORE_RELATIONS


# ── 적재기 — 파일마다 하나. (cur 문맥, 행) → inserted | updated | skipped. 줄 오류는 RowProblem ──
def load_items(c: Ctx, r: Row) -> str:
    v = r.values
    return c.upsert("""insert into bas_item (item_code, item_name, item_type, spec, unit, use_yn, attrs, created_by) values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (item_code) do update set item_name = excluded.item_name, item_type = excluded.item_type, spec = excluded.spec,
                           unit = excluded.unit, use_yn = excluded.use_yn, attrs = bas_item.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["item_code"], v["item_name"], v["item_type"], v["spec"], v["unit"], v["use_yn"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_partners(c: Ctx, r: Row) -> str:
    v = r.values
    return c.upsert("""insert into bas_partner (partner_code, partner_name, partner_type, contact, use_yn, attrs, created_by) values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (partner_code) do update set partner_name = excluded.partner_name, partner_type = excluded.partner_type,
                           contact = excluded.contact, use_yn = excluded.use_yn, attrs = bas_partner.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["partner_code"], v["partner_name"], v["partner_type"], v["contact"], v["use_yn"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_processes(c: Ctx, r: Row) -> str:
    v = r.values
    return c.upsert("""insert into bas_process (process_code, process_name, seq, use_yn, attrs, created_by) values (%s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (process_code) do update set process_name = excluded.process_name, seq = excluded.seq, use_yn = excluded.use_yn,
                           attrs = bas_process.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["process_code"], v["process_name"], v["seq"], v["use_yn"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_process_params(c: Ctx, r: Row) -> str:
    v = r.values
    pid = c.ref("bas_process", "process_code", v["process_code"], what="process_code", required=True)
    return c.upsert("""insert into bas_process_param (process_id, param_key, label, unit, value_type, min_value, max_value, required_yn, source, agg, seq, attrs, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (process_id, param_key) do update set label = excluded.label, unit = excluded.unit, value_type = excluded.value_type,
                           min_value = excluded.min_value, max_value = excluded.max_value, required_yn = excluded.required_yn, source = excluded.source,
                           agg = excluded.agg, seq = excluded.seq, attrs = bas_process_param.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (pid, v["param_key"], v["label"], v["unit"], v["value_type"], v["min_value"], v["max_value"], v["required_yn"], v["source"], v["agg"],
                     v["seq"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_equipment(c: Ctx, r: Row) -> str:
    v = r.values
    pid = c.ref("bas_process", "process_code", v["process_code"], what="process_code")
    return c.upsert("""insert into bas_equipment (equip_code, equip_name, process_id, collect_yn, use_yn, attrs, created_by) values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (equip_code) do update set equip_name = excluded.equip_name, process_id = excluded.process_id, collect_yn = excluded.collect_yn,
                           use_yn = excluded.use_yn, attrs = bas_equipment.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["equip_code"], v["equip_name"], pid, v["collect_yn"], v["use_yn"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_bom(c: Ctx, r: Row) -> str:
    v = r.values
    item_id = c.ref("bas_item", "item_code", v["item_code"], what="item_code", required=True)
    comp_id = c.ref("bas_item", "item_code", v["component_code"], what="component_code", required=True)
    if item_id == comp_id:
        raise RowProblem("component_code: 자기 자신을 구성품으로 둘 수 없다")
    if v["qty"] <= 0:
        raise RowProblem("qty: 0 보다 커야 한다")
    c.cur.execute("""insert into bas_bom (item_id, version, attrs, created_by) values (%s, %s, %s::jsonb, %s)
                     on conflict (item_id, version) do update set updated_at = now(), updated_by = %s returning id""",
                  (item_id, v["version"] or "1", c.attrs(r), LOADED_BY, LOADED_BY))
    bom_id = c.cur.fetchone()["id"]
    have = c.one("select id from bas_bom_dtl where bom_id = %s and component_item_id = %s", (bom_id, comp_id))
    if have:
        c.cur.execute("""update bas_bom_dtl set qty = %s, unit = %s, loss_rate = %s, attrs = attrs || %s::jsonb, updated_at = now(), updated_by = %s where id = %s""",
                      (v["qty"], v["unit"], v["loss_rate"], c.attrs(r), LOADED_BY, have["id"]))
        return UPDATED
    c.cur.execute("""insert into bas_bom_dtl (bom_id, component_item_id, qty, unit, loss_rate, attrs, created_by) values (%s, %s, %s, %s, %s, %s::jsonb, %s)""",
                  (bom_id, comp_id, v["qty"], v["unit"], v["loss_rate"], c.attrs(r), LOADED_BY))
    return INSERTED


def load_workers(c: Ctx, r: Row) -> str:
    v = r.values
    pid = c.ref("bas_process", "process_code", v["process_code"], what="process_code")
    return c.upsert("""insert into bas_worker (worker_code, worker_name, process_id, use_yn, attrs, created_by) values (%s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (worker_code) do update set worker_name = excluded.worker_name, process_id = excluded.process_id, use_yn = excluded.use_yn,
                           attrs = bas_worker.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["worker_code"], v["worker_name"], pid, v["use_yn"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_defect_codes(c: Ctx, r: Row) -> str:
    v = r.values
    pid = c.ref("bas_process", "process_code", v["process_code"], what="process_code")
    return c.upsert("""insert into bas_defect_code (defect_code, defect_name, process_id, use_yn, attrs, created_by) values (%s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (defect_code) do update set defect_name = excluded.defect_name, process_id = excluded.process_id, use_yn = excluded.use_yn,
                           attrs = bas_defect_code.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["defect_code"], v["defect_name"], pid, v["use_yn"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_codes(c: Ctx, r: Row) -> str:
    v = r.values
    return c.upsert("""insert into bas_code (group_code, code, code_name, seq, use_yn, attrs, created_by) values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (group_code, code) do update set code_name = excluded.code_name, seq = excluded.seq, use_yn = excluded.use_yn,
                           attrs = bas_code.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["group_code"], v["code"], v["code_name"], v["seq"], v["use_yn"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_orders(c: Ctx, r: Row) -> str:
    v = r.values
    partner_id = c.ref("bas_partner", "partner_code", v["partner_code"], what="partner_code", required=True)
    item_id = c.ref("bas_item", "item_code", v["item_code"], what="item_code", required=True)
    if v["qty"] <= 0:
        raise RowProblem("qty: 0 보다 커야 한다")
    c.cur.execute("""insert into ord_order (order_no, partner_id, order_date, due_date, status, attrs, created_by) values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                     on conflict (order_no) do update set partner_id = excluded.partner_id, order_date = excluded.order_date, due_date = excluded.due_date,
                         status = excluded.status, updated_at = now(), updated_by = %s
                     returning id""", (v["order_no"], partner_id, v["order_date"], v["due_date"], v["status"], c.attrs(r), LOADED_BY, LOADED_BY))
    order_id = c.cur.fetchone()["id"]
    return c.upsert("""insert into ord_order_dtl (order_id, line_no, item_id, qty, unit, attrs, created_by) values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (order_id, line_no) do update set item_id = excluded.item_id, qty = excluded.qty, unit = excluded.unit,
                           attrs = ord_order_dtl.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (order_id, v["line_no"], item_id, v["qty"], v["unit"], c.attrs(r), LOADED_BY, LOADED_BY))


def _order_dtl_id(c: Ctx, order_no: str | None, line_no: int | None) -> int | None:
    if not order_no:
        return None
    if line_no is None:
        raise RowProblem("line_no: order_no 를 주면 줄 번호도 준다")
    row = c.one("""select d.id from ord_order_dtl d join ord_order o on o.id = d.order_id where o.order_no = %s and d.line_no = %s""", (order_no, line_no))
    if row is None:
        raise RowProblem(f"order_no/line_no: 없는 수주 상세 {order_no!r} {line_no}")
    return row["id"]


def load_work_orders(c: Ctx, r: Row) -> str:
    v = r.values
    item_id = c.ref("bas_item", "item_code", v["item_code"], what="item_code", required=True)
    process_id = c.ref("bas_process", "process_code", v["process_code"], what="process_code", required=True)
    equip_id = c.ref("bas_equipment", "equip_code", v["equip_code"], what="equip_code")
    dtl_id = _order_dtl_id(c, v["order_no"], v["line_no"])
    if v["plan_qty"] <= 0:
        raise RowProblem("plan_qty: 0 보다 커야 한다")
    return c.upsert("""insert into job_work_order (work_order_no, item_id, process_id, equipment_id, order_dtl_id, plan_qty, unit, plan_date, status, attrs, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                       on conflict (work_order_no) do update set item_id = excluded.item_id, process_id = excluded.process_id, equipment_id = excluded.equipment_id,
                           order_dtl_id = excluded.order_dtl_id, plan_qty = excluded.plan_qty, unit = excluded.unit, plan_date = excluded.plan_date,
                           status = excluded.status, attrs = job_work_order.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["work_order_no"], item_id, process_id, equip_id, dtl_id, v["plan_qty"], v["unit"], v["plan_date"], v["status"], c.attrs(r), LOADED_BY, LOADED_BY))


def _shipment_header_rows(c: Ctx) -> dict[str, Row]:
    """같은 폴더의 34_shipments.csv — ship_lot_no → 행 (SHIPMENT LOT 적재용 · D-301). 파일이 없으면 빈 사전."""
    cached = getattr(c, "_ship_rows", None)
    if cached is not None:
        return cached
    path = c.dir / "34_shipments.csv"
    rows: dict[str, Row] = {}
    if path.exists():
        for row in read_file(path, SPECS["34_shipments.csv"]).rows:
            if row.values.get("ship_lot_no"):
                rows[row.values["ship_lot_no"]] = row
    c._ship_rows = rows  # type: ignore[attr-defined]
    return rows


def upsert_shipment(c: Ctx, r: Row) -> tuple[int, str]:
    v = r.values
    partner_id = c.ref("bas_partner", "partner_code", v["partner_code"], what="partner_code", required=True)
    order_id = None
    if v["order_no"]:
        row = c.one("select id from ord_order where order_no = %s", (v["order_no"],))
        if row is None:
            raise RowProblem(f"order_no: 없는 수주 {v['order_no']!r}")
        order_id = row["id"]
    c.cur.execute("""insert into shp_shipment (shipment_no, partner_id, ship_date, order_id, status, approved_at, approved_by, attrs, created_by)
                     values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                     on conflict (shipment_no) do update set partner_id = excluded.partner_id, ship_date = excluded.ship_date, order_id = excluded.order_id,
                         status = excluded.status, approved_at = excluded.approved_at, approved_by = excluded.approved_by,
                         attrs = shp_shipment.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                     returning id, (xmax = 0) as inserted""",
                  (v["shipment_no"], partner_id, v["ship_date"], order_id, v["status"], v["approved_at"], v["approved_by"], c.attrs(r), LOADED_BY, LOADED_BY))
    got = c.cur.fetchone()
    return got["id"], (INSERTED if got["inserted"] else UPDATED)


def load_lots(c: Ctx, r: Row) -> str:
    v = r.values
    base = _kind_base(v["kind"])
    item_id = c.ref("bas_item", "item_code", v["item_code"], what="item_code", required=(base != "SHIPMENT"))
    wo_id = None
    if v["work_order_no"]:
        row = c.one("select id from job_work_order where work_order_no = %s", (v["work_order_no"],))
        if row is None:
            raise RowProblem(f"work_order_no: 없는 작업지시 {v['work_order_no']!r}")
        wo_id = row["id"]
    process_id = c.ref("bas_process", "process_code", v["process_code"], what="process_code")
    equip_id = c.ref("bas_equipment", "equip_code", v["equip_code"], what="equip_code")
    partner_id = c.ref("bas_partner", "partner_code", v["partner_code"], what="partner_code")
    shipment_id = None
    if base == "SHIPMENT":
        header = _shipment_header_rows(c).get(v["lot_no"])
        if header is None:
            raise RowProblem("kind SHIPMENT: 같은 폴더 34_shipments.csv 에 ship_lot_no 가 이 LOT 인 출하 헤더가 없다 (D-301)")
        shipment_id, _ = upsert_shipment(c, header)
    return c.upsert("""insert into lot (lot_no, kind, kind_base, item_id, work_order_id, process_id, equipment_id, partner_id, shipment_id, qty, unit, insp_status, made_at, attrs, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()), %s::jsonb, %s)
                       on conflict (lot_no) do update set kind = excluded.kind, kind_base = excluded.kind_base, item_id = excluded.item_id,
                           work_order_id = excluded.work_order_id, process_id = excluded.process_id, equipment_id = excluded.equipment_id,
                           partner_id = excluded.partner_id, shipment_id = excluded.shipment_id, qty = excluded.qty, unit = excluded.unit,
                           insp_status = excluded.insp_status, made_at = excluded.made_at, attrs = lot.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (v["lot_no"], v["kind"], base, item_id, wo_id, process_id, equip_id, partner_id, shipment_id, v["qty"], v["unit"], v["insp_status"],
                     v["made_at"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_genealogy(c: Ctx, r: Row) -> str:
    v = r.values
    if not _known_relation(v["relation"]):
        raise RowProblem(f"relation: 코어 5종이나 팩 등록 관계가 아니다 {v['relation']!r}")
    parent = c.one("select id from lot where lot_no = %s", (v["parent_lot_no"],))
    child = c.one("select id from lot where lot_no = %s", (v["child_lot_no"],))
    if parent is None:
        raise RowProblem(f"parent_lot_no: 없는 LOT {v['parent_lot_no']!r}")
    if child is None:
        raise RowProblem(f"child_lot_no: 없는 LOT {v['child_lot_no']!r}")
    if parent["id"] == child["id"]:
        raise RowProblem("자기 자신을 부모로 하는 계보")
    if c.one("select 1 from lot_genealogy where parent_lot_id = %s and child_lot_id = %s and relation = %s", (parent["id"], child["id"], v["relation"])):
        return SKIPPED                                            # 이미 있다 — 계보 행은 불변(변경하지 않는다)
    try:
        _lineage().link(c.cur, parent["id"], child["id"], v["relation"], by=LOADED_BY, qty=v["qty"])
    except HTTPException as exc:                                  # lineage 의 422 (순환 · 모르는 관계 · …) → 그 줄 오류
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        raise RowProblem(f"lineage.link 거부: {detail.get('message') or exc.detail}") from None
    return INSERTED


def _result_id(c: Ctx, work_order_no: str, started_at: datetime) -> tuple[int | None, int | None]:
    wo = c.one("select id, process_id from job_work_order where work_order_no = %s", (work_order_no,))
    if wo is None:
        raise RowProblem(f"work_order_no: 없는 작업지시 {work_order_no!r}")
    row = c.one("select id from pop_work_result where work_order_id = %s and started_at = %s", (wo["id"], started_at))
    return wo["id"], (row["id"] if row else None)


def load_work_results(c: Ctx, r: Row) -> str:
    v = r.values
    wo_id, rid = _result_id(c, v["work_order_no"], v["started_at"])
    process_id = c.ref("bas_process", "process_code", v["process_code"], what="process_code", required=True)
    equip_id = c.ref("bas_equipment", "equip_code", v["equip_code"], what="equip_code")
    worker_id = c.ref("bas_worker", "worker_code", v["worker_code"], what="worker_code")
    lot_id = None
    if v["product_lot_no"]:
        lot = c.one("select id from lot where lot_no = %s", (v["product_lot_no"],))
        if lot is None:
            raise RowProblem(f"product_lot_no: 21_lots.csv 에 없는 LOT {v['product_lot_no']!r}")
        lot_id = lot["id"]
    if rid is None:
        c.cur.execute("""insert into pop_work_result (work_order_id, process_id, equipment_id, worker_id, started_at, ended_at, good_qty, defect_qty, unit, product_lot_id, attrs, created_by)
                         values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s) returning id""",
                      (wo_id, process_id, equip_id, worker_id, v["started_at"], v["ended_at"], v["good_qty"], v["scrap_qty"], v["unit"], lot_id, c.attrs(r), LOADED_BY))
        rid, status = c.cur.fetchone()["id"], INSERTED
    else:
        c.cur.execute("""update pop_work_result set process_id = %s, equipment_id = %s, worker_id = %s, ended_at = %s, good_qty = %s, defect_qty = %s, unit = %s,
                                product_lot_id = %s, attrs = attrs || %s::jsonb, updated_at = now(), updated_by = %s where id = %s""",
                      (process_id, equip_id, worker_id, v["ended_at"], v["good_qty"], v["scrap_qty"], v["unit"], lot_id, c.attrs(r), LOADED_BY, rid))
        status = UPDATED
    if lot_id is not None:
        c.cur.execute("update lot set work_result_id = %s, updated_at = now(), updated_by = %s where id = %s and work_result_id is distinct from %s",
                      (rid, LOADED_BY, lot_id, rid))
    return status


def _num_or_text(text: str | None) -> tuple[Decimal | None, str | None]:
    if text is None or text == "":
        return None, None
    try:
        return Decimal(text.replace(",", "")), None
    except InvalidOperation:
        return None, text


def load_measures(c: Ctx, r: Row) -> str:
    v = r.values
    _wo_id, rid = _result_id(c, v["work_order_no"], v["started_at"])
    if rid is None:
        raise RowProblem(f"work_order_no/started_at: 31_work_results.csv 에 없는 실적 {v['work_order_no']!r} {v['started_at']}")
    num, text = _num_or_text(v["value"])
    param = c.one("""select p.id, p.min_value, p.max_value from bas_process_param p join pop_work_result w on w.process_id = p.process_id
                      where w.id = %s and p.param_key = %s""", (rid, v["param_key"]))
    deviated = bool(param and num is not None and ((param["min_value"] is not None and num < param["min_value"]) or
                                                   (param["max_value"] is not None and num > param["max_value"])))
    return c.upsert("""insert into pop_measure (work_result_id, param_id, param_key, value_num, value_text, unit, source, deviated, measured_at, attrs, created_by)
                       values (%s, %s, %s, %s, %s, %s, 'manual', %s, %s, %s::jsonb, %s)
                       on conflict (work_result_id, param_key) do update set param_id = excluded.param_id, value_num = excluded.value_num, value_text = excluded.value_text,
                           unit = excluded.unit, deviated = excluded.deviated, attrs = pop_measure.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                       returning (xmax = 0) as inserted""",
                    (rid, param["id"] if param else None, v["param_key"], num, text, v["unit"], deviated, v["started_at"], c.attrs(r), LOADED_BY, LOADED_BY))


def load_inspections(c: Ctx, r: Row) -> str:
    v = r.values
    lot = c.one("select id, item_id from lot where lot_no = %s", (v["lot_no"],))
    if lot is None:
        raise RowProblem(f"lot_no: 없는 LOT {v['lot_no']!r}")
    insp = c.one("select id from qua_inspection where lot_id = %s and inspected_at = %s", (lot["id"], v["inspected_at"]))
    judged_at = v["inspected_at"] if v["judgement"] else None
    if insp is None:
        c.cur.execute("""insert into qua_inspection (lot_id, insp_type, inspected_at, inspector, judgement, judged_at, judged_by, attrs, created_by)
                         values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s) returning id""",
                      (lot["id"], v["insp_type"], v["inspected_at"], v["inspector"], v["judgement"], judged_at, v["inspector"] if v["judgement"] else None, c.attrs(r), LOADED_BY))
        insp_id = c.cur.fetchone()["id"]
    else:
        insp_id = insp["id"]
        c.cur.execute("""update qua_inspection set insp_type = %s, inspector = %s, judgement = %s, judged_at = %s, judged_by = %s, updated_at = now(), updated_by = %s where id = %s""",
                      (v["insp_type"], v["inspector"], v["judgement"], judged_at, v["inspector"] if v["judgement"] else None, LOADED_BY, insp_id))
    num, text = _num_or_text(v["item_value"])
    plan = c.one("""select id, min_value, max_value from qua_insp_plan where insp_type = %s and item_key = %s and (item_id is null or item_id = %s)
                     order by item_id nulls last limit 1""", (v["insp_type"], v["item_key"], lot["item_id"]))
    deviated = bool(plan and num is not None and ((plan["min_value"] is not None and num < plan["min_value"]) or
                                                  (plan["max_value"] is not None and num > plan["max_value"])))
    status = c.upsert("""insert into qua_insp_item (inspection_id, plan_id, item_key, value_num, value_text, item_judgement, deviated, attrs, created_by)
                         values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                         on conflict (inspection_id, item_key) do update set plan_id = excluded.plan_id, value_num = excluded.value_num, value_text = excluded.value_text,
                             item_judgement = excluded.item_judgement, deviated = excluded.deviated, attrs = qua_insp_item.attrs || excluded.attrs, updated_at = now(), updated_by = %s
                         returning (xmax = 0) as inserted""",
                      (insp_id, plan["id"] if plan else None, v["item_key"], num, text, v["item_judgement"], deviated, c.attrs(r), LOADED_BY, LOADED_BY))
    # 검사 판정 → lot.insp_status (최신 검사 기준)
    c.cur.execute("""update lot l set insp_status = x.judgement, updated_at = now(), updated_by = %s
                       from (select judgement from qua_inspection where lot_id = %s and judgement is not null order by inspected_at desc, id desc limit 1) x
                      where l.id = %s and l.insp_status is distinct from x.judgement""", (LOADED_BY, lot["id"], lot["id"]))
    return status


def load_shipments(c: Ctx, r: Row) -> str:
    v = r.values
    lot = None
    if v["ship_lot_no"]:
        lot = c.one("select id, kind_base, shipment_id from lot where lot_no = %s", (v["ship_lot_no"],))
        if lot is None:
            raise RowProblem(f"ship_lot_no: 21_lots.csv 에 없는 LOT {v['ship_lot_no']!r}")
        if lot["kind_base"] != "SHIPMENT":
            raise RowProblem(f"ship_lot_no: SHIPMENT 종류가 아니다 {v['ship_lot_no']!r}")
    shipment_id, status = upsert_shipment(c, r)
    if lot is not None and lot["shipment_id"] != shipment_id:
        c.cur.execute("update lot set shipment_id = %s, updated_at = now(), updated_by = %s where id = %s", (shipment_id, LOADED_BY, lot["id"]))
    return status


LOADERS: dict[str, Callable[[Ctx, Row], str]] = {
    "01_items.csv": load_items, "02_partners.csv": load_partners, "03_processes.csv": load_processes, "04_process_params.csv": load_process_params,
    "05_equipment.csv": load_equipment, "06_bom.csv": load_bom, "07_workers.csv": load_workers, "08_defect_codes.csv": load_defect_codes,
    "09_codes.csv": load_codes, "11_orders.csv": load_orders, "12_work_orders.csv": load_work_orders, "21_lots.csv": load_lots,
    "22_genealogy.csv": load_genealogy, "31_work_results.csv": load_work_results, "32_measures.csv": load_measures,
    "33_inspections.csv": load_inspections, "34_shipments.csv": load_shipments,
}
