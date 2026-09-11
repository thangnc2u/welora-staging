/* Welora App shell — inject 4-tab bottom nav. No innerHTML. */
(function () {
  var tabs = [
    { id: "tabHome", href: "/app", label: "Trang chủ", ico: "○", key: "home" },
    { id: "tabPedia", href: "/app/content", label: "Từ điển", ico: "□", key: "pedia" },
    { id: "tabChat", href: "/app/chat", label: "Chat với Agent", ico: "✉", key: "chat", gate: true },
    { id: "tabAcademy", href: "/app/academy", label: "Học viện", ico: "◈", key: "academy" }
  ];
  var path = (location.pathname || "").replace(/\/+$/, "") || "/app";
  var active = "home";
  var forced = document.currentScript && document.currentScript.getAttribute("data-shell-tab");
  /* goals / safety are not bottom tabs — map to home so no ghost "on" */
  if (forced === "goals") active = "home";
  else if (forced) active = forced;
  else if (path.indexOf("/app/content") === 0) active = "pedia";
  else if (path.indexOf("/app/chat") === 0) active = "chat";
  else if (path.indexOf("/app/academy") === 0 || path.indexOf("/app/learn") === 0) active = "academy";
  else if (
    path === "/app" ||
    path === "/app/home" ||
    path.indexOf("/app/health-score") === 0 ||
    path.indexOf("/app/goals") === 0 ||
    path.indexOf("/app/safety") === 0
  ) active = "home";

  document.body.classList.add("welora-shell");
  var nav = document.createElement("nav");
  nav.id = "weloraBottomNav";
  nav.setAttribute("aria-label", "Điều hướng Welora");
  var chatLink = null;
  tabs.forEach(function (t) {
    var a = document.createElement("a");
    a.id = t.id;
    a.href = t.href;
    if (t.key === active) a.className = "on";
    if (t.gate) {
      a.hidden = true; /* parity with #navChat — hidden until gate passed */
      chatLink = a;
    }
    var ico = document.createElement("span");
    ico.className = "tab-ico";
    ico.textContent = t.ico;
    var lab = document.createElement("span");
    lab.textContent = t.label;
    a.appendChild(ico);
    a.appendChild(lab);
    nav.appendChild(a);
  });
  document.body.appendChild(nav);

  if (chatLink) {
    (async function () {
      try {
        var KEY = "welora_device_id";
        var d = localStorage.getItem(KEY);
        if (!d) {
          d = "dev-" + Math.random().toString(36).slice(2, 10);
          localStorage.setItem(KEY, d);
        }
        var auth = await fetch("/auth/device", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: d })
        });
        var a = await auth.json();
        var uid = a.user_id || "";
        if (!uid) return;
        var gR = await fetch("/users/" + encodeURIComponent(uid) + "/safety-gate");
        var gate = await gR.json();
        var st = gate.status || gate.safety_gate_status || "not_passed";
        chatLink.hidden = st !== "passed";
      } catch (_e) {
        chatLink.hidden = true;
      }
    })();
  }
})();
