/* Welora early auth gate — sync, blocking, before body paint.
   /app/* requires welora_token; auth pages allowlisted. No logout query deeplink. */
(function () {
  var path = (location.pathname || "").replace(/\/+$/, "") || "/app";
  var allow = {
    "/app/login": 1,
    "/app/register": 1,
    "/app/forgot-password": 1,
    "/app/reset-password": 1,
    "/app/otp": 1
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
