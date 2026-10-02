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
     Skip auth pages (and OTP). No logout query deeplink.
     P0 follow-up: /app/onboarding is open to guests (Founder) — they use the in-memory
     /auth/device token from session.js; keep in sync with auth-gate.js. */
  var _authAllow = {
    "/app/login": 1,
    "/app/register": 1,
    "/app/forgot-password": 1,
    "/app/reset-password": 1,
    "/app/otp": 1,
    "/app/onboarding": 1,
    "/app/onboarding/result": 1
  };
  /* migration-019 ticket item 5: /app/academy for guests only when the server marked the page
     (<meta name="welora-guest-academy" content="1"> — WELORA_GUEST_DEMO on); keep in sync with auth-gate.js. */
  var _guestAcademy = false;
  if (path === "/app/academy" || path === "/app/learn") {  /* follow-up item 3: /app/learn = Academy alias */
    try {
      var _gm = document.querySelector('meta[name="welora-guest-academy"]');
      _guestAcademy = !!(_gm && _gm.getAttribute("content") === "1");
    } catch (_eGm) {}
  }
  if (!_authAllow[path] && !_guestAcademy) {
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

    /* Guest on /app/onboarding (no welora_token): offer "Đăng nhập" instead of logout. */
    var _guestTok = "";
    try {
      _guestTok = localStorage.getItem("welora_token") || "";
    } catch (_eGuest) {}
    if (!_guestTok && (path === "/app/onboarding" || path === "/app/onboarding/result" || _guestAcademy)) {
      btn.textContent = "Đăng nhập";
      btn.setAttribute("aria-label", "Đăng nhập");
      btn.addEventListener("click", function () {
        location.href = "/app/login";
      });
      chrome.appendChild(btn);
      document.body.insertBefore(chrome, document.body.firstChild);
      document.body.classList.add("welora-has-logout");
      return;
    }

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

  /* Migration 020: «Xác minh tài khoản» reminder for signed-in accounts whose e-mail / phone is not
     verified yet (GET /auth/me → verify_eligible && !verified && can_verify_now). Skippable:
     «Để sau» hides it for 24 h; it never blocks the page. Demo personas / device guests / admin
     never see it (server flags). */
  (function injectVerifyBanner() {
    var skip = { "/app/login": 1, "/app/register": 1, "/app/forgot-password": 1, "/app/reset-password": 1,
                 "/app/otp": 1, "/app/verify": 1 };
    if (skip[path]) return;
    var tok = "";
    try { tok = localStorage.getItem("welora_token") || ""; } catch (_eVt) {}
    if (!tok) return;
    try {
      var until = parseInt(localStorage.getItem("welora_verify_banner_until") || "0", 10) || 0;
      if (until > Date.now()) return;
    } catch (_eVu) {}
    fetch("/auth/me", { headers: { Authorization: "Bearer " + tok } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (me) {
        if (!me || !me.verify_eligible || me.verified || !me.can_verify_now) return;
        if (document.getElementById("weloraVerifyBanner")) return;
        var box = document.createElement("div");
        box.id = "weloraVerifyBanner";
        box.setAttribute("role", "status");
        box.style.cssText = "margin:8px 0 12px;padding:12px 14px;border-radius:12px;border:1px solid var(--border-default,#2F3D54);" +
          "background:var(--bg-surface,#1A2536);color:var(--text-primary,#F4F1E8);font-size:14px;line-height:1.4";
        var t = document.createElement("strong");
        t.textContent = "Xác minh tài khoản";
        var p = document.createElement("div");
        p.style.cssText = "margin-top:4px;color:var(--text-secondary,#A8B0C0);font-size:13px";
        p.textContent = "Tài khoản của bạn chưa được xác minh. Xác minh email hoặc số điện thoại giúp bảo vệ tài khoản và mở đủ lượt làm bài KUAT.";
        var row = document.createElement("div");
        row.style.cssText = "margin-top:8px;display:flex;gap:12px;align-items:center";
        var go = document.createElement("a");
        go.id = "weloraVerifyGo";
        go.className = "welora-btn-primary";
        go.style.cssText = "padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:600;font-size:13px";
        go.href = "/app/verify?next=" + encodeURIComponent(path);
        go.textContent = "Xác minh ngay";
        var later = document.createElement("button");
        later.type = "button";
        later.id = "weloraVerifyLater";
        later.style.cssText = "background:none;border:0;color:var(--text-secondary,#A8B0C0);text-decoration:underline;cursor:pointer;font-size:13px";
        later.textContent = "Để sau";
        later.addEventListener("click", function () {
          try { localStorage.setItem("welora_verify_banner_until", String(Date.now() + 24 * 3600 * 1000)); } catch (_eVl) {}
          if (box.parentNode) box.parentNode.removeChild(box);
        });
        row.appendChild(go);
        row.appendChild(later);
        box.appendChild(t);
        box.appendChild(p);
        box.appendChild(row);
        var chrome = document.getElementById("weloraTopChrome");
        if (chrome && chrome.parentNode) chrome.parentNode.insertBefore(box, chrome.nextSibling);
        else document.body.insertBefore(box, document.body.firstChild);
      })
      .catch(function () {});
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
