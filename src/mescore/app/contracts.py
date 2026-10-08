"""계약 로더 — `contracts/function-list.md` §2 의 표를 기계가 읽는 형태로 준다 (`interfaces.md` §2).

    functions()            136줄(화면 132 + 이관 배치 4) → Function 튜플. 수가 안 맞으면 import 시점에 실패
    function("F-BAS-01")   한 줄 (팩 function-list.md 의 F-X-… 도)
    functions_of("BAS-01") 그 화면의 기능들 — placeholder 화면 · 우측 계약 패널 · rbac 가 쓴다
    batch_functions()      B-MIG-*
    pack_functions()       packs/<팩>/function-list.md (있으면)
    db_tables()            contracts/db-schema.md §4 렌더본의 테이블 → 컬럼 (tools/check_schema.py)

표가 깨졌거나 수가 안 맞으면 **import 시점에 실패한다** — 조용히 넘어가지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import nav, packs
from .settings import ROOT

CONTRACTS_DIR = ROOT / "contracts"
FUNCTION_LIST = CONTRACTS_DIR / "function-list.md"
DB_SCHEMA = CONTRACTS_DIR / "db-schema.md"

N_SCREEN_FUNCTIONS, N_BATCH_FUNCTIONS = 132, 4
#: goal.md §2 G-C02 — 모듈별 기능 수 (bas … ifc)
MODULE_COUNTS: dict[str, int] = {"bas": 36, "ord": 10, "job": 7, "mat": 11, "pop": 8, "qua": 11, "eqp": 8, "shp": 10,
                                 "trc": 3, "kpi": 8, "sys": 16, "ifc": 4}
WRITE_KINDS: frozenset[str] = frozenset({"등록", "수정", "삭제", "취소", "판정", "승인", "스캔", "실행"})
READ_KINDS: frozenset[str] = frozenset({"조회", "출력"})
BATCH_KIND = "배치"
SCOPE_GENERAL = "일반"
READ_ROLE_LABEL = "조회 이상"
TOKEN_ROLE = "토큰"           # F-IFC-01 — 사용자가 아니라 X-Collect-Token 으로 인증

FUNCTION_HEADER = ["ID", "모듈", "화면", "기능명", "유형", "쓰는 테이블", "채널", "권한", "범위", "API", "훅", "담당", "계약"]


# ── 마크다운 표 ─────────────────────────────────────────────────────────
def md_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """문서 안의 표를 전부 (머리행, 본문 행들) 로. 칸 전체가 백틱 한 쌍이면 벗긴다."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    cur: list[list[str]] = []
    for ln in text.splitlines() + [""]:
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            cur.append([_unquote(c) for c in cells])
        elif cur:
            tables.append((cur[0], cur[1:]))
            cur = []
    return tables


def _unquote(cell: str) -> str:
    if len(cell) >= 2 and cell.startswith("`") and cell.endswith("`") and cell.count("`") == 2:
        return cell[1:-1].strip()
    return cell


def md_section(text: str, head_prefix: str) -> str:
    m = re.search(rf"^## {re.escape(head_prefix)}.*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


# ── 기능 ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Function:
    id: str                    # F-BAS-01 · B-MIG-01 · F-X-CLR-01
    module: str                # bas … ifc · migrate · 팩 모듈
    screen_id: str             # BAS-01 (배치는 '')
    name: str
    kind: str                  # 등록 · 수정 · 삭제 · 취소 · 판정 · 승인 · 스캔 · 실행 · 조회 · 출력 · 배치
    tables: tuple[str, ...]    # 쓰는 테이블 (읽기 기능은 빈 튜플)
    channels: tuple[str, ...]
    roles: tuple[str, ...]     # 입력할 수 있는 역할명 (읽기 기능은 빈 튜플 = '조회 이상'). ('토큰',) 은 사용자 밖
    scope: str                 # 일반 · 입고검사 · 승인 · 지표 · 재전송 (읽기 · 배치 · 토큰은 '-')
    api: str                   # 'POST /bas/items' · 'cli basics'
    hooks: tuple[str, ...]
    owner: str
    text: str
    is_pack: bool = False

    @property
    def is_batch(self) -> bool:
        return self.kind == BATCH_KIND

    @property
    def is_write(self) -> bool:
        return self.kind in WRITE_KINDS

    @property
    def is_token(self) -> bool:
        return self.roles == (TOKEN_ROLE,)

    @property
    def method(self) -> str:
        return self.api.split(" ", 1)[0]

    @property
    def path(self) -> str:
        return self.api.split(" ", 1)[1] if " " in self.api else ""

    @property
    def path_base(self) -> str:
        """`?` 앞 경로 — 라우트 대조용."""
        return self.path.split("?", 1)[0]

    @property
    def menu_code(self) -> str:
        return "" if self.is_batch else self.module


def _split(cell: str, sep: str = ",") -> tuple[str, ...]:
    return tuple(p.strip() for p in cell.split(sep) if p.strip() and p.strip() != "-")


def _parse(text: str, source: str, *, pack: bool) -> tuple[Function, ...]:
    found = [rows for head, rows in md_tables(md_section(text, "2.")) if head == FUNCTION_HEADER]
    if len(found) != 1:
        raise RuntimeError(f"{source} §2 에 머리행이 {FUNCTION_HEADER} 인 표가 정확히 하나 있어야 한다 — 실제 {len(found)}")
    out: list[Function] = []
    for r in found[0]:
        if len(r) != len(FUNCTION_HEADER):
            raise RuntimeError(f"{source}: 칸 수가 {len(FUNCTION_HEADER)} 이 아닌 행 — {r[:2]}")
        fid, module, screen, name, kind, tables, channels, roles, scope, api, hooks, owner, body = r
        out.append(Function(
            id=fid, module=module, screen_id="" if screen == "-" else screen, name=name, kind=kind, tables=_split(tables),
            channels=_split(channels.replace(" (API)", ""), ","), roles=() if roles in (READ_ROLE_LABEL, "-") else _split(roles, "·"),
            scope=scope, api=api, hooks=_split(hooks), owner=owner, text=body, is_pack=pack))
    _validate(out, source, pack=pack)
    return tuple(out)


def _validate(fns: list[Function], source: str, *, pack: bool) -> None:
    errs: list[str] = []
    ids = [f.id for f in fns]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append(f"기능 ID 중복 {dup}")
    screen_fns = [f for f in fns if not f.is_batch]
    batch_fns = [f for f in fns if f.is_batch]
    if not pack and (len(screen_fns), len(batch_fns)) != (N_SCREEN_FUNCTIONS, N_BATCH_FUNCTIONS):
        errs.append(f"화면 기능 {N_SCREEN_FUNCTIONS} + 배치 {N_BATCH_FUNCTIONS} 이어야 한다 — 실제 {len(screen_fns)} + {len(batch_fns)}")
    if pack and batch_fns:
        errs.append(f"팩 목록에는 배치가 없다 — {[f.id for f in batch_fns]}")
    id_re = re.compile(r"^F-X-[A-Z0-9]+-\d{2}$") if pack else re.compile(r"^F-[A-Z]{3}-\d{2}$")
    for f in fns:
        if f.kind not in WRITE_KINDS | READ_KINDS | {BATCH_KIND}:
            errs.append(f"{f.id}: 유형 {f.kind!r}")
        if " " not in f.api:
            errs.append(f"{f.id}: API 는 '<메서드> <경로>' 형식 — {f.api!r}")
        if f.is_batch:
            if not re.fullmatch(r"B-MIG-\d{2}", f.id) or f.module != "migrate":
                errs.append(f"{f.id}: 배치 ID 형식 B-MIG-nn · 모듈 migrate")
            continue
        if not id_re.match(f.id):
            errs.append(f"{f.id}: ID 형식")
        try:
            sc = nav.by_id(f.screen_id)
            m = nav.menu(sc.menu_code)
        except KeyError as exc:
            errs.append(f"{f.id}: {exc}")
            continue
        if sc.is_pack != pack:
            errs.append(f"{f.id}: 화면 {f.screen_id} 는 {'팩' if sc.is_pack else '코어'} 화면이라 이 목록({source})에 올 수 없다")
        if f.module != m.code:
            errs.append(f"{f.id}: 모듈 {f.module} ≠ 화면 {f.screen_id} 의 모듈 {m.code}")
        if not pack and f.id.split("-")[1] != m.code.upper():
            errs.append(f"{f.id}: ID 는 F-{m.code.upper()}-nn 이어야 한다")
        if f.owner != m.owner:
            errs.append(f"{f.id}: 담당 {f.owner} ≠ core.yaml {m.owner}")
        if f.channels and not set(f.channels) <= set(sc.channels):
            errs.append(f"{f.id}: 채널 {f.channels} ⊄ core.yaml 화면 채널 {sc.channels}")
        if not f.path_base.startswith(f"/{m.module}/"):
            errs.append(f"{f.id}: 경로 {f.path} 가 /{m.module}/ 로 시작하지 않는다")
        if f.is_write and not f.is_token and (not f.roles or f.scope == "-" or not f.tables):
            errs.append(f"{f.id}: 쓰기 기능은 권한 · 범위 · 쓰는 테이블이 있어야 한다")
        if not f.is_write and (f.roles or f.scope != "-" or f.tables):
            errs.append(f"{f.id}: 읽기 기능은 권한 '{READ_ROLE_LABEL}' · 범위 '-' · 쓰는 테이블 '-'")
    if not pack:
        for code, n in MODULE_COUNTS.items():
            got = sum(1 for f in screen_fns if f.module == code)
            if got != n:
                errs.append(f"{code}: 기능 {got} ≠ goal.md G-C02 {n}")
        for s in nav.CORE_SCREENS:
            if not any(f.screen_id == s.screen_id for f in screen_fns):
                errs.append(f"{s.screen_id} {s.name}: 기능이 한 줄도 없다")
    apis = [f.api for f in fns]
    dup_api = sorted({a for a in apis if apis.count(a) > 1})
    if dup_api:
        errs.append(f"API 중복 {dup_api}")
    if errs:
        raise RuntimeError(f"{source} 검증 실패 {len(errs)}건:\n  - " + "\n  - ".join(errs))


@lru_cache(maxsize=1)
def functions() -> tuple[Function, ...]:
    """코어 136줄 (화면 132 + 배치 4). 게이트가 세는 것은 이것뿐이다."""
    if not FUNCTION_LIST.exists():
        raise RuntimeError(f"계약 없음: {FUNCTION_LIST}")
    return _parse(FUNCTION_LIST.read_text(encoding="utf-8"), FUNCTION_LIST.name, pack=False)


@lru_cache(maxsize=1)
def pack_functions() -> tuple[Function, ...]:
    """`packs/<팩>/function-list.md` — 팩 화면(X-)이 있으면 필수, 없으면 빈 튜플."""
    p = packs.current()
    if p.dir is None:
        return ()
    path = p.dir / "function-list.md"
    if not path.exists():
        if nav.PACK_SCREENS:
            raise RuntimeError(f"팩 화면 {[s.screen_id for s in nav.PACK_SCREENS]} 가 있는데 계약이 없다: {path}")
        return ()
    fns = _parse(path.read_text(encoding="utf-8"), f"packs/{p.name}/function-list.md", pack=True)
    clash = sorted({f.id for f in fns} & {f.id for f in functions()}) + sorted({f.api for f in fns} & {f.api for f in functions()})
    if clash:
        raise RuntimeError(f"팩 계약이 코어 계약과 겹친다 {clash} (R4)")
    return fns


def all_functions() -> tuple[Function, ...]:
    return functions() + pack_functions()


def function(function_id: str) -> Function:
    for f in all_functions():
        if f.id == function_id:
            return f
    raise KeyError(f"function-list.md 에 없는 기능 ID: {function_id}")


def functions_of(screen_id: str) -> list[Function]:
    return [f for f in all_functions() if not f.is_batch and f.screen_id == screen_id]


def functions_of_module(module: str) -> list[Function]:
    return [f for f in all_functions() if not f.is_batch and f.module == module]


def batch_functions() -> list[Function]:
    return [f for f in functions() if f.is_batch]


def reset_cache() -> None:
    functions.cache_clear()
    pack_functions.cache_clear()
    db_tables.cache_clear()


# ── 테이블 계약 (db-schema.md §4 렌더본) ────────────────────────────────
TABLE_HEAD_RE = re.compile(r"^### `(\w+)` — (\w+) · (.*)$", re.M)
COLUMN_HEADER = ["컬럼", "타입", "NULL", "설명"]


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: bool
    desc: str


@dataclass(frozen=True)
class Table:
    name: str
    module: str
    desc: str
    columns: tuple[Column, ...]     # 공통 컬럼 6 을 뺀 것


@lru_cache(maxsize=1)
def db_tables() -> dict[str, Table]:
    """`contracts/db-schema.md` §4 의 `### \\`테이블\\` — 모듈 · 설명` + 컬럼 표."""
    if not DB_SCHEMA.exists():
        raise RuntimeError(f"계약 없음: {DB_SCHEMA}")
    text = md_section(DB_SCHEMA.read_text(encoding="utf-8"), "4.")
    heads = list(TABLE_HEAD_RE.finditer(text))
    out: dict[str, Table] = {}
    for i, m in enumerate(heads):
        body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        tables = [rows for head, rows in md_tables(body) if head == COLUMN_HEADER]
        if not tables:
            raise RuntimeError(f"{DB_SCHEMA.name}: `{m.group(1)}` 아래에 컬럼 표가 없다 — `make contracts`")
        cols = tuple(Column(name=r[0], type=r[1], nullable=(r[2] == "Y"), desc=r[3]) for r in tables[0])
        out[m.group(1)] = Table(name=m.group(1), module=m.group(2), desc=m.group(3).strip(), columns=cols)
    return out
