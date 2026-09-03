/* Welora money — user-facing VND + %. No innerHTML. */
(function (w) {
  function formatVnd(n) {
    var x = Math.round(Number(n) || 0);
    var sign = x < 0 ? "-" : "";
    var s = String(Math.abs(x));
    var out = "";
    while (s.length > 3) {
      out = "." + s.slice(-3) + out;
      s = s.slice(0, -3);
    }
    return sign + s + out + " ₫";
  }
  function parseVnd(s) {
    var t = String(s == null ? "" : s).replace(/[^0-9-]/g, "");
    if (!t || t === "-") return 0;
    return Number(t) || 0;
  }
  function formatPct(n) {
    var x = Number(n);
    if (!isFinite(x)) return "0%";
    var r = Math.round(x * 10) / 10;
    if (Math.abs(r - Math.round(r)) < 1e-9) return String(Math.round(r)) + "%";
    return String(r).replace(".", ",") + "%";
  }
  function bindMoneyInput(el) {
    if (!el) return;
    function paint() {
      var n = parseVnd(el.value);
      el.value = n ? formatVnd(n) : "";
      el.setAttribute("data-vnd", String(n));
    }
    el.addEventListener("blur", paint);
    el.addEventListener("focus", function () {
      var n = parseVnd(el.value);
      el.value = n ? String(n) : "";
    });
    if (el.value && /[0-9]/.test(el.value)) paint();
  }
  function bindChips(container, input) {
    if (!container || !input) return;
    container.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;
      var v = t.getAttribute("data-vnd");
      if (!v) return;
      e.preventDefault();
      input.value = formatVnd(Number(v));
      input.setAttribute("data-vnd", v);
    });
  }
  w.WeloraMoney = {
    formatVnd: formatVnd,
    parseVnd: parseVnd,
    formatPct: formatPct,
    bindMoneyInput: bindMoneyInput,
    bindChips: bindChips
  };
})(window);
