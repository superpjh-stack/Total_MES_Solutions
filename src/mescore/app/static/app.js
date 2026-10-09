/* 공통 UI 동작 — 좌측 메뉴 접기 · 목록 정렬 · 쪽 넘김 · 알림 팝업 · 스캔칸 포커스(POP S-01~S-15) · 현황판 자동 새로고침.
   외부 라이브러리 0. 실패를 조용히 삼키지 않는다(콘솔에 그대로 남긴다). 스크립트는 이 파일 하나다 (CLAUDE.md).
   POP 동작 사양 S-01~S-14 는 docs/design/README.md "POP · 모바일" §2 — 번호를 주석에 그대로 적는다. */
(function () {
  "use strict";

  /* 좌측 메뉴 접기/펼치기 — 메뉴를 누르면 그 화면 목록이 펼쳐지고, 펼쳐져 있던 다른 메뉴는 접힌다 (base.html .mg > button.menu-head[aria-expanded]) */
  /* 사이드바 줄이기 · 늘이기 — #side-toggle 이 body.side-collapsed 를 바꾼다(줄이면 아이콘 막대). 상태는 이 브라우저에만 기억한다(localStorage — 막혀 있으면 기억만 안 한다) */
  var SIDE_KEY = "mes.side.collapsed", sideBtn = document.getElementById("side-toggle");
  function setSide(collapsed, remember) {
    document.body.classList.toggle("side-collapsed", collapsed);
    if (sideBtn) sideBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    if (remember) { try { window.localStorage.setItem(SIDE_KEY, collapsed ? "1" : "0"); } catch (e) { /* 저장 불가 — 이번 화면에서만 적용 */ } }
  }
  if (sideBtn) {
    var saved = null;
    try { saved = window.localStorage.getItem(SIDE_KEY); } catch (e) { saved = null; }
    if (saved === "1") setSide(true, false);
    sideBtn.addEventListener("click", function () { setSide(!document.body.classList.contains("side-collapsed"), true); });
  }

  document.querySelectorAll(".menu-head").forEach(function (head) {
    head.addEventListener("click", function () {
      if (document.body.classList.contains("side-collapsed")) {   /* 줄인 막대에서 누르면 늘이고 그 메뉴를 연다 */
        setSide(false, true);
        if (head.parentElement.classList.contains("open") || head.parentElement.classList.contains("on")) return;
      }
      var group = head.parentElement, opening = !group.classList.contains("open");
      group.parentElement.querySelectorAll(".menu-group.open").forEach(function (g) {
        if (g !== group) { g.classList.remove("open"); var h = g.querySelector(".menu-head"); if (h && !g.classList.contains("on")) h.setAttribute("aria-expanded", "false"); }
      });
      group.classList.toggle("open", opening);
      head.setAttribute("aria-expanded", (opening || group.classList.contains("on")) ? "true" : "false");
    });
  });

  /* 관리자 Web 레이아웃(디자이너1 base.html) — 메뉴 · 계약 패널 접기, 토스트 · 알림 닫기, 인라인 확인 취소. 키보드만으로 끝난다(button) */
  function toggleBody(btn, cls) {
    if (!btn) return;
    btn.addEventListener("click", function () {
      var on = document.body.classList.toggle(cls);
      btn.setAttribute("aria-expanded", on ? "false" : "true");
    });
  }
  toggleBody(document.getElementById("desc-toggle"), "desc-closed");
  document.querySelectorAll("[data-toast-close]").forEach(function (b) {
    b.addEventListener("click", function () { var tst = b.closest(".toast"); if (tst) tst.remove(); });
  });
  document.querySelectorAll(".toast[data-auto]").forEach(function (tst) { setTimeout(function () { if (tst.parentNode) tst.remove(); }, 8000); });   /* 8초 뒤 사라진다(닫기 버튼 있음) */
  document.querySelectorAll("[data-alert-close]").forEach(function (b) {
    b.addEventListener("click", function () { var al = b.closest(".alert"); if (al) al.remove(); });
  });
  document.querySelectorAll("[data-close-details]").forEach(function (b) {
    b.addEventListener("click", function () { var d = b.closest("details"); if (d) { d.open = false; var sm = d.querySelector("summary"); if (sm) sm.focus(); } });
  });

  /* 목록 머리행 클릭 정렬 — 이 쪽에 받은 행만. 서버 정렬 링크(th.th-sort > a · ?sort=)가 있는 열은 링크가 맡는다 */
  function dataRows(table) {
    return Array.prototype.slice.call(table.tBodies[0] ? table.tBodies[0].rows : []).filter(function (r) {
      return !r.querySelector(".empty");
    });
  }
  document.querySelectorAll("table.grid:not(.plain) thead th:not(.th-sort)").forEach(function (th) {
    th.addEventListener("click", function () {
      var table = th.closest("table"), tbody = table.tBodies[0];
      if (!tbody) return;
      var idx = Array.prototype.indexOf.call(th.parentElement.cells, th);
      var asc = th.dataset.sort !== "asc";
      table.querySelectorAll("thead th").forEach(function (o) { delete o.dataset.sort; });
      th.dataset.sort = asc ? "asc" : "desc";
      var rows = dataRows(table);
      rows.sort(function (a, b) {
        var x = (a.cells[idx] ? a.cells[idx].textContent : "").trim();
        var y = (b.cells[idx] ? b.cells[idx].textContent : "").trim();
        var nx = parseFloat(x.replace(/[, ]/g, "")), ny = parseFloat(y.replace(/[, ]/g, ""));
        var cmp = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : x.localeCompare(y, "ko");
        return asc ? cmp : -cmp;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
      table.dataset.page = "1";
      applyPage(table);
    });
  });

  /* 목록 쪽 넘김 — 서버는 상한만 걸고 화면이 한 쪽씩 보인다 */
  var PAGE = parseInt(document.body.dataset.gridPageSize || "10", 10) || 10;
  function applyPage(table) {
    var rows = dataRows(table), total = rows.length;
    var pages = Math.max(1, Math.ceil(total / PAGE));
    var cur = Math.min(Math.max(1, parseInt(table.dataset.page || "1", 10) || 1), pages);
    table.dataset.page = String(cur);
    rows.forEach(function (r, i) { r.hidden = (i < (cur - 1) * PAGE || i >= cur * PAGE); });
    var bar = table.nextElementSibling;
    if (!bar || !bar.classList.contains("pager")) {
      bar = document.createElement("div"); bar.className = "pager";
      table.parentNode.insertBefore(bar, table.nextSibling);
      bar.innerHTML = '<button type="button" class="btn btn-sm" data-pg="prev">이전</button>' +
        '<span class="pg-info"></span>' +
        '<button type="button" class="btn btn-sm" data-pg="next">다음</button>';
    }
    bar.hidden = total <= PAGE;
    bar.querySelector(".pg-info").textContent = total ? (cur + " / " + pages + " 쪽 · " + total + "행") : "";
    bar.querySelector('[data-pg="prev"]').disabled = cur <= 1;
    bar.querySelector('[data-pg="next"]').disabled = cur >= pages;
    bar.querySelector('[data-pg="prev"]').onclick = function () { table.dataset.page = String(cur - 1); applyPage(table); };
    bar.querySelector('[data-pg="next"]').onclick = function () { table.dataset.page = String(cur + 1); applyPage(table); };
  }
  document.querySelectorAll("table.grid:not(.plain)").forEach(function (t) { applyPage(t); });

  /* ── 스캔칸 · 알림 팝업 (G-C13 · D-10: 스캐너 = 키보드 입력 + Enter) — S-01 ~ S-12 ──
     스캔칸(`[data-scan]`)이 있는 화면에서는 스캔칸이 포커스의 주인이다. 스캔칸이 없는 화면(관리자 Web · 모바일)에서는
     S-02~S-08 · S-10~S-12 가 동작하지 않고 알림의 「확인」이 포커스를 갖는다 (S-01). */
  var scans = document.querySelectorAll("[data-scan]");
  if (scans.length > 1) console.error("data-scan 이 " + scans.length + "개 — 화면에 하나여야 한다 (S-01)");   /* S-01 조용히 첫 것을 고르지 않는다 */
  var scan = scans.length === 1 ? scans[0] : null;
  var layer = document.getElementById("popup-layer");
  function popupOpen() { return !!layer && !layer.hidden; }

  /* S-03 다른 입력칸 · 선택칸 · 버튼 · 링크를 쓰는 중(activeElement 가 그것)에는 빼앗지 않는다 */
  function idle(a) {
    return !a || a === document.body || a === scan || (!!layer && layer.contains(a)) ||
      !/^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/.test(a.tagName);
  }
  /* S-12 disabled 스캔칸(503 화면)에는 포커스를 주지 않는다 */
  function focusScan() {
    if (scan && !scan.disabled && document.activeElement !== scan && idle(document.activeElement)) scan.focus();
  }
  if (scan) {
    focusScan();                                                                 /* S-02 열리면 포커스 (autofocus 와 둘 다) */
    document.addEventListener("click", function () { setTimeout(focusScan, 0); }); /* S-03 빈 곳을 눌렀다 놓으면 복귀 */
    window.addEventListener("focus", focusScan);                                 /* S-04 창이 다시 활성화되면 복귀 */
    /* S-05 바코드 1회 = 요청 1회 = 1건. 보내면 스캔칸을 비운다(서버가 다시 그리므로 저절로 빈다) — 여기서는 아무것도 가로채지 않는다 */
  }

  /* 알림 팝업 — 쓰기 결과 · 422 (base.html 의 #popup-layer). 떠 있어도 다음 스캔을 막지 않는다 */
  function popup(title, body, fields, kind) {
    if (!layer) { console.warn("popup-layer 없음:", title, body); return; }
    var box0 = layer.querySelector(".popup");
    box0.classList.toggle("warn", kind === "warn" || kind === "error");
    box0.classList.toggle("ok", kind === "ok");
    document.getElementById("popup-title").textContent = title || "알림";
    var box = document.getElementById("popup-body");
    box.innerHTML = "";
    var p = document.createElement("p");
    p.textContent = body || "";
    box.appendChild(p);
    if (fields && fields.length) {                                               /* S-09 fields[].label — reason 을 줄로 */
      var ul = document.createElement("ul");
      ul.className = "fields";
      fields.forEach(function (f) {
        var li = document.createElement("li");
        li.textContent = (f.label || f.name || "입력") + " — " + (f.reason || "");
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }
    layer.hidden = false;
    if (scan) { focusScan(); return; }                                           /* S-06 포커스는 「확인」이 아니라 스캔칸에 */
    var ok = layer.querySelector("[data-popup-close]");
    if (ok) ok.focus();
  }
  function closePopup() {
    if (!layer) return;
    layer.hidden = true;
    setTimeout(focusScan, 0);                                                    /* S-08 방금 누른 「확인」이 포커스를 쥐고 있어도 돌려준다 */
  }
  if (layer) {
    layer.querySelectorAll("[data-popup-close]").forEach(function (b) { b.addEventListener("click", closePopup); });
    layer.addEventListener("click", function (e) { if (e.target === layer) closePopup(); });   /* S-08 바깥 누르기 */
    document.addEventListener("keydown", function (e) {
      if (!popupOpen()) return;
      if (e.key === "Escape") { closePopup(); return; }                           /* S-08 Esc */
      if (!scan) return;
      var a = document.activeElement;
      if (e.key === "Enter") {                                                   /* S-07 빈 스캔칸 · 본문의 Enter 는 닫기만. 글자가 있으면 전송(기본 동작) */
        if ((a === scan && scan.value === "") || !a || a === document.body) { e.preventDefault(); closePopup(); }
        return;                                                                  /* 「확인」 위 Enter 는 클릭 · 다른 입력칸의 Enter 는 그 폼의 것 */
      }
      if (e.key && e.key.length === 1 && e.key !== " " && !e.ctrlKey && !e.metaKey && !e.altKey && idle(a)) {
        closePopup();                                                            /* S-07 글자 키 = 다음 스캔의 시작 — 알림을 닫고 */
        if (!scan.disabled && a !== scan) scan.focus();                          /*      그 글자는 스캔칸에 들어간다 */
      }
    }, true);
  }
  window.mesPopup = popup;

  /* S-10 쓰기 성공 배너 — 본문 #scan-result 에 초록 28px 로 1초 보이고 회색으로 가라앉는다.
     S-11 422 재렌더의 #scan-result.err(role=alert) 는 건드리지 않는다. */
  function banner(message, kind) {
    var el = document.getElementById("scan-result");
    if (!el || el.classList.contains("err")) return false;
    el.innerHTML = "";
    var p = document.createElement("p");
    p.className = "result-msg";
    p.textContent = message;
    el.appendChild(p);
    el.className = "result " + (kind === "ok" ? "ok" : "");
    el.hidden = false;
    if (kind === "ok") setTimeout(function () { el.className = "result"; }, 1000);
    return true;
  }

  /* S-09 서버가 303 뒤에 실어 보낸 #flash-data(JSON: title message fields[] kind) → 알림. 파싱 실패는 콘솔 경고(화면은 멀쩡히 둔다) */
  var flashEl = document.getElementById("flash-data");
  if (flashEl) {
    try {
      var f = JSON.parse(flashEl.textContent || "{}");
      if (f && (f.message || (f.fields && f.fields.length))) {
        var bannerOnly = false;
        if (scan && f.kind === "ok") {                                           /* S-10 팝업까지 띄울지는 화면이 정한다 (#scan-result[data-flash-banner]) */
          var el = document.getElementById("scan-result");
          bannerOnly = !!el && el.hasAttribute("data-flash-banner");
          banner(f.message || "", "ok");
        }
        if (!bannerOnly) popup(f.title || "알림", f.message || "", f.fields, f.kind);
      }
    } catch (e) { console.warn("flash 파싱 실패", e); }
  }
  /* S-15 고르기 칩 — button[data-pick-into=칸 id][data-pick-value=번호] 를 누르면 그 칸(쉼표 목록)에 번호를 넣고, 다시 누르면 뺀다.
     칸이 폼 값의 주인이다(손으로 고쳐도 칩 표시가 따라온다). 쓰기는 하지 않는다 — 전송은 그 폼의 버튼. POP-02 종료 폼 merge_lot_ids */
  function pickList(input) { return input.value.split(",").map(function (v) { return v.trim(); }).filter(Boolean); }
  function pickSync(input) {
    var have = pickList(input);
    document.querySelectorAll('[data-pick-into="' + input.id + '"]').forEach(function (b) {
      b.setAttribute("aria-pressed", have.indexOf(b.dataset.pickValue) >= 0 ? "true" : "false");
    });
  }
  document.querySelectorAll("[data-pick-into]").forEach(function (b) {
    var input = document.getElementById(b.dataset.pickInto);
    if (!input) { console.warn("data-pick-into 칸 없음:", b.dataset.pickInto); return; }
    b.addEventListener("click", function () {
      var have = pickList(input), v = b.dataset.pickValue, i = have.indexOf(v);
      input.value = (i >= 0 ? have.filter(function (x) { return x !== v; }) : have.concat([v])).join(", ");
      pickSync(input);
    });
    if (!input.dataset.pickBound) { input.dataset.pickBound = "1"; input.addEventListener("input", function () { pickSync(input); }); pickSync(input); }
  });

  /* S-13 시각 · 작업자 · 설비는 서버 렌더값 — 시계를 돌리지 않는다. S-14 원형 전용 시연 조각(pop.js)은 템플릿 · 이 파일에 없다. */

  /* 현황판 자동 새로고침 (G-C13) — body.ch-board 의 data-refresh-seconds 가 있을 때만 (디자이너3 board.js 와 겹치지 않게). 조작 없이 다시 그린다.
     주기마다 먼저 서버가 응답하는지(/health — 상태코드는 따지지 않는다) 보고, 응답이 오면 이 주소를 다시 그리고,
     안 오면 화면에 남아 「연결 끊김」 을 띄운 채 다시 시도한다. 낡은 화면을 새것처럼 보이게 두지 않는다. POP 은 자동 새로고침하지 않는다(S-12). */
  var refreshSeconds = parseInt(document.body.dataset.refreshSeconds || "0", 10) || 0;
  var RETRY_MS = 5000;
  function showStale() {
    var bar = document.getElementById("stale-banner");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "stale-banner"; bar.className = "stale-banner"; bar.setAttribute("role", "alert");
      document.body.appendChild(bar);
    }
    var at = document.getElementById("refreshed-at");
    bar.textContent = "서버 연결 끊김 — 다시 시도하는 중" + (at ? " (화면은 " + at.textContent + " 기준)" : "");
  }
  function refreshTick() {
    if (!window.fetch) { location.reload(); return; }
    fetch("/health", { cache: "no-store", credentials: "same-origin" })
      .then(function () { location.reload(); })
      .catch(function (err) {
        console.warn("현황판 새로고침 실패 — 서버 응답 없음", err);
        showStale();
        setTimeout(refreshTick, RETRY_MS);
      });
  }
  if (refreshSeconds > 0 && document.body.classList.contains("ch-board")) setTimeout(refreshTick, refreshSeconds * 1000);
})();
