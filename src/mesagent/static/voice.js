/* MES AI Agent 음성 질의 · 답변 (D-48) — 브라우저 내장 음성 인식(SpeechRecognition) · 음성 합성(speechSynthesis)만 쓴다.
   · 「로뎀」 이라고 부른 말만 질문으로 보낸다. 부르지 않은 말은 화면에 "답하지 않음" 만 보인다.
   · 「로뎀」 만 부르면 "네, 말씀하세요" 라고 답하고 8초 동안 다음 말을 질문으로 받는다.
   · 답을 읽는 동안에는 마이크를 멈춘다(제 목소리를 다시 듣지 않게). 다 읽으면 다시 듣는다.
   · 듣기 켜짐 여부는 이 탭(sessionStorage)에만 둔다 — 화면이 다시 그려져도 이어서 듣는다. */
(() => {
  const root = document.querySelector("[data-agent]");
  if (!root) return;
  const form = root.querySelector("form.ag-form");
  const ta = form.querySelector("textarea");
  const voiceIn = form.querySelector("input[name=voice]");
  const btnMic = root.querySelector("[data-mic]");
  const btnSpeak = root.querySelector("[data-speak]");
  const chkRead = root.querySelector("[data-autoread]");
  const st = root.querySelector("[data-voice-status]");
  const heard = root.querySelector("[data-heard]");
  const wakeName = root.dataset.wakeName || "로뎀";
  let wakeRe;
  try { wakeRe = new RegExp(root.dataset.wake, "i"); } catch (e) { wakeRe = new RegExp("^\\s*" + wakeName, "i"); }

  const KEY = "mes.agent.voice", READ = "mes.agent.read";
  const ss = {
    get(k, d) { try { const v = sessionStorage.getItem(k); return v === null ? d : v === "on"; } catch (e) { return d; } },
    set(k, v) { try { sessionStorage.setItem(k, v ? "on" : "off"); } catch (e) { /* 사생활 모드 — 이 화면에서만 */ } },
  };
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  let rec = null, listening = false, speaking = false, armedUntil = 0, sending = false;
  let wanted = ss.get(KEY, false);
  if (chkRead) chkRead.checked = ss.get(READ, true);

  function status(text, state) { st.textContent = text; st.dataset.state = state || ""; }
  function render() {
    btnMic.setAttribute("aria-pressed", wanted ? "true" : "false");
    btnMic.classList.toggle("on", wanted);
    btnMic.querySelector("span").textContent = wanted ? "음성 듣기 끄기" : "음성 질의 켜기";
  }
  function koVoice() { return (synth.getVoices() || []).find((v) => (v.lang || "").toLowerCase().startsWith("ko")); }

  function speak(text, then) {
    if (!synth || !text) { if (then) then(); return; }
    stopRec();
    speaking = true;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR"; u.rate = 1.05;
    const v = koVoice(); if (v) u.voice = v;
    u.onend = u.onerror = () => { speaking = false; if (then) then(); };
    status("답을 읽는 중…", "speak");
    synth.speak(u);
  }

  function submit(text) {
    sending = true;
    ta.value = text;
    voiceIn.value = "1";
    stopRec();
    status("질문을 보냈습니다 — 에이전트가 답을 찾는 중…", "busy");
    if (form.requestSubmit) form.requestSubmit(); else form.submit();
  }

  function handle(raw) {
    const text = (raw || "").trim();
    if (!text || sending) return;
    heard.textContent = "들은 말: " + text;
    const m = text.match(wakeRe);
    if (m) {
      const rest = text.slice(m[0].length).trim();
      if (rest) { submit(text); return; }
      armedUntil = Date.now() + 8000;
      speak("네, 말씀하세요.", () => { startRec(); status("말씀하세요 — 8초 안에 질문하면 답합니다", "armed"); });
      return;
    }
    if (Date.now() < armedUntil) { armedUntil = 0; submit(wakeName + ", " + text); return; }
    status("「" + wakeName + "」 라고 부르지 않아 답하지 않습니다", "ignored");
  }

  function startRec() {
    if (!SR || !wanted || speaking || listening || sending) return;
    rec = new SR();
    rec.lang = "ko-KR"; rec.continuous = true; rec.interimResults = true;
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) handle(r[0].transcript); else heard.textContent = "듣는 중: " + r[0].transcript;
      }
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        wanted = false; ss.set(KEY, false); render();
        status("마이크 권한이 없습니다 — 주소창의 마이크 권한을 허용한 뒤 다시 켭니다", "err");
      } else if (e.error === "network") {
        status("음성 인식 서비스에 연결하지 못했습니다(브라우저의 인식 서버) — 글로 질문해 주세요", "err");
      }
    };
    rec.onend = () => { listening = false; if (wanted && !speaking && !sending) setTimeout(startRec, 400); };
    try {
      rec.start(); listening = true;
      if (Date.now() >= armedUntil) status("듣는 중 — 「" + wakeName + "」 라고 부른 뒤 질문하세요", "on");
    } catch (e) { listening = false; }
  }

  function stopRec() {
    if (!rec) return;
    rec.onend = null; listening = false;
    try { rec.abort(); } catch (e) { /* 이미 멈춤 */ }
    rec = null;
  }

  // ── 버튼 ──
  if (!SR) {
    btnMic.disabled = true;
    status("이 브라우저는 음성 인식을 지원하지 않습니다 — Chrome · Edge 에서 쓰세요. 답 읽기는 됩니다", "err");
  } else if (!window.isSecureContext) {
    btnMic.disabled = true;
    status("음성 인식은 HTTPS 또는 이 PC(localhost)에서만 켜집니다", "err");
  } else {
    status(wanted ? "듣는 중…" : "음성 질의가 꺼져 있습니다 — 켜면 「" + wakeName + "」 호출을 기다립니다", wanted ? "on" : "");
  }
  render();
  btnMic.addEventListener("click", () => {
    wanted = !wanted; ss.set(KEY, wanted); render();
    if (wanted) { startRec(); } else { stopRec(); armedUntil = 0; status("음성 질의를 껐습니다", ""); }
  });
  if (chkRead) chkRead.addEventListener("change", () => ss.set(READ, chkRead.checked));
  if (btnSpeak) btnSpeak.addEventListener("click", () => speak(root.dataset.speech || "", startRec));
  if (!synth && btnSpeak) btnSpeak.disabled = true;
  form.addEventListener("submit", () => { if (!voiceIn.value) stopRec(); });

  // ── 화면이 다시 그려진 뒤: 음성으로 물었거나 '답 읽기' 가 켜져 있으면 읽고, 다시 듣는다 ──
  const speech = root.dataset.speech || "";
  const fromVoice = root.dataset.voiceMode === "1";
  if (speech && synth && (fromVoice || (chkRead && chkRead.checked && wanted))) {
    let done = false;
    const go = () => { if (done) return; done = true; synth.onvoiceschanged = null; speak(speech, startRec); };
    if (synth.getVoices().length) go(); else { synth.onvoiceschanged = go; setTimeout(go, 600); }
  } else {
    startRec();
  }
})();
