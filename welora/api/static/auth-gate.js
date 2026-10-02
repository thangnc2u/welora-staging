/* Welora early auth gate — sync, blocking, before body paint.
   /app/* requires welora_token; auth pages allowlisted. No logout query deeplink.
   P0 follow-up (Founder): guests may onboard before logging in — /app/onboarding is exempt and
   runs on the in-memory /auth/device guest token (session.js); no token is written here.
   Follow-up 2: /app/onboarding/result (guest result + "đăng ký để lưu") is exempt as well.
   Migration-019 ticket: /app/academy is exempt only when the server marks it (WELORA_GUEST_DEMO on).
   Follow-up item 3: /app/learn (the Academy alias, same page) follows the same rule. */
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
  /* migration-019 ticket item 5: /app/academy is open to device guests ONLY when the server marked
     the page (<meta name="welora-guest-academy" content="1">, emitted only while WELORA_GUEST_DEMO
     is on). Production (WELORA_GUEST_DEMO=0): no marker → login required (and the Academy APIs
     refuse device guests server-side). */
  function guestAcademy() {
    if (path !== "/app/academy" && path !== "/app/learn") return false;
    try {
      var m = document.querySelector('meta[name="welora-guest-academy"]');
      return !!(m && m.getAttribute("content") === "1");
    } catch (_eMeta) {
      return false;
    }
  }
  if (allow[path] || guestAcademy()) {
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
