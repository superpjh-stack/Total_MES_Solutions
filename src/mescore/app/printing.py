"""출력 — 양식 4(작업지시서 · LOT 라벨 · 출하 라벨 · 성적서) · Code128 인라인 SVG · 라벨 데이터 · 프린터 어댑터 (G-C14 · `interfaces.md` §5 · D-10).

담당 **개발2**. 라벨 · 바코드는 이 모듈뿐이다. 외부 CDN · 이미지 · 클라이언트 JS 바코드 0.

    render_print(request, template, data, *, screen_id) -> HTMLResponse   # templates/print/<template>.html (팩이 같은 이름으로 덮어쓴다 · E7)
    barcode_svg(text, *, height=40) -> Markup                               # docs/design/print/barcode_spec.md §2 — 값은 번호 글자 그대로
    label_for(lot_id) -> dict                                               # LOT 라벨 데이터 (번호 · 품목 · 수량 · 일시 · attrs 표시용)
    class PrintAdapter: send(job) -> PrintResult                            # 기본 = 브라우저 인쇄(아무것도 보내지 않는다 · sent=False)
    adapter() -> PrintAdapter                                               # 팩 adapters.printing 이 있으면 그 모듈의 adapter() / ADAPTER

바코드 값은 `A-Z 0-9 -` 만 — 밖의 글자가 오면 `ValueError`(조용히 바꾸지 않는다). 세트 B ↔ C 자동 전환으로 모듈 수를 줄인다.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from markupsafe import Markup, escape

from ..db import conn
from . import packs, rbac, templating
from .packs import t
from .util import http, screen

# ── Code 128 (ISO/IEC 15417) ────────────────────────────────────────────
#: 심벌 값 0~105 의 막대 · 공백 폭(막대부터 번갈아 6개 · 합 11 모듈)
CODE128_WIDTHS: tuple[str, ...] = (
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232",
)
CODE128_STOP = "2331112"                    # 정지 심벌 13 모듈
START_B, START_C, CODE_B, CODE_C = 104, 105, 100, 99
QUIET_ZONE = 10                             # 좌우 각 10 모듈 (barcode_spec.md §2)
ALLOWED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
MAX_LEN = 24


def _digits(s: str, i: int) -> int:
    n = 0
    while i + n < len(s) and s[i + n].isdigit():
        n += 1
    return n


def code128_symbols(value: str) -> list[int]:
    """번호 → 심벌 값(시작 + 데이터 + 체크섬 · 정지 제외). 세트 B 기본, 숫자 4자리 이상 연속은 세트 C. 허용 밖 글자 · 빈 값 · 24자 초과는 ValueError."""
    if not isinstance(value, str) or value == "":
        raise ValueError("바코드로 찍을 값이 비어 있다")
    bad = sorted({ch for ch in value if ch not in ALLOWED})
    if bad:
        raise ValueError(f"바코드 허용 문자(A-Z 0-9 -) 밖의 글자: {bad!r}")
    if len(value) > MAX_LEN:
        raise ValueError(f"바코드 값이 {MAX_LEN}자를 넘는다 ({len(value)}자) — 번호를 자르지 않는다")
    n = len(value)
    first = _digits(value, 0)
    in_c = first >= 4 or (first == n and n % 2 == 0 and n >= 2)
    out = [START_C if in_c else START_B]
    i = 0
    while i < n:
        if in_c:
            if i + 1 < n and value[i].isdigit() and value[i + 1].isdigit():
                out.append(int(value[i:i + 2]))
                i += 2
            else:
                out.append(CODE_B)
                in_c = False
            continue
        run = _digits(value, i)
        if run >= 4:
            if run % 2 == 1:
                out.append(ord(value[i]) - 32)
                i += 1
            out.append(CODE_C)
            in_c = True
            continue
        out.append(ord(value[i]) - 32)
        i += 1
    out.append((out[0] + sum(pos * v for pos, v in enumerate(out[1:], start=1))) % 103)
    return out


def code128_modules(value: str) -> str:
    """`1` 막대 · `0` 공백 모듈 문자열 (시작 · 데이터 · 체크섬 · 정지). quiet zone 제외."""
    parts: list[str] = []
    for widths in [CODE128_WIDTHS[s] for s in code128_symbols(value)] + [CODE128_STOP]:
        for k, w in enumerate(widths):
            parts.append(("1" if k % 2 == 0 else "0") * int(w))
    return "".join(parts)


def barcode_svg(text: str, *, height: int = 40) -> Markup:
    """Code128 인라인 SVG — barcode_spec.md §2. viewBox `0 0 {quiet 10 + 모듈 + quiet 10} 100`, preserveAspectRatio none, crispEdges, 검은 막대만,
    aria-label = 값, 텍스트 노드 없음(사람이 읽는 글자는 양식이 바코드 아래에 찍는다). `height` 는 양식이 CSS 로 덮는 기본 높이 힌트(px)."""
    modules = code128_modules(text)
    total = len(modules) + 2 * QUIET_ZONE
    rects: list[str] = []
    x = 0
    while x < len(modules):
        if modules[x] == "1":
            w = 1
            while x + w < len(modules) and modules[x + w] == "1":
                w += 1
            rects.append(f'<rect x="{QUIET_ZONE + x}" width="{w}" height="100"/>')
            x += w
        else:
            x += 1
    safe = escape(text)
    return Markup(f'<svg class="barcode" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} 100" preserveAspectRatio="none" '
                  f'shape-rendering="crispEdges" role="img" aria-label="{safe}" data-barcode="{safe}" data-symbology="code128" '
                  f'data-modules="{total}" height="{max(8, int(height))}" style="fill:#000">{"".join(rects)}</svg>')


# ── 양식 렌더 ───────────────────────────────────────────────────────────
PRINT_TEMPLATES = ("work_order", "label_lot", "label_shipment", "document")


def render_print(request, template: str, data: dict, *, screen_id: str, status_code: int = 200):
    """`templates/print/<template>.html` 을 인쇄용 레이아웃으로. ctx 에 `barcode_svg` · `printed_at` · `printed_by` 가 더해진다.
    백엔드 우선(D-18) — Accept 에 text/html 이 없으면 data 가 JSON 으로 온다(함수는 빠진다)."""
    user = rbac.current_user(request)
    ctx = dict(data)
    ctx.setdefault("printed_at", datetime.now())
    ctx.setdefault("printed_by", user.user_name if user else "")
    ctx["barcode_svg"] = barcode_svg
    ctx["print_template"] = template
    return templating.render(request, f"print/{template}.html", ctx, screen_id=screen_id, status_code=status_code)


def _attr_lines(table: str, attrs: dict | None, limit: int = 2) -> list[dict]:
    """팩 속성(E2) 중 선언된 것만 라벨 두 줄까지 — 라벨 · 값."""
    if not attrs:
        return []
    out = []
    for spec in packs.attrs_of(table):
        v = attrs.get(spec.key)
        if v not in (None, ""):
            out.append({"label": t(spec.label), "value": v})
        if len(out) >= limit:
            break
    return out


def label_for(lot_id: int, *, size: str = "100x50") -> dict:
    """LOT 라벨 데이터 (F-MAT-07 · F-POP-08 — 분할 · 합병 LOT 도 같은 양식). 없는 LOT 은 404. 바코드 값 = lot_no."""
    from . import lineage  # noqa: PLC0415 — 순환 import 회피

    r = conn.q1("""select l.*, i.item_code, i.item_name, i.spec, w.work_order_no, p.partner_name, s.state
                     from lot l
                     join v_lot_state s on s.lot_id = l.id
                     left join bas_item i on i.id = l.item_id
                     left join job_work_order w on w.id = l.work_order_id
                     left join bas_partner p on p.id = l.partner_id
                    where l.id = %s""", (int(lot_id),))
    if r is None:
        raise http.not_found(t("없는 LOT 입니다"))
    if size not in ("100x50", "50x30"):
        raise http.validation_error(t("라벨 크기는 100x50 또는 50x30 입니다"), fields=[{"name": "size", "label": t("크기"), "reason": size}])
    return {
        "lot_id": r["id"], "lot_no": r["lot_no"], "kind": r["kind"], "kind_base": r["kind_base"], "kind_label": lineage.kind_label(r["kind"]),
        "item_code": r["item_code"], "item_name": r["item_name"], "spec": r["spec"], "qty": r["qty"], "unit": r["unit"], "made_at": r["made_at"],
        "insp_status": r["insp_status"], "state": r["state"], "work_order_no": r["work_order_no"], "partner_name": r["partner_name"],
        "attrs": _attr_lines("lot", r["attrs"]), "size": size,
    }


def shipment_label_for(shipment_id: int) -> dict:
    """출하 라벨 데이터 (D-601 가설 경로 `GET /shp/shipments/{id}/label` — 개발3 이 부른다). 바코드 값 = shipment_no."""
    s = conn.q1("""select s.*, p.partner_code, p.partner_name, o.order_no from shp_shipment s
                     join bas_partner p on p.id = s.partner_id left join ord_order o on o.id = s.order_id where s.id = %s""", (int(shipment_id),))
    if s is None:
        raise http.not_found(t("없는 출하입니다"))
    x = conn.q1("select lot_no from lot where shipment_id = %s and kind_base = 'SHIPMENT' order by id limit 1", (s["id"],))
    agg = conn.q1("""select count(*) as n, sum(g.qty) as qty, min(l.unit) as unit
                       from lot_genealogy g join lot x on x.id = g.child_lot_id join lot l on l.id = g.parent_lot_id
                      where x.shipment_id = %s and g.relation_base = '출하'""", (s["id"],))
    return {"shipment_no": s["shipment_no"], "partner_code": s["partner_code"], "partner_name": s["partner_name"], "ship_date": s["ship_date"],
            "status": s["status"], "approved_at": s["approved_at"], "approved_by": s["approved_by"], "lot_count": agg["n"] if agg else 0,
            "total_qty": agg["qty"] if agg else None, "unit": agg["unit"] if agg else None, "order_no": s["order_no"],
            "shipment_lot_no": x["lot_no"] if x else None}


# ── 프린터 어댑터 (E7) ────────────────────────────────────────────────────
@dataclass
class PrintJob:
    kind: str                    # label_lot | label_shipment | work_order | document
    template: str
    data: dict = field(default_factory=dict)
    copies: int = 1
    printer: str | None = None


@dataclass(frozen=True)
class PrintResult:
    sent: bool
    printer: str | None = None
    message: str = ""


class PrintAdapter:
    """기본 = 브라우저 인쇄. 아무것도 보내지 않고 `sent=False` 를 돌려준다 — 화면의 인쇄 버튼이 출력한다(D-10). 팩이 ZPL 등으로 교체한다."""

    name = "browser"

    def send(self, job: PrintJob) -> PrintResult:
        return PrintResult(sent=False, printer=None, message=t("브라우저 인쇄 — 프린터로 보내지 않았다"))


_ADAPTER: PrintAdapter | None = None


def adapter() -> PrintAdapter:
    """팩 `pack.yaml: adapters.printing` 모듈의 `adapter()` 또는 `ADAPTER`. 없으면 코어 기본. 모듈이 있는데 둘 다 없으면 실패한다(조용한 폴백 0)."""
    global _ADAPTER
    if _ADAPTER is not None:
        return _ADAPTER
    pack = packs.current()
    rel = pack.adapters.get("printing")
    if not rel or pack.dir is None:
        _ADAPTER = PrintAdapter()
        return _ADAPTER
    path = pack.dir / rel
    spec = importlib.util.spec_from_file_location(f"packs.{pack.name}.adapters.printing", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    obj: Any = getattr(mod, "ADAPTER", None) or (getattr(mod, "adapter", None) and mod.adapter())
    if not isinstance(obj, PrintAdapter):
        raise RuntimeError(f"{path}: `adapter()` 또는 `ADAPTER` 가 printing.PrintAdapter 가 아니다")
    _ADAPTER = obj
    return _ADAPTER


def reset_adapter() -> None:
    global _ADAPTER
    _ADAPTER = None


def fmt(v: Any, blank: str = screen.EMPTY) -> str:
    return screen.txt(v, blank)
