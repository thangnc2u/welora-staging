/* Welora — safe post-action redirect target (PR #244 round 2, CoS B1).
   WeloraSafeNext(raw, fallback) returns a SAME-ORIGIN /app path for a ?next= value, else fallback
   ("/app"). Rejected: anything not starting with exactly one "/", backslashes (raw or %5C — browsers
   treat "\" as "/", so "/\evil.com" is "//evil.com"), ASCII control chars / whitespace (URL parsing
   strips tab/newline: "/\t/evil.com" → "//evil.com"), protocol-relative "//…", absolute URLs
   (https:, javascript:, data:), a parsed origin different from ours, and paths outside /app.
   Parsing goes through new URL(raw, location.origin); the result is pathname + search + hash. */
(function (w) {
  var BAD = /[\u0000-\u0020\u007F\\]|%5c|%2f%2f/i;
  function safeNext(raw, fallback) {
    var fb = fallback || "/app";
    if (typeof raw !== "string" || !raw || raw.length > 512) return fb;
    if (BAD.test(raw)) return fb;
    if (raw.charAt(0) !== "/" || raw.charAt(1) === "/") return fb;
    var u;
    try {
      u = new w.URL(raw, w.location.origin);
    } catch (_e) {
      return fb;
    }
    if (u.origin !== w.location.origin || (u.protocol !== "http:" && u.protocol !== "https:")) return fb;
    var out = u.pathname + u.search + u.hash;
    if (out.charAt(0) !== "/" || out.charAt(1) === "/" || out.indexOf("\\") >= 0 || BAD.test(u.pathname)) return fb;
    if (!(u.pathname === "/app" || u.pathname.indexOf("/app/") === 0)) return fb;
    return out;
  }
  w.WeloraSafeNext = safeNext;
})(window);
