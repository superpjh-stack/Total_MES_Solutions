"""trc 라우터 — LOT 추적 (기능 3 · F-TRC-01~03) · 담당 개발3.

**어떤 테이블에도 쓰지 않는다**(G-C05). 이 파일에는 SQL 이 한 줄도 없다 — 개발2 `lineage` 의 **읽기 함수만** 부른다
(`resolve` · `search` · `trace_forward` · `trace_backward`). 추적은 `lot_genealogy` 를 따라가는 재귀 조회 하나이고 경로 · 결과를 어디에도 저장하지 않는다.
화면을 열 때 남는 접근 로그 한 줄은 공통 코드(`templating.render`)의 것이다.

번호 하나(원재료 LOT · 생산 LOT · 출하 LOT)를 넣으면 경로가 깊이 순서로 보인다. 자식이 없는 생산 LOT 은 `재고` 로 표시한다.
없는 번호는 **그 화면을 422 로 다시 그린다**(스캔칸 유지 · api-contract.md §2). 모바일 390px 에서는 표가 아니라 카드(접기)로 그린다(G-C13).
각 노드에서 지시 · 실적 · 측정값 · 검사로 가는 링크(G-C08)는 그 화면의 경로 + `?no=`(LOT 번호) / `?wo=`(지시 번호 · D-604).

  TRC-01 정방향 추적  GET /trc/forward?no=    F-TRC-01  lineage.trace_forward
  TRC-02 역방향 추적  GET /trc/backward?no=   F-TRC-02  lineage.trace_backward
  TRC-03 번호 검색    GET /trc/search?q=      F-TRC-03  lineage.search
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .. import nav, rbac, templating
from ..packs import t
from ..util import http

router = APIRouter()

SEARCH_LIMIT = 50
FORWARD, BACKWARD = "forward", "backward"
#: 모바일 접힘 규칙(디자이너2 §4) — 깊이 2 부터 접힘 · 형제 3건 초과면 그 단도 접힘
MOBILE_OPEN_DEPTH = 1
MOBILE_FOLD_OVER = 3


def _lineage():
    from .. import lineage  # noqa: PLC0415 — 개발2 모듈 (읽기 함수만)
    return lineage


def _links(node) -> dict[str, str]:
    """G-C08 — LOT 번호 하나로 지시 · 실적 · 측정값 · 검사 · 출하 화면을 연다. 경로는 nav 에서."""
    no = quote(node.no, safe="")
    out = {"lot": f"{nav.path_of('MAT-03') if node.kind_base == 'MATERIAL' else nav.path_of('QUA-02')}?no={no}"}
    if node.work_order_no:                                                              # D-604 — JOB-02 `?wo=` 는 지시 번호를 받는다(개발1 wo_of_key)
        out["work_order"] = f"{nav.path_of('JOB-02')}?wo={quote(node.work_order_no, safe='')}"   # 실적 · 측정값은 지시 현황에서 드릴다운
    if node.kind_base == "PRODUCT":
        out["inspection"] = f"{nav.path_of('QUA-02')}?no={no}"
    if node.kind_base == "SHIPMENT":
        out["shipment"] = f"{nav.path_of('SHP-02')}?id={node.shipment_id}" if node.shipment_id else nav.path_of("SHP-01")
    out["forward"] = f"{nav.path_of('TRC-01')}?no={no}"
    out["backward"] = f"{nav.path_of('TRC-02')}?no={no}"
    return out


def _stages(trace) -> list[dict]:
    """화살표를 출발점에서 가까운 순(`depth`)으로 묶는다 — 화면의 "단계". 계산해서 보여 줄 뿐 저장하지 않는다.
    수량은 둘이다(DEF-QA3-006): `qty` = 화살표 수량(lot_genealogy.qty — 이 관계로 옮겨 간 양) · `lot_qty` = 도착 LOT 의 `lot.qty`(= `to.qty`).
    합병 LOT 은 화살표 50 + 50 이어도 노드는 100 이다 — 트리 노드에는 `lot_qty` 를, 관계 옆에는 `qty` 를 쓴다."""
    stages: dict[int, dict] = {}
    for e in trace.edges:
        near, far = (e.parent, e.child) if trace.direction == FORWARD else (e.child, e.parent)
        st = stages.setdefault(e.depth, {"depth": e.depth, "edges": [], "relations": [], "nodes": {}})
        st["edges"].append({"genealogy_id": e.genealogy_id, "relation": e.relation, "relation_base": e.relation_base, "qty": e.qty,
                            "lot_qty": far.qty, "unit": far.unit, "from": near, "to": far, "links": _links(far)})
        if e.relation not in st["relations"]:
            st["relations"].append(e.relation)
        st["nodes"].setdefault(far.id, far)
    out = []
    for d in sorted(stages):
        st = stages[d]
        st["nodes"] = list(st["nodes"].values())
        st["open"] = d <= MOBILE_OPEN_DEPTH and len(st["edges"]) <= MOBILE_FOLD_OVER
        out.append(st)
    return out


def _render(request: Request, template: str, screen_id: str, status_code: int = 200, **ctx):
    base = {"mode": "search", "q": "", "no": "", "results": None, "trace": None, "stages": [], "start": None, "start_links": None,
            "materials": [], "shipments": [], "stock": [], "limit": SEARCH_LIMIT, "scan_error": None, "forward": FORWARD, "backward": BACKWARD}
    base.update(ctx)
    return templating.render(request, template, base, screen_id=screen_id, status_code=status_code)


def _trace(request: Request, no: str, direction: str, screen_id: str, template: str):
    """번호 하나에서 그 방향으로. 없는 번호 422 — JSON 은 올리고, 브라우저는 **이 화면**을 422 로 다시 그린다."""
    no = (no or "").strip()
    if not no:
        return _render(request, template, screen_id, mode=direction)
    lineage = _lineage()
    node = lineage.resolve(no)
    if node is None:
        problem = http.validation_error(t("없는 번호입니다") + " — " + t("원재료 LOT · 생산 LOT · 출하 LOT 번호가 아닙니다"),
                                        fields=[{"name": "no", "label": t("번호"), "reason": no}])
        if not http.wants_html(request):
            raise problem
        detail = problem.detail if isinstance(problem.detail, dict) else {}
        return _render(request, template, screen_id, status_code=422, mode=direction, no=no,
                       scan_error={"message": detail.get("message", ""), "fields": detail.get("fields") or []})
    trace = lineage.trace_forward(node.id) if direction == FORWARD else lineage.trace_backward(node.id)
    return _render(request, template, screen_id, mode=direction, no=node.no, q=node.no, trace=trace, start=trace.start, start_links=_links(trace.start),
                   stages=_stages(trace), materials=trace.materials(), shipments=trace.shipments(), stock=trace.stock(),
                   node_count=len(trace.nodes()), edge_count=len(trace.edges), depth=max((e.depth for e in trace.edges), default=0))


@router.get(nav.path_of("TRC-01"), response_class=HTMLResponse)                     # F-TRC-01 정방향 추적
def forward(request: Request, no: str = "", user: rbac.User = rbac.require_fn("F-TRC-01")):
    return _trace(request, no, FORWARD, "TRC-01", "trc/forward.html")


@router.get(nav.path_of("TRC-02"), response_class=HTMLResponse)                     # F-TRC-02 역방향 추적
def backward(request: Request, no: str = "", user: rbac.User = rbac.require_fn("F-TRC-02")):
    return _trace(request, no, BACKWARD, "TRC-02", "trc/backward.html")


@router.get(nav.path_of("TRC-03"), response_class=HTMLResponse)                     # F-TRC-03 번호 검색
def search(request: Request, q: str = "", user: rbac.User = rbac.require_fn("F-TRC-03")):
    q = (q or "").strip()
    results = None
    if q:
        results = [{"node": n, "links": _links(n)} for n in _lineage().search(q, limit=SEARCH_LIMIT)]
    return _render(request, "trc/search.html", "TRC-03", mode="search", q=q, results=results)
