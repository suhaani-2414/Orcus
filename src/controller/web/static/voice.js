// Orcus voice control — hold-to-talk mic button + spacebar.
// Recording lasts only while you hold (press → /listen/start, release →
// /listen/stop), so the clip is as short as your command — cutting the old
// fixed 4s recording and the upload/STT time that scales with clip length.
// Results arrive over the existing WebSocket (handled by app.js); this file
// only drives the button, so it doesn't collide with the dashboard's app.js.
(function () {
  const btn = document.createElement("button");
  btn.id = "mic";
  btn.type = "button";
  btn.setAttribute("aria-label", "Hold to speak a command");
  btn.textContent = "🎤 Hold to talk";
  Object.assign(btn.style, {
    position: "fixed", right: "24px", bottom: "24px", zIndex: "60",
    padding: "14px 24px", fontSize: "1.05rem", fontWeight: "700",
    color: "#04121a", background: "linear-gradient(135deg,#22e4ff,#8b5cf6)",
    border: "none", borderRadius: "999px", cursor: "pointer",
    fontFamily: "inherit", boxShadow: "0 6px 26px rgba(34,228,255,.45)",
    userSelect: "none", touchAction: "none",
  });

  const hint = document.createElement("div");
  Object.assign(hint.style, {
    position: "fixed", right: "24px", bottom: "78px", zIndex: "60",
    maxWidth: "300px", textAlign: "right", fontFamily: "monospace",
    fontSize: ".82rem", color: "#8b949e", pointerEvents: "none",
  });

  document.body.append(btn, hint);

  let recording = false;
  let starting = false;

  async function start() {
    if (recording || starting) return;
    starting = true;
    btn.textContent = "● Listening…";
    btn.style.background = "#f85149";
    hint.textContent = "listening — release to send";
    try {
      const r = await fetch("/listen/start", { method: "POST" });
      const d = await r.json();
      if (!d.ok) { hint.textContent = d.error || "mic error"; reset(); }
      else recording = true;
    } catch { hint.textContent = "start failed"; reset(); }
    finally { starting = false; }
  }

  async function stop() {
    if (!recording) return;
    recording = false;
    btn.textContent = "… transcribing";
    hint.textContent = "transcribing…";
    try {
      const r = await fetch("/listen/stop", { method: "POST" });
      const d = await r.json();
      hint.textContent = d.ok ? `heard: "${d.transcript}"` : (d.error || "nothing transcribed");
    } catch { hint.textContent = "stop failed"; }
    finally { reset(); }
  }

  function reset() {
    btn.textContent = "🎤 Hold to talk";
    btn.style.background = "linear-gradient(135deg,#22e4ff,#8b5cf6)";
  }

  // Mouse / touch hold
  btn.addEventListener("mousedown", start);
  btn.addEventListener("touchstart", e => { e.preventDefault(); start(); });
  addEventListener("mouseup", stop);
  btn.addEventListener("touchend", e => { e.preventDefault(); stop(); });

  // Spacebar hold-to-talk (ignore auto-repeat and typing fields)
  addEventListener("keydown", e => {
    if (e.code === "Space" && !e.repeat && !/input|textarea/i.test(e.target.tagName)) {
      e.preventDefault(); start();
    }
  });
  addEventListener("keyup", e => {
    if (e.code === "Space" && !/input|textarea/i.test(e.target.tagName)) {
      e.preventDefault(); stop();
    }
  });
})();
