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
  if (allow[path]) return;
  var tok = "";
  try {
    tok = localStorage.getItem("welora_token") || "";
  } catch (_e) {}
  if (!tok) {
    location.replace("/app/login");
  }
})();
