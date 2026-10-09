"""팩 로더 — `core.yaml` + `packs/<팩>/pack.yaml` 병합본 (`contracts/interfaces.md` §2 · `pack-contract.md` §2 · §4).

    packs.load(name) -> Pack          병합. 규칙 R4~R6 위반이면 PackError 로 기동 거부. name 이 비면 코어만으로 돈다
    packs.current() -> Pack           지금 병합본 (없으면 settings.pack 으로 load)
    packs.t(text) -> str              용어 치환 — 사전에 없으면 원문 (D-07). 템플릿 전역 t()
    packs.hook(name) -> Callable      등록된 훅. 없으면 no-op
    packs.attrs_of(table) -> list[AttrSpec]
    packs.read_attrs(form, table) -> dict
    packs.template_dirs() -> list[Path]      packs/<팩>/templates 가 코어보다 먼저
    packs.router_modules() -> list[str]      코어 13 + 팩 라우터 모듈 경로

**개발자는 이 파일을 만지지 않는다.** 팩이 할 수 있는 일은 확장 지점 7개(spec.md §3)뿐이고, 그 모양은 pack-contract.md §2 가 정한다.
"""

from __future__ import annotations

import csv
import importlib
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from .settings import ROOT, get_settings

CORE_YAML = Path(__file__).resolve().parents[1] / "core.yaml"
SCHEMA_SQL = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
PACKS_DIR = ROOT / "packs"
CORE_ROUTER_MODULES = ["home", "bas", "ord", "job", "mat", "pop", "qua", "eqp", "shp", "trc", "kpi", "sys", "ifc", "dashboard", "popup"]   # 15 = 모듈 12 + home(CMN-02) · dashboard(CMN-04) · popup(CMN-05)
LOT_BASES = ("MATERIAL", "PRODUCT", "SHIPMENT")
PACK_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
MODULE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PACK_SCREEN_ID_RE = re.compile(r"^X-[A-Z0-9]+-\d{2}$")
LEVELS = ("없음", "조회", "입력")
#: `seeds[]` 의 `{file, table, key}` 가 쓸 수 있는 코어 테이블 — 그 밖은 `x_<팩>_*` 만 (CR-9)
SEED_CORE_TABLES = ("bas_process", "bas_item", "bas_equipment", "bas_partner", "bas_worker", "bas_defect_code", "bas_code", "kpi_indicator")
#: 채널 — 코드(`web/pop/mobile/board`)와 라벨(`관리자 Web` …) 둘 다 받는다 (pack-contract.md §2). nav.DEVICE_CHANNEL 과 같은 값(nav 가 이 모듈을 import 하므로 여기 둔다)
CHANNEL_LABEL: dict[str, str] = {"web": "관리자 Web", "pop": "현장 POP", "mobile": "모바일", "board": "현황판"}
CHANNEL_CODE: dict[str, str] = {v: k for k, v in CHANNEL_LABEL.items()}
NOOP_HOOK: Callable[..., None] = lambda *a, **k: None  # noqa: E731


class PackError(RuntimeError):
    """병합 규칙 위반 — 기동을 거부한다. 메시지에 위반 항목 전부."""


@dataclass(frozen=True)
class AttrSpec:
    key: str
    label: str
    type: str = "text"          # number | text | bool | date | select
    required: bool = False
    choices: tuple[str, ...] = ()


@dataclass
class Pack:
    name: str | None                       # 팩 코드 (None = 코어 단독)
    display_name: str
    company: str
    core_version: str
    system_name: str
    requires_core: str | None
    dir: Path | None
    devices: dict[str, str]
    modules: list[dict]                    # 코어 12 + 팩 add (is_pack)
    order: list[str]
    hidden: set[str]
    screens: list[dict]                    # 코어 51 + 팩 X- (is_pack)
    common: list[dict]
    roles: list[dict]
    permissions: dict[str, dict[str, dict]]   # module → role → {level, scopes}
    scope_general: str
    scopes: list[str]
    numbering: dict[str, dict]
    lineage: dict[str, Any]
    channels: dict[str, list[str]]
    terms: dict[str, str]
    terms_keys: list[str]
    attrs: dict[str, list[AttrSpec]]
    write_scope: dict[str, list[str]]
    hooks_path: Path | None
    adapters: dict[str, str | None]
    seeds: list[dict]                      # [{file, table(None = 파일 이름으로), key}] (pack-contract.md §2 · CR-9)
    process_params: str | None
    inspection_items: str | None
    tests_dir: str | None
    gates_path: Path | None
    code_groups: dict[str, Any]
    collect_tags: list[str]
    forbidden_terms: dict[str, list[str]]
    warnings: list[str] = field(default_factory=list)
    _hooks: Any = None
    _terms_sorted: list[tuple[str, str]] = field(default_factory=list)
    _values_sorted: list[str] = field(default_factory=list)      # 키를 품은 치환값 — 겹말 방지 (t)
    verbatim: set[str] = field(default_factory=set)              # 팩이 쓴 최종 문구(menus.rename 값) — t() 를 걸지 않는다

    @property
    def is_core_only(self) -> bool:
        return self.name is None

    @property
    def core_modules(self) -> list[dict]:
        return [m for m in self.modules if not m.get("is_pack")]

    @property
    def pack_modules(self) -> list[dict]:
        return [m for m in self.modules if m.get("is_pack")]

    @property
    def core_screens(self) -> list[dict]:
        return [s for s in self.screens if not s.get("is_pack")]

    @property
    def pack_screens(self) -> list[dict]:
        return [s for s in self.screens if s.get("is_pack")]

    def permission(self, module: str, role: str) -> dict:
        return self.permissions.get(module, {}).get(role, {"level": "없음", "scopes": []})


_CURRENT: Pack | None = None


# ── 읽기 ────────────────────────────────────────────────────────────────
def core_manifest() -> dict:
    data = yaml.safe_load(CORE_YAML.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PackError(f"{CORE_YAML} 가 비었다")
    return data


def core_tables() -> list[str]:
    """`db/schema.sql` 의 `-- @table 이름 | 모듈 | 설명` 표식 — attrs · write_scope 가 가리키는 코어 테이블 검증용."""
    if not SCHEMA_SQL.exists():
        return []
    return re.findall(r"^-- @table (\w+) \|", SCHEMA_SQL.read_text(encoding="utf-8"), re.M)


def _cell(value: Any, general: str) -> dict:
    """권한 칸 — `입력` → {level: 입력, scopes: [일반]} · `{level, scopes}` 그대로 · `조회` `없음` → scopes []."""
    if isinstance(value, dict):
        level = str(value.get("level", "없음"))
        scopes = [str(s) for s in (value.get("scopes") or [])]
        if level == "입력" and not scopes:
            scopes = [general]
    else:
        level = str(value)
        scopes = [general] if level == "입력" else []
    if level not in LEVELS:
        raise PackError(f"권한 칸 값 {value!r} — 없음 | 조회 | 입력 만")
    return {"level": level, "scopes": scopes}


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", v)[:3]) + (0,) * (3 - len(re.findall(r"\d+", v)[:3]))


def requires_ok(core_version: str, spec: str | None) -> bool:
    """semver 범위 — `>=0.1,<1.0` · `>=0.1.0` · `0.1.0` (정확히). 비면 통과."""
    if not spec:
        return True
    have = _version_tuple(core_version)
    for part in str(spec).split(","):
        part = part.strip()
        m = re.fullmatch(r"(>=|<=|==|>|<|=)?\s*([0-9][0-9.]*)", part)
        if not m:
            raise PackError(f"requires_core 형식을 모른다: {spec!r}")
        op, ver = m.group(1) or "==", _version_tuple(m.group(2))
        ok = {">=": have >= ver, "<=": have <= ver, ">": have > ver, "<": have < ver, "==": have == ver, "=": have == ver}[op]
        if not ok:
            return False
    return True


def channel_label(value: Any) -> str | None:
    """`pop` · `POP` · `현장 POP` → `현장 POP`. 모르면 None."""
    v = str(value).strip()
    if v in CHANNEL_CODE:
        return v
    return CHANNEL_LABEL.get(v.lower())


def channel_code(value: Any) -> str | None:
    """`현장 POP` · `pop` → `pop`. 모르면 None."""
    label = channel_label(value)
    return CHANNEL_CODE[label] if label else None


def _channel_labels(values: Any, where: str, errs: list[str]) -> list[str]:
    out: list[str] = []
    for v in values or [CHANNEL_LABEL["web"]]:
        label = channel_label(v)
        if label is None:
            errs.append(f"{where} 채널 {v!r} — web | pop | mobile | board (또는 {' | '.join(CHANNEL_CODE)})")
        elif label not in out:
            out.append(label)
    return out


def _read_permissions_csv(path: Path, general: str) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            menu, role, level = (row.get("menu_code") or "").strip(), (row.get("role_code") or "").strip(), (row.get("level") or "").strip()
            scopes = [s.strip() for s in (row.get("scopes") or "").replace("·", ",").split(",") if s.strip()]
            if not menu or not role:
                continue
            out.setdefault(menu, {})[role] = _cell({"level": level, "scopes": scopes} if level == "입력" else level, general)
    return out


# ── 병합 ────────────────────────────────────────────────────────────────
def load(name: str | None) -> Pack:
    """코어 → 팩 순으로 병합한다. 위반은 모아서 한 번에 `PackError`."""
    global _CURRENT
    core = core_manifest()
    general = str(core.get("scope_general", "일반"))
    errs: list[str] = []
    warns: list[str] = []

    modules = [dict(m, is_pack=False) for m in core["modules"]]
    core_codes = [m["code"] for m in modules]
    screens = [dict(s, is_pack=False) for s in core["screens"]]
    core_paths = {s["path"] for s in screens}
    core_ids = {s["id"] for s in screens}
    permissions = {mod: {role: _cell(v, general) for role, v in cells.items()} for mod, cells in core["permissions"].items()}
    roles = [dict(r) for r in core["roles"]]
    numbering = {k: dict(v) for k, v in core["numbering"].items()}
    lineage = {"lot_kinds": [dict(x) for x in core["lineage"]["lot_kinds"]],
               "relations": [dict(x) for x in core["lineage"]["relations"]],
               "states": dict(core["lineage"]["states"])}
    channels = {k: list(v) for k, v in core["channels"].items()}
    order = list(core["order"])
    terms_keys = list(core["terms_keys"])
    pack = Pack(
        name=None, display_name=str(core["system_name"]), company=str(core["system_name"]), core_version=str(core["core_version"]),
        system_name=str(core["system_name"]), requires_core=None, dir=None, devices=dict(core["devices"]), modules=modules,
        order=order, hidden=set(), screens=screens, common=[dict(c) for c in core["common"]], roles=roles, permissions=permissions,
        scope_general=general, scopes=list(core.get("scopes", [general])), numbering=numbering, lineage=lineage, channels=channels,
        terms={}, terms_keys=terms_keys, attrs={}, write_scope={}, hooks_path=None,
        adapters={"printing": None, "erp": None, "collect": None}, seeds=[], process_params=None, inspection_items=None,
        tests_dir=None, gates_path=None, code_groups=dict(core.get("code_groups", {})), collect_tags=list(core.get("collect_tags", [])),
        forbidden_terms={k: list(v) for k, v in core.get("forbidden_terms", {}).items()}, warnings=warns,
    )

    name = (name or "").strip() or None
    if name is None:
        _index_terms(pack)
        _CURRENT = pack
        return pack

    if not PACK_NAME_RE.match(name):
        raise PackError(f"팩 이름 {name!r} — ^[a-z_][a-z0-9_]*$")
    pdir = PACKS_DIR / name
    yml = pdir / "pack.yaml"
    if not yml.exists():
        raise PackError(f"팩 {name!r} 의 pack.yaml 이 없다: {yml}")
    try:
        p = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PackError(f"{yml}: YAML 오류 — {exc}") from None
    if not isinstance(p, dict):
        raise PackError(f"{yml} 가 매핑이 아니다")

    # 필수
    if p.get("pack") != name:
        errs.append(f"pack: {p.get('pack')!r} ≠ 폴더명 {name!r}")
    if not p.get("name"):
        errs.append("name 이 없다")
    if "requires_core" not in p:
        errs.append("requires_core 가 없다 (예: \">=0.1,<1.0\")")
    else:
        try:
            if not requires_ok(pack.core_version, p["requires_core"]):
                errs.append(f"requires_core {p['requires_core']!r} 를 코어 {pack.core_version} 이 만족하지 않는다 (R6)")
        except PackError as exc:
            errs.append(str(exc))
    if p.get("env_prefix", "MES_") != "MES_":
        errs.append("env_prefix 는 바꾸지 않는다 (MES_)")
    pack.name, pack.dir, pack.requires_core = name, pdir, p.get("requires_core")
    pack.display_name = str(p.get("name") or name)
    pack.company = str(p.get("company") or pack.display_name)

    # terms (R6)
    terms = p.get("terms") or {}
    for k, v in terms.items():
        if k not in terms_keys:
            errs.append(f"terms 키 {k!r} 는 core.yaml: terms_keys 에 없다 (R6)")
        else:
            pack.terms[str(k)] = str(v)

    # menus (R4 — 이름 · 숨김 · 순서 · 추가만)
    menus = p.get("menus") or {}
    for code in menus.get("hide") or []:
        if code not in core_codes:
            errs.append(f"menus.hide {code!r} 는 코어 모듈이 아니다")
        pack.hidden.add(str(code))
    for code, new_name in (menus.get("rename") or {}).items():
        m = next((x for x in modules if x["code"] == code), None)
        if m is None:
            errs.append(f"menus.rename {code!r} 는 코어 모듈이 아니다")
        else:
            m["name"] = str(new_name)
            pack.verbatim.add(str(new_name))          # 팩이 쓴 최종 이름 — t() 를 걸지 않는다(붙여 쓴 합성어 「품질이상」 의 겹말까지 막는다 · 회전 4)
    added: list[str] = []
    for add in menus.get("add") or []:
        code = str(add.get("code", ""))
        if not MODULE_CODE_RE.match(code):
            errs.append(f"menus.add code {code!r} 형식 (영문 소문자)")
        if code in core_codes or code in added:
            errs.append(f"menus.add {code!r} 가 코어 12 또는 다른 팩 모듈과 겹친다 (R5)")
        if not add.get("name"):
            errs.append(f"menus.add {code!r} 에 name 이 없다")
        after = add.get("after")
        if after is not None and after not in core_codes + added:
            errs.append(f"menus.add {code!r} 의 after {after!r} 는 모르는 모듈")
        modules.append({"code": code, "name": str(add.get("name", code)), "owner": str(add.get("owner", name)),
                        "channels": _channel_labels(add.get("channels"), f"menus.add {code!r}", errs), "is_pack": True, "after": after})
        added.append(code)
    if menus.get("order"):
        order_in = [str(c) for c in menus["order"]]
        unknown = [c for c in order_in if c not in core_codes + added]
        if unknown:
            errs.append(f"menus.order 에 모르는 모듈 {unknown}")
        pack.order = order_in + [c for c in order if c not in order_in] + [c for c in added if c not in order_in]
    else:
        new_order = list(order)
        for add in pack.pack_modules:
            after = add.get("after")
            idx = new_order.index(after) + 1 if after in new_order else len(new_order)
            new_order.insert(idx, add["code"])
        pack.order = new_order

    # screens (R4 · R5)
    seen_ids: set[str] = set()
    for s in p.get("screens") or []:
        sid, mod, path = str(s.get("id", "")), str(s.get("module", "")), str(s.get("path", ""))
        if not PACK_SCREEN_ID_RE.match(sid):
            errs.append(f"screens {sid!r}: 팩 화면 ID 는 X-<MOD>-nn (R5)")
        if sid in core_ids or sid in seen_ids:
            errs.append(f"screens {sid!r}: 코어 화면 ID 또는 중복 (R4)")
        if mod not in added:
            errs.append(f"screens {sid!r}: module {mod!r} 는 menus.add 로 더한 팩 모듈이어야 한다 (R5)")
        if path in core_paths or not path.startswith(f"/{mod}/"):
            errs.append(f"screens {sid!r}: path {path!r} — 코어 경로와 겹치거나 /{mod}/ 로 시작하지 않는다 (R4 · R5)")
        seen_ids.add(sid)
        screens.append({"id": sid, "name": str(s.get("name", sid)), "module": mod, "path": path,
                        "channels": _channel_labels(s.get("channels"), f"screens {sid!r}", errs), "owner": str(s.get("owner", name)), "is_pack": True})

    # roles (대체 — ADMIN 필수)
    if p.get("roles"):
        rs = [{"code": str(r["code"]), "name": str(r.get("name", r["code"]))} for r in p["roles"]]
        if "ADMIN" not in {r["code"] for r in rs}:
            errs.append("roles 에 ADMIN 이 없다")
        pack.roles = rs
    role_codes = [r["code"] for r in pack.roles]

    # permissions (csv — 코어 + 팩 메뉴 × 역할 전 칸)
    if p.get("permissions"):
        csv_path = pdir / str(p["permissions"])
        if not csv_path.exists():
            errs.append(f"permissions 파일이 없다: {csv_path}")
        else:
            pack.permissions = _read_permissions_csv(csv_path, general)
            missing = [f"{m['code']}×{r}" for m in modules for r in role_codes if r not in pack.permissions.get(m["code"], {})]
            if missing:
                errs.append(f"permissions.csv 에 빈 칸 {len(missing)} — {missing[:5]} (코어 + 팩 메뉴 × 역할 전 칸)")
    else:
        for r in role_codes:
            for m in pack.core_modules:
                if r not in pack.permissions.setdefault(m["code"], {}):
                    pack.permissions[m["code"]][r] = {"level": "없음", "scopes": []}
                    warns.append(f"권한 칸 {m['code']}×{r} 이 없어 `없음`")
        for m in pack.pack_modules:
            pack.permissions[m["code"]] = {r: {"level": "없음", "scopes": []} for r in role_codes}
            warns.append(f"팩 모듈 {m['code']} 의 권한 칸이 없다 — 전 역할 `없음` (permissions.csv 로 준다)")

    # numbering
    for kind, rule in (p.get("numbering") or {}).items():
        if not isinstance(rule, dict) or "prefix" not in rule:
            errs.append(f"numbering {kind!r}: {{prefix, date, digits}} 이어야 한다")
            continue
        base = dict(pack.numbering.get(str(kind), {}))
        base.update({"prefix": str(rule.get("prefix", "")), "date": str(rule.get("date", base.get("date", ""))),
                     "digits": int(rule.get("digits", base.get("digits", 3)))})
        base.setdefault("label", str(rule.get("label", kind)))
        pack.numbering[str(kind)] = base

    # channels (대체)
    if p.get("channels"):
        all_ids = {s["id"] for s in screens}
        ch = {}
        for dev_in, ids in p["channels"].items():
            dev = channel_code(dev_in)                   # 키도 코드 · 라벨 둘 다 (`pop` · `현장 POP`)
            if dev not in ("pop", "mobile", "board"):
                errs.append(f"channels {dev_in!r} — pop | mobile | board (또는 현장 POP | 모바일 | 현황판)")
                continue
            bad = [i for i in (ids or []) if i not in all_ids]
            if bad:
                errs.append(f"channels.{dev} 에 모르는 화면 {bad}")
            ch.setdefault(dev, [])
            ch[dev] += [str(i) for i in (ids or []) if str(i) not in ch[dev]]
        pack.channels = ch

    # attrs (E2 — 코어 테이블만)
    tables = core_tables()
    for table, specs in (p.get("attrs") or {}).items():
        if tables and table not in tables:
            errs.append(f"attrs {table!r} 는 코어 테이블이 아니다")
        out = []
        for a in specs or []:
            typ = str(a.get("type", "text"))
            if typ not in ("number", "text", "bool", "date", "select"):
                errs.append(f"attrs {table}.{a.get('key')}: type {typ!r}")
            out.append(AttrSpec(key=str(a["key"]), label=str(a.get("label", a["key"])), type=typ,
                                required=bool(a.get("required", False)), choices=tuple(str(c) for c in (a.get("choices") or []))))
        pack.attrs[str(table)] = out

    # lineage (R6)
    core_kind_names = {k["kind"] for k in pack.lineage["lot_kinds"]}
    core_rel_names = {r["name"] for r in pack.lineage["relations"]}
    lin = p.get("lineage") or {}
    for k in lin.get("lot_kinds") or []:
        if k.get("base") not in LOT_BASES:
            errs.append(f"lineage.lot_kinds {k.get('kind')!r}: base 는 {LOT_BASES} 중 하나 (R6)")
        if k.get("kind") in core_kind_names:
            errs.append(f"lineage.lot_kinds {k.get('kind')!r} 는 코어 종류와 겹친다")
        pack.lineage["lot_kinds"].append({"kind": str(k.get("kind")), "base": str(k.get("base")), "label": str(k.get("label", k.get("kind")))})
    for r in lin.get("relations") or []:
        if r.get("base") not in core_rel_names:
            errs.append(f"lineage.relations {r.get('name')!r}: base 는 코어 5종({sorted(core_rel_names)}) 중 하나 (R6)")
        if r.get("name") in core_rel_names:
            errs.append(f"lineage.relations {r.get('name')!r} 는 코어 관계와 겹친다")
        pack.lineage["relations"].append({"name": str(r.get("name")), "base": str(r.get("base"))})
    if lin.get("states"):
        pack.lineage["states"].update({str(k): str(v) for k, v in lin["states"].items()})

    # write_scope
    for mod, tbls in (p.get("write_scope") or {}).items():
        if mod not in added and mod != "hooks":
            errs.append(f"write_scope {mod!r} 는 팩 모듈(또는 hooks)이어야 한다")
        bad = [t for t in (tbls or []) if tables and t not in tables]
        if bad:
            errs.append(f"write_scope.{mod} 에 코어 테이블이 아닌 것 {bad}")
        pack.write_scope[str(mod)] = [str(t) for t in (tbls or [])]

    # hooks · adapters · seeds · 경로
    hooks_rel = p.get("hooks", "hooks.py")
    if hooks_rel:
        hp = pdir / str(hooks_rel)
        if hp.exists():
            pack.hooks_path = hp
        elif "hooks" in p:
            errs.append(f"hooks 파일이 없다: {hp}")
    for key in ("printing", "erp", "collect"):
        val = (p.get("adapters") or {}).get(key)
        if val and not (pdir / str(val)).exists():
            errs.append(f"adapters.{key} 파일이 없다: {pdir / str(val)}")
        pack.adapters[key] = str(val) if val else None
    pack.seeds = []
    for e in p.get("seeds") or []:
        if isinstance(e, dict):                  # {file, table, key} — x_<팩>_* · 허용 코어 기준정보 테이블 (CR-9)
            f, table, key = e.get("file"), str(e.get("table") or ""), e.get("key")
            keys = [str(k) for k in ([key] if isinstance(key, str) else (key or []))]
            if not f or not table or not keys:
                errs.append(f"seeds {e!r} — {{file, table, key}} 셋 다 필요")
                continue
            if not (table.startswith(f"x_{name}_") or table in SEED_CORE_TABLES):
                errs.append(f"seeds {f}: table {table!r} — x_{name}_* 또는 {', '.join(SEED_CORE_TABLES)} 만")
            entry = {"file": str(f), "table": table, "key": keys}
        else:
            entry = {"file": str(e), "table": None, "key": None}
        if not (pdir / entry["file"]).exists():
            errs.append(f"seeds 파일이 없다: {pdir / entry['file']}")
        pack.seeds.append(entry)
    for key in ("process_params", "inspection_items"):
        val = p.get(key)
        if val and not (pdir / str(val)).exists():
            errs.append(f"{key} 파일이 없다: {pdir / str(val)}")
        setattr(pack, key, str(val) if val else None)
    pack.tests_dir = str(p.get("tests") or "tests/")
    gates = pdir / str(p.get("gates") or "gates.yaml")
    pack.gates_path = gates if gates.exists() else None

    if errs:
        raise PackError(f"팩 {name!r} 병합 규칙 위반 {len(errs)}건:\n  - " + "\n  - ".join(errs))
    _index_terms(pack)
    _CURRENT = pack
    return pack


def current() -> Pack:
    global _CURRENT
    if _CURRENT is None:
        _CURRENT = load(get_settings().pack)
    return _CURRENT


def reset() -> None:
    """테스트용 — 다음 current() 가 다시 load 한다."""
    global _CURRENT
    _CURRENT = None


# ── 용어 · 훅 · 속성 ───────────────────────────────────────────────────
def _index_terms(pack: Pack) -> None:
    pack._terms_sorted = sorted(pack.terms.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    pack._values_sorted = sorted({v for k, v in pack.terms.items() if k in v and k != v}, key=lambda v: (-len(v), v))
    # rename 값이 용어 키와 똑같으면(`출하`) 그 낱말 전체가 치환 대상이므로 verbatim 에서 뺀다 — 안 빼면 다른 화면의 「출하」 까지 안 바뀐다
    pack.verbatim = {v for v in pack.verbatim if v not in pack.terms}


def translate(text: str, terms: Mapping[str, str], terms_sorted: list[tuple[str, str]] | None = None,
              values_sorted: list[str] | None = None) -> str:
    """한 번 훑는 치환 — 같은 자리에서 **긴 키가 먼저**, 치환한 결과를 다시 치환하지 않는다.
    겹말 방지: 치환값이 키를 품고(`추적` → `LOT 추적`) 원문 그 자리가 이미 그 치환값이면 그대로 둔다(`LOT 추적` → `LOT LOT 추적` 금지)."""
    if not text or not terms:
        return text or ""
    if text in terms:
        return terms[text]
    keys = terms_sorted if terms_sorted is not None else sorted(terms.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    vals = values_sorted if values_sorted is not None else sorted({v for k, v in terms.items() if k in v and k != v}, key=lambda v: (-len(v), v))
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        hit = next((v for v in vals if text.startswith(v, i)), None)
        if hit is not None:                       # 이미 업종어 — 그대로 건너뛴다
            out.append(hit)
            i += len(hit)
            continue
        kv = next(((k, v) for k, v in keys if text.startswith(k, i)), None)
        if kv is not None:
            out.append(kv[1])
            i += len(kv[0])
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def t(text: str) -> str:
    """용어 치환 (E1 · D-07). 사전에 키가 그대로 있으면 그 값, 아니면 긴 키부터 한 번 훑어 부분 치환(겹말 방지 — `translate`).
    `menus.rename` 값(`pack.verbatim`)은 팩이 쓴 최종 이름이라 **그대로** 돌려준다(개발1 ⑤ · 회전 4). 사전이 비면 원문."""
    if text is None:
        return ""
    pack = current()
    if not pack.terms:
        return text
    if text in pack.verbatim:
        return text
    return translate(text, pack.terms, pack._terms_sorted, pack._values_sorted)


def _hooks_module(pack: Pack):
    if pack._hooks is None and pack.hooks_path is not None:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        spec = importlib.util.spec_from_file_location(f"packs.{pack.name}.hooks", pack.hooks_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)      # 임포트 실패는 그대로 올린다 — 조용히 no-op 가 되지 않는다
        pack._hooks = mod
    return pack._hooks


def hook(name: str) -> Callable[..., Any]:
    """등록된 훅. 팩이 없거나 그 이름이 없으면 no-op. 훅 안의 `HookError` 는 main.py 가 422 로 바꾼다."""
    mod = _hooks_module(current())
    fn = getattr(mod, name, None) if mod is not None else None
    return fn if callable(fn) else NOOP_HOOK


def has_hook(name: str) -> bool:
    return hook(name) is not NOOP_HOOK


def attrs_of(table: str) -> list[AttrSpec]:
    """팩 속성 선언 — **라벨은 `t()` 를 거친 값**(DEF-QA1-003 · 회전 5). 라벨은 terms 키(중립어)로 쓴다: `공정구분` → `조리 공정구분`.
    선택지(`choices`)는 저장되는 값이라 바꾸지 않는다. 원문 선언은 `current().attrs`."""
    return [replace(a, label=t(a.label)) for a in current().attrs.get(table, [])]


def _is_request(obj: Any) -> bool:
    """starlette `Request` 는 **Mapping**(ASGI scope 를 감싼다)이라 isinstance(Mapping) 로는 못 가른다 (개발1 ①)."""
    try:
        from starlette.requests import HTTPConnection
    except ImportError:                       # pragma: no cover — starlette 는 fastapi 의존성
        return False
    return isinstance(obj, HTTPConnection)


def read_attrs(form: Mapping[str, Any] | Any, table: str) -> dict[str, Any]:
    """폼에서 `attr_<key>`(또는 `attrs.<key>`) 칸을 읽어 attrs dict 로. `form` 은 Mapping(폼 값 · FormData) 또는 `Request`
    (동기 라우터 — 스레드풀에서 `await` 없이 `request.form()` 을 읽는다. FastAPI 가 `Form()` 인자로 이미 읽었으면 캐시를 쓴다).
    필수 키가 비면 ValueError(라우터가 422 로 바꾼다). 형식 변환: number → float, bool → True/False."""
    if _is_request(form):
        import anyio
        form = anyio.from_thread.run(form.form)
    elif not isinstance(form, Mapping):
        raise TypeError(f"read_attrs 는 폼 값(Mapping) 또는 Request 를 받는다 — {type(form).__name__}")
    out: dict[str, Any] = {}
    for spec in attrs_of(table):
        raw = form.get(f"attr_{spec.key}")
        if raw is None:
            raw = form.get(f"attrs.{spec.key}")
        if raw is None or str(raw).strip() == "":
            if spec.required:
                raise ValueError(f"{spec.label} 은(는) 필수입니다")
            continue
        if spec.type == "number":
            out[spec.key] = float(raw)
        elif spec.type == "bool":
            out[spec.key] = str(raw).lower() in ("1", "true", "y", "yes", "on")
        else:
            out[spec.key] = str(raw)
    return out


# ── 검색 경로 ───────────────────────────────────────────────────────────
def template_dirs() -> list[Path]:
    core = Path(__file__).resolve().parent / "templates"
    pack = current()
    dirs = []
    if pack.dir is not None and (pack.dir / "templates").is_dir():
        dirs.append(pack.dir / "templates")
    dirs.append(core)
    return dirs


def overridden_templates() -> list[str]:
    """팩이 같은 이름으로 덮어쓴 코어 템플릿 — check_pack 이 WARN 으로 찍는다."""
    dirs = template_dirs()
    if len(dirs) < 2:
        return []
    pack_dir, core_dir = dirs[0], dirs[-1]
    return sorted(str(p.relative_to(pack_dir)) for p in pack_dir.rglob("*.html") if (core_dir / p.relative_to(pack_dir)).exists())


def extra_routes() -> list[dict]:
    """`core.yaml: extra_routes` — 기능 수 밖 허용 라우트 [{method, path, decision, note}] (D-12 · D-601). `check_trace` 가 고아에서 뺀다."""
    return [dict(x) for x in (core_manifest().get("extra_routes") or [])]


def router_modules() -> list[str]:
    """코어 15(`mescore.app.routers.<모듈>` — 모듈 12 + home · dashboard · popup) + 팩 `packs/<팩>/routers/*.py`(`_` 로 시작하는 파일 제외)."""
    out = [f"mescore.app.routers.{m}" for m in CORE_ROUTER_MODULES]
    pack = current()
    if pack.dir is not None and (pack.dir / "routers").is_dir():
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        for p in sorted((pack.dir / "routers").glob("*.py")):
            if not p.name.startswith("_"):
                out.append(f"packs.{pack.name}.routers.{p.stem}")
    return out
