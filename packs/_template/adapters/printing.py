"""E7 프린터 어댑터 틀 — 코어 `mescore.app.printing.PrintAdapter`(개발2) 의 서명. pack.yaml: adapters.printing: adapters/printing.py"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PrintJob:
    template: str                      # work_order | label_lot | label_shipment | document
    data: dict = field(default_factory=dict)


@dataclass
class PrintResult:
    ok: bool
    message: str = ""


class PrintAdapter:
    """send(job) — 기본(코어)은 아무것도 보내지 않는다(브라우저 인쇄). ZPL 등 드라이버는 여기서 보낸다. 실패는 PrintResult(ok=False, message=…) 로 — 조용히 삼키지 않는다."""

    def send(self, job: PrintJob) -> PrintResult:
        raise NotImplementedError("프린터 드라이버 미구현 — 코어 기본(브라우저 인쇄)을 쓰려면 pack.yaml: adapters.printing: null")
