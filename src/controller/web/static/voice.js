// Voice controls live in the header so they cannot cover dashboard content.
(function () {
  const MAX_SECONDS = 12;
  const btn = document.getElementById("mic");
  const alwaysBtn = document.getElementById("alwaysListen");
  const hint = document.getElementById("voiceHint");
  if (!btn || !alwaysBtn || !hint) return;

  let state = "idle";
  let autostop = null;
  let alwaysOn = false;

  function paint() {
    btn.textContent = state === "recording" ? "Stop recording"
      : state === "busy" ? "Transcribing…" : "Talk";
    btn.disabled = state === "busy";
    alwaysBtn.textContent = alwaysOn ? "Stop listening" : "Always listen";
    alwaysBtn.classList.toggle("voice-active", alwaysOn);
  }

  async function start() {
    state = "busy"; paint(); hint.textContent = "starting microphone…";
    try {
      const result = await (await fetch("/listen/start", {method: "POST"})).json();
      if (!result.ok) throw new Error(result.error || "microphone unavailable");
      state = "recording"; paint();
      hint.textContent = "speak, then press Stop";
      autostop = setTimeout(stop, MAX_SECONDS * 1000);
    } catch (error) {
      hint.textContent = error.message;
      state = "idle"; paint();
    }
  }

  async function stop() {
    if (autostop) clearTimeout(autostop);
    autostop = null;
    state = "busy"; paint(); hint.textContent = "transcribing…";
    try {
      const result = await (await fetch("/listen/stop", {method: "POST"})).json();
      hint.textContent = result.ok ? `heard: "${result.transcript}"` : (result.error || "nothing heard");
    } catch {
      hint.textContent = "transcription request failed";
    }
    state = "idle"; paint();
  }

  async function toggleAlwaysOn() {
    alwaysBtn.disabled = true;
    const endpoint = alwaysOn ? "/api/voice/always-on/stop" : "/api/voice/always-on/start";
    try {
      const result = await (await fetch(endpoint, {method: "POST"})).json();
      if (result.error || (!alwaysOn && !result.active)) {
        throw new Error(result.error || "always-on listener did not start");
      }
      alwaysOn = result.active;
      hint.textContent = alwaysOn
        ? `say "${result.wake_word || "orcus"}" followed by a command`
        : "always-on voice stopped";
    } catch (error) {
      hint.textContent = error.message;
    } finally {
      alwaysBtn.disabled = false;
      paint();
    }
  }

  async function syncAlwaysOn() {
    try {
      const result = await (await fetch("/api/voice/always-on")).json();
      alwaysOn = result.active;
      if (alwaysOn) hint.textContent = `say "${result.wake_word}" followed by a command`;
      else if (result.error) hint.textContent = result.error;
      paint();
    } catch {
      hint.textContent = "voice status unavailable";
    }
  }

  btn.addEventListener("click", () => {
    if (state === "idle") start();
    else if (state === "recording") stop();
  });
  alwaysBtn.addEventListener("click", toggleAlwaysOn);
  addEventListener("keydown", event => {
    if (event.code === "Space" && !event.repeat && !/input|textarea|select/i.test(event.target.tagName)) {
      event.preventDefault();
      if (state === "idle") start();
      else if (state === "recording") stop();
    }
  });
  paint();
  syncAlwaysOn();
})();
