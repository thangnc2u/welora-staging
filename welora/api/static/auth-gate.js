/* Welora early auth gate — sync, blocking, before body paint.
   /app/* requires welora_token; auth pages allowlisted. No logout query deeplink.
   P0 follow-up (Founder): guests may onboard before logging in — /app/onboarding is exempt and
   runs on the in-memory /auth/device guest token (session.js); no token is written here.
   Follow-up 2: /app/onboarding/result (guest result + "đăng ký để lưu") is exempt as well. */
(function () {
  var path = (location.pathname || "").replace(/\/+$/, "") || "/app";
  var allow = {
    "/app/login": 1,
    "/app/register": 1,
    "/app/forgot-password": 1,
    "/app/reset-password": 1,
    "/app/otp": 1,
    "/app/admin/login": 1,
    "/app/onboarding": 1,
    "/app/onboarding/result": 1
  };
  if (allow[path]) {
    /* Hotfix #4 belt: wipe stray token on /app/login entry (keep device_id). */
    if (path === "/app/login") {
      try {
        localStorage.removeItem("welora_token");
      } catch (_eBelt) {}
    }
    return;
  }
  var tok = "";
  try {
    tok = localStorage.getItem("welora_token") || "";
  } catch (_e) {}
  if (!tok) {
    location.replace("/app/login");
  }
})();
