#!/usr/bin/env python
"""foodservice 팩 시드 한 벌 — 코어 시드 + 팩 시드 + 코어 API 로만 넣는 것(레시피 · KPI 지표 · 역할별 계정) + attrs → ext 따라잡기. **두 번 돌려도 행 수가 같다**(G-C09 팩판).

    MES_PACK=foodservice MES_PG_DSN=postgresql:///mes_foodservice_db uv run python packs/foodservice/seed_pack.py

왜 따로 있는가 (README 「구현 메모」)
- `seed_core.seed_pack()` 은 `process_params` · `inspection_items` 를 `seeds[]`(processes.csv) **앞에** 넣어 팩 공정(PRC-040 …)이 아직 없는 첫 시드에서
  `bas_process_param.process_id` NOT NULL 로 실패한다 → 이 스크립트가 공정을 **코어 API(F-BAS-09)** 로 먼저 만든 뒤 `seed_core` 를 부른다 (코어 변경 요청 · progress-dev1.md §3).
- `seeds[]` 는 codes* · items* · processes* · equipment* · partners* 만 받는다 → 레시피(`bom_example.csv`) 는 F-BAS-05, KPI 지표(`kpi_indicators.csv`) 는 F-KPI-06,
  역할 6 계정은 F-SYS-01 로 넣는다. 코어 테이블에 쓰는 SQL 은 이 파일에 없다 (pack-contract R7) — 쓰기는 전부 코어 라우터가 한다.
- 설비 · 거래처의 `attrs`(설비유형 · 통신방식 · 제조사모델 · 냉장/냉동 · 임계 · 사업자번호 …) 는 F-BAS-18 · 22 수정 API 로 넣고, 훅 `after_save_*` 가 ext 로 복사한다.
- 비밀번호는 `MES_SEED_PASSWORD` 뿐 — 값은 어디에도 적지 않는다 (G-C19).
"""

from __future__ import annotations

import csv
import os
import sys
import warnings
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent
ROOT = PACK_DIR.parents[1]
PACK = PACK_DIR.name
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ["MES_PACK"] = PACK
warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")

from mescore.app import packs  # noqa: E402
from mescore.app.settings import get_settings, reset_cache  # noqa: E402
from mescore.db import conn, seed_core  # noqa: E402

#: 역할별 시드 계정 — 로그인 ID = 역할 코드 소문자 (seed_core.USERS 와 같은 규칙 · D-08). admin 은 seed_core 가 만든다
PACK_USERS = [("production", "생산관리 담당", "PRODUCTION"), ("nutritionist", "영양사", "NUTRITIONIST"), ("worker", "현장 작업자", "WORKER"),
              ("shipping", "출고 담당", "SHIPPING"), ("vendor", "외부업체", "VENDOR"),
              # 코어 테스트(tests/) 가 쓰는 코어 역할 계정의 별칭 — 역할 6 이 코어 4 를 대체(D-503)해 prod · qa · field 가 없다 (pack-contract R9 · progress-dev1.md §3)
              ("prod", "생산 담당 (코어 별칭)", "PRODUCTION"), ("qa", "품질 담당 (코어 별칭)", "NUTRITIONIST"), ("field", "현장 작업자 (코어 별칭)", "WORKER")]


def _csv(name: str) -> list[dict]:
    with (PACK_DIR / "seed" / name).open(encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k is not None} for r in csv.DictReader(f)]   # 머리행보다 긴 행의 꼬리(None 키)는 버린다


def _client():
    from fastapi.testclient import TestClient
    from mescore.app.main import app

    pw = get_settings().seed_password
    if not pw:
        raise SystemExit("MES_SEED_PASSWORD 미설정 — 시드 계정 · API 로그인을 할 수 없다 (G-C19: 기본 비밀번호는 두지 않는다)")
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/login", data={"login_id": "admin", "password": pw})
    if r.status_code != 200 or not r.json().get("ok"):
        raise SystemExit(f"admin 로그인 실패 {r.status_code} — {r.text[:200]}")
    return c


def _ok(r, what: str) -> dict:
    if r.status_code != 200:
        raise SystemExit(f"{what}: {r.status_code} {r.text[:300]}")
    return r.json()


def seed_processes(c) -> int:
    """공정 9 — F-BAS-09 등록 · 있으면 F-BAS-10 으로 attrs(collect_type) 만 갱신. seed_core 의 process_params 보다 먼저 있어야 한다."""
    n = 0
    for r in _csv("processes.csv"):
        row = conn.q1("select id from bas_process where process_code = %s", (r["process_code"],))
        data = {"process_name": r["process_name"], "seq": r.get("seq") or "0", "use_yn": (r.get("use_yn") or "Y").upper(), "attr_collect_type": r.get("collect_type") or ""}
        if row is None:
            _ok(c.post("/bas/processes", data={"process_code": r["process_code"], **data}), f"공정 {r['process_code']}")
            n += 1
        else:
            _ok(c.post(f"/bas/processes/{row['id']}", data=data), f"공정 {r['process_code']} 수정")
    return n


def seed_equipment_attrs(c) -> int:
    n = 0
    for r in _csv("equipment.csv"):
        row = conn.q1("select id from bas_equipment where equip_code = %s", (r["equip_code"],))
        if row is None:
            continue
        data = {"attr_equip_type": r.get("equip_type") or "", "attr_comm_type": r.get("comm_type") or "", "attr_maker_model": r.get("maker_model") or "",
                "attr_storage_kind": r.get("storage_kind") or "", "attr_temp_limit": r.get("temp_limit") or ""}
        _ok(c.post(f"/bas/equipment/{row['id']}", data=data), f"설비 {r['equip_code']} attrs")
        n += 1
    return n


def seed_partner_attrs(c) -> int:
    n = 0
    for r in _csv("partners_example.csv"):
        row = conn.q1("select id from bas_partner where partner_code = %s", (r["partner_code"],))
        if row is None:
            continue
        _ok(c.post(f"/bas/partners/{row['id']}", data={"attr_biz_no": r.get("biz_no") or "", "attr_delivery_addr": r.get("delivery_addr") or ""}), f"거래처 {r['partner_code']} attrs")
        n += 1
    return n


def seed_bom(c) -> int:
    """레시피 — bom_example.csv 의 (item_code, version) 마다 F-BAS-05 한 번. 있으면 건드리지 않는다."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in _csv("bom_example.csv"):
        groups.setdefault((r["item_code"], r["version"]), []).append(r)
    n = 0
    for (item_code, version), lines in groups.items():
        item = conn.q1("select id from bas_item where item_code = %s", (item_code,))
        if item is None:
            raise SystemExit(f"레시피 상위 메뉴 {item_code} 가 없다 — items_example.csv 먼저")
        if conn.q1("select 1 as hit from bas_bom where item_id = %s and version = %s", (item["id"], version)):
            continue
        data: dict = {"item_id": str(item["id"]), "version": version, "use_yn": "Y", "attr_batch_serve_qty": lines[0].get("batch_serve_qty") or "",
                      "attr_cook_step_desc": lines[0].get("cook_step_desc") or "", "attr_caution_note": lines[0].get("caution_note") or "",
                      "component_item_id": [], "qty": [], "unit": [], "loss_rate": []}
        for ln in lines:
            comp = conn.q1("select id from bas_item where item_code = %s", (ln["component_code"],))
            if comp is None:
                raise SystemExit(f"레시피 구성품 {ln['component_code']} 가 없다")
            for k, v in (("component_item_id", str(comp["id"])), ("qty", ln["qty"]), ("unit", ln.get("unit") or ""), ("loss_rate", ln.get("loss_rate") or "")):
                data[k].append(v)
        _ok(c.post("/bas/bom", data=data), f"레시피 {item_code} {version}")
        n += 1
    return n


def seed_kpi(c) -> int:
    n = 0
    for r in _csv("kpi_indicators.csv"):
        if conn.q1("select 1 as hit from kpi_indicator where indicator_key = %s", (r["indicator_key"],)):
            continue
        _ok(c.post("/kpi/indicators", data={"indicator_key": r["indicator_key"], "name": r["name"], "unit": r.get("unit") or "", "target_value": r.get("target_value") or "",
                                            "calc_kind": r["calc_kind"], "visible_yn": (r.get("visible_yn") or "Y").upper(), "seq": r.get("seq") or "0"}),
            f"KPI {r['indicator_key']}")
        n += 1
    return n


def seed_users(c) -> int:
    pw = get_settings().seed_password
    roles = {r["role_code"]: r["id"] for r in conn.q("select id, role_code from sys_role")}
    n = 0
    for login_id, name, role in PACK_USERS:
        if role not in roles or conn.q1("select 1 as hit from sys_user where login_id = %s", (login_id,)):
            continue
        _ok(c.post("/sys/users", data={"login_id": login_id, "user_name": f"{name} (예시)", "role_id": str(roles[role]), "password": pw}), f"계정 {login_id}")
        n += 1
    return n


def main() -> int:
    reset_cache()
    p = packs.load(PACK)
    from mescore.app import nav
    nav.rebuild()
    before = conn.table_counts()
    seed_core.seed_roles()
    seed_core.seed_permissions()
    seed_core.seed_users()
    seed_core.seed_numbering()
    seed_core.seed_codes()
    seed_core.seed_examples()
    c = _client()
    n_proc = seed_processes(c)
    files = seed_core.seed_pack()                     # process_params · inspection_items · codes · processes · equipment · partners · items
    dev = seed_core.run_dev_seeds()
    n_eq, n_pt, n_bom, n_kpi, n_usr = seed_equipment_attrs(c), seed_partner_attrs(c), seed_bom(c), seed_kpi(c), seed_users(c)
    from packs.foodservice import hooks               # noqa: PLC0415 — 팩 훅의 sync_ext
    with conn.tx() as cur:
        synced = hooks.sync_ext(cur)
    after = conn.table_counts()
    diff = {k: (before.get(k, 0), after.get(k, 0)) for k in sorted(set(before) | set(after)) if before.get(k, 0) != after.get(k, 0)}
    print(f"foodservice 시드 완료 — 팩 {p.name} · 공정 신규 {n_proc} · 팩 파일 {files} · 개발 시드 {dev} · 설비 attrs {n_eq} · 거래처 attrs {n_pt} · 레시피 신규 {n_bom} · KPI 신규 {n_kpi} · 계정 신규 {n_usr} · ext 동기 {synced}")
    print(f"행 수 변화 {len(diff)} 테이블: {diff if diff else '0 (멱등)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
