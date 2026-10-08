"""E7 ERP 어댑터 틀 — 코어 `mescore.app.erp.ErpAdapter`(개발3) 의 서명. 기본은 전부 501 `ERP 연계 미확정 (D-02)` — 조용한 폴백 0 (G-C16)."""

from __future__ import annotations

from datetime import datetime


class ErpAdapter:
    def push(self, kind: str, payload: dict) -> dict:
        """코어 기본: raise http.undecided("D-02", "ERP 연계"). 드라이버는 결과 dict {"ok": bool, "message": str, ...} 를 돌려준다."""
        raise NotImplementedError("ERP 드라이버 미구현 — 코어 기본(501)을 쓰려면 pack.yaml: adapters.erp: null")

    def pull(self, kind: str, since: datetime) -> list[dict]:
        raise NotImplementedError("ERP 드라이버 미구현")
