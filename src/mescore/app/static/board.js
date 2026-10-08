/* 현황판(KPI-01) 폴링 — 디자이너3. docs/design/board/board.html 의 스크립트에서 [원형 전용] 블록(데모 JSON · #state= 해시)만 뺐다.
   templates/kpi/board.html 만 읽는다(base.html · app.js 를 쓰지 않는 벽걸이 전용 문서라 app.js 의 전체 새로고침 폴링과 겹치지 않는다).
   · 첫 렌더는 서버. 그 뒤 body[data-refresh-seconds] 초마다 body[data-poll-url] 을 Accept: application/json 으로 받아 [data-key] 글자만 바꾼다.
   · 실패(503 · 네트워크 · JSON 오류)면 html[data-state="stale"] + 머리글 "갱신 실패 HH:MM, 재시도 중". 마지막 값은 지우지 않고 폴링은 계속(api-contract.md §2).
   · 값 null → body[data-empty](미수집) · 목표 없음 → data-empty 속성의 글자(미확정). 외부 라이브러리 0. */
(function () {
  "use strict";
  var body = document.body, root = document.documentElement;
  var URL = body.dataset.pollUrl, INTERVAL = (parseInt(body.dataset.refreshSeconds || "5", 10) || 5) * 1000, EMPTY = body.dataset.empty || "미수집";
  if (!URL || !window.fetch) return;

  function get(o, p) { return p.split(".").reduce(function (a, k) { return a == null ? undefined : a[k]; }, o); }
  function hhmm(d, s) { var z = function (n) { return (n < 10 ? "0" : "") + n; }; return z(d.getHours()) + ":" + z(d.getMinutes()) + (s ? ":" + z(d.getSeconds()) : ""); }
  function fmt(v, el) {
    if (v == null || v === "") return el.dataset.empty || EMPTY;
    if (typeof v === "number") { var d = el.dataset.digits == null ? 1 : +el.dataset.digits; return v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d }); }
    return String(v);
  }
  /* 상태 판정: 목표값(data-target-key) 이 있으면 값 ≥ 목표 → good, 목표의 95% 이상 → warn, 그 밖 critical.
     data-good/data-warn 고정 문턱도 같은 규칙. data-zero-good 은 0 이면 good, 1 이상이면 critical(건수형). 목표가 없으면 상태색 없음. */
  function status(el, scope) {
    var v = get(scope, el.dataset.statusKey);
    if (v == null) { el.removeAttribute("data-status"); return; }
    if (el.hasAttribute("data-zero-good")) { el.dataset.status = v > 0 ? "critical" : "good"; return; }
    var tgt = el.dataset.targetKey ? get(scope, el.dataset.targetKey) : (el.dataset.good != null ? +el.dataset.good : null);
    if (tgt == null) { if (typeof v === "string") el.dataset.status = v; else el.removeAttribute("data-status"); return; }
    var warn = el.dataset.warn != null ? +el.dataset.warn : tgt * 0.95;
    el.dataset.status = v >= tgt ? "good" : v >= warn ? "warn" : "critical";
  }
  function fill(scope, data) {
    scope.querySelectorAll("[data-key]").forEach(function (el) {
      if (el.dataset.key.charAt(0) === "_") return;            // _as_of · _failed_at 는 화면 쪽 시각
      var v = get(data, el.dataset.key);
      el.textContent = fmt(v, el); el.classList.toggle("is-empty", v == null || v === "");
    });
    scope.querySelectorAll("[data-width-key]").forEach(function (el) {
      var v = get(data, el.dataset.widthKey); var t = el.tagName === "I" ? el : el.querySelector("i");
      if (t) t.style.width = (v == null ? 0 : Math.max(0, Math.min(100, v))) + "%";
    });
    scope.querySelectorAll("[data-status-key]").forEach(function (el) { status(el, data); });
    scope.querySelectorAll("[data-state-key]").forEach(function (el) { var v = get(data, el.dataset.stateKey); if (v == null) el.removeAttribute("data-state"); else el.dataset.state = v; });
  }
  function lists(data) {
    document.querySelectorAll("[data-list]").forEach(function (box) {
      var rows = get(data, box.dataset.list) || [], tpl = box.querySelector("template");
      box.querySelectorAll("[data-row]").forEach(function (r) { r.remove(); });
      rows.slice(0, +(box.dataset.max || 99)).forEach(function (row) {
        var n = tpl.content.firstElementChild.cloneNode(true); n.setAttribute("data-row", ""); fill(n, row); box.appendChild(n);
      });
      if (!rows.length) {                                      // 0건 → `미수집` 한 줄 (빈 표를 두지 않는다 · G-C11)
        var e = document.createElement(box.tagName === "UL" ? "li" : "tr");
        e.setAttribute("data-row", ""); e.className = "is-empty";
        if (box.tagName === "UL") { e.textContent = EMPTY; }
        else { var td = document.createElement("td"); td.className = "is-empty"; td.colSpan = +(box.dataset.cols || 3); td.textContent = EMPTY; e.appendChild(td); }
        box.appendChild(e);
      }
    });
  }
  function bars(data) {                                        // 인라인 SVG 막대 — 시간대별 실적. 막대 하나 = 한 시간, 현재 시간은 진한색
    document.querySelectorAll("svg[data-bars]").forEach(function (svg) {
      var rows = get(data, svg.dataset.bars) || [], g = svg.querySelector("g.b"), t = svg.querySelector("g.t");
      var W = 560, H = 126, n = Math.max(rows.length, 1), slot = W / n, bw = Math.max(8, slot - 10), max = rows.reduce(function (m, r) { return Math.max(m, r.qty || 0); }, 0) || 1;
      var nowH = new Date().getHours(); g.innerHTML = ""; t.innerHTML = "";
      rows.forEach(function (r, i) {
        var h = Math.round((r.qty || 0) / max * 100), x = Math.round(i * slot + (slot - bw) / 2);
        g.insertAdjacentHTML("beforeend", '<rect x="' + x + '" y="' + (H - h) + '" width="' + Math.round(bw) + '" height="' + h + '" rx="4"' + (+r.hour === nowH ? ' class="now"' : "") + "/>");
        if (i % 4 === 0 || i === rows.length - 1) t.insertAdjacentHTML("beforeend", '<text x="' + Math.round(x + bw / 2) + '" y="148" text-anchor="middle">' + String(r.hour).replace(/[<>&]/g, "") + "</text>");
      });
    });
  }
  function apply(data) {
    fill(document, data); lists(data); bars(data);
    root.dataset.state = "ok";
    var at = document.querySelector('[data-key="_as_of"]'); if (at) at.textContent = hhmm(new Date(), true);
  }
  function fail(err) {                                         // 화면은 남긴다. 마지막 값 유지 + 실패 시각 표시. 폴링은 계속
    console.warn("현황판 갱신 실패 — 마지막 값 유지, 재시도", err);
    root.dataset.state = "stale";
    var at = document.querySelector('[data-key="_failed_at"]'); if (at) at.textContent = hhmm(new Date());
  }
  function tick() {
    fetch(URL, { headers: { "Accept": "application/json" }, cache: "no-store", credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(apply).catch(fail)
      .then(function () { setTimeout(tick, INTERVAL); });
  }
  /* 첫 화면의 시간대별 막대는 서버가 넣어 준 JSON(#board-by-hour)으로 그린다 — 더미 막대 없음 */
  var seed = document.getElementById("board-by-hour");
  if (seed) { try { bars({ production: { by_hour: JSON.parse(seed.textContent || "[]") } }); } catch (e) { console.warn("by_hour 파싱 실패", e); } }
  setTimeout(tick, INTERVAL);
})();
