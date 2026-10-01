/* Welora — guest → account claim after login / register / OTP (P0 follow-up 2, item 1).
   The onboarding result page sets localStorage.welora_guest_claim=1. After a successful login the
   auth page calls WeloraGuestClaim.run(accountToken): it re-opens the guest session for this
   browser's welora_device_id (POST /auth/device → guest token, the proof of ownership) and posts
   it to /auth/guest/claim with the account bearer. The server is idempotent and applies the
   conflict policy (account data wins). The marker is cleared ONLY when the claim answers
   200 (claimed or already); every error (4xx/5xx/429/network/timeout) keeps it so the next login
   retries. Never blocks navigation for long (≤ ~4 s). */
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
    if (!g.ok) return { ok: false, status: g.status };
    var gd = await g.json().catch(function () { return {}; });
    if (!gd.token) return { ok: false, status: 0 };
    var r = await fetch("/auth/guest/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + accountToken },
      body: JSON.stringify({ guest_token: gd.token })
    });
    var body = await r.json().catch(function () { return {}; });
    if (r.status === 200 && body && body.ok === true) clear(); /* claimed or already — never on errors */
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
