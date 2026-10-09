"""E7 수집 태그 매핑 — 염도 · 온습도 · 소독수 · 테이핑 센서 태그 ↔ 설비 ↔ `bas_process_param.param_key` (개발3 · 2026-10-09).

수집 **드라이버는 코어 기본(HTTP `POST /ifc/collect` → `collect.receive`)을 그대로 쓴다** — 여기에는 구독 · 제어가 없다.
이 모듈은 (1) 설비 종류 · 태그 표(`seed/equipment_example.csv` 의 `attrs.equip_type` · `attrs.collect_tags` 열을 읽는다 — 지어내지 않는다),
(2) 태그 → 알람 종류(`bas_code ALARM_KIND`), (3) 염도센서 ↔ 절임통 고정 매핑 **(미확정 D-206 → 빈 표)** 을 준다.
훅(`hooks.on_collect`)과 라우터(`tank` · `wsh` · `age`)가 같은 표를 본다. 운영 데이터에서는 `bas_equipment.attrs.equip_type`(pack.yaml attrs) 이 우선이고
이 CSV 표는 `(예시)` 시드의 보조다.
"""

from __future__ import annotations

import csv
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parents[1]
EQUIPMENT_CSV = PACK_DIR / "seed" / "equipment_example.csv"

#: 염도센서 → 절임통 고정 매핑 — 임진강 산출물에 없다(D-206). 빈 표 = 판정하지 않는다. 배치 등록 때 `x_kimchi_tank.sensor_equipment_id` 로 주는 것이 우선.
SENSOR_TO_TANK: dict[str, str] = {}

#: 태그 → 환경 알람 종류 (`seed/codes.csv` ALARM_KIND). 없는 태그는 `<라벨> 이탈` 로 적는다.
TAG_ALARM_KIND: dict[str, str] = {
    "temp_c": "냉장고 온도 이탈",
    "humidity_pct": "냉장고 습도 이탈",
    "sanitizer_ppm": "소독수 10ppm 미달",
    "salinity_pct": "절임 염도 이탈",
}

#: 테이핑기(자동포장기) 태그 — `on_collect` 집계 C
TAPING_COUNT_TAG, TAPING_RUN_TAG = "pack_count", "run_state"
SALINITY_TAG = "salinity_pct"

#: 설비 종류 (equip_type) — 라우터가 절임통 · 냉장고 · 염도센서 · 소독수 장치 · 자동포장기를 고를 때
TANK, FRIDGE, SALINITY_SENSOR, SANITIZER, TAPING_MACHINE = "절임통", "냉장고", "염도센서", "소독수공급장치", "자동테이핑기"


def _read() -> list[dict]:
    if not EQUIPMENT_CSV.exists():
        return []
    with EQUIPMENT_CSV.open(encoding="utf-8-sig", newline="") as fh:
        # 열 이름 `attrs.<키>` (seed_core 가 attrs 에 넣는다 · CR-9) 와 예전 맨 이름 둘 다 같은 키로 읽는다
        return [{k.strip().removeprefix("attrs."): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


_ROWS = _read()
#: 설비 코드 → 종류 (CSV)
EQUIP_TYPE: dict[str, str] = {r["equip_code"]: r["equip_type"] for r in _ROWS if r.get("equip_code")}
#: 설비 코드 → 수집 태그 목록 (CSV `collect_tags` 열 `a;b`)
EQUIPMENT_TAGS: dict[str, tuple[str, ...]] = {r["equip_code"]: tuple(x for x in r.get("collect_tags", "").split(";") if x) for r in _ROWS if r.get("equip_code")}


def equip_type_of(equip_code: str, attrs: dict | None = None) -> str | None:
    """설비 종류 — `attrs.equip_type`(BAS-05 입력) 이 있으면 그것, 없으면 (예시) CSV 표. 둘 다 없으면 None."""
    if attrs and attrs.get("equip_type"):
        return str(attrs["equip_type"])
    return EQUIP_TYPE.get(equip_code)


def is_type(equip_code: str, kind: str, attrs: dict | None = None) -> bool:
    return equip_type_of(equip_code, attrs) == kind


def tags_of(equip_code: str) -> tuple[str, ...]:
    return EQUIPMENT_TAGS.get(equip_code, ())


def alarm_kind(tag: str, label: str | None = None) -> str:
    return TAG_ALARM_KIND.get(tag) or f"{label or tag} 이탈"


def tank_code_for(sensor_code: str) -> str | None:
    """센서 → 절임통 고정 매핑 (미확정이면 None)."""
    return SENSOR_TO_TANK.get(sensor_code)


class CollectDriver:
    """E7 드라이버 자리 — 이 팩은 코어 HTTP 수신(`POST /ifc/collect`)을 그대로 쓴다. 구독할 것이 없으므로 start/stop 은 아무 일도 하지 않는다(제어 명령 0)."""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None
