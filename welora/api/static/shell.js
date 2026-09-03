/* Welora App shell — inject 4-tab bottom nav. No innerHTML. */
(function () {
  var tabs = [
    { id: "tabHome", href: "/app", label: "Trang chủ", ico: "○", key: "home" },
    { id: "tabPedia", href: "/app/content", label: "Từ điển", ico: "□", key: "pedia" },
    { id: "tabChat", href: "/app/chat", label: "Trợ lý AI", ico: "✉", key: "chat" },
    { id: "tabAcademy", href: "/app/academy", label: "Học viện", ico: "◈", key: "academy" }
  ];
  var path = (location.pathname || "").replace(/\/+$/, "") || "/app";
  var active = "home";
  var forced = document.currentScript && document.currentScript.getAttribute("data-shell-tab");
  if (forced) active = forced;
  else if (path.indexOf("/app/content") === 0) active = "pedia";
  else if (path.indexOf("/app/chat") === 0) active = "chat";
  else if (path.indexOf("/app/academy") === 0 || path.indexOf("/app/learn") === 0) active = "academy";
  else if (path === "/app" || path === "/app/home" || path.indexOf("/app/health-score") === 0) active = "home";

  document.body.classList.add("welora-shell");
  var nav = document.createElement("nav");
  nav.id = "weloraBottomNav";
  nav.setAttribute("aria-label", "Welora");
  tabs.forEach(function (t) {
    var a = document.createElement("a");
    a.id = t.id;
    a.href = t.href;
    if (t.key === active) a.className = "on";
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
})();
