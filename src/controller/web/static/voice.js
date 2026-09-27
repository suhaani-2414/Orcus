// Orcus voice control — a floating mic button that triggers server-side
// record → ElevenLabs Scribe → Laya pipeline. Results arrive via the existing
// WebSocket (handled by app.js), so this file only drives the button + hint.
// Kept as a separate file so it doesn't collide with the dashboard's app.js.
(function () {
  const btn = document.createElement("button");
  btn.id = "mic";
  btn.type = "button";
  btn.setAttribute("aria-label", "Speak a command");
  btn.textContent = "🎤 Speak";
  Object.assign(btn.style, {
    position: "fixed", right: "24px", bottom: "24px", zIndex: "60",
    padding: "14px 24px", fontSize: "1.05rem", fontWeight: "700",
    color: "#04121a", background: "linear-gradient(135deg,#22e4ff,#8b5cf6)",
    border: "none", borderRadius: "999px", cursor: "pointer",
    fontFamily: "inherit", boxShadow: "0 6px 26px rgba(34,228,255,.45)",
    transition: "transform .1s ease",
  });

  const hint = document.createElement("div");
  Object.assign(hint.style, {
    position: "fixed", right: "24px", bottom: "78px", zIndex: "60",
    maxWidth: "280px", textAlign: "right", fontFamily: "monospace",
    fontSize: ".82rem", color: "#8b949e", pointerEvents: "none",
  });

  document.body.append(btn, hint);

  let busy = false;
  async function listen() {
    if (busy) return;
    busy = true;
    btn.textContent = "● Listening…";
    btn.style.background = "#f85149";
    hint.textContent = "recording ~4s — speak now";
    try {
      const res = await fetch("/listen", { method: "POST" });
      const data = await res.json();
      hint.textContent = data.ok
        ? `heard: "${data.transcript}"`
        : (data.error || "nothing transcribed");
    } catch {
      hint.textContent = "voice request failed";
    } finally {
      busy = false;
      btn.textContent = "🎤 Speak";
      btn.style.background = "linear-gradient(135deg,#22e4ff,#8b5cf6)";
    }
  }

  btn.addEventListener("click", listen);
  // Spacebar as push-to-talk (ignore when typing in a field).
  addEventListener("keydown", e => {
    if (e.code === "Space" && !/input|textarea/i.test(e.target.tagName)) {
      e.preventDefault();
      listen();
    }
  });
})();
