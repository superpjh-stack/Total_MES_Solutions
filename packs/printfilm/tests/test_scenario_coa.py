"""G-P04 S3 — COA 발행: 승인 출하의 롤별 ΔE · 판정 · 불량 · 길이 · 폭 · 공정 구분 스냅샷 · 바코드 = 출하 LOT 번호 · 발행본 불변 · 재발행 새 번호 (gates.yaml: S3 · 개발2)."""

from __future__ import annotations

import json

import pytest

from mescore.db import conn

from _helpers import HTML, P, approve, client, inspect, new_shipment, s1_upto_slitting, scan


def _approved_shipment() -> tuple[dict, dict]:
    x = s1_upto_slitting()
    inspect(x["s1"]["lot_no"], "합격", delta_e=0.9)
    inspect(x["s2"]["lot_no"], "합격", delta_e=1.3)
    ship = new_shipment()
    scan(ship["shipment_no"], x["s1"]["lot_no"])
    scan(ship["shipment_no"], x["s2"]["lot_no"])
    approve(ship["id"])
    return x, ship


@pytest.mark.fn("F-X-RLL-07")
def test_coa_snapshot():
    x, ship = _approved_shipment()
    prod = client("prod")
    # 2. 발행 — 번호 C+YYMMDD-+3 · snapshot.lots = [S①, S②] 각각 delta_e · judgement · defects · length_m · width_mm · process_type=슬리팅 · inspected_at
    r = prod.post(P["SHP-04"], data={"shipment_id": ship["id"], "doc_type": "성적서"})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["document_no"].startswith("C") and len(doc["document_no"]) == 11 and doc["lot_count"] == 2 and doc["judgement"] == "합격"
    row = conn.q1("select snapshot from shp_document where id = %s", (doc["id"],))
    snap = row["snapshot"]
    lots = {l["lot_no"]: l for l in snap["lots"]}
    assert set(lots) == {x["s1"]["lot_no"], x["s2"]["lot_no"]}
    for k in ("delta_e", "judgement", "defects", "length_m", "width_mm", "process_type", "inspected_at", "slit_seq"):
        assert all(k in l for l in lots.values()), k
    assert lots[x["s1"]["lot_no"]]["delta_e"] == 0.9 and lots[x["s2"]["lot_no"]]["delta_e"] == 1.3
    assert {l["process_type"] for l in lots.values()} == {"슬리팅"} and {l["judgement"] for l in lots.values()} == {"합격"}
    assert lots[x["s1"]["lot_no"]]["width_mm"] == 300 and lots[x["s2"]["lot_no"]]["width_mm"] == 300 and lots[x["s1"]["lot_no"]]["length_m"] == 2000
    assert all(l["defects"] == [] for l in lots.values())
    xlot = conn.q1("select lot_no from lot where shipment_id = %s and kind_base = 'SHIPMENT'", (ship["id"],))
    assert snap["shipment"]["shipment_lot_no"] == xlot["lot_no"] and snap["pack"] == "printfilm"
    # 3. 출력 — 팩 양식 · 제목 COA · 바코드 값 = 출하 LOT 번호 · '성적서' 날것 0 (G-P05)
    html = prod.get(f"{P['SHP-04']}/{doc['id']}/print", headers=HTML).text
    assert "COA" in html and f'aria-label="{xlot["lot_no"]}"' in html and f'aria-label="{doc["document_no"]}"' not in html
    assert "성적서" not in html and "0.9" in html and "1.3" in html and "슬리팅" in html
    # 4. 미승인 출하 → 422 (코어)
    other = new_shipment()
    assert prod.post(P["SHP-04"], data={"shipment_id": other["id"], "doc_type": "성적서"}).status_code == 422
    # 5. 승인 뒤 S① 새 검사 → 422 (코어 '출하된 LOT')
    assert client("qc").post(P["QUA-02"], data={"insp_type": "최종", "lot_no": x["s1"]["lot_no"], "i_delta_e": "9"}).status_code == 422
    # 6. 재발행 → 새 번호 · 이전 발행본 스냅샷 불변 (바이트 동일)
    before = json.dumps(conn.q1("select snapshot from shp_document where id = %s", (doc["id"],))["snapshot"], sort_keys=True, ensure_ascii=False)
    r2 = prod.post(P["SHP-04"], data={"shipment_id": ship["id"], "doc_type": "성적서"})
    assert r2.status_code == 200 and r2.json()["document_no"] != doc["document_no"]
    after = json.dumps(conn.q1("select snapshot from shp_document where id = %s", (doc["id"],))["snapshot"], sort_keys=True, ensure_ascii=False)
    assert before == after
    # 7. 미검사 롤 COA — S③ 은 코어 스캔이 막아 발생하지 않는다 (D-504 · 문서화만)
    print("\nS3:", doc["document_no"], "→", r2.json()["document_no"], "· 바코드", xlot["lot_no"], "· lots", sorted(lots))
