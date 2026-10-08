"""출력 printing — Code128 심벌 · B/C 전환 · 체크섬 · SVG 모양(barcode_spec.md §2) · 허용 밖 글자 ValueError · label_for · PrintAdapter 기본 (개발2)."""

from __future__ import annotations

import re

import pytest

from mescore.app import printing


def _checksum_ok(symbols: list[int]) -> bool:
    data, check = symbols[:-1], symbols[-1]
    return (data[0] + sum(i * v for i, v in enumerate(data[1:], start=1))) % 103 == check


def test_code128_symbols_and_checksum():
    s = printing.code128_symbols("P261009-0001")
    assert s[0] == printing.START_B and _checksum_ok(s)
    assert printing.CODE_C in s                                                  # 숫자 4자리 이상 연속은 세트 C
    s2 = printing.code128_symbols("123456")
    assert s2[0] == printing.START_C and s2[1:4] == [12, 34, 56] and _checksum_ok(s2)
    s3 = printing.code128_symbols("AB-1")
    assert s3[0] == printing.START_B and printing.CODE_C not in s3 and _checksum_ok(s3)
    m = printing.code128_modules("AB-1")
    assert set(m) == {"0", "1"} and m.endswith("11") and len(m) == 11 * len(s3) + 13
    # 세트 C 혼합이 세트 B 만보다 모듈이 적다
    assert len(printing.code128_modules("P261009-0001")) < 11 * (len("P261009-0001") + 2) + 13


def test_barcode_svg_shape_per_spec():
    svg = printing.barcode_svg("M261009-0007", height=40)
    assert svg.startswith("<svg") and 'preserveAspectRatio="none"' in svg and 'shape-rendering="crispEdges"' in svg
    assert 'aria-label="M261009-0007"' in svg and 'data-symbology="code128"' in svg and "<text" not in svg
    vb = re.search(r'viewBox="0 0 (\d+) 100"', svg)
    assert vb and int(vb.group(1)) == len(printing.code128_modules("M261009-0007")) + 2 * printing.QUIET_ZONE
    rects = re.findall(r'<rect x="(\d+)" width="(\d+)" height="100"/>', svg)
    assert rects and int(rects[0][0]) == printing.QUIET_ZONE                      # 첫 막대는 quiet zone 뒤
    assert "fill:#000" in svg and "http" not in svg.replace("http://www.w3.org/2000/svg", "")


@pytest.mark.parametrize("bad", ["", "abc", "A B", "LOT_1", "가-1", "A" * 25, "A.1"])
def test_barcode_rejects_disallowed_characters(bad):
    with pytest.raises(ValueError):
        printing.barcode_svg(bad)


def test_print_adapter_default_is_browser():
    printing.reset_adapter()
    a = printing.adapter()
    res = a.send(printing.PrintJob(kind="label_lot", template="label_lot", data={}))
    assert isinstance(a, printing.PrintAdapter) and res.sent is False and res.printer is None and "브라우저" in res.message


def test_label_for_404_and_fields():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ex:
        printing.label_for(999999)
    assert ex.value.status_code == 404
    from mescore.db import conn
    row = conn.q1("select id from lot order by id limit 1")
    if row is None:
        pytest.skip("LOT 없음")
    d = printing.label_for(row["id"])
    assert {"lot_no", "kind", "kind_label", "item_code", "item_name", "qty", "unit", "made_at", "insp_status", "work_order_no", "partner_name", "attrs", "size"} <= set(d)
    with pytest.raises(HTTPException):
        printing.label_for(row["id"], size="10x10")
