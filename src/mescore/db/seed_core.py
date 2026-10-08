"""공통 시드 — 역할 · 권한 표(모듈 × 역할 전 칸) · 계정 · 채번 규칙 · 공통코드 코어 그룹 · (예시) 기준정보 몇 개. **두 번 돌려도 행 수가 같다**(G-C09).

    uv run python -m mescore.db.seed_core             # 코어 → 팩(process_params · inspection_items · seeds) → 개발 시드(seed_dev1~3 · 있는 것만)
    uv run python -m mescore.db.seed_core --core-only
    uv run python -m mescore.db.seed_core --reset     # 권한 표 · 채번 규칙을 core.yaml(+팩) 기본값으로 되돌린다

- 기대값은 전부 `packs.current()`(core.yaml + pack.yaml 병합본)에서 온다 — 여기 박힌 수는 없다. `MES_PACK=<팩>` 이면 팩 역할 · 칸 · 채번이 들어간다.
- 이미 있는 권한 칸 · 채번 규칙은 건드리지 않는다(SYS-03 · SYS-05 에서 바꾼 값을 시드가 되돌리면 안 된다). `--reset` 만 덮어쓴다.
- 계정 비밀번호는 `MES_SEED_PASSWORD` 로만 받는다. 없으면 **실패한다** — 기본 비밀번호를 지어내지 않는다(G-C19).
- 회사 실데이터는 없다. 표시명에는 `(예시)` 를 붙이고 코드에 `-EX-` 를 넣는다.
"""

from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

from ..app import auth, packs
from ..app.settings import get_settings
from ..app.util.screen import example
from . import conn

SEEDED_BY = "seed"
#: 역할별 시드 계정 — 로그인 ID = 역할 코드 소문자 (D-08). admin 은 반드시, 나머지는 그 역할이 병합본에 있을 때만
USERS: list[tuple[str, str, str]] = [
    ("admin", "관리자", "ADMIN"),
    ("prod", "생산 담당", "PROD"),
    ("qa", "품질 담당", "QA"),
    ("field", "현장 작업자", "FIELD"),
]
DEV_SEEDS = ("seed_dev1", "seed_dev2", "seed_dev3")

#: (예시) 기준정보 — 코어 한 바퀴 · 테스트용. 코드 -EX- · 이름 (예시)
EXAMPLE_PROCESSES = [("PRC-EX-01", "공정 1", 1), ("PRC-EX-02", "공정 2", 2)]
EXAMPLE_ITEMS = [("PRD-EX-01", "제품 1", "제품", "EA"), ("RAW-EX-01", "원재료 1", "원재료", "kg"), ("RAW-EX-02", "원재료 2", "원재료", "kg")]
EXAMPLE_EQUIPMENT = [("EQ-EX-01", "설비 1", "PRC-EX-01", "N")]
EXAMPLE_PARTNERS = [("CUST-EX-01", "고객사 1", "고객"), ("SUP-EX-01", "공급사 1", "공급")]
EXAMPLE_WORKERS = [("WK-EX-01", "작업자 1", "PRC-EX-01")]
EXAMPLE_DEFECTS = [("DF-EX-01", "불량 1", None)]


def seed_roles() -> None:
    for r in packs.current().roles:
        conn.x("""insert into sys_role (role_code, role_name, use_yn, created_by) values (%s, %s, 'Y', %s)
                  on conflict (role_code) do update set role_name = excluded.role_name, use_yn = 'Y', updated_at = now(), updated_by = %s""",
               (r["code"], r["name"], SEEDED_BY, SEEDED_BY))


def permission_rows() -> list[tuple[str, str, str, list[str]]]:
    """(role_code, menu_code, level, scopes) — 병합본의 모듈 × 역할 전 칸."""
    p = packs.current()
    rows = []
    for m in p.modules:
        for r in p.roles:
            c = p.permission(m["code"], r["code"])
            rows.append((r["code"], m["code"], c["level"], list(c["scopes"])))
    return rows


def seed_permissions(reset: bool = False) -> None:
    role_ids = {r["role_code"]: r["id"] for r in conn.q("select id, role_code from sys_role")}
    for role_code, menu_code, level, scopes in permission_rows():
        sql = """insert into sys_permission (role_id, menu_code, level, scopes, created_by) values (%s, %s, %s, %s, %s)
                 on conflict (role_id, menu_code) do """ + (
            "update set level = excluded.level, scopes = excluded.scopes, updated_at = now(), updated_by = excluded.created_by"
            if reset else "nothing")
        conn.x(sql, (role_ids[role_code], menu_code, level, scopes, SEEDED_BY))


def seed_users() -> None:
    """시드 계정을 환경변수 비밀번호로 맞춘다. 비밀번호가 이미 그 값이면 해시를 다시 쓰지 않는다 — 다시 쓰면 트리거가 그 계정의 세션을 끊는다(D-19)."""
    password = get_settings().seed_password
    if not password:
        raise SystemExit("MES_SEED_PASSWORD 미설정 — 시드 계정을 만들 수 없다. `make setup` 으로 `.env` 를 만들거나 환경변수로 준다. 기본 비밀번호는 두지 않는다(G-C19).")
    role_ids = {r["role_code"]: r["id"] for r in conn.q("select id, role_code from sys_role where use_yn = 'Y'")}
    for login_id, name, role_code in USERS:
        if role_code not in role_ids:
            if login_id == "admin":
                raise SystemExit("역할 ADMIN 이 없다 — core.yaml/pack.yaml: roles 에 ADMIN 은 필수다")
            continue
        cur = conn.q1("select password_hash from sys_user where login_id = %s", (login_id,))
        if cur is not None and auth.verify(password, cur["password_hash"]):
            conn.x("""update sys_user set role_id = %s, user_name = %s, status = '사용', fail_count = 0, updated_at = now(), updated_by = %s
                       where login_id = %s""", (role_ids[role_code], example(name), SEEDED_BY, login_id))
            continue
        conn.x("""insert into sys_user (login_id, user_name, password_hash, role_id, created_by) values (%s, %s, %s, %s, %s)
                  on conflict (login_id) do update
                     set password_hash = excluded.password_hash, role_id = excluded.role_id, user_name = excluded.user_name,
                         status = '사용', fail_count = 0, updated_at = now(), updated_by = excluded.created_by""",
               (login_id, example(name), auth.hash_password(password), role_ids[role_code], SEEDED_BY))


def seed_numbering(reset: bool = False) -> None:
    for kind, rule in packs.current().numbering.items():
        sql = """insert into sys_number_rule (kind, prefix, date_format, seq_digits, created_by) values (%s, %s, %s, %s, %s)
                 on conflict (kind) do """ + (
            "update set prefix = excluded.prefix, date_format = excluded.date_format, seq_digits = excluded.seq_digits, updated_at = now(), updated_by = excluded.created_by"
            if reset else "nothing")
        conn.x(sql, (kind, str(rule.get("prefix", "")), str(rule.get("date", "")), int(rule.get("digits", 3)), SEEDED_BY))


def seed_codes() -> None:
    for group, spec in packs.current().code_groups.items():
        for seq, c in enumerate(spec.get("codes", []), start=1):
            code, name = (c["code"], c["name"]) if isinstance(c, dict) else (str(c), str(c))
            conn.x("""insert into bas_code (group_code, code, code_name, seq, is_core, created_by) values (%s, %s, %s, %s, 'Y', %s)
                      on conflict (group_code, code) do update set code_name = excluded.code_name, seq = excluded.seq, is_core = 'Y'""",
                   (group, code, name, seq, SEEDED_BY))


def seed_examples() -> None:
    for code, name, seq in EXAMPLE_PROCESSES:
        conn.x("insert into bas_process (process_code, process_name, seq, created_by) values (%s, %s, %s, %s) on conflict (process_code) do nothing",
               (code, example(name), seq, SEEDED_BY))
    for code, name, typ, unit in EXAMPLE_ITEMS:
        conn.x("insert into bas_item (item_code, item_name, item_type, unit, created_by) values (%s, %s, %s, %s, %s) on conflict (item_code) do nothing",
               (code, example(name), typ, unit, SEEDED_BY))
    for code, name, proc, collect in EXAMPLE_EQUIPMENT:
        conn.x("""insert into bas_equipment (equip_code, equip_name, process_id, collect_yn, created_by)
                  values (%s, %s, (select id from bas_process where process_code = %s), %s, %s) on conflict (equip_code) do nothing""",
               (code, example(name), proc, collect, SEEDED_BY))
    for code, name, typ in EXAMPLE_PARTNERS:
        conn.x("insert into bas_partner (partner_code, partner_name, partner_type, created_by) values (%s, %s, %s, %s) on conflict (partner_code) do nothing",
               (code, example(name), typ, SEEDED_BY))
    for code, name, proc in EXAMPLE_WORKERS:
        conn.x("""insert into bas_worker (worker_code, worker_name, process_id, created_by)
                  values (%s, %s, (select id from bas_process where process_code = %s), %s) on conflict (worker_code) do nothing""",
               (code, example(name), proc, SEEDED_BY))
    for code, name, proc in EXAMPLE_DEFECTS:
        conn.x("""insert into bas_defect_code (defect_code, defect_name, process_id, created_by)
                  values (%s, %s, (select id from bas_process where process_code = %s), %s) on conflict (defect_code) do nothing""",
               (code, example(name), proc, SEEDED_BY))


# ── 팩 시드 (E1 · E3) ────────────────────────────────────────────────
def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()} for row in csv.DictReader(f)]


def _num(v):
    return None if v in (None, "") else float(v)


def seed_pack() -> list[str]:
    """팩의 process_params · inspection_items · seeds[] CSV 를 멱등으로 넣는다. 돌린 파일 목록을 돌려준다."""
    p = packs.current()
    if p.dir is None:
        return []
    done: list[str] = []
    if p.process_params:
        for r in _read_csv(p.dir / p.process_params):
            conn.x("""insert into bas_process_param (process_id, param_key, label, unit, value_type, min_value, max_value, required_yn, source, collect_tag, agg, seq, created_by)
                      values ((select id from bas_process where process_code = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                      on conflict (process_id, param_key) do update set label = excluded.label, unit = excluded.unit, value_type = excluded.value_type,
                          min_value = excluded.min_value, max_value = excluded.max_value, required_yn = excluded.required_yn, source = excluded.source,
                          collect_tag = excluded.collect_tag, agg = excluded.agg, seq = excluded.seq""",
                   (r["process_code"], r["param_key"], r["label"], r.get("unit") or None, r.get("value_type") or "number", _num(r.get("min_value")),
                    _num(r.get("max_value")), (r.get("required_yn") or "N").upper(), r.get("source") or "manual", r.get("collect_tag") or None,
                    r.get("agg") or "last", int(r.get("seq") or 0), f"seed:{p.name}"))
        done.append(p.process_params)
    if p.inspection_items:
        for r in _read_csv(p.dir / p.inspection_items):
            conn.x("""insert into qua_insp_plan (insp_type, item_id, process_id, item_key, label, unit, value_type, standard, min_value, max_value, seq, created_by)
                      values (%s, (select id from bas_item where item_code = %s), (select id from bas_process where process_code = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                      on conflict (insp_type, coalesce(item_id, 0), coalesce(process_id, 0), item_key) do update set label = excluded.label, unit = excluded.unit,
                          value_type = excluded.value_type, standard = excluded.standard, min_value = excluded.min_value, max_value = excluded.max_value, seq = excluded.seq""",
                   (r["insp_type"], r.get("item_code") or None, r.get("process_code") or None, r["item_key"], r["label"], r.get("unit") or None,
                    r.get("value_type") or "number", r.get("standard") or None, _num(r.get("min_value")), _num(r.get("max_value")),
                    int(r.get("seq") or 0), f"seed:{p.name}"))
        done.append(p.inspection_items)
    for rel in p.seeds:
        stem = Path(rel).stem
        rows = _read_csv(p.dir / rel)
        if stem.startswith("codes"):
            for r in rows:
                conn.x("""insert into bas_code (group_code, code, code_name, seq, created_by) values (%s, %s, %s, %s, %s)
                          on conflict (group_code, code) do update set code_name = excluded.code_name, seq = excluded.seq""",
                       (r["group_code"], r["code"], r["code_name"], int(r.get("seq") or 0), f"seed:{p.name}"))
        elif stem.startswith("items"):
            for r in rows:
                conn.x("""insert into bas_item (item_code, item_name, item_type, spec, unit, attrs, created_by) values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                          on conflict (item_code) do update set item_name = excluded.item_name, item_type = excluded.item_type, spec = excluded.spec, unit = excluded.unit, attrs = excluded.attrs""",
                       (r["item_code"], r["item_name"], r["item_type"], r.get("spec") or None, r.get("unit") or None,
                        json.dumps({k[6:]: v for k, v in r.items() if k.startswith("attrs.") and v}, ensure_ascii=False), f"seed:{p.name}"))
        elif stem.startswith("processes"):
            for r in rows:
                conn.x("""insert into bas_process (process_code, process_name, seq, created_by) values (%s, %s, %s, %s)
                          on conflict (process_code) do update set process_name = excluded.process_name, seq = excluded.seq""",
                       (r["process_code"], r["process_name"], int(r.get("seq") or 0), f"seed:{p.name}"))
        elif stem.startswith("equipment"):
            for r in rows:
                conn.x("""insert into bas_equipment (equip_code, equip_name, process_id, collect_yn, created_by)
                          values (%s, %s, (select id from bas_process where process_code = %s), %s, %s)
                          on conflict (equip_code) do update set equip_name = excluded.equip_name, process_id = excluded.process_id, collect_yn = excluded.collect_yn""",
                       (r["equip_code"], r["equip_name"], r.get("process_code") or None, (r.get("collect_yn") or "N").upper(), f"seed:{p.name}"))
        elif stem.startswith("partners"):
            for r in rows:
                conn.x("""insert into bas_partner (partner_code, partner_name, partner_type, contact, created_by) values (%s, %s, %s, %s, %s)
                          on conflict (partner_code) do update set partner_name = excluded.partner_name, partner_type = excluded.partner_type, contact = excluded.contact""",
                       (r["partner_code"], r["partner_name"], r["partner_type"], r.get("contact") or None, f"seed:{p.name}"))
        else:
            raise SystemExit(f"모르는 팩 시드 파일 {rel} — 이름이 codes* · items* · processes* · equipment* · partners* 로 시작해야 한다 (pack-contract.md §2)")
        done.append(rel)
    return done


def run_dev_seeds() -> list[str]:
    ran: list[str] = []
    here = Path(__file__).resolve().parent
    for name in DEV_SEEDS:
        if not (here / f"{name}.py").exists():
            continue
        mod = importlib.import_module(f"mescore.db.{name}")
        rc = mod.main()
        if rc:
            raise SystemExit(f"{name} 실패 (rc={rc})")
        ran.append(name)
    return ran


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    reset = "--reset" in argv
    seed_roles()
    seed_permissions(reset=reset)
    seed_users()
    seed_numbering(reset=reset)
    seed_codes()
    seed_examples()
    pack_files = seed_pack()
    ran = [] if "--core-only" in argv else run_dev_seeds()
    counts = conn.table_counts()
    p = packs.current()
    print(f"시드 완료 — 팩 {p.name or '(코어 단독)'} · 역할 {counts.get('sys_role')} · 권한 칸 {counts.get('sys_permission')} · 계정 {counts.get('sys_user')} "
          f"· 채번 규칙 {counts.get('sys_number_rule')} · 공통코드 {counts.get('bas_code')} · 팩 시드 {pack_files or '없음'} · 개발 시드 {ran or '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
