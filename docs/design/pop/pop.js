/* 현장 POP 시연 스크립트 — 디자이너2.
   실제 구현은 static/app.js(아키텍트 소유) 하나다. 여기 번호(S-nn)는 docs/design/README.md "POP · 모바일" 절의 동작 사양 번호와 같다.
   외부 라이브러리 0. 오류를 삼키지 않는다(console 에 그대로). `data-demo` 가 붙은 폼만 서버 없이 흉내 낸다 — 템플릿으로 옮길 때 data-demo 는 지운다. */
(function () {
  "use strict";

  var scan = document.querySelector("[data-scan]");           /* S-01 화면에 하나 */
  var layer = document.getElementById("popup-layer");
  var scans = document.querySelectorAll("[data-scan]");
  if (scans.length > 1) console.error("data-scan 이 " + scans.length + "개 — 화면에 하나여야 한다 (S-01)");

  function popupOpen() { return !!layer && !layer.hidden; }

  /* S-03 다른 입력칸·버튼을 쓰는 중이 아니면(=idle) 스캔칸이 포커스를 가진다 */
  function idle(a) {
    return !a || a === document.body || a === scan || (!!layer && layer.contains(a)) ||
      !/^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/.test(a.tagName);
  }
  function focusScan() {
    if (scan && !scan.disabled && document.activeElement !== scan && idle(document.activeElement)) scan.focus();
  }

  if (scan) {
    focusScan();                                                          /* S-02 열리면 포커스 */
    document.addEventListener("click", function () { setTimeout(focusScan, 0); });   /* S-03 빈 곳을 눌러도 복귀 */
    window.addEventListener("focus", focusScan);                          /* S-04 창이 다시 활성화되면 복귀 */
  }

  /* 알림 팝업 — 쓰기 결과 · 422. 떠 있어도 다음 스캔을 막지 않는다 */
  function popup(title, body, fields, kind) {
    if (!layer) { console.warn("popup-layer 없음:", title, body); return; }
    layer.querySelector(".popup").classList.toggle("ok", kind === "ok");
    document.getElementById("popup-title").textContent = title || "알림";
    var box = document.getElementById("popup-body");
    box.innerHTML = "";
    var p = document.createElement("p"); p.textContent = body || ""; box.appendChild(p);
    if (fields && fields.length) {
      var ul = document.createElement("ul");
      fields.forEach(function (f) {
        var li = document.createElement("li");
        li.textContent = (f.label || f.name || "입력") + " — " + (f.reason || "");
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }
    layer.hidden = false;
    if (scan) { focusScan(); return; }                                    /* S-06 포커스는 「확인」이 아니라 스캔칸에 */
    var ok = layer.querySelector("[data-popup-close]");
    if (ok) ok.focus();
  }
  function closePopup() {
    if (!layer) return;
    layer.hidden = true;
    setTimeout(focusScan, 0);                                             /* S-08 닫으면 스캔칸으로 */
  }
  if (layer) {
    layer.querySelectorAll("[data-popup-close]").forEach(function (b) { b.addEventListener("click", closePopup); });
    layer.addEventListener("click", function (e) { if (e.target === layer) closePopup(); });
    document.addEventListener("keydown", function (e) {
      if (!popupOpen()) return;
      if (e.key === "Escape") { closePopup(); return; }
      if (!scan) return;
      var a = document.activeElement;
      if (e.key === "Enter") {                                            /* S-07 빈 스캔칸의 Enter 는 닫기만. 글자가 있으면 그 스캔을 보낸다 */
        if ((a === scan && scan.value === "") || !a || a === document.body) { e.preventDefault(); closePopup(); }
        return;
      }
      if (e.key && e.key.length === 1 && e.key !== " " && !e.ctrlKey && !e.metaKey && !e.altKey && idle(a)) {
        closePopup();                                                     /* S-07 첫 글자 = 다음 스캔의 시작. 글자는 스캔칸에 들어간다 */
      }
    }, true);
  }
  window.popPopup = popup;

  /* S-09 서버가 303 뒤에 실어 보낸 flash → 알림 */
  var flashEl = document.getElementById("flash-data");
  if (flashEl) {
    try {
      var f = JSON.parse(flashEl.textContent || "{}");
      if (f && f.message) popup(f.title || "알림", f.message, f.fields, f.kind);
    } catch (e) { console.warn("flash 파싱 실패", e); }
  }

  /* ── 아래는 시연 전용 (템플릿에 옮기지 않는다) ── */
  document.querySelectorAll("[data-demo-popup]").forEach(function (b) {
    b.addEventListener("click", function () {
      var fields = [];
      try { fields = JSON.parse(b.dataset.fields || "[]"); } catch (e) { console.warn(e); }
      popup(b.dataset.title || "알림", b.dataset.demoPopup, fields, b.dataset.kind);
    });
  });
  document.querySelectorAll("form[data-demo]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = form.querySelector("[data-scan]") || form.querySelector("input");
      var banner = document.getElementById("scan-result");
      if (!banner) return;
      var v = input ? input.value : "";
      banner.className = "result ok";
      banner.innerHTML = "";
      var p = document.createElement("p"); p.className = "result-msg";
      p.textContent = (v ? v + " " : "") + "처리했습니다 (시연)";
      banner.appendChild(p);
      banner.hidden = false;
      if (input && input.hasAttribute("data-scan")) input.value = "";    /* S-05 스캔 1회 = 1건, 보내면 비운다 */
      setTimeout(function () { banner.className = "result"; p.textContent = "다음 바코드를 스캔한다"; }, 1000);  /* S-10 초록 1초 */
      focusScan();
    });
  });
})();
