/* Welora session — resolve logged-in user_id from welora_token (/auth/me).
   Falls back to /auth/device only when no usable password/OTP session.
   Does not touch Hard Deny · TARGET_MONTHS · gate_months · login 1-ô · logout. */
(function (w) {
  var TOKEN_KEY = "welora_token";
  var DEVICE_KEY = "welora_device_id";
  var cachedUid = "";

  function token() {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (_e) {
      return "";
    }
  }

  function deviceId() {
    var d = "";
    try {
      d = localStorage.getItem(DEVICE_KEY) || "";
    } catch (_e) {}
    if (!d) {
      d = "dev-" + Math.random().toString(36).slice(2, 10);
      try {
        localStorage.setItem(DEVICE_KEY, d);
      } catch (_e2) {}
    }
    return d;
  }

  function clearCache() {
    cachedUid = "";
  }

  /* P0 authz: every user-scoped API now requires Bearer token (owner = token user).
     Same-origin fetch() calls without an Authorization header get one attached:
       1) the token returned by the most recent POST /auth/device on this page
          (guest/device identity — kept in memory only, never written to localStorage,
          so logout / auth-gate behaviour is unchanged);
       2) otherwise localStorage.welora_token (password / OTP / demo / admin login),
          unless /auth/me already rejected it on this page. */
  var pageToken = "";
  var storedRejected = false;

  function activeToken() {
    if (pageToken) return pageToken;
    if (storedRejected) return "";
    return token();
  }

  function sameOriginPath(url) {
    if (!url) return "";
    try {
      var u = new URL(url, w.location.href);
      if (u.origin !== w.location.origin) return "";
      return u.pathname;
    } catch (_e) {
      return "";
    }
  }

  var nativeFetch = w.fetch ? w.fetch.bind(w) : null;
  if (nativeFetch && !w.__weloraAuthFetch) {
    w.__weloraAuthFetch = true;
    w.fetch = function (input, init) {
      var url = typeof input === "string" ? input : (input && input.url) || String(input || "");
      var path = sameOriginPath(url);
      var sentStored = false;
      /* /auth/* (login, device, logout, me …) manage their own headers */
      if (path && path.indexOf("/static/") !== 0 && path.indexOf("/auth/") !== 0) {
        init = Object.assign({}, init || {});
        var h = new Headers(init.headers || (typeof input !== "string" && input && input.headers) || undefined);
        if (!h.has("Authorization")) {
          var t = activeToken();
          if (t) {
            h.set("Authorization", "Bearer " + t);
            sentStored = !pageToken;
          }
        } else if (h.get("Authorization") === "Bearer " + token()) {
          sentStored = true;
        }
        init.headers = h;
      }
      var p = nativeFetch(input, init);
      if (path === "/auth/me") {
        return p.then(function (r) {
          if (r.status === 401 && sentStored) storedRejected = true;
          return r;
        });
      }
      if (path === "/auth/device") {
        /* resolve only after the guest token is captured, so the page's next call carries it */
        return p.then(function (r) {
          if (!r.ok) return r;
          return r.clone().json().then(function (d) {
            if (d && d.token) pageToken = d.token;
            return r;
          }, function () {
            return r;
          });
        });
      }
      return p;
    };
  }

  async function resolveUserId(opts) {
    opts = opts || {};
    if (cachedUid && !opts.force) return cachedUid;
    var tok = token();
    if (tok) {
      try {
        var meR = await fetch("/auth/me", {
          headers: { Authorization: "Bearer " + tok }
        });
        if (meR.ok) {
          var me = await meR.json();
          var uid = me.user_id || me.user || "";
          if (uid) {
            cachedUid = uid;
            return uid;
          }
        }
      } catch (_eMe) {}
    }
    var auth = await fetch("/auth/device", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId() })
    });
    var a = await auth.json().catch(function () {
      return {};
    });
    cachedUid = a.user_id || a.user || "";
    return cachedUid;
  }

  w.WeloraSession = {
    resolveUserId: resolveUserId,
    deviceId: deviceId,
    token: token,
    clearCache: clearCache,
    activeToken: activeToken,
    TOKEN_KEY: TOKEN_KEY,
    DEVICE_KEY: DEVICE_KEY
  };
})(window);
