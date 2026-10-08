"""E7 수집 드라이버 틀 — 코어 `mescore.app.collect`(개발2) 의 `CollectMessage` 를 만들어 `collect.receive(cur, msg)` 로 넘긴다.
코어 기본은 HTTP POST /ifc/collect (api-contract.md §4). MQTT 구독 등은 여기서 돌며 같은 함수를 부른다. 제어 명령은 없다."""

from __future__ import annotations


class CollectDriver:
    def start(self) -> None:
        """구독 시작 — 받은 메시지마다 collect.receive(cur, CollectMessage(equip_code, ts, tags, source)) 를 conn.tx() 안에서 부른다."""
        raise NotImplementedError("수집 드라이버 미구현 — 코어 기본(HTTP 수신)을 쓰려면 pack.yaml: adapters.collect: null")

    def stop(self) -> None:
        raise NotImplementedError("수집 드라이버 미구현")
