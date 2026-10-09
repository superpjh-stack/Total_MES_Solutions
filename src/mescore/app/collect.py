"""수집 — Data Gateway 메시지 수신 → `ifc_collect_raw`(원문 · 멱등) → `eqp_collect`(정제 시계열) → `hook("on_collect")`. (`interfaces.md` §6 · `api-contract.md` §4)

담당 **개발2**. `POST /ifc/collect` 엔드포인트는 개발3 의 `routers/ifc.py` 가 `auth.require_collect_token` 뒤에서 `collect.receive(cur, msg)` 를 부른다.
쓰는 테이블은 `ifc_collect_raw` · `eqp_collect` 둘뿐이다. **제어 명령 · 쓰기 방향 엔드포인트는 없다** — 수집값은 기록이다.

    CollectMessage(equip_code, ts, tags, source="gateway", resend=False)
    receive(cur, msg) -> ReceiveResult(raw_id, duplicate, unknown_tags, saved)   # 모르는 설비: 거부 사유를 원문에 남긴 뒤 422
    latest(equip_id) -> dict | None            # {"equipment_id", "ts", "tags": {tag: {"value", "ts"}}}
    series(equip_id, tag, frm, to) -> list[dict]
    aggregate(equip_id, tag, frm, to, agg) -> float | None   # agg = last | avg | max | min — on_result_closed 가 측정값 collect 소스를 채울 때

태그 이름을 `bas_process_param.collect_tag`(없으면 `param_key`) 와 같게 두면 실적 측정값으로 이어진다. 코어가 아는 공용 태그는
`core.yaml: collect_tags`(run_state · count — D-17). 그 밖의 태그는 저장하되 `unknown_tags` 로 센다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..db import conn
from . import packs
from .packs import t
from .util import http

AGGS: tuple[str, ...] = ("last", "avg", "max", "min")


@dataclass
class CollectMessage:
    equip_code: str
    ts: datetime | str
    tags: dict[str, Any] = field(default_factory=dict)
    source: str = "gateway"
    resend: bool = False

    @classmethod
    def from_payload(cls, payload: dict) -> "CollectMessage":
        """`POST /ifc/collect` 본문 → 메시지. 형식 오류는 422 (조용히 기본값을 끼우지 않는다)."""
        if not isinstance(payload, dict):
            raise http.validation_error(t("수집 메시지는 객체여야 합니다"), fields=[{"name": "body", "reason": type(payload).__name__}])
        code = payload.get("equip_code")
        ts = payload.get("ts")
        tags = payload.get("tags")
        errs = []
        if not code or not isinstance(code, str):
            errs.append({"name": "equip_code", "label": t("설비 코드"), "reason": t("필수 항목입니다")})
        if not ts:
            errs.append({"name": "ts", "label": t("시각"), "reason": t("필수 항목입니다")})
        if not isinstance(tags, dict) or not tags:
            errs.append({"name": "tags", "label": t("태그"), "reason": t("태그 객체가 비었습니다")})
        if errs:
            raise http.validation_error(t("수집 메시지 형식이 올바르지 않습니다"), fields=errs)
        return cls(equip_code=code.strip(), ts=ts, tags=dict(tags), source=str(payload.get("source") or "gateway"), resend=bool(payload.get("resend", False)))


@dataclass(frozen=True)
class ReceiveResult:
    raw_id: int
    duplicate: bool = False
    unknown_tags: tuple[str, ...] = ()
    saved: int = 0                 # eqp_collect 에 쓴 행 수

    def __int__(self) -> int:
        return self.raw_id


def _ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise http.validation_error(t("시각 형식이 올바르지 않습니다 (ISO 8601)"), fields=[{"name": "ts", "label": t("시각"), "reason": str(value)}]) from None


def _split_value(v: Any) -> tuple[Decimal | None, str | None]:
    """숫자면 value_num, 아니면 value_text. bool 은 1/0."""
    if isinstance(v, bool):
        return (Decimal(1) if v else Decimal(0)), None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v)), None
    if v is None:
        return None, None
    s = str(v)
    try:
        return Decimal(s), None
    except InvalidOperation:
        return None, s


def known_tags(cur=None) -> set[str]:
    """코어 공용 태그 + `bas_process_param(source=collect)` 가 선언한 태그."""
    sql = "select coalesce(collect_tag, param_key) as tag from bas_process_param where source = 'collect' and use_yn = 'Y'"
    if cur is None:
        rows = conn.q(sql)
    else:
        cur.execute(sql)
        rows = cur.fetchall()
    return set(packs.current().collect_tags) | {r["tag"] for r in rows}


def receive(cur, msg: CollectMessage) -> ReceiveResult:
    """원문 적재(멱등 — `(equip_code, ts, source)` 유니크) → 정제 → `on_collect` 훅.
    같은 메시지 재전송은 적재하지 않고 `duplicate=True`. 모르는 설비는 **거부 사유와 함께 원문을 남긴 뒤** 422 — 그 행은 호출자의 트랜잭션 밖(자동 커밋)에
    쓴다. 트랜잭션이 되돌아가도 거부 기록이 남아야 하기 때문이다."""
    ts = _ts(msg.ts)
    payload = json.dumps({"equip_code": msg.equip_code, "ts": ts.isoformat(), "tags": msg.tags, "source": msg.source, "resend": msg.resend},
                         ensure_ascii=False, default=str)
    cur.execute("select id, use_yn from bas_equipment where equip_code = %s", (msg.equip_code,))
    eq = cur.fetchone()
    if eq is None:
        reason = f"모르는 설비 {msg.equip_code}"
        conn.x("""insert into ifc_collect_raw (equip_code, ts, source, payload, resend, rejected_reason, created_by)
                  values (%s, %s, %s, %s::jsonb, %s, %s, 'collect') on conflict (equip_code, ts, source) do nothing""",
               (msg.equip_code, ts, msg.source, payload, msg.resend, reason))
        raise http.validation_error(t("등록되지 않은 설비의 수집값입니다"), fields=[{"name": "equip_code", "label": t("설비"), "reason": msg.equip_code}])
    cur.execute("""insert into ifc_collect_raw (equip_code, ts, source, payload, resend, created_by) values (%s, %s, %s, %s::jsonb, %s, 'collect')
                   on conflict (equip_code, ts, source) do nothing returning id""", (msg.equip_code, ts, msg.source, payload, msg.resend))
    row = cur.fetchone()
    if row is None:
        cur.execute("select id from ifc_collect_raw where equip_code = %s and ts = %s and source = %s", (msg.equip_code, ts, msg.source))
        return ReceiveResult(raw_id=int(cur.fetchone()["id"]), duplicate=True)
    raw_id = int(row["id"])
    known = known_tags(cur)
    unknown: list[str] = []
    saved = 0
    for tag, v in msg.tags.items():
        num, text = _split_value(v)
        cur.execute("""insert into eqp_collect (equipment_id, tag, ts, value_num, value_text, raw_id, created_by) values (%s, %s, %s, %s, %s, %s, 'collect')
                       on conflict (equipment_id, tag, ts) do update set value_num = excluded.value_num, value_text = excluded.value_text, raw_id = excluded.raw_id,
                                                                         updated_at = now(), updated_by = 'collect'""",
                    (eq["id"], str(tag), ts, num, text, raw_id))
        saved += 1
        if str(tag) not in known:
            unknown.append(str(tag))
    raw = {"id": raw_id, "equip_code": msg.equip_code, "equipment_id": eq["id"], "ts": ts, "tags": dict(msg.tags), "source": msg.source,
           "resend": msg.resend, "unknown_tags": unknown}
    packs.hook("on_collect")(cur, raw, None)
    return ReceiveResult(raw_id=raw_id, duplicate=False, unknown_tags=tuple(unknown), saved=saved)


# ── 읽기 ────────────────────────────────────────────────────────────────
def _val(r: dict):
    return float(r["value_num"]) if r["value_num"] is not None else r["value_text"]


def latest(equip_id: int) -> dict | None:
    """설비의 태그별 마지막 값. 수집 행이 하나도 없으면 None (화면은 `미수집`)."""
    rows = conn.q("""select distinct on (tag) tag, ts, value_num, value_text from eqp_collect
                      where equipment_id = %s order by tag, ts desc""", (int(equip_id),))
    if not rows:
        return None
    return {"equipment_id": int(equip_id), "ts": max(r["ts"] for r in rows),
            "tags": {r["tag"]: {"value": _val(r), "ts": r["ts"]} for r in rows}}


def series(equip_id: int, tag: str, frm, to) -> list[dict]:
    """EQP-04 — 구간의 시계열 [{ts, value}] (오래된 순). 비면 []."""
    rows = conn.q("""select ts, value_num, value_text from eqp_collect
                      where equipment_id = %s and tag = %s and ts >= %s and ts <= %s order by ts""", (int(equip_id), tag, frm, to))
    return [{"ts": r["ts"], "value": _val(r)} for r in rows]


def aggregate(equip_id: int, tag: str, frm, to, agg: str = "last") -> float | None:
    """구간 대표값 — 숫자 값만. 수신 0 이면 None (`미수집`)."""
    if agg not in AGGS:
        raise ValueError(f"agg 는 {AGGS} 중 하나: {agg!r}")
    if agg == "last":
        r = conn.q1("""select value_num from eqp_collect where equipment_id = %s and tag = %s and ts >= %s and ts <= %s and value_num is not null
                       order by ts desc limit 1""", (int(equip_id), tag, frm, to))
        return float(r["value_num"]) if r else None
    r = conn.q1(f"""select {agg}(value_num) as v from eqp_collect where equipment_id = %s and tag = %s and ts >= %s and ts <= %s""",
                (int(equip_id), tag, frm, to))
    return float(r["v"]) if r and r["v"] is not None else None


def counts(frm=None, to=None) -> dict:
    """IFC-01 수신 현황용 — 원문 수 · 거부 수 · 마지막 수신."""
    # None 인 경계는 조건에서 뺀다 — `%s is null` 로 None 을 넘기면 드라이버 · 서버 설정에 따라 형 추론이 갈려 AmbiguousParameter (개발3 §3-6)
    where, params = [], {}
    if frm not in (None, ""):
        where.append("received_at >= %(f)s::timestamptz")
        params["f"] = frm
    if to not in (None, ""):
        where.append("received_at <= %(t)s::timestamptz")
        params["t"] = to
    r = conn.q1("""select count(*)::int as total, count(*) filter (where rejected_reason is not null)::int as rejected,
                          count(*) filter (where resend)::int as resent, max(received_at) as last_at
                     from ifc_collect_raw""" + (" where " + " and ".join(where) if where else ""), params or None)
    return dict(r) if r else {"total": 0, "rejected": 0, "resent": 0, "last_at": None}
