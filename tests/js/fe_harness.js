/* Minimal browser stand-in to run welora/api/static/{auth-gate,session}.js under node:vm.
   Usage: node fe_harness.js <scenario>  → prints one JSON line. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const STATIC = path.resolve(__dirname, "..", "..", "welora", "api", "static");

function makeStorage(init) {
  const m = new Map(Object.entries(init || {}));
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    clear: () => m.clear(),
    dump: () => Object.fromEntries(m),
  };
}

function makeWindow(pathname, store, routes) {
  const calls = [];
  const replaced = [];
  const loc = {
    pathname,
    origin: "https://welora.test",
    href: "https://welora.test" + pathname,
    replace: (u) => replaced.push(u),
  };
  const fetchImpl = async (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    const u = new URL(url, loc.href);
    const h = new Headers((init && init.headers) || undefined);
    calls.push({ path: u.pathname, auth: h.get("Authorization") || "" });
    const fn = routes[u.pathname] || (() => [404, { detail: "Not Found" }]);
    const [status, body] = fn(h.get("Authorization") || "", init);
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  };
  const w = {
    location: loc,
    localStorage: makeStorage(store),
    sessionStorage: makeStorage({}),
    fetch: fetchImpl,
    Headers, Response, URL, Promise, JSON, Object, String, Math, console,
  };
  w.window = w;
  return { w, calls, replaced };
}

function run(file, ctx) {
  vm.runInContext(fs.readFileSync(path.join(STATIC, file), "utf8"), ctx, { filename: file });
}

const scenarios = {
  async gate_guest_onboarding() {
    const out = {};
    for (const [p, tok] of [["/app/onboarding", ""], ["/app/onboarding/", ""], ["/app/goals", ""], ["/app/safety", ""], ["/app/pre-rule", ""], ["/app/onboarding", "T1"], ["/app/login", "T1"]]) {
      const { w, replaced } = makeWindow(p, tok ? { welora_token: tok } : {}, {});
      const ctx = vm.createContext(w);
      run("auth-gate.js", ctx);
      out[p + (tok ? "+tok" : "")] = { redirect: replaced[0] || null, token_kept: w.localStorage.getItem("welora_token") };
    }
    return out;
  },

  async expired_on_app_page() {
    const routes = {
      "/goals": (auth) => (auth === "Bearer OLD" ? [401, { detail: { error_code: "TOKEN_EXPIRED", message: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại." } }] : [200, { items: [] }]),
    };
    const { w, calls, replaced } = makeWindow("/app/goals", { welora_token: "OLD", welora_device_id: "dev-x" }, routes);
    const ctx = vm.createContext(w);
    run("session.js", ctx);
    const r = await w.fetch("/goals?user_id=u1");
    return { status: r.status, sent: calls[0].auth, redirect: replaced, token: w.localStorage.getItem("welora_token"),
             device: w.localStorage.getItem("welora_device_id"), notice: w.sessionStorage.getItem("welora_auth_notice") };
  },

  async expired_on_onboarding_guest_continues() {
    const routes = {
      "/auth/me": (auth) => (auth === "Bearer OLD" ? [401, { detail: { error_code: "TOKEN_EXPIRED" } }] : [401, { detail: "invalid or expired token" }]),
      "/auth/device": () => [200, { user_id: "guest-1", token: "DEV1", kind: "device" }],
      "/onboarding/session": (auth) => (auth === "Bearer DEV1" ? [201, { session_id: "s1" }] : [401, { detail: { error_code: "AUTH_REQUIRED" } }]),
      "/goals": (auth) => (auth === "Bearer DEV1" ? [201, { type: "emergency_fund" }] : [401, { detail: { error_code: "AUTH_REQUIRED" } }]),
    };
    const { w, calls, replaced } = makeWindow("/app/onboarding", { welora_token: "OLD" }, routes);
    const ctx = vm.createContext(w);
    run("session.js", ctx);
    const uid = await w.WeloraSession.resolveUserId();
    const s = await w.fetch("/onboarding/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const g = await w.fetch("/goals", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    return { uid, session: s.status, goal: g.status, redirect: replaced, token: w.localStorage.getItem("welora_token"),
             auths: calls.map((c) => c.path + "=" + c.auth) };
  },

  async guest_onboarding_no_token() {
    const routes = {
      "/auth/device": () => [200, { user_id: "guest-2", token: "DEV2", kind: "device" }],
      "/goals": (auth) => (auth === "Bearer DEV2" ? [201, { type: "emergency_fund" }] : [401, { detail: { error_code: "AUTH_REQUIRED" } }]),
    };
    const { w, calls, replaced } = makeWindow("/app/onboarding", {}, routes);
    const ctx = vm.createContext(w);
    run("auth-gate.js", ctx);
    run("session.js", ctx);
    const uid = await w.WeloraSession.resolveUserId();
    const g = await w.fetch("/goals", { method: "POST", body: "{}" });
    return { uid, goal: g.status, redirect: replaced, stored: w.localStorage.getItem("welora_token"), auths: calls.map((c) => c.path + "=" + c.auth) };
  },

  async other_401_codes_untouched() {
    const routes = {
      "/api/admin/v1/orders": () => [401, { detail: { error_code: "ADMIN_2FA_REQUIRED", message: "Nhập mã 2FA để tiếp tục" } }],
    };
    const { w, replaced } = makeWindow("/app/admin/checkout", { welora_token: "ADM" }, routes);
    const ctx = vm.createContext(w);
    run("session.js", ctx);
    const r = await w.fetch("/api/admin/v1/orders");
    return { status: r.status, redirect: replaced, token: w.localStorage.getItem("welora_token") };
  },
};

(async () => {
  const name = process.argv[2];
  const out = await scenarios[name]();
  process.stdout.write("RESULT=" + JSON.stringify(out) + "\n");
})().catch((e) => {
  process.stderr.write(String((e && e.stack) || e));
  process.exit(1);
});
