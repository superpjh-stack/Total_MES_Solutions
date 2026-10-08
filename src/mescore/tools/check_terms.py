#!/usr/bin/env python
"""G-C23 용어 중립 · G-P05 팩 용어 — `make check-terms` · `make check-terms --pack`.

  G-C23  `src/mescore/` 전체(코드 · 템플릿 · 시드 · core.yaml · SQL · JS · CSS)에 `core.yaml: forbidden_terms` 의 금지어 0건.
         한국어 금지어는 부분 문자열로, 영문 금지어는 대소문자 구분 · 낱말 경계(D-22).
         `core.yaml` 의 `forbidden_terms` 블록 자체는 검사에서 뺀다.
         + 템플릿의 `t()` 누락: terms_keys 의 중립어가 템플릿 글(태그 밖)에 날것으로 나오는 곳 0 (WARN — 팩이 치환하지 못한다).
  G-P05  (`--pack` · MES_PACK) 팩 terms 의 키가 로그인한 화면 전부의 HTML 에 치환되지 않은 채 노출 0.

출력: `G-nn  항목  PASS|FAIL|WARN|미검증  실측`. 종료코드 0 = FAIL 없음.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "mescore"
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

CORE_YAML = SRC / "core.yaml"
EXTS = {".py", ".html", ".sql", ".js", ".css", ".yaml", ".yml", ".csv", ".md", ".txt", ".json"}
LATIN = re.compile(r"^[A-Za-z\u0394]")   # 영문 · 그리스 문자로 시작하는 금지어는 대소문자 구분 · 낱말 경계


def forbidden_terms() -> dict[str, list[str]]:
    data = yaml.safe_load(CORE_YAML.read_text(encoding="utf-8"))
    return {k: list(v) for k, v in (data.get("forbidden_terms") or {}).items()}


def terms_keys() -> list[str]:
    return list(yaml.safe_load(CORE_YAML.read_text(encoding="utf-8")).get("terms_keys") or [])


def core_yaml_text_without_block() -> str:
    """core.yaml 에서 forbidden_terms · forbidden_terms_notes 블록을 뺀 글 — 목록 자체를 위반으로 세지 않는다."""
    out, skip = [], False
    for ln in CORE_YAML.read_text(encoding="utf-8").splitlines():
        if re.match(r"^forbidden_terms(_notes)?:", ln):
            skip = True
            continue
        if skip and (ln.startswith(" ") or ln.strip() == "" or ln.startswith("#")):
            continue
        skip = False
        out.append(ln)
    return "\n".join(out)


def find_hits(text: str, terms: dict[str, list[str]]) -> list[tuple[int, str, str]]:
    hits = []
    for i, ln in enumerate(text.splitlines(), start=1):
        for src, words in terms.items():
            for w in words:
                if LATIN.match(w):
                    if re.search(rf"(?<![A-Za-z0-9]){re.escape(w)}(?![a-z0-9])", ln):
                        hits.append((i, w, src))
                elif w in ln:
                    hits.append((i, w, src))
    return hits


def scan_core() -> tuple[list[str], int]:
    terms = forbidden_terms()
    files = [p for p in SRC.rglob("*") if p.is_file() and p.suffix in EXTS and "__pycache__" not in p.parts]
    bad: list[str] = []
    for p in sorted(files):
        text = core_yaml_text_without_block() if p == CORE_YAML else p.read_text(encoding="utf-8", errors="replace")
        for line, w, src in find_hits(text, terms):
            bad.append(f"{p.relative_to(ROOT)}:{line} `{w}` ({src})")
    return bad, len(files)


def scan_raw_terms_in_templates() -> list[str]:
    """템플릿 글(태그 · Jinja 식 밖)에 terms_keys 가 날것으로 — `{{ t('…') }}` 를 거치지 않은 곳."""
    keys = sorted(terms_keys(), key=len, reverse=True)
    bad: list[str] = []
    for p in sorted((SRC / "app" / "templates").rglob("*.html")):
        text = p.read_text(encoding="utf-8")
        text = re.sub(r"{#.*?#}", "", text, flags=re.S)
        text = re.sub(r"{{.*?}}|{%.*?%}", "", text, flags=re.S)
        for i, ln in enumerate(text.splitlines(), start=1):
            plain = re.sub(r"<[^>]*>", " ", ln)
            for k in keys:
                if k in plain:
                    bad.append(f"{p.relative_to(ROOT)}:{i} `{k}`")
                    break
    return bad


def scan_pack(pack_name: str) -> tuple[list[str], int, int]:
    """G-P05 — 관리자로 로그인해 화면 전부를 HTML 로 열고 terms 키가 치환 없이 보이는 곳."""
    import warnings
    warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")
    os.environ["MES_PACK"] = pack_name
    from fastapi.testclient import TestClient

    from mescore.app import nav, packs
    from mescore.app.main import app
    from mescore.app.settings import get_settings

    terms = packs.current().terms
    if not terms:
        return [], 0, 0
    keys = sorted(terms, key=len, reverse=True)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/login", data={"login_id": "admin", "password": get_settings().seed_password or ""}, follow_redirects=False)
    if r.status_code not in (200, 303):
        return [f"admin 로그인 실패 {r.status_code}"], 0, len(keys)
    bad, n = [], 0
    for s in nav.COMMON + nav.SCREENS:
        if not s.auth:
            continue
        resp = c.get(s.probe or s.path, headers={"accept": "text/html"})
        if resp.status_code != 200:
            continue
        n += 1
        plain = re.sub(r"<[^>]*>", " ", resp.text)
        plain = re.sub(r"<code>.*?</code>", " ", resp.text)
        for k in keys:
            if k in plain and terms[k] not in plain:
                bad.append(f"{s.screen_id} `{k}`")
    return bad, n, len(keys)


def main() -> int:
    rows: list[tuple[str, str, str, str]] = []
    if "--pack" in sys.argv:
        pack = os.environ.get("MES_PACK") or ""
        if not pack:
            rows.append(("G-P05", "팩 용어", "미검증", "MES_PACK 비어 있음"))
        else:
            try:
                bad, n, nk = scan_pack(pack)
                rows.append(("G-P05", "팩 용어", "PASS" if not bad else "FAIL",
                             f"[{pack}] 화면 {n} · terms 키 {nk} · 치환 안 된 노출 {len(bad)}" + (f" {bad[:3]}" if bad else "")))
            except Exception as exc:  # noqa: BLE001
                rows.append(("G-P05", "팩 용어", "FAIL", f"[{pack}] {type(exc).__name__}: {str(exc)[:160]}"))
    else:
        bad, n = scan_core()
        terms = forbidden_terms()
        rows.append(("G-C23", "코어 금지어 0", "PASS" if not bad else "FAIL",
                     f"파일 {n} · 금지어 {sum(len(v) for v in terms.values())}개 · 위반 {len(bad)}" + (f" — {bad[:5]}" if bad else "")))
        raw = scan_raw_terms_in_templates()
        rows.append(("G-C23", "템플릿 t() 누락 0", "PASS" if not raw else "WARN", f"날것 중립어 {len(raw)}" + (f" — {raw[:5]}" if raw else "")))
    w = max(len(i) for _, i, _, _ in rows)
    for g, item, st, actual in rows:
        print(f"{g}  {item:<{w}}  {st}  {actual}")
    return 1 if any(st == "FAIL" for _, _, st, _ in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
