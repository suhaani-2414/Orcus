// Orcus camera preview — a modal showing the gesture camera (/camera MJPEG,
// with MediaPipe hand landmarks). Doubles as a gesture debug view: if you see
// yourself + a hand skeleton, detection works; blank = camera issue.
// Isolated file + one <script> tag so it doesn't collide with app.js/actions.js.
// The stream is only pulled while the modal is open (src cleared on close).
(function () {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "Camera";
  btn.setAttribute("aria-label", "Show gesture camera");
  Object.assign(btn.style, {
    position: "fixed", left: "24px", bottom: "24px", zIndex: "60",
    padding: "12px 20px", fontSize: "1rem", fontWeight: "700",
    color: "#e6edf3", background: "rgba(22,27,34,.85)",
    border: "1px solid #30363d", borderRadius: "999px", cursor: "pointer",
    fontFamily: "inherit", backdropFilter: "blur(6px)",
  });

  const backdrop = document.createElement("div");
  Object.assign(backdrop.style, {
    position: "fixed", inset: "0", zIndex: "70", display: "none",
    alignItems: "center", justifyContent: "center",
    background: "rgba(2,6,12,.7)", backdropFilter: "blur(4px)",
  });

  const box = document.createElement("div");
  Object.assign(box.style, {
    background: "#0d1117", border: "1px solid #30363d", borderRadius: "16px",
    padding: "14px", maxWidth: "92vw", boxShadow: "0 20px 60px rgba(0,0,0,.6)",
  });

  const img = document.createElement("img");
  Object.assign(img.style, {
    display: "block", width: "min(560px, 88vw)", borderRadius: "10px",
    background: "#000", aspectRatio: "4 / 3", objectFit: "cover",
  });
  img.alt = "gesture camera";

  const cap = document.createElement("div");
  Object.assign(cap.style, {
    marginTop: "8px", fontFamily: "monospace", fontSize: ".8rem",
    color: "#8b949e", display: "flex", justifyContent: "space-between",
  });
  cap.innerHTML = "<span>live gesture camera · swipe to control</span>";
  const close = document.createElement("button");
  close.textContent = "close";
  Object.assign(close.style, {
    background: "none", border: "none", color: "#22e4ff", cursor: "pointer",
    fontFamily: "monospace", fontSize: ".8rem",
  });
  cap.append(close);

  box.append(img, cap);
  backdrop.append(box);
  document.body.append(btn, backdrop);

  function open() {
    img.src = "/camera?t=" + Date.now();  // cache-bust, start stream
    backdrop.style.display = "flex";
  }
  function shut() {
    backdrop.style.display = "none";
    img.src = "";  // stop pulling the MJPEG stream
  }
  btn.addEventListener("click", open);
  close.addEventListener("click", shut);
  backdrop.addEventListener("click", e => { if (e.target === backdrop) shut(); });
  addEventListener("keydown", e => { if (e.key === "Escape") shut(); });
})();
