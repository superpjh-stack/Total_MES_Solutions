/* 데이터 허브 실시간 화면 — 5초마다 /hub/realtime/live 를 읽어 숫자 칸(data-live)만 바꾼다. 탭이 숨으면 멈춘다. */
(() => {
  const root = document.querySelector("[data-hub-live]");
  if (!root) return;
  const stat = root.querySelector("[data-live-status]");
  const fmt = (v) => (typeof v === "number" ? v.toLocaleString("ko-KR") : (v ? String(v).replace("T", " ").slice(0, 19) : "—"));
  const pick = (o, path) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
  let timer = null;
  async function tick() {
    if (document.hidden) return;
    try {
      const r = await fetch("/hub/realtime/live", { headers: { Accept: "application/json" }, credentials: "same-origin" });
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      root.querySelectorAll("[data-live]").forEach((el) => { el.textContent = fmt(pick(d, el.dataset.live)); });
      if (stat) { stat.dataset.state = "on"; stat.textContent = "실시간 · " + new Date().toLocaleTimeString("ko-KR"); }
    } catch (e) {
      if (stat) { stat.dataset.state = ""; stat.textContent = "새로 고침 실패 — 다음 주기에 다시 시도"; }
    }
  }
  timer = setInterval(tick, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
  window.addEventListener("beforeunload", () => clearInterval(timer));
})();
