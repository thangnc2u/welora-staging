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
    TOKEN_KEY: TOKEN_KEY,
    DEVICE_KEY: DEVICE_KEY
  };
})(window);
