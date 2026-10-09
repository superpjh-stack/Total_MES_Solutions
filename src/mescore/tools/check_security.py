#!/usr/bin/env python
"""QA3 채널 · 보안 · 운영 검사기 — `make check-security` (G-C13~G-C20) · gate 가 부른다. **고치지 않는다 — 재고 적는다.**

    uv run python src/mescore/tools/check_security.py                  # G-C13~G-C20 판정 행 (gate 가 읽는다)
    uv run python src/mescore/tools/check_security.py --e2e            # + G-C22 브라우저 한 바퀴 (캡처 outputs/e2e/core/NN_*.png)
    uv run python src/mescore/tools/check_security.py --pack-isolation # + G-P01 팩 3 check_pack · 팩 폴더를 지운 worktree 에서 코어 tests/ 전건
    uv run python src/mescore/tools/check_security.py --port 8053      # 기동할 서버 포트 (기본 8053 — QA3 전용)

무엇을 어떻게 재는가 (전부 **실제 서버**를 띄워 HTTP · 헤드리스 Chrome 으로 — TestClient 아님)
  G-C13 4채널   POP: 화면마다 `data-scan` 0|1 · 열자마자 스캔칸 포커스 · 없는 번호 `?no=` → 그 화면 422 재렌더(URL 그대로 · 포커스 유지 ·
                `#scan-result.err`) · 같은 LOT 2회 스캔 = `pop_input` 2행. 모바일: 채널 화면 전부 390px 에서 `scrollWidth == clientWidth`.
                현황판: 갱신 시각이 주기마다 바뀜 · 폴링 1배 · 폴링 503 이면 `data-state=stale` + 마지막 값 유지 + 폴링 계속 · 회복.
                채널 밖 화면 403. DB 를 끊고 띄운 서버: `/health` 503 · 로그인 503 · POP 화면 503 + 스캔칸 disabled(S-12) · 현황판 오류 화면 새로고침.
  G-C14 출력물  작업지시서 · LOT 라벨(100×50 · 50×30) · 출하 라벨 · 성적서 — 인라인 `<svg>` · 외부 요청 0 · **바코드를 이미지로 해독(zxing)** 한 값 =
                번호. LOT 라벨 해독값을 POP-03 · POP-04 스캔칸에 키보드로 쳐서 그 LOT 이 열린다(`barcode_spec.md` §5 1·3·4·6·7·8·9).
  G-C15 이관    예시 세트를 임시 폴더로 복사 → 4 명령 실제 적재 2회 · 2회째 대상 테이블 행 수 diff 0 · 적재 0 · `sys_migration_log` 행 ·
                `--dry-run` 쓰기 0 · 깨진 파일 1건 → 종료 코드 1 + 오류 리포트 행 + 로그 행.
  G-C16 ERP     `erp.adapter().push` 501 D-02 · `POST /ifc/erp/{id}/retry` 가 HTTP 501(200 위장 없음) · flush 가 `미확정` 으로 남김(삼키지 않음) ·
                수집 토큰 틀림/없음 401 · 맞는 토큰 + 없는 설비 422.
  G-C17 (일부) 역할 변경이 다음 요청부터 — 48칸 전수는 QA1 check_screens. gate 는 check_security 의 G-C13~G-C20 을 읽으므로 이 행을 낸다.
  G-C18 접근 로그 · 세션  시험 계정으로 로그인 성공 · 실패 · 화면 조회 · 데이터 변경 → `sys_access_log` 4종 + SYS-04 화면에 보임 · 로그에 비밀번호 없음.
                세션: 중지 · 비밀번호 변경 · 잠금(`MES_LOGIN_LOCK_COUNT=3` 으로 띄운 서버) · 로그아웃 뒤 같은 쿠키 → 다음 요청 401 · 역할 변경이 다음 요청부터.
  G-C19 비밀    `git ls-files -co --exclude-standard` 전부에서 `.env` 의 비밀 값 grep 0 · `.env` · `backups/` gitignore · 팩 안 외부 CDN 0 (R11).
  G-C20 백업    `backup.py backup` → `restore-check` 종료 코드 0 · 행 수 일치 문장.

출력: `G-nn  항목  PASS|FAIL|미검증  실측` (interfaces.md §10). 비밀 값은 어디에도 찍지 않는다. 서버 로그는 스크래치에만.
브라우저 부분은 `uv run --with playwright --with zxing-cpp --with pillow` 로 이 파일을 다시 부른다(프로젝트 의존성을 늘리지 않는다 · Chrome 채널).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

PASS, FAIL, UNVERIFIED = "PASS", "FAIL", "미검증"
BROWSER_WITH = ["--with", "playwright", "--with", "zxing-cpp", "--with", "pillow"]
ROWS: list[tuple[str, str, str, str]] = []
NOPE = "NOPE-QA3-0000"
COOKIES: dict[str, dict] = {}          # DB 끊김 검사용 세션 쿠키 — 메모리에만 (파일 · 출력에 남기지 않는다)


def row(gid: str, item: str, ok: bool | None, measured: str) -> None:
    st = UNVERIFIED if ok is None else (PASS if ok else FAIL)
    ROWS.append((gid, item, st, measured.replace("\n", " ")[:600]))


def run(cmd: list[str], env: dict | None = None, timeout: int = 900, cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s"


def scratch() -> Path:
    d = Path(tempfile.gettempdir()) / "mes-qa3"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 서버 ─────────────────────────────────────────────────────────────────
class Server:
    """uvicorn 을 포트 하나에 띄운다 (코어 단독 · 현재 MES_PG_DSN). 로그는 스크래치에만."""

    def __init__(self, port: int, extra_env: dict | None = None, name: str = "core"):
        self.port, self.name = port, name
        self.env = dict(os.environ)
        self.env["MES_PACK"] = self.env.get("MES_PACK", "")
        self.env.update(extra_env or {})
        self.proc = None
        self.base = f"http://127.0.0.1:{port}"
        self.log = scratch() / f"server-{name}-{port}.log"

    def __enter__(self):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", self.port)) == 0:
                raise RuntimeError(f"포트 {self.port} 를 이미 누가 쓰고 있다 — QA3 전용 포트를 비우고 다시")
        self.proc = subprocess.Popen(["uv", "run", "uvicorn", "mescore.app.main:app", "--app-dir", "src", "--port", str(self.port), "--host", "127.0.0.1"],
                                     cwd=ROOT, env=self.env, stdout=open(self.log, "w"), stderr=subprocess.STDOUT)
        import httpx
        for _ in range(120):
            try:
                httpx.get(self.base + "/health", timeout=2)
                return self
            except Exception:  # noqa: BLE001 — 기동 대기
                if self.proc.poll() is not None:
                    raise RuntimeError(f"서버 기동 실패 rc={self.proc.returncode} — {self.log}")
                time.sleep(0.5)
        raise RuntimeError(f"서버가 60초 안에 뜨지 않았다 — {self.log}")

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def http_client(base: str, login_id: str | None = None, password: str | None = None, device: str | None = None):
    import httpx
    c = httpx.Client(base_url=base, follow_redirects=False, timeout=30)
    if login_id:
        data = {"login_id": login_id, "password": password}
        if device:
            data["device"] = device
        r = c.post("/login", data=data)
        if r.status_code != 200:
            raise RuntimeError(f"{login_id} 로그인 실패 {r.status_code}")
    return c


# ── 픽스처 — 화면이 부르는 API(JSON)로 만든다 ─────────────────────────────
def build_fixture(base: str, pw: str) -> dict:
    from mescore.db import conn

    def one(sql, p=()):
        r = conn.q1(sql, p)
        if r is None:
            raise RuntimeError(f"시드 없음: {sql[:60]} {p}")
        return r

    admin, prod, qa, field = (http_client(base, u, pw) for u in ("admin", "prod", "qa", "field"))
    raw1 = one("select id from bas_item where item_code = 'RAW-EX-01'")["id"]
    raw2 = one("select id from bas_item where item_code = 'RAW-EX-02'")["id"]
    prd = one("select id, item_code from bas_item where item_code = 'PRD-EX-01'")
    sup = one("select id from bas_partner where partner_code = 'SUP-EX-01'")["id"]
    proc = one("select id from bas_process where process_code = 'PRC-EX-02'")["id"]   # 측정값 선언이 없는 공정 — 픽스처는 측정값과 무관
    mats = []
    for iid in (raw1, raw2):
        r = prod.post("/mat/receipts", data={"item_id": iid, "qty": 100, "partner_id": sup}).json()
        assert qa.post("/mat/inspections", data={"lot_no": r["lot_no"], "judgement": "합격"}).status_code == 200
        mats.append(r)
    pl = prod.post("/ord/plans", data={"item_code": prd["item_code"], "plan_date": str(date.today()), "plan_qty": 100}).json()
    assert prod.post(f"/ord/plans/{pl['id']}/confirm").status_code == 200, "계획 확정 실패"
    wo = prod.post("/job/work-orders", data={"item_id": prd["id"], "process_id": proc, "plan_qty": 100, "plan_id": pl["id"], "plan_date": str(date.today())}).json()
    assert wo.get("ok"), f"작업지시 등록 실패 {wo}"
    wo_no = one("select work_order_no from job_work_order where id = %s", (wo["id"],))["work_order_no"]
    s = prod.post("/pop/result/start", data={"work_order_id": wo["id"]}).json()
    assert prod.post("/pop/inputs", data={"work_result_id": s["id"], "barcode": mats[0]["lot_no"], "qty": 30}).status_code == 200
    e = prod.post(f"/pop/result/{s['id']}/end", data={"good_qty": 40}).json()
    assert e.get("ok"), f"종료 실패 {e}"
    plot = {"id": e["lot_id"], "no": e["lot_no"]}
    open_res = prod.post("/pop/result/start", data={"work_order_id": wo["id"]}).json()         # 열린 실적 — POP-03 투입 화면용
    ins = qa.post("/qua/inspections", data={"lot_id": plot["id"], "insp_type": "최종"}).json()
    assert qa.post(f"/qua/inspections/{ins['id']}/judge", data={"judgement": "합격"}).status_code == 200
    shp = prod.post("/shp/shipments", data={"partner_code": "CUST-EX-01", "ship_date": str(date.today())}).json()
    shp_no = one("select shipment_no from shp_shipment where id = %s", (shp["id"],))["shipment_no"]
    sc = prod.post("/shp/scan", data={"shipment_no": shp_no, "barcode": plot["no"]})
    assert sc.status_code == 200, f"출하 스캔 실패 {sc.text[:200]}"
    ap = admin.post(f"/shp/shipments/{shp['id']}/approve")
    assert ap.status_code == 200, f"승인 실패 {ap.text[:200]}"
    doc = prod.post("/shp/documents", data={"shipment_id": shp["id"], "doc_type": "성적서"}).json()
    doc_no = one("select document_no from shp_document where id = %s", (doc["id"],))["document_no"]
    for c in (admin, prod, qa, field):
        c.close()
    return {"mats": [{"id": m["lot_id"], "no": m["lot_no"]} for m in mats], "wo": {"id": wo["id"], "no": wo_no}, "plot": plot,
            "open_result": open_res["id"], "shipment": {"id": shp["id"], "no": shp_no}, "doc": {"id": doc["id"], "no": doc_no}}


# ── 브라우저 (별도 프로세스: uv run --with playwright …) ───────────────────
def browser_job(mode: str, base: str, payload: dict) -> tuple[dict | None, str]:
    inp, out = scratch() / f"in-{mode}.json", scratch() / f"out-{mode}.json"
    inp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if out.exists():
        out.unlink()
    code, log = run(["uv", "run", *BROWSER_WITH, "python", str(Path(__file__).resolve()), "--_browser", mode, base, str(inp), str(out)],
                    env=dict(os.environ), timeout=1500)
    if not out.exists():
        return None, f"브라우저 작업 실패 rc={code} — {log.strip().splitlines()[-1] if log.strip() else ''}"
    return json.loads(out.read_text(encoding="utf-8")), log


def _browser_main(mode: str, base: str, inp: str, out: str) -> int:
    from playwright.sync_api import sync_playwright

    from mescore.app.settings import get_settings

    payload = json.loads(Path(inp).read_text(encoding="utf-8"))
    pw = get_settings().seed_password
    result: dict = {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        try:
            if mode == "channels":
                result = _b_channels(b, base, pw, payload)
            elif mode == "e2e":
                result = _b_e2e(b, base, pw, payload)
            elif mode == "timing":
                result = _b_timing(b, base, pw, payload)
        finally:
            b.close()
    Path(out).write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


class Ui:
    """브라우저 조작 — 사람이 하는 대로(타이핑 · 클릭 · Enter). 비밀번호는 입력칸에만 들어간다."""

    def __init__(self, browser, base: str, pw: str, *, width: int = 1366, height: int = 900, scale: int = 2):
        self.base, self.pw = base, pw
        self.ctx = browser.new_context(viewport={"width": width, "height": height}, locale="ko-KR", device_scale_factor=scale)
        self.page = self.ctx.new_page()
        self.external: list[str] = []
        self.page.on("request", lambda r: self.external.append(r.url) if not r.url.startswith(base) and not r.url.startswith("data:") else None)

    def login(self, lid: str, device: str = "web") -> str:
        pg = self.page
        pg.goto(self.base + "/logout")
        pg.goto(self.base + "/login?device=" + device)
        pg.fill("#login-form input[name=login_id]", lid)
        pg.fill("#login-form input[name=password]", self.pw)
        pg.check(f"#login-form input[name=device][value={device}]")
        with pg.expect_navigation():
            pg.click("#login-form button.btn-primary")
        return pg.url

    def flash(self) -> dict | None:
        return self.page.evaluate("""(() => { const e = document.getElementById('flash-data');
          if (e) { try { const j = JSON.parse(e.textContent || 'null'); if (j) return {kind: j.kind, text: ((j.title||'') + ' ' + (j.message||'') + ' ' + (j.fields||[]).map(f => (f.label||f.name) + ':' + f.reason).join(',')).trim()} } catch (x) {} }
          const t = document.querySelector('.toast'); if (t) return {kind: 'ok', text: t.innerText.replace(/\\s+/g, ' ').trim()};
          const a = document.querySelector('.alert[role=alert]:not([hidden])'); if (a && a.offsetParent) return {kind: 'error', text: a.innerText.replace(/\\s+/g, ' ').trim()};
          return null })()""")

    def ok(self, f) -> bool:
        return bool(f and f.get("kind") == "ok")

    def submit(self, fid: str) -> dict | None:
        pg = self.page
        with pg.expect_navigation():
            pg.locator(f'button[form="{fid}"]:not([disabled]), #{fid} button[type=submit]:not([disabled])').first.click()
        return self.flash()

    def close_popup(self) -> None:
        if self.page.locator("#popup-layer:not([hidden])").count():
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(100)

    def scan(self, value: str) -> bool:
        """스캐너 = 키보드 입력 + Enter (S-05). 클릭하지 않는다 — 화면이 준 포커스(S-02)가 스캔칸이어야 들어간다."""
        pg = self.page
        focused = pg.evaluate("!!(document.activeElement && document.activeElement.hasAttribute('data-scan'))")
        with pg.expect_navigation():
            pg.keyboard.type(value)
            pg.keyboard.press("Enter")
        return focused

    def opt(self, sel: str, text: str) -> str:
        for lb in self.page.locator(sel + " option").all_inner_texts():
            if text in lb:
                return lb
        raise RuntimeError(f"{sel}: '{text}' 선택지 없음")

    def decode(self, loc=None) -> list[str]:
        """바코드 SVG 를 화면에서 이미지로 떠서 zxing 으로 해독 — 스캐너 대신."""
        import io

        import zxingcpp
        from PIL import Image

        loc = loc or self.page.locator("svg[aria-label]").first
        img = Image.open(io.BytesIO(loc.screenshot())).convert("L")
        pad = Image.new("L", (img.width + 80, img.height + 80), 255)
        pad.paste(img, (40, 40))
        return [r.text for r in zxingcpp.read_barcodes(pad)]

    def fill_items(self, fsel: str, temp: str = "70", qty: str = "50") -> None:
        for el in self.page.locator(f"{fsel} input[name^=i_], {fsel} input[name^=m_]").all():
            if el.is_disabled() or el.get_attribute("readonly") is not None:
                continue
            nm = el.get_attribute("name") or ""
            el.fill((temp if "temp" in nm else qty) if el.get_attribute("type") == "number" else "양호")


def _b_channels(b, base: str, pw: str, fx: dict) -> dict:
    res: dict = {}
    # POP — data-scan · 포커스 · 422 재렌더
    ui = Ui(b, base, pw)
    ui.login("admin", "pop")
    pg = ui.page
    pop = {}
    for sid, path in fx["pop_paths"]:
        r = pg.goto(base + path)
        pop[sid] = {"status": r.status, "scan": pg.locator("[data-scan]").count(),
                    "focused": pg.evaluate("!!(document.activeElement && document.activeElement.hasAttribute('data-scan'))"),
                    "body_class": pg.evaluate("document.body.className")}
    res["pop"] = pop
    rer = {}
    for sid, path in fx["scan_get_paths"]:
        r = pg.goto(base + path + ("&" if "?" in path else "?") + "no=" + NOPE)
        rer[sid] = {"status": r.status, "url_kept": NOPE in pg.url and "/error" not in pg.url,
                    "err_banner": pg.locator("#scan-result.err, [role=alert]").count() > 0,
                    "focused": pg.evaluate("!!(document.activeElement && document.activeElement.hasAttribute('data-scan'))"),
                    "nope_shown": NOPE in pg.locator("body").inner_text()}
    res["rerender"] = rer
    # 바코드 1회 = 1건 — 현장 역할로, 열린 실적의 투입 화면에서 같은 원재료 LOT 라벨을 두 번 스캔
    ui.login("field", "pop")
    lab = fx["mats"][1]
    pg.goto(f"{base}/mat/lots/{lab['id']}/label")
    code = (ui.decode() or [None])[0]
    seen = []
    for _ in range(2):
        pg.goto(f"{base}/pop/inputs?result={fx['open_result']}")
        ui.close_popup()
        pg.fill("input[name=qty]", "1")
        pg.focus("[data-scan]")
        ui.scan(code or "")
        seen.append(ui.flash())
    res["double_scan"] = {"code": code, "flash": seen}
    ui.ctx.close()

    # 모바일 390px
    ui = Ui(b, base, pw, width=390, height=844, scale=1)
    ui.login("admin", "mobile")
    mob = {}
    for sid, path in fx["mobile_paths"]:
        r = ui.page.goto(base + path)
        ui.page.wait_for_timeout(150)
        mob[sid] = {"status": r.status, "scrollWidth": ui.page.evaluate("document.documentElement.scrollWidth"),
                    "clientWidth": ui.page.evaluate("document.documentElement.clientWidth"),
                    "body_class": ui.page.evaluate("document.body.className")}
    ui.page.screenshot(path=str(scratch() / "mobile-last.png"))
    res["mobile"] = mob
    ui.ctx.close()

    # 현황판 — 갱신 시각 · 폴링 1배 · 503 이면 stale + 값 유지 + 폴링 계속 · 회복
    ui = Ui(b, base, pw, scale=1)
    ui.login("admin", "board")
    pg = ui.page
    polls: list[float] = []
    pg.on("request", lambda r: polls.append(time.time()) if "/kpi/board" in r.url and r.resource_type in ("fetch", "xhr") else None)
    pg.goto(base + "/kpi/board?device=board")
    sec = int(pg.evaluate("document.body.dataset.refreshSeconds || '0'") or 0)
    t0 = pg.locator("#refreshed-at").inner_text()
    pg.wait_for_timeout((sec * 2 + 1.5) * 1000)
    t1 = pg.locator("#refreshed-at").inner_text()
    n_poll = len(polls)
    keyvals = pg.evaluate("[...document.querySelectorAll('[data-key]')].filter(e => !e.dataset.key.startsWith('_')).slice(0, 12).map(e => e.dataset.key + '=' + e.textContent.trim())")
    pg.route("**/kpi/board*", lambda route: route.fulfill(status=503, content_type="application/json",
                                                          body=json.dumps({"code": "db_unavailable", "message": "서비스 일시 중단"})))
    p_before = len(polls)
    pg.wait_for_timeout((sec * 2 + 1.5) * 1000)
    state = pg.evaluate("document.documentElement.dataset.state || ''")
    failed_at = pg.locator("[data-key=_failed_at]").first.inner_text() if pg.locator("[data-key=_failed_at]").count() else ""
    kept = pg.evaluate("[...document.querySelectorAll('[data-key]')].filter(e => !e.dataset.key.startsWith('_')).slice(0, 12).map(e => e.dataset.key + '=' + e.textContent.trim())")
    p_during = len(polls) - p_before
    pg.screenshot(path=str(scratch() / "board-stale.png"))
    pg.unroute("**/kpi/board*")
    pg.wait_for_timeout((sec + 1.5) * 1000)
    state_after = pg.evaluate("document.documentElement.dataset.state || ''")
    res["board"] = {"refresh_seconds": sec, "t0": t0, "t1": t1, "polls_in_window": n_poll, "window_s": sec * 2 + 1.5,
                    "stale_state": state, "failed_at": failed_at, "values_kept": kept == keyvals, "polls_during_503": p_during,
                    "state_after_recover": state_after, "body_class": pg.evaluate("document.body.className")}
    ui.ctx.close()

    # 출력물 4종 + 스캔 왕복 — 출력물은 관리자 Web 에서 열어 해독하고(작업지시서 · 성적서는 Web 채널 화면), 스캔은 POP 세션에서
    ui = Ui(b, base, pw)
    ui.login("admin", "web")
    pg = ui.page
    forms = {}
    for name, path, want in fx["print_paths"]:
        ui.external.clear()
        r = pg.goto(base + path)
        pg.wait_for_timeout(200)
        codes = ui.decode() if pg.locator("svg[aria-label]").count() else []
        html = pg.content()
        forms[name] = {"status": r.status, "inline_svg": "<svg" in html, "external_requests": list(ui.external),
                       "ext_refs": re.findall(r'(?:src|href)="(https?://[^"]+)"', html)[:3], "decoded": codes, "want": want}
        pg.screenshot(path=str(scratch() / f"print-{name}.png"), full_page=True)
    res["print"] = forms
    plot = fx["plot"]
    lot_codes = {}
    for size in ("100x50", "50x30"):
        pg.goto(f"{base}/pop/labels?lot={plot['id']}&size={size}")
        lot_codes[size] = (ui.decode() or [None])[0]
    wcode = (forms["작업지시서"]["decoded"] or [None])[0]
    scode = (forms["출하 라벨"]["decoded"] or [None])[0]
    dcode = (forms["성적서"]["decoded"] or [None])[0]
    pg.goto(base + "/shp/documents?no=" + (dcode or ""))
    doc_ok = bool(dcode) and pg.locator(f"main tr:has-text('{dcode}')").count() > 0
    ui.ctx.close()
    ui = Ui(b, base, pw)
    ui.login("admin", "pop")
    pg = ui.page
    rt = {}
    for size, code in lot_codes.items():
        pg.goto(base + "/pop/inputs")
        f3 = ui.scan(code or "")
        st3 = pg.url
        opened3 = plot["no"] in pg.locator("main").inner_text()
        pg.goto(base + "/pop/labels")
        f4 = ui.scan(code or "")
        opened4 = pg.locator("svg[aria-label]").first.get_attribute("aria-label") if pg.locator("svg[aria-label]").count() else None
        rt[size] = {"decoded": code, "pop03_url": st3, "pop03_focused": f3, "pop03_opened": opened3, "pop04_focused": f4, "pop04_label": opened4}
    pg.goto(base + "/pop/work")
    ui.scan(wcode or "")
    rt["wo_to_pop02"] = {"decoded": wcode, "url": pg.url, "ok": "/pop/result" in pg.url and fx["wo"]["no"] in pg.locator("main").inner_text()}
    pg.goto(base + "/shp/scan")
    ui.scan(scode or "")
    rt["ship_to_shp02"] = {"decoded": scode, "url": pg.url, "ok": fx["shipment"]["no"] in pg.url}
    rt["doc_to_shp04"] = {"decoded": dcode, "ok": doc_ok}
    res["roundtrip"] = rt
    ui.ctx.close()
    return res


def _b_e2e(b, base: str, pw: str, fx: dict) -> dict:
    """G-C22 — 코어 단독 브라우저 한 바퀴. 단계마다 캡처 outputs/e2e/core/NN_*.png. 막히면 그 단계에서 멈추고 FAIL."""
    out = ROOT / "outputs" / "e2e" / "core"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    ui = Ui(b, base, pw)
    pg = ui.page
    steps: list[dict] = []
    st: dict = {}

    def shot(name):
        pg.screenshot(path=str(out / f"{name}.png"), full_page=True)

    def rec(nn, name, ok, note):
        steps.append({"nn": nn, "name": name, "ok": bool(ok), "note": note, "png": f"outputs/e2e/core/{nn}_{name}.png"})
        shot(f"{nn}_{name}")
        if not ok:
            raise StopIteration(f"{nn} {name}")

    today = date.today()
    try:
        # 01 관리자 로그인
        url = ui.login("admin")
        rec("01", "login_admin", url.rstrip("/") == base, f"admin → {url}")
        # 02 기준정보 — 품목 등록 (BAS-01)
        pg.goto(base + "/bas/items")
        code = "QA3-" + datetime.now().strftime("%H%M%S")
        pg.fill("#master-form input[name=item_code]", code)
        pg.fill("#master-form input[name=item_name]", "QA3 시험 품목 (예시)")
        pg.select_option("#master-form select[name=item_type]", label="제품")
        pg.fill("#master-form input[name=unit]", "EA")
        f = ui.submit("master-form")
        rec("02", "bas_item_register", ui.ok(f) and code in pg.content(), f"{code} · {f}")
        # 03 수주 등록 (ORD-01)
        pg.goto(base + "/ord/orders")
        pg.select_option("#order-new select[name=partner_code]", label=ui.opt("#order-new select[name=partner_code]", "CUST-EX-01"))
        pg.fill("#order-new input[name=due_date]", str(date.fromordinal(today.toordinal() + 7)))
        pg.locator("#order-new select[name=item_code]").first.select_option(label=ui.opt("#order-new select[name=item_code]", "PRD-EX-01"))
        pg.locator("#order-new input[name=qty]").first.fill("100")
        pg.locator("#order-new input[name=unit]").first.fill("EA")
        f = ui.submit("order-new")
        m = re.search(r"(O\d{6}-\d+)", (f or {}).get("text", ""))
        rec("03", "ord_order_register", ui.ok(f) and m, str(f))
        order_no = m.group(1)
        # 04 생산계획 등록 · 확정 (ORD-04) — 생산
        ui.login("prod")
        pg.goto(base + "/ord/plans")
        pg.select_option("#plan-new select[name=order_no]", label=ui.opt("#plan-new select[name=order_no]", order_no))
        pg.select_option("#plan-new select[name=item_code]", label=ui.opt("#plan-new select[name=item_code]", "PRD-EX-01"))
        pg.fill("#plan-new input[name=plan_qty]", "100")
        f = ui.submit("plan-new")
        plan_no = re.search(r"(N\d{6}-\d+)", (f or {}).get("text", "")).group(1)
        r = pg.locator(f"main tr:has-text('{plan_no}')").first
        r.locator("details.confirm summary").click()
        with pg.expect_navigation():
            r.locator("details.confirm form button[type=submit]").click()
        f2 = ui.flash()
        rec("04", "ord_plan_confirm", ui.ok(f2) and "확정" in pg.locator(f"main tr:has-text('{plan_no}')").first.inner_text(), f"{plan_no} 등록 {f} · 확정 {f2}")
        # 05 작업지시 등록 (JOB-01) — 생산 · 확정 계획에서
        pg.goto(base + "/job/work-orders")
        pg.select_option("#wo-form select[name=item_id]", label=ui.opt("#wo-form select[name=item_id]", "PRD-EX-01"))
        pg.select_option("#wo-form select[name=process_id]", label=ui.opt("#wo-form select[name=process_id]", "PRC-EX-01"))
        pg.select_option("#wo-form select[name=equipment_id]", label=ui.opt("#wo-form select[name=equipment_id]", "EQ-EX-01"))
        pg.fill("#wo-form input[name=plan_qty]", "100")
        pg.fill("#wo-form input[name=plan_date]", str(today))
        pg.select_option("#wo-form select[name=plan_id]", label=ui.opt("#wo-form select[name=plan_id]", plan_no))
        f = ui.submit("wo-form")
        m = re.search(r"(W\d{6}-\d+)", (f or {}).get("text", ""))
        rec("05", "job_work_order_register", ui.ok(f) and m, str(f))
        wo_no = m.group(1)
        # 06 작업지시서 출력 — 바코드 해독 = 지시 번호
        href = pg.locator(f"main tr:has-text('{wo_no}') a[href*='/job/print']").first.get_attribute("href")
        pg.goto(base + href)
        wcodes = ui.decode()
        body = pg.locator("body").inner_text()
        st["wo_print_order_shown"] = order_no in body
        rec("06", "job_print_work_order", wo_no in wcodes, f"{href} 바코드 해독 {wcodes} · 지시서에 수주 번호 {order_no} 표시 {order_no in body}")
        # 07 입고 2 (MAT-01) — 현장 · POP
        ui.login("field", "pop")
        mats = []
        for c in ("RAW-EX-01", "RAW-EX-02"):
            pg.goto(base + "/mat/receipts")
            pg.select_option("#receipt-form select[name=item_id]", label=ui.opt("#receipt-form select[name=item_id]", c))
            pg.select_option("#receipt-form select[name=partner_id]", label=ui.opt("#receipt-form select[name=partner_id]", "SUP-EX-01"))
            pg.fill("#receipt-form input[name=qty]", "100")
            f = ui.submit("receipt-form")
            m = re.search(r"(M\d{6}-\d+)", (f or {}).get("text", ""))
            mats.append(m.group(1) if m else None)
            ui.close_popup()
        rec("07", "mat_receipt_x2", all(mats), f"원재료 LOT {mats}")
        # 08 입고검사 (MAT-02) — 품질 · POP 스캔 → 합격
        ui.login("qa", "pop")
        res = []
        for mno in mats:
            pg.goto(base + "/mat/inspections")
            foc = ui.scan(mno)
            ui.fill_items("#judge-form", qty="10")
            pg.check("#judge-form input[name=judgement][value=합격]", force=True)
            f = ui.submit("judge-form")
            res.append((mno, foc, f))
            ui.close_popup()
        rec("08", "mat_inspection_pass_x2", all(x[1] and ui.ok(x[2]) for x in res), str(res))
        # 09 POP-01 에 작업지시서 바코드(해독값) 스캔 → POP-02 작업 시작 — 현장
        ui.login("field", "pop")

        def start_run():
            pg.goto(base + "/pop/work")
            foc = ui.scan(wcodes[0])
            u = pg.url
            pg.locator("#start-form input[name=equipment_id][value='1']").check(force=True)
            pg.locator("#start-form input[name=worker_id]").first.check(force=True)
            return foc, u, ui.submit("start-form")

        foc, u, f = start_run()
        r1 = pg.url
        rec("09", "pop_start_from_wo_barcode", foc and "/pop/result" in u and ui.ok(f), f"POP-01 스캔 {wcodes[0]} → {u} · {f} → {r1}")

        def mat_code(mno):
            pg.goto(base + "/mat/lots?no=" + mno)
            pg.goto(base + pg.locator("a[href^='/mat/lots/'][href$='/label']").first.get_attribute("href"))
            c = ui.decode()
            return c[0] if c else ""

        def inputs(rurl, pairs):
            out_ = []
            for mno, qty in pairs:
                c = mat_code(mno)
                pg.goto(rurl)
                ui.close_popup()
                pg.locator("a[href*='/pop/inputs?result=']").first.click()
                pg.wait_for_load_state()
                pg.fill("input[name=qty]", str(qty))
                pg.focus("[data-scan]")
                ui.scan(c)
                out_.append((c, ui.flash()))
                ui.close_popup()
            return out_

        def end(rurl, good, temp):
            pg.goto(rurl)
            ui.close_popup()
            pg.fill("#end-form input[name=good_qty]", str(good))
            ui.fill_items("#end-form", temp=temp, qty=str(good))
            f_ = ui.submit("end-form")
            mm = re.search(r"(P\d{6}-\d+)", (f_ or {}).get("text", ""))
            return f_, (mm.group(1) if mm else None)

        ins = inputs(r1, [(mats[0], 50)])
        rec("10", "pop_input_scan_r1", all(ui.ok(x[1]) for x in ins), f"원재료 라벨 해독 → 투입 스캔 {ins}")
        f, p1 = end(r1, 50, "70")
        meas = pg.locator("main").inner_text()
        rec("11", "pop_end_measure_r1", ui.ok(f) and p1 and "70.0000" in meas, f"측정값 중량 50 · 온도 70 → {f} · 생산 LOT {p1}")
        # 12 생산 LOT 라벨 → 해독 → POP-04 스캔 → 같은 LOT
        ui.close_popup()
        lab = pg.locator("main a[href*='/pop/labels?lot=']").first.get_attribute("href")
        pg.goto(base + lab)
        lc = ui.decode()
        pg.goto(base + "/pop/labels")
        foc = ui.scan(lc[0] if lc else "")
        opened = pg.locator("svg[aria-label]").first.get_attribute("aria-label") if pg.locator("svg[aria-label]").count() else None
        rec("12", "pop_label_scan_roundtrip", lc and lc[0] == p1 and foc and opened == p1, f"라벨 {lab} 해독 {lc} → POP-04 스캔 → 열린 라벨 {opened}")
        # 13 두 번째 실적 — 같은 지시 · 원재료 ①② · 온도 85 (범위 이탈 → 저장 + 이탈 표시)
        foc, u, f = start_run()
        r2 = pg.url
        ins = inputs(r2, [(mats[0], 50), (mats[1], 50)])
        f2, p2 = end(r2, 50, "85")
        dev = "이탈" in pg.locator("main").inner_text()
        rec("13", "pop_run2_deviation", ui.ok(f) and all(ui.ok(x[1]) for x in ins) and p2 and dev, f"시작 {f} · 투입 {ins} · 종료 {f2} · 이탈 표시 {dev}")
        # 14 합병 2:1
        ui.close_popup()
        pg.fill("#merge-form input[name=lot_ids]", f"{p1},{p2}")
        f = ui.submit("merge-form")
        m = re.search(r"(P\d{6}-\d+)", (f or {}).get("text", ""))
        rec("14", "merge_2to1", ui.ok(f) and m, str(f))
        mg = m.group(1)
        # 15 분할 1:3
        ui.close_popup()
        pg.select_option("#split-form select[name=lot_id]", label=ui.opt("#split-form select[name=lot_id]", mg))
        pg.fill("#split-form input[name=count]", "3")
        pg.fill("#split-form input[name=qtys]", "30,30,30")
        f = ui.submit("split-form")
        ui.close_popup()
        sp = [c for c in pg.locator("main ul.notes li code").all_inner_texts() if c not in (p1, p2, mg)][-3:]
        rec("15", "split_1to3", ui.ok(f) and len(sp) == 3, f"{f} → 화면의 재고 LOT {sp}")
        # 16 검사 (QUA-02) — 품질: 분할 ①② 최종 검사 등록 → 판정 합격
        ui.login("qa")
        res = []
        for no in sp[:2]:
            pg.goto(base + "/qua/inspections")
            ui.scan(no)
            pg.select_option("#insp-form select[name=insp_type]", label="최종")
            ui.fill_items("#insp-form")
            f = ui.submit("insp-form")
            jid = pg.locator("form[id^=judge-]").first.get_attribute("id")
            pg.locator(f"#{jid} input[name=judgement][value=합격]").check(force=True)
            res.append((no, f and f.get("kind"), ui.submit(jid)))
        rec("16", "qua_inspect_judge_x2", all(x[1] == "ok" and ui.ok(x[2]) for x in res), str(res))
        # 17 출하 등록 (SHP-01) — 현장 · POP
        ui.login("field", "pop")
        pg.goto(base + "/shp/shipments")
        pg.select_option("#shipment-new select[name=partner_code]", label=ui.opt("#shipment-new select[name=partner_code]", "CUST-EX-01"))
        pg.select_option("#shipment-new select[name=order_no]", label=ui.opt("#shipment-new select[name=order_no]", order_no))
        f = ui.submit("shipment-new")
        m = re.search(r"(S\d{6}-\d+)", (f or {}).get("text", ""))
        rec("17", "shp_register", ui.ok(f) and m, str(f))
        shp_no = m.group(1)
        ui.close_popup()
        # 18 출하 라벨 해독 → SHP-02 스캔 → 분할 ①② 라벨 해독 → 스캔
        slab = pg.locator("main a[href^='/shp/shipments/'][href$='/label']").first.get_attribute("href")
        pg.goto(base + slab)
        sc = ui.decode()
        lot_codes = []
        for n in sp[:2]:
            pg.goto(base + "/pop/labels?no=" + n)
            lot_codes.append((ui.decode() or [""])[0])
        pg.goto(base + "/shp/scan")
        ui.scan(sc[0] if sc else "")
        opened = pg.url
        res = []
        for c in lot_codes:
            pg.focus("[data-scan]")
            ui.scan(c)
            res.append((c, ui.flash()))
            ui.close_popup()
        approve_off = pg.locator("#approve").count() == 0 or pg.locator("#approve button[type=submit]").is_disabled()
        rec("18", "shp_scan_lots", sc and sc[0] == shp_no and f"no={shp_no}" in opened and all(ui.ok(x[1]) for x in res),
            f"출하 라벨 해독 {sc} → {opened} · LOT 라벨 해독 · 스캔 {res}")
        # 19 승인 — 관리자 (현장은 승인 버튼 비활성)
        ui.login("admin", "pop")
        pg.goto(base + "/shp/scan?no=" + shp_no)
        if pg.locator("details:has(#approve) > summary").count():
            pg.locator("details:has(#approve) > summary").click()
        f = ui.submit("approve")
        rec("19", "shp_approve_admin", ui.ok(f) and approve_off, f"현장 승인 버튼 비활성 {approve_off} · 관리자 {f}")
        # 20 성적서 발행 · 출력 — 생산
        ui.login("prod")
        pg.goto(base + "/shp/documents")
        pg.select_option("#doc-new select[name=shipment_id]", label=ui.opt("#doc-new select[name=shipment_id]", shp_no))
        pg.select_option("#doc-new select[name=doc_type]", label="성적서")
        f = ui.submit("doc-new")
        m = re.search(r"(C\d{6}-\d+)", (f or {}).get("text", ""))
        doc_no = m.group(1) if m else ""
        href = pg.locator(f"main tr:has-text('{doc_no}') a[href$='/print']").first.get_attribute("href") if doc_no else None
        if href:
            pg.goto(base + href)
        dc = ui.decode() if href else []
        body = pg.locator("body").inner_text()
        rec("20", "shp_document_print", ui.ok(f) and doc_no in dc and all(n in body for n in sp[:2]), f"{f} · {href} 바코드 해독 {dc} · 분할 ①② 행 {[n in body for n in sp[:2]]}")
        # 21 역추적 — 출하 LOT → 원재료 ①②
        pg.goto(base + slab)
        m = re.search(r"(X\d{6}-\d+)", pg.locator("body").inner_text())
        ship_lot = m.group(1) if m else ""
        pg.goto(base + "/trc/backward?no=" + ship_lot)
        bw = pg.locator("main").inner_text()
        rec("21", "trc_backward", ship_lot and all(x in bw for x in mats), f"출하 LOT {ship_lot} → 원재료 {[(x, x in bw) for x in mats]}")
        # 22 정방향 — 원재료 ① → 생산 ①② → 합병 → 분할 ①②③ → 출하 · ③ 재고
        pg.goto(base + "/trc/forward?no=" + mats[0])
        fw = pg.locator("main").inner_text()
        want = [p1, p2, mg, *sp, ship_lot]
        rec("22", "trc_forward", all(x in fw for x in want) and "재고" in fw, f"{[(x, x in fw) for x in want]} · 재고 표시 {'재고' in fw}")
        # 23 현황판 — 갱신 시각이 바뀐다
        ui.login("admin", "board")
        pg.goto(base + "/kpi/board?device=board")
        sec = int(pg.evaluate("document.body.dataset.refreshSeconds || '0'") or 0)
        t0 = pg.locator("#refreshed-at").inner_text()
        pg.wait_for_timeout((sec + 1.5) * 1000)
        t1 = pg.locator("#refreshed-at").inner_text()
        rec("23", "kpi_board", sec > 0 and t0 != t1, f"{sec}초 주기 · 갱신 시각 {t0} → {t1}")
    except StopIteration as stop:
        st["stopped_at"] = str(stop)
    except Exception as exc:  # noqa: BLE001 — 화면 조작이 막힌 단계를 그대로 적는다 (FAIL)
        nn = f"{len(steps) + 1:02d}"
        try:
            shot(f"{nn}_blocked")
        except Exception:  # noqa: BLE001
            pass
        steps.append({"nn": nn, "name": "blocked", "ok": False, "note": f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}", "png": f"outputs/e2e/core/{nn}_blocked.png"})
        st["stopped_at"] = f"{nn} 예외"
    ui.ctx.close()
    return {"steps": steps, "state": st}


def _b_timing(b, base: str, pw: str, payload: dict) -> dict:
    ui = Ui(b, base, pw, scale=1)
    t0 = time.time()
    url = ui.login("admin")
    t_login = time.time() - t0
    pages = {}
    for path in payload.get("paths", ["/"]):
        ui.page.goto(base + path)
        txt = ui.page.locator("body").inner_text()
        pages[path] = {k: (k in txt) for k in payload.get("terms", [])}
        ui.page.screenshot(path=str(scratch() / f"timing-{path.strip('/').replace('/', '_') or 'main'}.png"), full_page=True)
    ui.ctx.close()
    return {"login_url": url, "login_s": round(t_login, 2), "terms_on_pages": pages, "s_total": round(time.time() - t0, 2)}


# ── 검사 본체 ─────────────────────────────────────────────────────────────
def check_live(port: int) -> dict:
    """서버 하나를 띄워 G-C13 · G-C14 · G-C16 · G-C18 을 잰다. 반환 = 리포트용 상세."""
    from mescore.app import nav, packs
    from mescore.app.settings import get_settings
    from mescore.db import conn

    pw = get_settings().seed_password
    token = get_settings().collect_token
    detail: dict = {}
    if not pw:
        for g in ("G-C13", "G-C14", "G-C16", "G-C17", "G-C18"):
            row(g, "서버 실측", False, "MES_SEED_PASSWORD 미설정 — 시드 계정으로 로그인할 수 없다")
        return detail
    with Server(port) as srv:
        base = srv.base
        fx = build_fixture(base, pw)
        detail["fixture"] = fx
        ch = packs.current().channels

        def path_of(sid):
            sc = nav.by_id(sid)
            return sc.probe or sc.path

        fx["pop_paths"] = [(sid, path_of(sid)) for sid in ch.get("pop", [])]
        fx["scan_get_paths"] = [(sid, nav.path_of(sid)) for sid in ("POP-01", "POP-03", "POP-04", "MAT-02", "QUA-02", "SHP-02")]
        mob = []
        for sid in ch.get("mobile", []):
            pth = path_of(sid)
            if sid in ("TRC-01", "TRC-02"):
                pth = nav.path_of(sid) + "?no=" + (fx["mats"][0]["no"] if sid == "TRC-01" else fx["plot"]["no"])
            mob.append((sid, pth))
        fx["mobile_paths"] = mob
        fx["print_paths"] = [("작업지시서", f"/job/print?id={fx['wo']['id']}", fx["wo"]["no"]),
                             ("LOT 라벨", f"/pop/labels?lot={fx['plot']['id']}", fx["plot"]["no"]),
                             ("출하 라벨", f"/shp/shipments/{fx['shipment']['id']}/label", fx["shipment"]["no"]),
                             ("성적서", f"/shp/documents/{fx['doc']['id']}/print", fx["doc"]["no"])]

        # 채널 밖 403 (HTTP)
        adm = http_client(base, "admin", pw)
        off = {f"{sid}?device={d}": adm.get(nav.path_of(sid) + f"?device={d}", headers={"accept": "text/html"}).status_code
               for sid, d in (("BAS-01", "pop"), ("BAS-01", "mobile"), ("BAS-01", "board"), ("SYS-01", "pop"), ("POP-02", "board"))}
        in_ch = adm.get(nav.path_of("KPI-01") + "?device=board", headers={"accept": "text/html"}).status_code
        row("G-C13", "채널 밖 화면 403", all(v == 403 for v in off.values()) and in_ch == 200, f"{off} · 채널 안 KPI-01?device=board {in_ch}")

        n_in_before = conn.q1("select count(*) as n from pop_input where work_result_id = %s and canceled_yn = 'N'", (fx["open_result"],))["n"]
        b_res, b_log = browser_job("channels", base, fx)
        detail["channels"] = b_res
        if b_res is None:
            for g, it in (("G-C13", "POP · 모바일 · 현황판 (브라우저)"), ("G-C14", "출력물 4종 · 스캔 왕복 (브라우저)")):
                row(g, it, None, b_log[:300])
        else:
            pop = b_res["pop"]
            multi = [k for k, v in pop.items() if v["scan"] > 1]
            with_scan = [k for k, v in pop.items() if v["scan"] == 1]
            unfocused = [k for k in with_scan if not pop[k]["focused"]]
            not_pop = [k for k, v in pop.items() if "ch-pop" not in v["body_class"] or v["status"] != 200]
            row("G-C13", "POP data-scan 하나 · 열자마자 포커스 · 레이아웃", not multi and with_scan and not unfocused and not not_pop,
                f"POP 화면 {len(pop)} · data-scan 1개 {len(with_scan)} · 2개 이상 {multi or 0} · 포커스 못 받음 {unfocused or 0} · ch-pop 아님/200 아님 {not_pop or 0}")
            rr = b_res["rerender"]
            bad = {k: v for k, v in rr.items() if not (v["status"] == 422 and v["url_kept"] and v["err_banner"] and v["focused"])}
            row("G-C13", "없는 번호 스캔 → 그 화면 422 재렌더", not bad,
                f"스캔 진입 GET {len(rr)} 화면 ?no={NOPE} — 422 · URL 유지 · 오류 배너 · 스캔칸 포커스 어긋남 {bad or 0}")
            n_in_after = conn.q1("select count(*) as n from pop_input where work_result_id = %s and canceled_yn = 'N'", (fx["open_result"],))["n"]
            ds = b_res["double_scan"]
            row("G-C13", "바코드 1회 = 1건 (같은 라벨 2회 스캔 = 2행)", n_in_after - n_in_before == 2 and ds["code"] == fx["mats"][1]["no"],
                f"원재료 라벨 해독 {ds['code']} · POP-03 스캔 2회 → pop_input +{n_in_after - n_in_before}")
            mobv = b_res["mobile"]
            over = {k: (v["scrollWidth"], v["clientWidth"]) for k, v in mobv.items() if v["scrollWidth"] != v["clientWidth"] or v["status"] != 200}
            row("G-C13", "모바일 390px 가로 넘침 0 (헤드리스 Chrome)", not over and len(mobv) > 0,
                f"모바일 채널 화면 {len(mobv)} · scrollWidth≠clientWidth 또는 200 아님 {over or 0}")
            bd = b_res["board"]
            exp_polls = bd["window_s"] / bd["refresh_seconds"] if bd["refresh_seconds"] else 0
            ok_b = (bd["refresh_seconds"] > 0 and bd["t0"] != bd["t1"] and 1 <= bd["polls_in_window"] <= int(exp_polls) + 1
                    and bd["stale_state"] == "stale" and bd["failed_at"] not in ("", "-") and bd["values_kept"] and bd["polls_during_503"] >= 1
                    and bd["state_after_recover"] != "stale" and "ch-board" in bd["body_class"])
            row("G-C13", "현황판 자동 새로고침 · 갱신 시각 · 503 유지", ok_b,
                f"{bd['refresh_seconds']}초 주기 · 갱신 시각 {bd['t0']} → {bd['t1']} · {bd['window_s']}초 동안 폴링 {bd['polls_in_window']}회(1배) · "
                f"폴링 503 → data-state={bd['stale_state']} · 실패 시각 {bd['failed_at']} · 값 유지 {bd['values_kept']} · 503 중 폴링 {bd['polls_during_503']}회 · 회복 뒤 state='{bd['state_after_recover']}'")
            pr = b_res["print"]
            bad14 = {k: v for k, v in pr.items() if not (v["status"] == 200 and v["inline_svg"] and not v["external_requests"] and not v["ext_refs"] and v["want"] in v["decoded"])}
            row("G-C14", "출력물 4종 · 인라인 SVG · 외부 요청 0 · 바코드 해독 = 번호", not bad14,
                " · ".join(f"{k} {v['status']} 해독 {v['decoded']}" for k, v in pr.items()) + f" · 어긋남 {bad14 or 0}")
            rt = b_res["roundtrip"]
            ok_rt = all(rt[s]["decoded"] == fx["plot"]["no"] and rt[s]["pop03_opened"] and rt[s]["pop04_label"] == fx["plot"]["no"] and rt[s]["pop03_focused"] for s in ("100x50", "50x30"))
            row("G-C14", "LOT 라벨 → POP 스캔칸 → 그 LOT (100×50 · 50×30)", ok_rt,
                f"100×50 {rt['100x50']} · 50×30 {rt['50x30']}")
            ok_rt2 = rt["wo_to_pop02"]["ok"] and rt["ship_to_shp02"]["ok"] and rt["doc_to_shp04"]["ok"]
            row("G-C14", "지시서 → POP-01 · 출하 라벨 → SHP-02 · 성적서 → SHP-04", ok_rt2,
                f"지시 {rt['wo_to_pop02']['decoded']} → {rt['wo_to_pop02']['url'].replace(base, '')} · 출하 {rt['ship_to_shp02']['decoded']} → {rt['ship_to_shp02']['url'].replace(base, '')} · 성적서 {rt['doc_to_shp04']['decoded']} 검색 {rt['doc_to_shp04']['ok']}")
            detail["printing_adapter"] = None

        # G-C16 ERP · 수집 — HTTP 로
        from mescore.app import erp as _erp
        try:
            _erp.adapter().push("qa3", {})
            st501 = "예외 없음"
        except Exception as exc:  # noqa: BLE001
            d = getattr(exc, "detail", {})
            st501 = f"{getattr(exc, 'status_code', type(exc).__name__)} {d.get('decision', '') if isinstance(d, dict) else ''}".strip()
        ob = conn.q1("select id from ifc_outbox order by id desc limit 1")
        retry = adm.post(f"/ifc/erp/{ob['id']}/retry") if ob else None
        retry_st = retry.status_code if retry is not None else None
        retry_body = retry.json() if retry is not None and retry.headers.get("content-type", "").startswith("application/json") else {}
        ob_status = conn.q1("select status from ifc_outbox where id = %s", (ob["id"],))["status"] if ob else None
        sent = conn.q1("select count(*) as n from ifc_outbox where status = '전송'")["n"]
        shp_ob = conn.q1("""select count(*) as n from ifc_outbox where created_at > now() - interval '30 minutes' and status = '미확정'""")["n"]
        row("G-C16", "ERP 501 D-02 · 재전송 HTTP 501 · 200 위장 없음 · 큐 미확정 유지",
            st501.startswith("501") and "D-02" in st501 and retry_st == 501 and retry_body.get("code") == "undecided" and ob_status == "미확정" and sent == 0,
            f"push → {st501} · POST /ifc/erp/{ob['id'] if ob else '-'}/retry → {retry_st} {retry_body.get('code')} {retry_body.get('decision', '')} · 그 행 {ob_status} · '전송' 행 {sent} · 최근 30분 미확정 {shp_ob}")
        import httpx
        msg = {"equip_code": "EQ-EX-01", "ts": datetime.now().astimezone().isoformat(), "source": "qa3", "tags": {"temp_c": 70.1}}
        r_bad = httpx.post(base + "/ifc/collect", json=msg, headers={"X-Collect-Token": "qa3-wrong-token"})
        r_none = httpx.post(base + "/ifc/collect", json=msg)
        r_unk = httpx.post(base + "/ifc/collect", json={**msg, "equip_code": "NOPE-EQ"}, headers={"X-Collect-Token": token or ""})
        rej = conn.q1("select count(*) as n from ifc_collect_raw where rejected_reason is not null and equip_code = 'NOPE-EQ'")["n"] if token else 0
        row("G-C16", "수집 토큰 틀림/없음 401 · 모르는 설비 422 + 거부 기록", r_bad.status_code == 401 and r_none.status_code == 401 and (not token or (r_unk.status_code == 422 and rej > 0)),
            f"틀린 토큰 {r_bad.status_code} · 토큰 없음 {r_none.status_code} · 맞는 토큰+없는 설비 {r_unk.status_code if token else '토큰 미설정'} · 거부 기록 {rej}")

        # G-C18 접근 로그 4종 + SYS-04 · 세션 무효화
        lid = "qa3_" + secrets.token_hex(3)
        upw, wrong = secrets.token_urlsafe(16), "x" + secrets.token_urlsafe(12)
        prod_role = conn.q1("select id from sys_role where role_code = 'PROD'")["id"]
        qa_role = conn.q1("select id from sys_role where role_code = 'QA'")["id"]
        cr = adm.post("/sys/users", data={"login_id": lid, "user_name": "QA3 시험 계정 (예시)", "role_id": prod_role, "password": upw}).json()
        uid = cr["id"]
        import httpx as _h
        bad_login = _h.post(base + "/login", data={"login_id": lid, "password": wrong}).status_code
        u = http_client(base, lid, upw)
        v = u.get(nav.path_of("ORD-04")).status_code
        ch_ = u.post("/ord/plans", data={"item_code": "PRD-EX-01", "plan_date": str(date.today()), "plan_qty": 1}).status_code
        kinds = {r["kind"]: r["n"] for r in conn.q("select kind, count(*) as n from sys_access_log where login_id = %s group by kind", (lid,))}
        leak = conn.q1("select count(*) as n from sys_access_log where coalesce(detail::text, '') like %s or coalesce(target, '') like %s", (f"%{wrong}%", f"%{wrong}%"))["n"]
        logs_html = adm.get(nav.path_of("SYS-04") + f"?login_id={lid}", headers={"accept": "text/html"})
        shown = {k: (k in logs_html.text) for k in ("login_ok", "login_fail", "view", "change")}
        shown_lbl = lid in logs_html.text
        row("G-C18", "접근 로그 4종 + SYS-04 조회 · 비밀번호 미기록",
            all(kinds.get(k, 0) > 0 for k in ("login_ok", "login_fail", "view", "change")) and logs_html.status_code == 200 and shown_lbl and leak == 0,
            f"시험 계정 로그인 실패 {bad_login} · 조회 {v} · 변경 {ch_} → sys_access_log {kinds} · SYS-04 {logs_html.status_code} 계정 행 보임 {shown_lbl} · 로그에 틀린 비밀번호 {leak}건")
        # 역할 변경 → 다음 요청부터
        before = u.get(nav.path_of("QUA-02") + "?no=" + NOPE)
        w_before = u.post("/qua/inspections", data={"lot_id": fx["plot"]["id"], "insp_type": "최종"}).status_code
        adm.post(f"/sys/users/{uid}", data={"role_id": qa_role})
        w_after = u.post("/qua/inspections", data={"lot_id": fx["mats"][0]["id"], "insp_type": "입고"}).status_code
        p_after = u.post("/ord/plans", data={"item_code": "PRD-EX-01", "plan_date": str(date.today()), "plan_qty": 1}).status_code
        role_ok = w_before == 403 and w_after in (200, 422) and p_after == 403
        # 로그아웃 → 같은 쿠키 재사용 401
        cookies = dict(u.cookies)
        u.post("/logout")
        replay = _h.get(base + nav.path_of("ORD-04"), cookies=cookies).status_code
        # 중지 → 다음 요청 401 · 해제 뒤 다시 로그인
        u2 = http_client(base, lid, upw)
        adm.post(f"/sys/users/{uid}/toggle")
        stopped = u2.get(nav.path_of("ORD-04")).status_code
        relog_stopped = _h.post(base + "/login", data={"login_id": lid, "password": upw}).status_code
        adm.post(f"/sys/users/{uid}/toggle")
        # 비밀번호 변경 → 그 전 세션 401
        u3 = http_client(base, lid, upw)
        upw2 = secrets.token_urlsafe(16)
        adm.post(f"/sys/users/{uid}", data={"password": upw2})
        pw_changed = u3.get(nav.path_of("ORD-04")).status_code
        row("G-C17", "역할 변경이 다음 요청부터 (시험 계정 PROD→QA · 요청마다 DB)", role_ok,
            f"품질 검사 등록 {w_before}→{w_after} · 생산계획 등록(QA 조회 칸) →{p_after} · 세션 재로그인 없이 다음 요청에서 바뀜 (48칸 전수는 QA1 check_screens)")
        row("G-C18", "세션 무효화 — 로그아웃 · 중지 · 비밀번호 변경 뒤 다음 요청 401",
            replay == 401 and stopped == 401 and relog_stopped == 401 and pw_changed == 401,
            f"로그아웃 뒤 같은 쿠키 {replay} · 중지 뒤 다음 요청 {stopped} · 중지 계정 로그인 {relog_stopped} · 비밀번호 변경 전 세션 {pw_changed}")
        detail["session_user"] = lid
        for dev in ("web", "pop", "board"):
            c_ = http_client(base, "admin", pw, device=dev)
            COOKIES[dev] = dict(c_.cookies)
        adm.close()
        u.close()
    # 잠금 — MES_LOGIN_LOCK_COUNT=3 으로 띄운 서버 (정본에 수치 없음 · D-14 — 값이 있을 때의 동작만 잰다)
    with Server(port, {"MES_LOGIN_LOCK_COUNT": "3"}, name="lock") as srv:
        import httpx as _h
        lid2 = "qa3_" + secrets.token_hex(3)
        upw = secrets.token_urlsafe(16)
        adm = http_client(srv.base, "admin", pw)
        adm.post("/sys/users", data={"login_id": lid2, "user_name": "QA3 잠금 시험 (예시)", "role_id": conn.q1("select id from sys_role where role_code = 'PROD'")["id"], "password": upw})
        live = http_client(srv.base, lid2, upw)
        fails = [_h.post(srv.base + "/login", data={"login_id": lid2, "password": "x" + secrets.token_hex(6)}).status_code for _ in range(3)]
        st_db = conn.q1("select status from sys_user where login_id = %s", (lid2,))["status"]
        live_after = live.get(nav.path_of("ORD-04")).status_code
        right_pw = _h.post(srv.base + "/login", data={"login_id": lid2, "password": upw}).status_code
        row("G-C18", "잠금 (MES_LOGIN_LOCK_COUNT=3) → 기존 세션 · 바른 비밀번호 모두 401",
            st_db == "잠금" and live_after == 401 and right_pw == 401,
            f"틀린 비밀번호 3회 {fails} → 상태 {st_db} · 잠기기 전 세션의 다음 요청 {live_after} · 바른 비밀번호 로그인 {right_pw}")
        adm.close()
        live.close()
    return detail


def check_db_down(port: int) -> dict:
    """DB 를 끊은(없는 DB 이름) 서버 — 조용히 200 을 주지 않는가."""
    import httpx
    out = {}
    with Server(port, {"MES_PG_DSN": "postgresql:///mes_qa3_no_such_db"}, name="dbdown") as srv:
        b = srv.base
        h = httpx.get(b + "/health")
        lg = httpx.post(b + "/login", data={"login_id": "admin", "password": "x"})
        ck = COOKIES or {}
        main = httpx.get(b + "/", headers={"accept": "text/html"}, cookies=ck.get("web"))
        popw = httpx.get(b + "/pop/work?device=pop", headers={"accept": "text/html"}, cookies=ck.get("pop"))
        board = httpx.get(b + "/kpi/board?device=board", headers={"accept": "text/html"}, cookies=ck.get("board"))
        js = httpx.get(b + "/bas/items", cookies=ck.get("web"))
        anon = httpx.get(b + "/bas/items").status_code
        leak = any(s in (h.text + lg.text + main.text + js.text) for s in ("mes_qa3_no_such_db", "postgresql://", "/tmp"))
        scan_disabled = bool(re.search(r"<input[^>]*data-scan[^>]*disabled|<input[^>]*disabled[^>]*data-scan", popw.text))
        board_refresh = ("data-refresh-seconds" in board.text) or ("http-equiv=\"refresh\"" in board.text.lower())
        out = {"health": h.status_code, "login": lg.status_code, "main": main.status_code, "pop": popw.status_code, "pop_scan_disabled": scan_disabled,
               "board": board.status_code, "board_refresh": board_refresh, "json": js.status_code, "json_code": (js.json() if js.headers.get("content-type", "").startswith("application/json") else {}).get("code"),
               "leak": leak, "msg": "서비스 일시 중단" in main.text, "anon": anon, "with_session": bool(ck)}
    ok = (out["health"] == 503 and out["login"] == 503 and out["main"] == 503 and out["msg"] and out["pop"] == 503 and out["json"] == 503
          and out["json_code"] == "db_unavailable" and not leak)
    row("G-C13", "DB 끊긴 기동 — 503 · 조용한 200 없음", ok,
        f"(로그인 세션 쿠키로 요청 {out['with_session']}) /health {out['health']} · POST /login {out['login']} · 메인 {out['main']} 「서비스 일시 중단」 {out['msg']} · JSON {out['json']} {out['json_code']} · 접속 문자열 노출 {leak} · 쿠키 없는 JSON {out['anon']}")
    row("G-C13", "DB 끊김 — POP 스캔칸 disabled(S-12) · 현황판 오류 화면 새로고침", out["pop_scan_disabled"] and out["board_refresh"],
        f"POP-01 {out['pop']} 스캔칸 disabled {out['pop_scan_disabled']} · 현황판 {out['board']} 새로고침 표지 {out['board_refresh']}")
    return out


def check_migrate() -> dict:
    from mescore import migrate
    from mescore.app import contracts
    from mescore.db import conn

    src = ROOT / "src" / "mescore" / "migrate" / "examples"
    work = Path(tempfile.mkdtemp(prefix="qa3-mig-"))
    shutil.copytree(src, work / "ok")
    targets = {t for f in contracts.batch_functions() for t in f.tables} - {"sys_migration_log"}
    env = dict(os.environ)
    runs = []
    for i in (1, 2):
        b = conn.table_counts()
        codes = []
        for cmd in migrate.COMMANDS:
            c, o = run(["uv", "run", "python", "-m", "mescore.migrate", cmd, "--dir", str(work / "ok")], env=env)
            m = re.search(r"합계 읽음 (\d+) · 적재 (\d+) · 갱신 (\d+) · 건너뜀 (\d+) · 오류 (\d+) → 종료 코드 (\d+)", o)
            codes.append((cmd, c, m.groups() if m else o.strip().splitlines()[-1:]))
        a = conn.table_counts()
        runs.append({"codes": codes, "diff": {k: (b.get(k), a.get(k)) for k in sorted(targets) if b.get(k) != a.get(k)},
                     "log": a.get("sys_migration_log", 0) - b.get("sys_migration_log", 0)})
    second_loaded = sum(int(g[1]) for _, _, g in runs[1]["codes"] if isinstance(g, tuple))
    # dry-run 은 쓰지 않는다
    b = conn.table_counts()
    dry = [run(["uv", "run", "python", "-m", "mescore.migrate", cmd, "--dir", str(work / "ok"), "--dry-run"], env=env)[0] for cmd in migrate.COMMANDS]
    a = conn.table_counts()
    dry_diff = {k: (b.get(k), a.get(k)) for k in sorted(targets) if b.get(k) != a.get(k)}
    # 깨진 파일 — 품목 파일에 필수값 빠진 줄 하나
    shutil.copytree(src, work / "bad")
    items = work / "bad" / "01_items.csv"
    items.write_text(items.read_text(encoding="utf-8").rstrip("\n") + "\n,이름만 있는 줄 (예시),제품,,EA,Y\n", encoding="utf-8")
    lb = conn.q1("select coalesce(max(id), 0) as m, count(*) as n from sys_migration_log")
    c_bad, o_bad = run(["uv", "run", "python", "-m", "mescore.migrate", "basics", "--dir", str(work / "bad")], env=env)
    new_logs = conn.q("select file, errors, error_detail from sys_migration_log where id > %s order by id", (lb["m"],))
    la = lb["n"] + len(new_logs)
    lb = lb["n"]
    err_rows = [f"{r['file']} 오류 {r['errors']} {json.dumps(r['error_detail'], ensure_ascii=False)[:120]}" for r in new_logs if r["errors"]]
    err_logged, err_cols = bool(err_rows), err_rows
    report_line = [ln for ln in o_bad.splitlines() if "01_items.csv" in ln or "오류" in ln][:3]
    shutil.rmtree(work, ignore_errors=True)
    ok = (all(c == 0 for _, c, _ in runs[0]["codes"]) and all(c == 0 for _, c, _ in runs[1]["codes"]) and not runs[1]["diff"] and second_loaded == 0
          and runs[0]["log"] >= 4 and runs[1]["log"] >= 4 and not dry_diff and all(c == 0 for c in dry))
    row("G-C15", "이관 4 명령 실제 적재 2회 멱등 · dry-run 쓰기 0", ok,
        f"1회 {[(c, g) for c, _, g in runs[0]['codes']]} · 2회 적재 합 {second_loaded} · 2회째 대상 테이블 {len(targets)} 행 수 diff {runs[1]['diff'] or 0} · "
        f"sys_migration_log +{runs[0]['log']}/+{runs[1]['log']} · dry-run rc {dry} diff {dry_diff or 0}")
    row("G-C15", "깨진 파일 → 종료 코드 1 · 오류 리포트 · 로그 행", c_bad == 1 and la > lb and err_logged and bool(report_line),
        f"rc={c_bad} · 리포트 {report_line[1:2]} · sys_migration_log +{la - lb}(파일마다 한 행) · 오류 기록 행 {err_cols}")
    return {"runs": runs, "dry": dry, "bad_rc": c_bad, "bad_report": report_line}


def check_secrets() -> dict:
    vals = [v for v in (os.environ.get("MES_SEED_PASSWORD"), os.environ.get("MES_SESSION_SECRET"), os.environ.get("MES_COLLECT_TOKEN")) if v]
    _, listed = run(["git", "ls-files", "-co", "--exclude-standard"])
    files = [ROOT / f for f in listed.splitlines() if f.strip()]
    hits = []
    for f in files:
        try:
            data = f.read_bytes()
        except OSError:
            continue
        if any(v.encode() in data for v in vals):
            hits.append(str(f.relative_to(ROOT)))
    ign = {p: run(["git", "check-ignore", "-q", p])[0] == 0 for p in (".env", "backups/x.dump")}
    pat = re.compile(r"""(password|passwd|secret|token)\s*[:=]\s*["'][^"'\s{}]{6,}["']""", re.I)
    hard = []
    for f in files:
        if f.suffix not in (".py", ".yaml", ".yml", ".html", ".js", ".sql", ".toml", ".cfg", ".ini", ".json") or "outputs" in f.parts:
            continue
        try:
            for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pat.search(ln) and "example" not in ln.lower():
                    hard.append(f"{f.relative_to(ROOT)}:{i}")
        except OSError:
            continue
    cdn = []
    for f in (ROOT / "packs").rglob("*"):
        if f.is_file() and f.suffix in (".html", ".js", ".css", ".py", ".yaml") and "__pycache__" not in f.parts:
            for m in re.finditer(r"""(?:src|href)\s*=\s*["'](https?://[^"']+)|@import\s+url\(["']?(https?://[^)"']+)""", f.read_text(encoding="utf-8", errors="replace")):
                cdn.append(f"{f.relative_to(ROOT)} {m.group(1) or m.group(2)}")
    row("G-C19", "비밀 값 grep 0 · .env · backups gitignore", bool(vals) and not hits and all(ign.values()),
        f"저장소 대상 파일 {len(files)} 중 .env 비밀 값(3종 중 설정 {len(vals)})이 든 파일 {hits or 0} · gitignore {ign}")
    row("G-C19", "하드코딩 비밀 패턴 · 팩 외부 CDN 0 (R11)", not hard and not cdn,
        f"password/secret/token = '리터럴' {hard[:5] or 0} · 팩 외부 CDN {cdn[:5] or 0}")
    return {"files": len(files), "hits": hits, "hard": hard, "cdn": cdn}


def check_backup() -> dict:
    env = dict(os.environ)
    c1, o1 = run(["uv", "run", "python", str(TOOLS / "backup.py"), "backup"], env=env)
    c2, o2 = run(["uv", "run", "python", str(TOOLS / "backup.py"), "restore-check"], env=env)
    tail = [ln for ln in o2.splitlines() if "판정" in ln or "PASS" in ln or "FAIL" in ln][-1:] or o2.strip().splitlines()[-1:]
    leak = any(v and v in (o1 + o2) for v in (os.environ.get("MES_SEED_PASSWORD"), os.environ.get("MES_SESSION_SECRET")))
    row("G-C20", "backup → restore-check 임시 DB · 행 수 일치", c1 == 0 and c2 == 0 and "일치" in o2 and not leak,
        f"backup rc={c1} · restore-check rc={c2} · {tail} · 출력에 비밀 {leak}")
    return {"backup_rc": c1, "restore_rc": c2, "tail": tail}


def check_pack_isolation() -> dict:
    """G-P01 — 팩 3 check_pack + R9: 원본 트리는 건드리지 않고 `git worktree add` 복사본에서 팩 폴더를 지운 뒤 코어 tests/ 전건."""
    out = {}
    for pack in sorted(p.name for p in (ROOT / "packs").iterdir() if p.is_dir() and not p.name.startswith("_")):
        env = dict(os.environ)
        env["MES_PACK"] = pack
        env.pop("MES_PG_DSN", None)
        c, o = run(["uv", "run", "python", str(TOOLS / "check_pack.py")], env=env)
        bad = [ln for ln in o.splitlines() if re.match(r"^G-P01\s.*\s(FAIL|WARN)\s", ln)]
        out[pack] = {"rc": c, "bad": bad}
        row("G-P01", f"[{pack}] check_pack", c == 0 and not [b for b in bad if " FAIL " in b], f"rc={c} · FAIL/WARN {bad[:3] or 0}")
    wt = Path("/tmp/qa3-wt")
    run(["git", "worktree", "remove", "--force", str(wt)])
    shutil.rmtree(wt, ignore_errors=True)
    c, o = run(["git", "worktree", "add", "--detach", str(wt), "HEAD"])
    if c != 0:
        row("G-P01", "R9 팩 폴더를 지운 worktree 에서 코어 tests/", None, f"git worktree add 실패 — {o.strip()[:200]}")
        return out
    try:
        if (ROOT / ".env").exists():
            shutil.copy(ROOT / ".env", wt / ".env")                 # 비밀은 복사만 (worktree 는 커밋하지 않는다 · 지운다)
        removed = []
        for p in (wt / "packs").iterdir():
            if p.is_dir() and not p.name.startswith("_"):
                shutil.rmtree(p)
                removed.append(p.name)
        env = dict(os.environ)
        env["MES_PACK"] = ""
        env.pop("VIRTUAL_ENV", None)
        c1, o1 = run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", "tests"], env=env, timeout=3000, cwd=wt)
        m = re.search(r"(\d+) passed", o1)
        mf = re.search(r"(\d+) failed", o1)
        me = re.search(r"(\d+) error", o1)
        failed = re.findall(r"^(?:FAILED|ERROR) (\S+)", o1, re.M)
        out["r9_core"] = {"rc": c1, "passed": m.group(1) if m else 0, "failed": failed, "removed": removed, "tail": o1.strip().splitlines()[-1:] }
        row("G-P01", "R9 팩 폴더 지운 worktree — 코어 tests/ 전건", c1 == 0 and not failed,
            f"/tmp/qa3-wt (HEAD) 에서 packs/{removed} 삭제 · DB {os.environ.get('MES_PG_DSN') or '기본'} · passed {m.group(1) if m else 0} · failed {(int(mf.group(1)) if mf else 0) + (int(me.group(1)) if me else 0)} {failed[:5]}")
        # 팩 올린 채 tests/test_arch_*.py (아키텍트 확정 범위)
        for pack in removed:
            env2 = dict(os.environ)
            env2["MES_PACK"] = pack
            env2.pop("MES_PG_DSN", None)
            c2, o2 = run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_arch_*.py"))], env=env2, timeout=1200)
            f2 = re.findall(r"^(?:FAILED|ERROR) (\S+)", o2, re.M)
            out[f"r9_{pack}"] = {"rc": c2, "tail": o2.strip().splitlines()[-1:], "failed": f2}
            row("G-P01", f"[{pack}] R9 팩 올린 채 tests/test_arch_*.py", c2 == 0, f"mes_{pack}_db · {o2.strip().splitlines()[-1] if o2.strip() else ''} {f2[:3]}")
    finally:
        run(["git", "worktree", "remove", "--force", str(wt)])
        shutil.rmtree(wt, ignore_errors=True)
        run(["git", "worktree", "prune"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("MES_QA3_PORT", "8053")))
    ap.add_argument("--e2e", action="store_true")
    ap.add_argument("--pack-isolation", action="store_true")
    ap.add_argument("--only", default="", help="쉼표: live,dbdown,migrate,secrets,backup")
    ap.add_argument("--json", default="", help="상세를 이 파일에 JSON 으로")
    ap.add_argument("--_browser", nargs=4, metavar=("MODE", "BASE", "IN", "OUT"))
    a = ap.parse_args()
    if a._browser:
        return _browser_main(*a._browser)
    if (os.environ.get("MES_PACK") or "").strip() and not a.pack_isolation:
        print("G-C13  채널  미검증  check_security 는 코어 단독(MES_PACK=)으로 돈다")
        return 0
    from mescore.app import settings as _s  # noqa: F401 — .env 를 먼저 읽는다

    only = set(filter(None, a.only.split(","))) or {"live", "dbdown", "migrate", "secrets", "backup"}
    detail: dict = {}
    steps = [("live", lambda: check_live(a.port), ("G-C13", "G-C14", "G-C16", "G-C17", "G-C18")),
             ("dbdown", lambda: check_db_down(a.port), ("G-C13",)),
             ("migrate", check_migrate, ("G-C15",)),
             ("secrets", check_secrets, ("G-C19",)),
             ("backup", check_backup, ("G-C20",))]
    for name, fn, gids in steps:
        if name not in only:
            continue
        try:
            detail[name] = fn()
        except Exception as exc:  # noqa: BLE001 — 검사기 자체가 막히면 그 게이트는 FAIL 로 적는다 (통과로 두지 않는다)
            for g in gids:
                row(g, f"{name} 실측 중단", False, f"{type(exc).__name__}: {str(exc)[:240]}")
    if a.e2e:
        try:
            from mescore.app.settings import get_settings
            with Server(a.port, name="e2e") as srv:
                res, log = browser_job("e2e", srv.base, {})
            detail["e2e"] = res
            if res is None:
                row("G-C22", "브라우저 한 바퀴", None, log[:300])
            else:
                bad = [f"{s['nn']} {s['name']}: {s['note'][:160]}" for s in res["steps"] if not s["ok"]]
                row("G-C22", "브라우저 한 바퀴 (코어 단독 · 역할 4)", not bad and len(res["steps"]) >= 23,
                    f"단계 {len(res['steps'])} · 통과 {sum(s['ok'] for s in res['steps'])} · 막힌 단계 {bad or 0} · 캡처 outputs/e2e/core/")
            _ = get_settings
        except Exception as exc:  # noqa: BLE001
            row("G-C22", "브라우저 한 바퀴", False, f"{type(exc).__name__}: {str(exc)[:240]}")
    if a.pack_isolation:
        try:
            detail["pack"] = check_pack_isolation()
        except Exception as exc:  # noqa: BLE001
            row("G-P01", "팩 격리 실측 중단", False, f"{type(exc).__name__}: {str(exc)[:240]}")
    width = max((len(i) for _, i, _, _ in ROWS), default=10)
    for gid, item, st, measured in ROWS:
        print(f"{gid}  {item.ljust(width)}  {st}  {measured}")
    if a.json:
        Path(a.json).write_text(json.dumps(detail, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 1 if any(r[2] == FAIL for r in ROWS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
