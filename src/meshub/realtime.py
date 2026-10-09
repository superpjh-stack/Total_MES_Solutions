"""실시간 데이터 — 코어 수집 인터페이스가 쌓는 설비 수집값을 보고(저장 현황 · 최신값 · 추이) 오래 둘 수 있게 시간 단위로 집계한다.

원천은 코어 그대로다: `POST /ifc/collect` → `ifc_collect_raw`(원문) → `eqp_collect`(태그별 값). 허브는 원천에 쓰지 않는다.
`hub.ts_hourly` 는 설비 · 태그 · 시간마다 건수 · 최소 · 최대 · 평균 · 마지막 값을 둔다 — 원천을 줄여도 추이가 남는다(보존 정책은 사람이 정한다).
"""

from __future__ import annotations

import csv
import io

from mescore.db import conn

from . import store


def status() -> dict:
    store.ensure()
    v = conn.q1("""select count(*)::bigint as total,
                          count(*) filter (where ts >= now() - interval '1 hour')::bigint as h1,
                          count(*) filter (where ts >= now() - interval '24 hours')::bigint as h24,
                          count(*) filter (where ts >= current_date)::bigint as today,
                          max(ts) as last_ts, min(ts) as first_ts,
                          count(distinct equipment_id)::int as equipments, count(distinct (equipment_id, tag))::int as series,
                          coalesce(pg_total_relation_size('public.eqp_collect'), 0)::bigint as bytes
                     from eqp_collect""")
    raw = conn.q1("""select count(*)::bigint as total, count(*) filter (where rejected_reason is not null)::bigint as rejected,
                            count(*) filter (where resend)::bigint as resent, max(received_at) as last_at,
                            count(*) filter (where received_at >= now() - interval '24 hours')::bigint as h24,
                            coalesce(pg_total_relation_size('public.ifc_collect_raw'), 0)::bigint as bytes
                       from ifc_collect_raw""")
    hr = conn.q1("""select count(*)::bigint as rows, min(hour) as first_hour, max(hour) as last_hour,
                           coalesce(pg_total_relation_size('hub.ts_hourly'), 0)::bigint as bytes from hub.ts_hourly""")
    last_roll = conn.q1("select ran_at, ran_by, hours, rows_in from hub.rollup_log order by id desc limit 1")
    return {"values": v, "raw": raw, "hourly": hr, "last_rollup": last_roll}


def series() -> list[dict]:
    """설비 · 태그별 최신값 · 24시간 건수 · 24시간 최소/최대/평균."""
    return conn.q("""with last as (
                        select distinct on (c.equipment_id, c.tag) c.equipment_id, c.tag, c.ts, c.value_num, c.value_text
                          from eqp_collect c order by c.equipment_id, c.tag, c.ts desc)
                     select e.equip_code, e.equip_name, l.equipment_id, l.tag, l.ts as last_ts, l.value_num as last_num, l.value_text as last_text,
                            s.n24, s.vmin, s.vmax, s.vavg
                       from last l join bas_equipment e on e.id = l.equipment_id
                       left join lateral (select count(*)::int as n24, min(value_num) as vmin, max(value_num) as vmax, round(avg(value_num), 3) as vavg
                                            from eqp_collect x where x.equipment_id = l.equipment_id and x.tag = l.tag
                                             and x.ts >= now() - interval '24 hours') s on true
                      order by e.equip_code, l.tag""")


def trend(equipment_id: int, tag: str, hours: int = 24) -> dict:
    hours = max(1, min(int(hours), 24 * 31))
    pts = conn.q("""select ts, value_num from eqp_collect where equipment_id = %s and tag = %s and value_num is not null
                      and ts >= now() - make_interval(hours => %s) order by ts limit 5000""", (equipment_id, tag, hours))
    hourly = conn.q("""select hour, n, v_min, v_max, v_avg from hub.ts_hourly where equipment_id = %s and tag = %s
                         and hour >= now() - make_interval(hours => %s) order by hour""", (equipment_id, tag, hours))
    return {"points": pts, "hourly": hourly, "hours": hours}


def sparkline(values: list[float], w: int = 640, h: int = 120, pad: int = 6) -> str:
    """SVG polyline 의 points 문자열 (외부 차트 라이브러리 없이)."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = (w - 2 * pad) / (len(values) - 1)
    return " ".join(f"{pad + i * step:.1f},{h - pad - (v - lo) / span * (h - 2 * pad):.1f}" for i, v in enumerate(values))


def rollup(user_login: str, hours: int = 72) -> int:
    """최근 N시간 수집값을 시간 단위로 집계해 hub.ts_hourly 에 넣는다(같은 시간은 다시 계산해 덮는다 — 멱등)."""
    store.ensure()
    hours = max(1, min(int(hours), 24 * 90))
    with conn.tx() as cur:
        cur.execute("""insert into hub.ts_hourly (equipment_id, tag, hour, n, v_min, v_max, v_avg, v_last, rolled_at)
                       select equipment_id, tag, date_trunc('hour', ts), count(*), min(value_num), max(value_num), round(avg(value_num), 4),
                              (array_agg(value_num order by ts desc))[1], now()
                         from eqp_collect
                        where value_num is not null and ts >= date_trunc('hour', now() - make_interval(hours => %s))
                        group by equipment_id, tag, date_trunc('hour', ts)
                       on conflict (equipment_id, tag, hour) do update
                          set n = excluded.n, v_min = excluded.v_min, v_max = excluded.v_max, v_avg = excluded.v_avg,
                              v_last = excluded.v_last, rolled_at = now()""", (hours,))
        n = cur.rowcount
        cur.execute("insert into hub.rollup_log (ran_by, hours, rows_in) values (%s, %s, %s)", (user_login, hours, n))
    return n


def export_csv(hours: int = 24, equipment_id: int | None = None, tag: str = "") -> tuple[str, int]:
    hours = max(1, min(int(hours), 24 * 31))
    where, args = ["c.ts >= now() - make_interval(hours => %s)"], [hours]
    if equipment_id:
        where.append("c.equipment_id = %s")
        args.append(equipment_id)
    if tag:
        where.append("c.tag = %s")
        args.append(tag)
    rows = conn.q(f"""select e.equip_code as 설비코드, e.equip_name as 설비명, c.tag as 태그, c.ts as 시각, c.value_num as 값, c.value_text as 문자값
                        from eqp_collect c join bas_equipment e on e.id = c.equipment_id
                       where {' and '.join(where)} order by c.ts limit 100000""", args)
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["설비코드", "설비명", "태그", "시각", "값", "문자값"])
    for r in rows:
        w.writerow([r["설비코드"], r["설비명"], r["태그"], r["시각"], "" if r["값"] is None else r["값"], r["문자값"] or ""])
    return buf.getvalue(), len(rows)


def daily(days: int = 14) -> list[dict]:
    return conn.q("""select d::date as day, coalesce(x.n, 0)::bigint as n
                       from generate_series(current_date - (%s - 1), current_date, interval '1 day') d
                       left join (select ts::date as day, count(*) as n from eqp_collect where ts >= current_date - (%s - 1) group by 1) x
                         on x.day = d::date order by 1""", (days, days))
