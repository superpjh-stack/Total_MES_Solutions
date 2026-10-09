"""정형 지표 — 「오늘의 재고량 · 출하량 · 생산량 · 입고량 · 불량률 · 작업지시 현황」 처럼 자주 묻는 질문은 LLM 없이 미리 검증한 SQL 로 답한다.

오케스트레이터가 질문에서 지표와 기간을 찾으면 이 카탈로그의 SQL 을 SQL 관문(sqlguard)으로 똑같이 검사 · 읽기 전용 실행한다.
숫자를 LLM 이 다시 쓰지 않으므로 음성으로 읽어도 틀릴 일이 없다. 기간 날짜는 코드가 만든 date 값만 SQL 에 들어간다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable


@dataclass(frozen=True)
class Period:
    label: str
    d0: date
    d1: date            # 끝 날짜 다음 날(반열린 구간)

    def ts(self, col: str) -> str:
        return f"{col} >= date '{self.d0.isoformat()}' and {col} < date '{self.d1.isoformat()}'"

    def day(self, col: str) -> str:
        return f"{col} >= date '{self.d0.isoformat()}' and {col} < date '{self.d1.isoformat()}'"


def period(q: str, today: date | None = None) -> Period:
    t = today or date.today()
    md = lambda d: f"{d.month}/{d.day}"                                     # noqa: E731
    if re.search(r"그제|그저께", q):
        d = t - timedelta(days=2)
        return Period(f"그제({md(d)})", d, d + timedelta(days=1))
    if re.search(r"어제|전일", q):
        d = t - timedelta(days=1)
        return Period(f"어제({md(d)})", d, d + timedelta(days=1))
    m = re.search(r"최근\s*(\d{1,3})\s*일", q)
    if m:
        n = max(1, min(int(m.group(1)), 366))
        return Period(f"최근 {n}일({md(t - timedelta(days=n - 1))}~{md(t)})", t - timedelta(days=n - 1), t + timedelta(days=1))
    mon = t - timedelta(days=t.weekday())
    if re.search(r"지난\s*주|전주", q):
        return Period(f"지난주({md(mon - timedelta(days=7))}~{md(mon - timedelta(days=1))})", mon - timedelta(days=7), mon)
    if re.search(r"이번\s*주|금주|주간", q):
        return Period(f"이번 주({md(mon)}~{md(t)})", mon, t + timedelta(days=1))
    first = t.replace(day=1)
    if re.search(r"지난\s*달|전월", q):
        prev = (first - timedelta(days=1)).replace(day=1)
        return Period(f"지난달({prev.month}월)", prev, first)
    if re.search(r"이번\s*달|금월|이번\s*월|월간", q):
        return Period(f"이번 달({t.month}월)", first, t + timedelta(days=1))
    return Period(f"오늘({md(t)})", t, t + timedelta(days=1))


def num(v) -> str:
    if v is None:
        return "0"
    f = float(v)
    return f"{f:,.0f}" if f == int(f) else f"{f:,.1f}"


def _units(rows: list[dict], qty: str, unit: str = "단위") -> str:
    parts = [f"{num(r[qty])} {r.get(unit) or ''}".strip() for r in rows if r.get(qty)]
    return " · ".join(parts) or "0"


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    pattern: str                      # 질문에서 이 지표를 가리키는 말
    tables: tuple[str, ...]
    summary: Callable[[Period], str]  # 요약 SQL (답 문장용)
    detail: Callable[[Period], str]   # 상세 SQL (화면 표)
    say: Callable[[Period, list[dict]], str]
    uses_period: bool = True


def _say_stock(p, rows):
    if not rows or not any(r["LOT수"] for r in rows):
        return "지금 재고로 남은 LOT 이 없습니다."
    parts = [f"{r['구분']} {num(r['LOT수'])}개 LOT, {num(r['재고수량'])} {r['단위'] or ''}".strip() for r in rows]
    return f"지금 기준 재고는 {', '.join(parts)} 입니다."


def _say_prod(p, rows):
    tot = rows[0] if rows else {}
    if not tot or not tot.get("실적건수"):
        return f"{p.label} 종료된 생산 실적이 없습니다."
    rate = (float(tot["불량수량"] or 0) / (float(tot["양품수량"] or 0) + float(tot["불량수량"] or 0)) * 100) if (tot["양품수량"] or tot["불량수량"]) else 0
    return (f"{p.label} 생산량은 양품 {num(tot['양품수량'])} {tot['단위'] or ''}, 실적 {num(tot['실적건수'])}건, 품목 {num(tot['품목수'])}개입니다. "
            f"불량은 {num(tot['불량수량'])}, 불량률 {rate:.1f}퍼센트입니다.")


def _say_ship(p, rows):
    tot = rows[0] if rows else {}
    if not tot or not tot.get("출하건수"):
        return f"{p.label} 출하 예정 건이 없습니다."
    return (f"{p.label} 출하는 {num(tot['출하건수'])}건이고, 그중 승인 {num(tot['승인건수'])}건으로 출하 수량은 {num(tot['출하수량'])} {tot['단위'] or ''}입니다. "
            f"등록 건까지 합한 예정 수량은 {num(tot['예정포함수량'])} {tot['단위'] or ''}입니다.").replace(" 입니다", "입니다")


def _say_rcpt(p, rows):
    if not rows or not any(r["입고건수"] for r in rows):
        return f"{p.label} 입고가 없습니다."
    n = sum(int(r["입고건수"]) for r in rows)
    return f"{p.label} 입고는 {num(n)}건, 수량 {_units(rows, '입고수량')} 입니다."


def _say_defect(p, rows):
    tot = rows[0] if rows else {}
    total = float(tot.get("양품수량") or 0) + float(tot.get("불량수량") or 0)
    if not total:
        return f"{p.label} 종료된 생산 실적이 없어 불량률을 낼 수 없습니다."
    return (f"{p.label} 불량률은 {float(tot['불량수량'] or 0) / total * 100:.1f}퍼센트입니다. "
            f"생산 {num(total)} 중 불량 {num(tot['불량수량'])}, 검사 불합격 판정 {num(tot['불합격판정'])}건입니다.")


def _say_wo(p, rows):
    if not rows:
        return f"{p.label} 계획된 작업지시가 없습니다."
    n = sum(int(r["건수"]) for r in rows)
    return f"{p.label} 계획된 작업지시는 {num(n)}건이고, " + ", ".join(f"{r['상태']} {num(r['건수'])}건" for r in rows) + " 입니다."


CATALOG: tuple[Metric, ...] = (
    Metric("stock", "재고량", r"재고", ("lot", "v_lot_state", "v_lot_stock", "bas_item"),
           lambda p: """select case l.kind_base when 'MATERIAL' then '원재료' when 'PRODUCT' then '제품' else l.kind_base end as 구분,
                               count(*) as "LOT수", sum(st.remain_qty) as 재고수량, l.unit as 단위
                          from v_lot_state v join v_lot_stock st on st.lot_id = v.lot_id join lot l on l.id = v.lot_id
                         where v.state = '재고' group by l.kind_base, l.unit order by 1""",
           lambda p: """select case l.kind_base when 'MATERIAL' then '원재료' when 'PRODUCT' then '제품' else l.kind_base end as 구분,
                               i.item_code as 품목코드, i.item_name as 품목명, count(*) as "LOT수", sum(st.remain_qty) as 재고수량, l.unit as 단위
                          from v_lot_state v join v_lot_stock st on st.lot_id = v.lot_id join lot l on l.id = v.lot_id join bas_item i on i.id = l.item_id
                         where v.state = '재고' group by l.kind_base, i.item_code, i.item_name, l.unit order by 1, 재고수량 desc""",
           _say_stock, uses_period=False),
    Metric("production", "생산량", r"생산|양품|실적", ("pop_work_result", "job_work_order", "bas_item"),
           lambda p: f"""select count(*) as 실적건수, count(distinct w.item_id) as 품목수, coalesce(sum(r.good_qty), 0) as 양품수량,
                                coalesce(sum(r.defect_qty), 0) as 불량수량, min(r.unit) as 단위
                           from pop_work_result r join job_work_order w on w.id = r.work_order_id where {p.ts('r.ended_at')}""",
           lambda p: f"""select i.item_code as 품목코드, i.item_name as 품목명, count(*) as 실적건수, sum(r.good_qty) as 양품수량,
                                sum(r.defect_qty) as 불량수량, min(r.unit) as 단위
                           from pop_work_result r join job_work_order w on w.id = r.work_order_id join bas_item i on i.id = w.item_id
                          where {p.ts('r.ended_at')} group by i.item_code, i.item_name order by 양품수량 desc""",
           _say_prod),
    Metric("shipment", "출하량", r"출하|출고|납품", ("shp_shipment", "lot", "lot_genealogy", "bas_partner", "bas_item"),
           # 출하 수량은 출하 LOT 이 아니라 계보 「출하」 화살표(부모 = 제품 LOT)의 qty 에 있다 — db-schema §3.3
           lambda p: f"""with sl as (select s.id, s.status, g.qty, pl.unit
                                         from shp_shipment s left join lot l on l.shipment_id = s.id and l.kind_base = 'SHIPMENT'
                                         left join lot_genealogy g on g.child_lot_id = l.id and g.relation_base = '출하'
                                         left join lot pl on pl.id = g.parent_lot_id
                                        where s.status <> '취소' and {p.day('s.ship_date')})
                         select count(distinct id) as 출하건수, count(distinct id) filter (where status = '승인') as 승인건수,
                                coalesce(sum(qty) filter (where status = '승인'), 0) as 출하수량, coalesce(sum(qty), 0) as 예정포함수량, min(unit) as 단위 from sl""",
           lambda p: f"""select s.shipment_no as 출하번호, s.ship_date as 출하일, b.partner_name as 거래처, s.status as 상태,
                                string_agg(distinct i.item_name, ', ') as 품목, count(g.id) as "LOT수", sum(g.qty) as 수량, min(pl.unit) as 단위
                           from shp_shipment s join bas_partner b on b.id = s.partner_id
                           left join lot l on l.shipment_id = s.id and l.kind_base = 'SHIPMENT'
                           left join lot_genealogy g on g.child_lot_id = l.id and g.relation_base = '출하'
                           left join lot pl on pl.id = g.parent_lot_id left join bas_item i on i.id = pl.item_id
                          where s.status <> '취소' and {p.day('s.ship_date')}
                          group by s.id, s.shipment_no, s.ship_date, b.partner_name, s.status order by s.status, s.shipment_no""",
           _say_ship),
    Metric("receipt", "입고량", r"입고", ("mat_receipt", "bas_item"),
           lambda p: f"""select count(*) as 입고건수, sum(qty) as 입고수량, unit as 단위 from mat_receipt where {p.day('receipt_date')} group by unit""",
           lambda p: f"""select i.item_code as 품목코드, i.item_name as 품목명, count(*) as 입고건수, sum(r.qty) as 입고수량, r.unit as 단위
                           from mat_receipt r join bas_item i on i.id = r.item_id where {p.day('r.receipt_date')}
                          group by i.item_code, i.item_name, r.unit order by 입고수량 desc""",
           _say_rcpt),
    Metric("defect", "불량률", r"불량|불합격", ("pop_work_result", "qua_inspection"),
           lambda p: f"""select coalesce(sum(r.good_qty), 0) as 양품수량, coalesce(sum(r.defect_qty), 0) as 불량수량,
                                (select count(*) from qua_inspection q where q.judgement = '불합격' and {p.ts('q.judged_at')}) as 불합격판정
                           from pop_work_result r where {p.ts('r.ended_at')}""",
           lambda p: f"""select i.item_code as 품목코드, i.item_name as 품목명, sum(r.good_qty) as 양품수량, sum(r.defect_qty) as 불량수량,
                                round(100.0 * sum(r.defect_qty) / nullif(sum(r.good_qty) + sum(r.defect_qty), 0), 1) as "불량률(%)"
                           from pop_work_result r join job_work_order w on w.id = r.work_order_id join bas_item i on i.id = w.item_id
                          where {p.ts('r.ended_at')} group by i.item_code, i.item_name order by "불량률(%)" desc nulls last, 불량수량 desc""",
           _say_defect),
    Metric("work_order", "작업지시 현황", r"작업\s*지시|지시\s*현황", ("job_work_order",),
           lambda p: f"""select status as 상태, count(*) as 건수 from job_work_order where {p.day('plan_date')} group by status order by 2 desc""",
           lambda p: f"""select w.work_order_no as 작업지시번호, i.item_name as 품목명, w.plan_qty as 계획수량, w.unit as 단위, w.status as 상태, w.plan_date as 계획일
                           from job_work_order w left join bas_item i on i.id = w.item_id where {p.day('w.plan_date')} order by w.status, w.work_order_no""",
           _say_wo),
)
BY_KEY = {m.key: m for m in CATALOG}

#: 지표 질문의 신호(양 · 현황 · 기간) — 이게 없으면 「생산」 이라는 낱말만으로 지표로 보지 않는다
QTY_CUE = r"량|수량|실적|몇|얼마|합계|현황|률|율|건수|오늘|금일|어제|그제|이번|지난|최근|주간|월간|요약|보고"
#: 문서 질문의 신호 — 사용법 · 절차 · 규칙
DOC_CUE = r"어떻게|방법|순서|절차|화면|메뉴|프로세스|규칙|결정|의미|뜻|설명|정의|차이|왜|무엇|뭐야|뭔가|기능"
#: 정형 지표로는 못 푸는 세부 조건 — LLM SQL 로 넘긴다
FREE_CUE = r"[A-Z]{2,}-[A-Z0-9-]+|가장|상위|하위|top|비교|추이|평균|대비|별로|순위|목록|리스트|어느|누가|어떤\s*(품목|거래처|설비|작업자)"


def match(q: str) -> list[Metric]:
    if re.search(DOC_CUE, q) or not re.search(QTY_CUE, q):
        return []
    hits = [m for m in CATALOG if re.search(m.pattern, q)]
    if any(m.key == "defect" for m in hits):                     # 「불량률」 은 생산 지표 하나로 충분
        hits = [m for m in hits if m.key != "production" or re.search(r"생산\s*량|양품", q)]
    return hits[:3]


def is_free(q: str) -> bool:
    return bool(re.search(FREE_CUE, q, re.I))
