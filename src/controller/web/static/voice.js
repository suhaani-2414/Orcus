// Orcus voice control — click (or Spacebar) to START recording, click again to
// STOP and transcribe. Toggle, not hold: a hold-to-talk click on localhost
// records almost nothing (start resolves in ms), so toggle is robust and clear.
// Recording still lasts only as long as you leave it on, so the clip stays short.
// Results arrive over the existing WebSocket (handled by app.js); this file only
// drives the button, so it doesn't collide with the dashboard's app.js.
(function () {
  const MAX_SECONDS = 12;  // safety auto-stop so it can't record forever

  const btn = document.createElement("button");
  btn.id = "mic";
  btn.type = "button";
  btn.setAttribute("aria-label", "Click to start talking, click again to stop");
  Object.assign(btn.style, {
    position: "fixed", right: "24px", bottom: "24px", zIndex: "60",
    padding: "14px 24px", fontSize: "1.05rem", fontWeight: "700",
    color: "#04121a", background: "linear-gradient(135deg,#22e4ff,#8b5cf6)",
    border: "none", borderRadius: "999px", cursor: "pointer",
    fontFamily: "inherit", boxShadow: "0 6px 26px rgba(34,228,255,.45)",
    userSelect: "none",
  });

  const hint = document.createElement("div");
  Object.assign(hint.style, {
    position: "fixed", right: "24px", bottom: "78px", zIndex: "60",
    maxWidth: "300px", textAlign: "right", fontFamily: "monospace",
    fontSize: ".82rem", color: "#8b949e", pointerEvents: "none",
  });

  document.body.append(btn, hint);

  let state = "idle";  // idle | recording | busy
  let autostop = null;

  function paint() {
    if (state === "recording") {
      btn.textContent = "● Recording — click to stop";
      btn.style.background = "#f85149";
    } else if (state === "busy") {
      btn.textContent = "… transcribing";
      btn.style.background = "#8b949e";
    } else {
      btn.textContent = "🎤 Click to talk";
      btn.style.background = "linear-gradient(135deg,#22e4ff,#8b5cf6)";
    }
  }

  async function start() {
    state = "busy"; paint();
    hint.textContent = "starting…";
    try {
      const d = await (await fetch("/listen/start", { method: "POST" })).json();
      if (!d.ok) { hint.textContent = d.error || "mic error"; state = "idle"; paint(); return; }
      state = "recording"; paint();
      hint.textContent = "recording — speak, then click to stop";
      autostop = setTimeout(stop, MAX_SECONDS * 1000);
    } catch { hint.textContent = "start failed"; state = "idle"; paint(); }
  }

  async function stop() {
    if (autostop) { clearTimeout(autostop); autostop = null; }
    state = "busy"; paint();
    hint.textContent = "transcribing…";
    try {
      const d = await (await fetch("/listen/stop", { method: "POST" })).json();
      hint.textContent = d.ok ? `heard: "${d.transcript}"` : (d.error || "nothing transcribed");
    } catch { hint.textContent = "stop failed"; }
    state = "idle"; paint();
  }

  function toggle() {
    if (state === "idle") start();
    else if (state === "recording") stop();
    // ignore clicks while busy
  }

  paint();
  btn.addEventListener("click", toggle);
  addEventListener("keydown", e => {
    if (e.code === "Space" && !e.repeat && !/input|textarea/i.test(e.target.tagName)) {
      e.preventDefault();
      toggle();
    }
  });
})();
