"""팩 로더 — 병합 규칙 R4~R6 (contracts/pack-contract.md §4) · 용어 치환 · 메뉴 숨김 · 계보 선언 (아키텍트).

임시 팩을 `packs/_t_<이름>/` 에 만들어 `packs.load` 를 부르고 끝나면 지운다. 참조 팩 3개 폴더는 건드리지 않는다(D-24).
`_template` 팩은 그대로 로드돼야 한다. 끝에 **이 실행의 팩(`MES_PACK` — 비면 코어 단독)** 으로 되돌린다 — 다른 테스트가 그 병합본을 본다(R9 · CR-11).
"""

import shutil
from pathlib import Path

import pytest
import yaml

from mescore.app import nav, packs

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "packs"
BASE = {"pack": "", "name": "임시 팩", "requires_core": ">=0.1,<1.0"}


@pytest.fixture
def temp_pack():
    made: list[Path] = []

    def make(name: str, **spec) -> str:
        d = PACKS / name
        d.mkdir(parents=True, exist_ok=False)
        made.append(d)
        data = {**BASE, "pack": name, **spec}
        (d / "pack.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return name

    yield make
    for d in made:
        shutil.rmtree(d, ignore_errors=True)
    _restore()


def _restore() -> None:
    from mescore.app.settings import get_settings
    packs.load(get_settings().pack)
    nav.rebuild()


def test_template_pack_loads_and_core_only_restores():
    p = packs.load("_template")
    assert p.name == "_template" and len(p.core_modules) == 12 and len(p.core_screens) == 51
    assert packs.load(None).is_core_only
    _restore()


def test_terms_hide_rename_order_and_add(temp_pack):
    name = temp_pack("_t_ok", terms={"생산 LOT": "배치", "작업지시": "지시서"},
                     menus={"hide": ["ifc"], "rename": {"pop": "현장 실적"}, "add": [{"code": "exm", "name": "예시", "after": "pop"}]},
                     screens=[{"id": "X-EXM-01", "name": "예시 화면", "module": "exm", "path": "/exm/example", "channels": ["관리자 Web"]}],
                     lineage={"lot_kinds": [{"kind": "BATCH", "base": "PRODUCT", "label": "배치"}], "relations": [{"name": "혼합", "base": "합병"}]},
                     numbering={"LOT_PRODUCT": {"prefix": "B", "date": "YYMMDD-", "digits": 5}},
                     attrs={"lot": [{"key": "width_mm", "label": "폭(mm)", "type": "number"}]})
    p = packs.load(name)
    nav.rebuild()
    assert packs.t("생산 LOT") == "배치" and packs.t("생산 LOT 번호") == "배치 번호" and packs.t("품목") == "품목"
    assert "ifc" in p.hidden and nav.menu("ifc").hidden and "ifc" not in [m.code for m in nav.MENUS]
    assert nav.menu("pop").name == "현장 실적"
    codes = [m.code for m in nav.ALL_MENUS]
    assert codes.index("exm") == codes.index("pop") + 1 and nav.path_of("X-EXM-01") == "/exm/example"
    assert len(nav.CORE_SCREENS) == 51 and len(nav.PACK_SCREENS) == 1
    assert {k["kind"] for k in p.lineage["lot_kinds"]} == {"MATERIAL", "PRODUCT", "SHIPMENT", "BATCH"}
    assert p.numbering["LOT_PRODUCT"]["prefix"] == "B" and p.numbering["LOT_PRODUCT"]["digits"] == 5 and p.numbering["WORK_ORDER"]["prefix"] == "W"
    assert packs.attrs_of("lot")[0].key == "width_mm"
    assert packs.read_attrs({"attr_width_mm": "1200"}, "lot") == {"width_mm": 1200.0}
    assert p.permission("exm", "ADMIN")["level"] == "없음" and p.warnings   # permissions.csv 없이 더한 모듈은 전부 없음 + 경고


@pytest.mark.parametrize("spec, needle", [
    ({"terms": {"롤": "x"}}, "terms_keys"),                                                       # R6 모르는 용어 키
    ({"requires_core": ">=9.0"}, "requires_core"),                                               # R6 버전
    ({"lineage": {"relations": [{"name": "x", "base": "없는것"}]}}, "base"),                      # R6 base
    ({"lineage": {"lot_kinds": [{"kind": "PRODUCT", "base": "PRODUCT"}]}}, "겹친다"),             # 코어 종류 재정의
    ({"menus": {"add": [{"code": "bas", "name": "x"}]}}, "R5"),                                   # R5 모듈 코드 충돌
    ({"menus": {"add": [{"code": "exm", "name": "x"}]}, "screens": [{"id": "BAS-01", "name": "x", "module": "exm", "path": "/exm/a"}]}, "R4"),  # R4 코어 화면 ID
    ({"menus": {"add": [{"code": "exm", "name": "x"}]}, "screens": [{"id": "X-EXM-01", "name": "x", "module": "exm", "path": "/bas/items"}]}, "R4"),  # 코어 경로
    ({"screens": [{"id": "X-EXM-01", "name": "x", "module": "exm", "path": "/exm/a"}]}, "R5"),    # 선언 안 한 모듈
    ({"menus": {"hide": ["없는모듈"]}}, "hide"),
    ({"roles": [{"code": "PROD", "name": "생산"}]}, "ADMIN"),
    ({"channels": {"pop": ["없는화면"]}}, "channels"),
    ({"write_scope": {"exm": ["lot"]}}, "write_scope"),                                          # 팩 모듈이 아닌 키
    ({"attrs": {"없는테이블": []}}, "attrs"),
])
def test_merge_rule_violations_refuse_to_boot(temp_pack, spec, needle):
    name = temp_pack("_t_bad", **spec)
    with pytest.raises(packs.PackError) as exc:
        packs.load(name)
    assert needle in str(exc.value)


def test_pack_name_must_match_folder(temp_pack):
    name = temp_pack("_t_name", pack="other")
    with pytest.raises(packs.PackError) as exc:
        packs.load(name)
    assert "폴더명" in str(exc.value)


def test_missing_pack_is_refused():
    with pytest.raises(packs.PackError):
        packs.load("_t_없는팩")


def test_hook_is_noop_without_hooks_file(temp_pack):
    name = temp_pack("_t_hook")
    packs.load(name)
    assert packs.hook("on_lot_created") is packs.NOOP_HOOK and packs.hook("on_lot_created")(None, {}, None) is None


def test_hooks_file_is_registered_by_name(temp_pack):
    name = temp_pack("_t_hook2")
    (PACKS / name / "hooks.py").write_text(
        "from mescore.app.util.http import HookError\n"
        "def validate_bas_item(cur, row, user):\n    raise HookError('거부 (예시)', fields=[{'name': 'item_code', 'reason': row.get('item_code')}])\n",
        encoding="utf-8")
    packs.load(name)
    from mescore.app.util.http import HookError
    assert packs.has_hook("validate_bas_item") and not packs.has_hook("validate_lot")
    with pytest.raises(HookError) as exc:
        packs.hook("validate_bas_item")(None, {"item_code": "X"}, None)
    assert exc.value.fields[0]["reason"] == "X"


def test_permissions_csv_must_cover_every_cell(temp_pack):
    name = temp_pack("_t_perm", permissions="seed/permissions.csv")
    (PACKS / name / "seed").mkdir()
    (PACKS / name / "seed" / "permissions.csv").write_text("menu_code,role_code,level,scopes\nbas,ADMIN,입력,일반\n", encoding="utf-8")
    with pytest.raises(packs.PackError) as exc:
        packs.load(name)
    assert "빈 칸" in str(exc.value)


def test_requires_core_ranges():
    assert packs.requires_ok("0.1.0", ">=0.1,<1.0") and packs.requires_ok("0.1.0", "0.1.0") and packs.requires_ok("0.1.0", None)
    assert not packs.requires_ok("0.1.0", ">=0.2") and not packs.requires_ok("1.0.0", "<1.0")


def test_terms_longest_first_and_no_doubled_words(temp_pack):
    """긴 키 우선 · 한 번 훑기 · 겹말 방지(「LOT LOT 추적」 금지) · menus.rename 값은 다시 치환하지 않는다 (개발1 ⑤)."""
    name = temp_pack("_t_terms", terms={"추적": "LOT 추적", "실적": "조리 실적", "생산 LOT": "배치", "출하 LOT": "출고 LOT", "출하": "출고"},
                     menus={"rename": {"pop": "조리 실적 (POP)", "trc": "LOT 추적", "shp": "출하", "qua": "품질이상"}})
    packs.load(name)
    nav.rebuild()
    assert packs.t("추적") == "LOT 추적" and packs.t("LOT 추적") == "LOT 추적" and packs.t("LOT 추적 화면") == "LOT 추적 화면"
    assert packs.t("역방향 추적") == "역방향 LOT 추적"
    assert packs.t("실적 (POP)") == "조리 실적 (POP)" and packs.t("조리 실적 (POP)") == "조리 실적 (POP)"
    assert packs.t("품질이상") == "품질이상"                                                                       # 합성어 rename 도 그대로
    assert packs.t("출하 LOT 스캔") == "출고 LOT 스캔" and packs.t("출하 등록") == "출고 등록"     # 긴 키(출하 LOT)가 먼저 · 결과를 다시 치환하지 않음
    assert packs.t("생산 LOT 번호") == "배치 번호"
    assert packs.t(nav.menu("pop").name) == "조리 실적 (POP)" and packs.t(nav.menu("trc").name) == "LOT 추적"   # 업종어로 쓴 rename 값 그대로
    assert packs.t(nav.menu("shp").name) == "출고" and packs.t("출하") == "출고"                                     # 용어 키와 똑같은 rename 값만 예외(낱말 전체가 치환 대상)


def test_channels_accept_codes_and_labels(temp_pack):
    name = temp_pack("_t_ch", menus={"add": [{"code": "exm", "name": "예시", "after": "pop", "channels": ["web", "pop"]}]},
                     screens=[{"id": "X-EXM-01", "name": "예시 화면", "module": "exm", "path": "/exm/example", "channels": ["pop", "현황판"]}],
                     channels={"현장 POP": ["POP-01", "X-EXM-01"], "board": ["KPI-01", "X-EXM-01"], "mobile": []})
    p = packs.load(name)
    nav.rebuild()
    assert p.pack_modules[0]["channels"] == ["관리자 Web", "현장 POP"] and p.pack_screens[0]["channels"] == ["현장 POP", "현황판"]
    assert p.channels == {"pop": ["POP-01", "X-EXM-01"], "board": ["KPI-01", "X-EXM-01"], "mobile": []}
    assert nav.channel_allowed("X-EXM-01", "pop") and not nav.channel_allowed("X-EXM-01", "mobile")


def test_unknown_channel_is_refused(temp_pack):
    name = temp_pack("_t_ch_bad", menus={"add": [{"code": "exm", "name": "예시", "channels": ["kiosk"]}]})
    with pytest.raises(packs.PackError) as exc:
        packs.load(name)
    assert "kiosk" in str(exc.value)


def test_read_attrs_reads_form_from_request(temp_pack):
    """`Request` 는 Mapping 이라 예전엔 폼을 안 읽고 {} 였다 (개발1 ①). 동기 라우터에서 `attr_<key>` · `attrs.<key>` 를 읽는다."""
    from fastapi import FastAPI, Form, Request
    from fastapi.testclient import TestClient

    name = temp_pack("_t_attrs", attrs={"ord_order": [{"key": "due_time", "label": "납기 시각", "type": "text"},
                                                      {"key": "serve", "label": "식수", "type": "number", "required": True}]})
    packs.load(name)
    app = FastAPI()

    @app.post("/x")
    def x(request: Request, note: str = Form("")):
        try:
            return {"attrs": packs.read_attrs(request, "ord_order"), "note": note}
        except ValueError as exc:
            return {"error": str(exc)}

    c = TestClient(app)
    assert c.post("/x", data={"note": "n", "attr_due_time": "11:30", "attrs.serve": "120"}).json() == {"attrs": {"due_time": "11:30", "serve": 120.0}, "note": "n"}
    assert "필수" in c.post("/x", data={"attr_due_time": "11:30"}).json()["error"]
    with pytest.raises(TypeError):
        packs.read_attrs(object(), "ord_order")


def test_seed_entries_string_or_table_spec(temp_pack):
    """seeds[] — 문자열(이름 접두) 또는 {file, table, key}. table 은 x_<팩>_* · 허용 코어 기준정보만 (CR-9)."""
    name = temp_pack("_t_seed", seeds=["seed/codes.csv", {"file": "seed/plates.csv", "table": "x__t_seed_plate", "key": "plate_code"}])
    (PACKS / name / "seed").mkdir()
    for f in ("codes.csv", "plates.csv"):
        (PACKS / name / "seed" / f).write_text("a\n", encoding="utf-8")
    p = packs.load(name)
    assert p.seeds == [{"file": "seed/codes.csv", "table": None, "key": None},
                       {"file": "seed/plates.csv", "table": "x__t_seed_plate", "key": ["plate_code"]}]
    bad = temp_pack("_t_seed_bad", seeds=[{"file": "seed/x.csv", "table": "sys_user", "key": "login_id"}, {"file": "seed/y.csv"}])
    with pytest.raises(packs.PackError) as exc:
        packs.load(bad)
    assert "sys_user" in str(exc.value) and "셋 다" in str(exc.value)
