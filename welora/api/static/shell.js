/* Welora App shell — inject bottom nav (4 always-on + gated Chat). No innerHTML. */
(function () {
  var tabs = [
    { id: "tabHome", href: "/app", label: "Trang chủ", ico: "○", key: "home" },
    { id: "tabPedia", href: "/app/content", label: "Từ điển", ico: "□", key: "pedia" },
    { id: "tabAcademy", href: "/app/academy", label: "Học viện", ico: "◈", key: "academy" },
    { id: "tabOps", href: "/app/safety", label: "Điều hành", ico: "▣", key: "ops" },
    { id: "tabChat", href: "/app/chat", label: "Chat với Agent", ico: "✉", key: "chat", gate: true }
  ];
  var path = (location.pathname || "").replace(/\/+$/, "") || "/app";

  /* Auth gate: /app/* requires welora_token; device_id alone is not a login session.
     Skip auth pages (and OTP). No logout query deeplink. */
  var _authAllow = {
    "/app/login": 1,
    "/app/register": 1,
    "/app/forgot-password": 1,
    "/app/reset-password": 1,
    "/app/otp": 1
  };
  if (!_authAllow[path]) {
    var _tok = "";
    try {
      _tok = localStorage.getItem("welora_token") || "";
    } catch (_eGate) {}
    if (!_tok) {
      location.replace("/app/login");
      return;
    }
  }

  var active = "home";
  var forced = document.currentScript && document.currentScript.getAttribute("data-shell-tab");
  /* Điều hành cluster — not home (#173 goals→home fixed) */
  if (forced) active = forced;
  else if (path.indexOf("/app/content") === 0) active = "pedia";
  else if (path.indexOf("/app/chat") === 0) active = "chat";
  else if (path.indexOf("/app/academy") === 0 || path.indexOf("/app/learn") === 0) active = "academy";
  else if (
    path.indexOf("/app/safety") === 0 ||
    path.indexOf("/app/goals") === 0 ||
    path.indexOf("/app/dna") === 0 ||
    path.indexOf("/app/constitution") === 0 ||
    path.indexOf("/app/health-score") === 0 ||
    path.indexOf("/app/onboarding") === 0 ||
    path.indexOf("/app/dual-control") === 0 ||
    path.indexOf("/app/accounts") === 0 ||
    path.indexOf("/app/transactions") === 0 ||
    path.indexOf("/app/categories") === 0 ||
    path.indexOf("/app/budget") === 0
  ) active = "ops";
  else if (path === "/app" || path === "/app/home") active = "home";

  document.documentElement.setAttribute("data-theme", "dark");
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
        var uid = "";
        if (window.WeloraSession && WeloraSession.resolveUserId) {
          uid = await WeloraSession.resolveUserId();
        } else {
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
          uid = a.user_id || "";
        }
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


  /* Scope B: Đăng xuất chrome (parity CP) — skip auth pages; no logout query deeplink */
  (function injectLogout() {
    var authPaths = {
      "/app/login": 1,
      "/app/register": 1,
      "/app/forgot-password": 1,
      "/app/reset-password": 1
    };
    if (authPaths[path]) return;
    if (document.getElementById("weloraLogout") || document.getElementById("btnLogout")) return;

    var chrome = document.createElement("div");
    chrome.id = "weloraTopChrome";
    chrome.setAttribute("role", "banner");

    var btn = document.createElement("button");
    btn.type = "button";
    btn.id = "weloraLogout";
    btn.className = "welora-logout-btn";
    btn.setAttribute("aria-label", "Đăng xuất");
    btn.textContent = "Đăng xuất";

    btn.addEventListener("click", function () {
      /* Capture Bearer BEFORE any storage clear; logout POST is fire-and-forget. */
      var token = "";
      try {
        token = localStorage.getItem("welora_token") || "";
      } catch (_eTok) {}

      /* SYNCHRONOUS clear BEFORE fetch/redirect — token must die even if clear() throws. */
      function clearAuthStorage() {
        try {
          localStorage.removeItem("welora_token");
        } catch (_eRm) {}
        try {
          if (window.WeloraSession && WeloraSession.clearCache) WeloraSession.clearCache();
        } catch (_eCache) {}
        try {
          localStorage.removeItem("welora_dev");
        } catch (_eDevKey) {}
        var deviceId = "";
        try {
          deviceId = localStorage.getItem("welora_device_id") || "";
        } catch (_eDev) {}
        try {
          localStorage.clear();
        } catch (_eClear) {}
        try {
          if (deviceId) localStorage.setItem("welora_device_id", deviceId);
        } catch (_eRest) {}
        try {
          sessionStorage.clear();
        } catch (_eSess) {}
        /* Best-effort clear session-ish cookies (path=/ and path=/app). */
        try {
          var parts = (document.cookie || "").split(";");
          for (var i = 0; i < parts.length; i++) {
            var name = (parts[i].split("=")[0] || "").trim();
            if (!name) continue;
            if (!/welora|token|session|auth/i.test(name)) continue;
            document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
            document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/app";
          }
        } catch (_eCk) {}
      }

      clearAuthStorage();

      if (token) {
        try {
          fetch("/auth/logout", {
            method: "POST",
            headers: { Authorization: "Bearer " + token },
            keepalive: true
          }).catch(function () {});
        } catch (_eFetch) {}
      }

      /* Belt + assert: token must be gone before replace (do not wait on fetch). */
      try {
        localStorage.removeItem("welora_token");
      } catch (_eBelt) {}
      try {
        if (localStorage.getItem("welora_token")) {
          localStorage.removeItem("welora_token");
        }
      } catch (_eAssert) {}
      try {
        if (localStorage.getItem("welora_token")) {
          localStorage.removeItem("welora_token");
        }
      } catch (_eAssert2) {}
      /* keep welora_device_id — device identity, not login session */
      location.replace("/app/login");
    });

    chrome.appendChild(btn);
    document.body.insertBefore(chrome, document.body.firstChild);
    document.body.classList.add("welora-has-logout");
  })();

  /* P1 ops-tabs: mark active from pathname if missing */
  (function markOpsTabs() {
    var cluster = document.getElementById("opsCluster");
    if (!cluster || !cluster.classList.contains("ops-tabs")) return;
    if (cluster.querySelector("a.ops-nav.is-active, a.ops-nav[aria-current='page']")) return;
    var p = (location.pathname || "").replace(/\/+$/, "") || "/app";
    var links = cluster.querySelectorAll("a.ops-nav");
    for (var i = 0; i < links.length; i++) {
      var href = (links[i].getAttribute("href") || "").replace(/\/+$/, "") || "/app";
      if (href === p) {
        links[i].classList.add("is-active");
        links[i].setAttribute("aria-current", "page");
        break;
      }
    }
  })();

})();
