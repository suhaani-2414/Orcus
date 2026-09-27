// Gesture-to-action editor. The server validates action names before persisting
// them, and the current pipeline is updated without restarting the dashboard.
(function () {
  const modal = document.getElementById("mappingsModal");
  const list = document.getElementById("mappingList");
  const status = document.getElementById("mappingStatus");
  const openBtn = document.getElementById("openMappings");
  const closeBtn = document.getElementById("closeMappings");
  const saveBtn = document.getElementById("saveMappings");
  let lastFocus = null;

  const human = value => value.replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase());
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };

  function render(data) {
    list.replaceChildren();
    for (const item of data.mappings || []) {
      const row = el("label", "mapping-row");
      row.append(el("span", "mapping-name mono", human(item.gesture)));
      const select = document.createElement("select");
      select.className = "mapping-select";
      select.dataset.gesture = item.gesture;
      const none = el("option", null, "No action");
      none.value = "";
      select.append(none);
      for (const action of data.actions || []) {
        const option = el("option", null, human(action.name));
        option.value = action.name;
        option.title = action.description;
        select.append(option);
      }
      select.value = item.action || "";
      row.append(select);
      list.append(row);
    }
  }

  async function load() {
    status.className = "mapping-status mono";
    status.textContent = "Loading…";
    try {
      const response = await fetch("/api/gesture-mappings");
      if (!response.ok) throw new Error("request failed");
      render(await response.json());
      status.textContent = "";
    } catch {
      status.className = "mapping-status mono bad";
      status.textContent = "Couldn’t load gesture mappings.";
    }
  }

  async function save() {
    const mappings = {};
    list.querySelectorAll("select").forEach(select => {
      mappings[select.dataset.gesture] = select.value || null;
    });
    saveBtn.disabled = true;
    status.className = "mapping-status mono";
    status.textContent = "Saving…";
    try {
      const response = await fetch("/api/gesture-mappings", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mappings}),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "save failed");
      status.className = "mapping-status mono ok";
      status.textContent = "Saved. New gesture events use these mappings.";
    } catch (error) {
      status.className = "mapping-status mono bad";
      status.textContent = error.message;
    } finally {
      saveBtn.disabled = false;
    }
  }

  function open() {
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    requestAnimationFrame(() => modal.classList.add("show"));
    load();
  }
  function close() {
    modal.classList.remove("show");
    document.body.classList.remove("modal-open");
    setTimeout(() => { modal.hidden = true; }, 180);
    if (lastFocus) lastFocus.focus();
  }

  openBtn.addEventListener("click", open);
  closeBtn.addEventListener("click", close);
  saveBtn.addEventListener("click", save);
  modal.addEventListener("click", event => { if (event.target === modal) close(); });
  addEventListener("keydown", event => {
    if (!modal.hidden && event.key === "Escape") close();
  });
})();
