// Orcus web dashboard — renders pipeline entries streamed from server.py.
// Each message is one audit entry:
//   { timestamp, platform, input_type, raw_input, decision, parameters,
//     confidence, policy, execution }
// On connect the server may also send { kind: "history", entries: [...] }.

const PASS = 0.50;               // mirrors min_confidence in config/config.yaml
const RING_LEN = 2 * Math.PI * 52;
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = id => document.getElementById(id);

const ICONS = {
  voice: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  gesture: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12M11 11.5v-7a1.5 1.5 0 0 1 3 0V12M14 11.5v-5a1.5 1.5 0 0 1 3 0V14c0 4-2.5 7-6.5 7S5 18.5 4 16l-1.3-3a1.5 1.5 0 0 1 2.6-1.4L8 15"/></svg>',
  keyboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 14h9"/></svg>',
};
const EXEC_CLASS = {
  success: "ok", error: "bad", unsupported: "warn", skipped: "",
  pending: "warn", confirmation_required: "warn", cancelled: "warn",
};
let pendingConfirmationEvent = null;

function requestConfirmation(event) {
  pendingConfirmationEvent = event;
  window.pendingConfirmationEvent = event;
  const modal = $("confirmModal");
  const description = $("confirmDescription");
  const proceed = $("confirmProceed");
  const cancel = $("confirmCancel");
  if (!modal || !description || !proceed || !cancel) return;

  description.textContent =
    `${String(event.decision || "This action").replace(/_/g, " ")} requires your confirmation.`;
  modal.hidden = false;
  modal.classList.add("show");

  const answer = async confirmed => {
    proceed.disabled = cancel.disabled = true;
    try {
      const response = await fetch("/api/confirm", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({confirmed}),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        description.textContent = result.detail || "Confirmation failed; the action was not executed.";
        return;
      }
      pendingConfirmationEvent = null;
      window.pendingConfirmationEvent = null;
      modal.classList.remove("show");
      setTimeout(() => { modal.hidden = true; }, 180);
    } catch {
      description.textContent = "Could not reach the controller; the action was not executed.";
    } finally {
      proceed.disabled = cancel.disabled = false;
    }
  };
  proceed.onclick = () => answer(true);
  cancel.onclick = () => answer(false);
  proceed.focus();
}

// ───────────── helpers ─────────────
function rawText(raw) {
  if (!raw) return "";
  if (raw.type === "voice") return `“${raw.text}”`;
  if (raw.type === "gesture") return raw.name.replace(/_/g, " ");
  if (raw.type === "keyboard") return raw.key;
  return JSON.stringify(raw);
}
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;   // textContent = no HTML injection
  return n;
}
function flash(node) {
  node.classList.remove("flash");
  void node.offsetWidth;                    // restart the CSS animation
  node.classList.add("flash");
}

// Futuristic "decode" effect: characters scramble, then lock in left→right.
const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789#%/<>";
function decode(node, text) {
  if (REDUCED) { node.textContent = text; return; }
  const frames = 16;
  let f = 0;
  clearInterval(node._decode);
  node._decode = setInterval(() => {
    const locked = Math.floor((f / frames) * text.length);
    let out = text.slice(0, locked);
    for (let i = locked; i < text.length; i++) {
      out += text[i] === " " ? " " : GLYPHS[(Math.random() * GLYPHS.length) | 0];
    }
    node.textContent = out;
    if (++f > frames) { clearInterval(node._decode); node.textContent = text; }
  }, 28);
}

let lastSpoken = "";
function speak(text) {
  if (!("speechSynthesis" in window) || text === lastSpoken) return;
  lastSpoken = text;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  speechSynthesis.speak(u);
}

// ───────────── pipeline stages ─────────────
function stageStates(e) {
  const laya = e.decision ? ["ok", "intent"] : ["bad", "no intent"];
  let policy = ["", "skipped"];
  if (e.policy === "allowed") policy = ["ok", "allowed"];
  else if (e.policy && e.policy.startsWith("denied")) policy = ["bad", "denied"];
  else if (e.policy && e.policy.includes("requires confirmation")) {
    policy = ["warn", "confirm"];
  }
  const execCls = EXEC_CLASS[e.execution] ?? "";
  return { input: ["ok", e.input_type], laya, policy, exec: [execCls, e.execution || "—"] };
}

function renderPipeline(e) {
  const states = stageStates(e);
  const nodes = [...document.querySelectorAll(".pipeline .node")];
  const links = [...document.querySelectorAll(".pipeline .link")];
  nodes.forEach(n => { n.className = "node"; n.querySelector(".node-state").textContent = "—"; });
  links.forEach(l => l.classList.remove("on"));

  // Light each stage in sequence so you can watch the signal travel.
  nodes.forEach((n, i) => {
    const [cls, label] = states[n.dataset.stage];
    setTimeout(() => {
      if (cls) n.classList.add(cls);
      n.querySelector(".node-state").textContent = label;
      // only draw the link forward if this stage passed
      if (cls === "ok" && links[i]) links[i].classList.add("on");
    }, REDUCED ? 0 : i * 170);
  });
}

// ───────────── main panels ─────────────
function renderCurrent(e) {
  $("platform").textContent = e.platform;
  $("modality").innerHTML = ICONS[e.input_type] || "";
  $("modalityName").textContent = `${e.input_type} input`;
  $("heard").textContent = rawText(e.raw_input);

  const dec = $("decision");
  if (e.decision) { dec.classList.remove("none"); decode(dec, e.decision); }
  else { dec.classList.add("none"); dec.textContent = "No matching action"; }

  const chips = $("params");
  chips.replaceChildren();
  for (const [k, v] of Object.entries(e.parameters || {})) chips.append(el("span", "chip", `${k}: ${v}`));

  // confidence ring
  const fill = $("ringFill");
  const note = $("confnote");
  if (e.confidence == null) {
    fill.style.strokeDashoffset = RING_LEN;
    fill.style.opacity = 0;                 // hide the round line-cap dot
    $("pct").textContent = "--";
    note.textContent = "";
  } else {
    const pct = Math.round(e.confidence * 100);
    fill.style.opacity = 1;
    fill.style.strokeDashoffset = RING_LEN * (1 - e.confidence);
    fill.classList.toggle("low", e.confidence < PASS);
    $("pct").textContent = pct + "%";
    note.replaceChildren(e.confidence >= PASS
      ? el("span", "ok", `✓ above ${Math.round(PASS * 100)}% threshold`)
      : el("span", "bad", `✗ below ${Math.round(PASS * 100)}% threshold`));
  }

  const ex = $("exec");
  ex.textContent = e.execution || "—";
  ex.className = "exec " + (EXEC_CLASS[e.execution] ?? "");
  $("policy").textContent = e.policy ? `policy › ${e.policy}` : "";
  if (e.execution === "pending" && e.policy && e.policy.includes("requires confirmation")
      ) {
    requestConfirmation(e);
  }

  renderPipeline(e);
  document.querySelectorAll("main .panel").forEach(flash);

  // Spoken confirmation only for real, successful actions (accessibility).
  if (e.execution === "success" && e.decision) speak(e.decision.replace(/_/g, " "));
}

// ───────────── session stats + log ─────────────
const stats = { total: 0, allowed: 0, blocked: 0, confSum: 0, confN: 0, voice: 0, gesture: 0, keyboard: 0 };

function renderStats(e) {
  stats.total++;
  if (e.execution === "success") stats.allowed++;
  else stats.blocked++;
  if (e.confidence != null) { stats.confSum += e.confidence; stats.confN++; }
  if (e.input_type in stats) stats[e.input_type]++;

  $("sTotal").textContent = stats.total;
  $("sAllowed").textContent = stats.allowed;
  $("sBlocked").textContent = stats.blocked;
  $("sAvg").textContent = stats.confN ? Math.round((stats.confSum / stats.confN) * 100) + "%" : "--";
  for (const m of ["voice", "gesture", "keyboard"]) {
    const key = m[0].toUpperCase() + m.slice(1);
    $("n" + key).textContent = stats[m];
    $("b" + key).style.width = (stats.total ? (stats[m] / stats.total) * 100 : 0) + "%";
  }
}

// Short outcome label for the log badge: why it ran or didn't.
function outcome(e) {
  if (e.execution === "success") return ["ok", "done"];
  if (e.execution === "pending") return ["warn", "confirm"];
  if (e.execution === "cancelled") return ["warn", "cancelled"];
  if (e.policy === "no_intent") return ["warn", "no match"];
  if (e.policy && e.policy.startsWith("denied")) return ["bad", "denied"];
  return [EXEC_CLASS[e.execution] || "muted", e.execution || "—"];
}

function addLog(e) {
  const li = el("li");

  const ico = el("span", "ico");
  ico.innerHTML = ICONS[e.input_type] || "";
  li.append(ico);

  const what = el("span", "what");
  const act = el("span", "act", "→ ");
  act.append(el("b", null, e.decision || "no action"));
  what.append(el("span", null, rawText(e.raw_input)), act);
  li.append(what);

  const side = el("span", "side");
  const [cls, label] = outcome(e);
  const t = e.timestamp ? new Date(e.timestamp) : new Date();
  side.append(el("span", "badge " + cls, label), el("time", null, t.toLocaleTimeString([], { hour12: false })));
  li.append(side);

  const log = $("log");
  log.prepend(li);
  while (log.children.length > 30) log.lastChild.remove();
}

// ───────────── websocket ─────────────
function handle(e, { live = true } = {}) {
  renderStats(e);
  addLog(e);
  if (live) renderCurrent(e);
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    $("conn").classList.add("live");
    $("status").textContent = "Listening";
  };
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.kind === "history") {
      const entries = msg.entries || [];
      entries.forEach((e, i) => handle(e, { live: i === entries.length - 1 }));
    } else {
      handle(msg);
    }
  };
  ws.onclose = () => {
    $("conn").classList.remove("live");
    $("status").textContent = "Reconnecting…";
    setTimeout(connect, 1000);
  };
}

// ───────────── starfield background ─────────────
function starfield() {
  const c = $("stars");
  const ctx = c.getContext("2d");
  let w, h, stars;
  const COLORS = ["34,228,255", "139,92,246", "232,238,255"];

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = c.width = innerWidth * dpr;
    h = c.height = innerHeight * dpr;
    const count = Math.round((innerWidth * innerHeight) / 9000);
    stars = Array.from({ length: count }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      r: (Math.random() * 1.3 + 0.3) * dpr,
      vx: (Math.random() - 0.5) * 0.08 * dpr, vy: (Math.random() - 0.5) * 0.08 * dpr,
      tw: Math.random() * Math.PI * 2,
      col: COLORS[(Math.random() * COLORS.length) | 0],
    }));
  }

  function frame() {
    ctx.clearRect(0, 0, w, h);
    const linkDist = 110 * (w / innerWidth);
    for (let i = 0; i < stars.length; i++) {
      const s = stars[i];
      s.x = (s.x + s.vx + w) % w;
      s.y = (s.y + s.vy + h) % h;
      s.tw += 0.02;
      ctx.fillStyle = `rgba(${s.col},${0.45 + Math.sin(s.tw) * 0.35})`;
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
      // faint "constellation" lines between nearby stars
      for (let j = i + 1; j < stars.length; j++) {
        const o = stars[j], dx = s.x - o.x, dy = s.y - o.y, d = Math.hypot(dx, dy);
        if (d < linkDist) {
          ctx.strokeStyle = `rgba(34,228,255,${0.12 * (1 - d / linkDist)})`;
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(o.x, o.y); ctx.stroke();
        }
      }
    }
    if (!REDUCED) requestAnimationFrame(frame);
  }

  resize();
  addEventListener("resize", resize);
  frame();
}

// Threshold tick on the confidence ring. The tick is drawn at the top of the
// (unrotated) SVG, i.e. 270° from where the stroke starts, hence the +90.
$("ringThreshold").style.transform = `rotate(${PASS * 360 + 90}deg)`;
starfield();
connect();
