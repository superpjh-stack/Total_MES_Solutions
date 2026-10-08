"""printfilm 프린터 어댑터 (E7 · pack.yaml: adapters.printing) — 브라우저 인쇄 그대로 + 라벨 양식 HTML 은 templates/print/ 가 그린다 (엘컴화인 D-04).

코어 `printing.PrintAdapter` 를 상속한다. `send` 는 아무것도 보내지 않고 `sent=False` 와 "어느 양식 · 몇 장" 을 돌려준다 —
프린터 규격(ZPL 등)이 정해지면 여기서 보낸다(D-5nn 미확정). 조용한 폴백 없음: 모르는 양식은 ValueError.
"""

from __future__ import annotations

from mescore.app import printing
from mescore.app.packs import t

#: 이 팩이 덮어쓰는 양식 3 + 코어 출하 라벨 (templates/print/)
TEMPLATES: tuple[str, ...] = ("label_lot", "document", "work_order", "label_shipment")


class PrintAdapter(printing.PrintAdapter):
    name = "browser-html"

    def send(self, job: printing.PrintJob) -> printing.PrintResult:
        if job.template not in TEMPLATES:
            raise ValueError(f"모르는 인쇄 양식 {job.template!r} — {TEMPLATES}")
        return printing.PrintResult(sent=False, printer=None,
                                    message=f"{t('브라우저 인쇄')} — {job.template} × {max(1, int(job.copies or 1))} ({t('프린터 규격 미확정')})")


ADAPTER = PrintAdapter()


def adapter() -> printing.PrintAdapter:
    return ADAPTER
