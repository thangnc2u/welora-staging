/* Welora — guest → account claim after login / register / OTP (P0 follow-up 2, item 1).
   The onboarding result page sets localStorage.welora_guest_claim=1. After a successful login the
   auth page calls WeloraGuestClaim.run(accountToken): it re-opens the guest session for this
   browser's welora_device_id (POST /auth/device → guest token, the proof of ownership) and posts
   it to /auth/guest/claim with the account bearer. The server is idempotent and applies the
   conflict policy (account data wins). The marker is cleared on any final answer; a network error
   or 429 keeps it for the next login. Never blocks navigation for long (≤ ~4 s). */
(function (w) {
  var MARK = "welora_guest_claim";
  var DEVICE_KEY = "welora_device_id";

  function get(k) {
    try { return w.localStorage.getItem(k) || ""; } catch (_e) { return ""; }
  }
  function clear() {
    try { w.localStorage.removeItem(MARK); } catch (_e) {}
  }
  function pending() {
    return get(MARK) === "1" && !!get(DEVICE_KEY);
  }
  function withTimeout(p, ms) {
    return Promise.race([p, new Promise(function (resolve) { setTimeout(function () { resolve(null); }, ms); })]);
  }

  async function claim(accountToken) {
    var g = await fetch("/auth/device", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: get(DEVICE_KEY) })
    });
    if (!g.ok) {
      if (g.status === 403 || g.status === 400) clear(); /* not a guest device any more */
      return { ok: false, status: g.status };
    }
    var gd = await g.json().catch(function () { return {}; });
    if (!gd.token) return { ok: false, status: 0 };
    if (gd.created) { clear(); return { ok: true, status: 200, body: { nothing: true } }; } /* fresh, empty guest */
    var r = await fetch("/auth/guest/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + accountToken },
      body: JSON.stringify({ guest_token: gd.token })
    });
    var body = await r.json().catch(function () { return {}; });
    if (r.status !== 429 && r.status < 500) clear();
    return { ok: r.ok, status: r.status, body: body };
  }

  async function run(accountToken) {
    if (!accountToken || !pending()) return null;
    try {
      return await withTimeout(claim(accountToken), 4000);
    } catch (_e) {
      return null;
    }
  }

  /* Short Vietnamese summary for the auth page status line. */
  function summary(res) {
    if (!res || !res.body) return "";
    var b = res.body;
    if (res.ok && b.already) return "Kết quả onboarding đã được lưu trước đó.";
    if (res.ok && b.moved) {
      var skipped = b.skipped || {};
      var keys = Object.keys(skipped);
      return keys.length
        ? "Đã lưu kết quả khách vào tài khoản (giữ nguyên dữ liệu sẵn có của tài khoản)."
        : "Đã lưu kết quả onboarding vào tài khoản.";
    }
    return "";
  }

  w.WeloraGuestClaim = { run: run, pending: pending, summary: summary, clear: clear, MARK: MARK };
})(window);
