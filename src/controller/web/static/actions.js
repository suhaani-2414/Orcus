// Orcus actions modal — lists every action Laya is allowed to choose, with the
// gesture, key and example phrase that triggers it. Data comes from
// /api/actions (the real registry + config), so it can't drift from the policy
// layer. Kept in its own file so it doesn't collide with app.js or voice.js.
(function () {
  const modal = document.getElementById("actionsModal");
  const body = document.getElementById("actionsBody");
  const meta = document.getElementById("actionsMeta");
  const search = document.getElementById("actionSearch");
  const openBtn = document.getElementById("openActions");
  const closeBtn = document.getElementById("closeActions");

  // UI-only content: grouping and a sample phrase per action. Phrases match
  // the keyword rules, so they work even when Laya isn't loaded.
  const GROUPS = [
    { title: "Apps & windows", actions: ["open_app", "close_app", "focus_window", "move_window", "resize_window"] },
    { title: "Workspaces", actions: ["switch_workspace", "next_workspace", "previous_workspace"] },
    { title: "Media", actions: ["play_pause", "next_track", "previous_track"] },
    { title: "Sound", actions: ["volume_up", "volume_down", "mute"] },
    { title: "System", actions: ["lock_screen"] },
  ];
  const PHRASES = {
    open_app: "open Firefox", close_app: "close this", focus_window: "focus that window",
    move_window: "move the window left", resize_window: "make it bigger",
    switch_workspace: "go to workspace three", next_workspace: "next workspace",
    previous_workspace: "previous workspace", play_pause: "pause the music",
    next_track: "skip this song", previous_track: "previous track",
    volume_up: "turn it up", volume_down: "quieter", mute: "mute", lock_screen: "lock the screen",
  };
  const ICON = {
    voice: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
    gesture: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12M11 11.5v-7a1.5 1.5 0 0 1 3 0V12M14 11.5v-5a1.5 1.5 0 0 1 3 0V14c0 4-2.5 7-6.5 7S5 18.5 4 16l-1.3-3a1.5 1.5 0 0 1 2.6-1.4L8 15"/></svg>',
    keyboard: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 14h9"/></svg>',
  };

  let actions = null;       // loaded once, on first open
  let lastFocus = null;

  // ───────────── helpers ─────────────
  const human = s => s.replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase());
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;   // textContent = no HTML injection
    return n;
  }
  function paramText(p) {
    const opts = p.pattern && p.pattern.match(/^\^\((.+)\)\$$/);
    if (opts) return `${p.name}: ${opts[1].split("|").join(" / ")}`;
    let s = p.name;
    if (p.minimum != null && p.maximum != null) s += ` ${p.minimum}–${p.maximum}`;
    if (p.default != null) s += ` (default ${p.default})`;
    return s;
  }
  function trigger(kind, label) {
    const t = el("span", "trig trig-" + kind);
    t.innerHTML = ICON[kind];                  // static, trusted SVG
    t.append(el("span", null, label));
    return t;
  }

  // ───────────── rendering ─────────────
  function card(a) {
    const c = el("article", "act");
    c.dataset.search = [a.name, a.description, PHRASES[a.name], ...a.gestures, ...a.keys]
      .join(" ").toLowerCase().replace(/_/g, " ");

    const head = el("div", "act-head");
    head.append(el("h3", "act-name mono", a.name));
    if (a.destructive) head.append(el("span", "badge warn", "asks to confirm"));
    c.append(head, el("p", "act-desc", a.description));

    const trigs = el("div", "trigs");
    if (PHRASES[a.name]) trigs.append(trigger("voice", `“${PHRASES[a.name]}”`));
    a.gestures.forEach(g => trigs.append(trigger("gesture", human(g))));
    a.keys.forEach(k => trigs.append(trigger("keyboard", k)));
    c.append(trigs);

    const foot = el("div", "act-foot mono");
    const params = a.parameters.length ? a.parameters.map(paramText).join(" · ") : "no parameters";
    foot.append(el("span", null, params), el("span", null, `≥ ${Math.round(a.min_confidence * 100)}% conf`));
    c.append(foot);
    return c;
  }

  function render() {
    body.replaceChildren();
    const byName = Object.fromEntries(actions.map(a => [a.name, a]));
    const seen = new Set();
    const groups = GROUPS.map(g => ({ title: g.title, items: g.actions.filter(n => byName[n]) }));
    // Anything the registry has that GROUPS doesn't know yet still shows up.
    const extra = actions.map(a => a.name).filter(n => !GROUPS.some(g => g.actions.includes(n)));
    if (extra.length) groups.push({ title: "Other", items: extra });

    for (const g of groups) {
      if (!g.items.length) continue;
      const sec = el("section", "act-group");
      sec.append(el("h4", "group-title mono", g.title));
      const grid = el("div", "act-grid");
      g.items.forEach(n => { grid.append(card(byName[n])); seen.add(n); });
      sec.append(grid);
      body.append(sec);
    }
    body.append(el("p", "no-match muted", "No actions match that search."));
    filter();
  }

  function filter() {
    const q = search.value.trim().toLowerCase();
    let shown = 0;
    body.querySelectorAll(".act").forEach(c => {
      const hit = !q || c.dataset.search.includes(q);
      c.hidden = !hit;
      if (hit) shown++;
    });
    body.querySelectorAll(".act-group").forEach(s => {
      s.hidden = !s.querySelector(".act:not([hidden])");
    });
    body.querySelector(".no-match").hidden = shown > 0;
    meta.textContent = q ? `${shown} of ${actions.length} actions` : `${actions.length} actions`;
  }

  async function load() {
    try {
      const d = await (await fetch("/api/actions")).json();
      actions = d.actions || [];
      render();
    } catch {
      body.replaceChildren(el("p", "bad mono", "Couldn't load actions. Is the server running?"));
    }
  }

  // ───────────── open / close ─────────────
  function open() {
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    requestAnimationFrame(() => modal.classList.add("show"));
    if (!actions) load();
    search.focus();
  }
  function close() {
    modal.classList.remove("show");
    document.body.classList.remove("modal-open");
    setTimeout(() => { modal.hidden = true; }, 180);
    if (lastFocus) lastFocus.focus();
  }

  openBtn.addEventListener("click", open);
  closeBtn.addEventListener("click", close);
  modal.addEventListener("click", e => { if (e.target === modal) close(); });
  search.addEventListener("input", () => actions && filter());

  addEventListener("keydown", e => {
    if (modal.hidden) return;
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    // Keep Tab inside the dialog while it's open.
    if (e.key === "Tab") {
      const f = [...modal.querySelectorAll("button, input")].filter(n => !n.disabled);
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }, true);

  // Space toggles the mic in voice.js; don't let that fire while the modal is up.
  addEventListener("keydown", e => {
    if (!modal.hidden && e.code === "Space" && e.target.tagName !== "INPUT") e.stopImmediatePropagation();
  }, true);
})();
