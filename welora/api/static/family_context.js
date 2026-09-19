/* Welora — household → family_context lock (mirrors welora.personas.allowed_family_contexts). */
(function (w) {
  var ALLOWED = {
    solo: ["alone"],
    young_family: ["with_family"],
    couple_no_kids: ["with_family"],
    sandwich_3gen: ["with_family"],
    retire_companion: ["with_family"],
    pre_retire: ["alone", "with_family"]
  };
  var DEFAULTS = {
    solo: "alone",
    young_family: "with_family",
    couple_no_kids: "with_family",
    sandwich_3gen: "with_family",
    retire_companion: "with_family",
    pre_retire: "with_family"
  };
  var LEGACY = {
    young_single: "solo",
    established_single: "solo",
    young_couple: "couple_no_kids",
    family: "young_family",
    pre_retire: "pre_retire",
    retired: "retire_companion"
  };

  function normalizeHousehold(v) {
    var s = String(v == null ? "" : v).trim();
    if (ALLOWED[s]) return s;
    if (LEGACY[s]) return LEGACY[s];
    return "";
  }

  function allowedFamilyContexts(household) {
    var h = normalizeHousehold(household);
    if (!h || !ALLOWED[h]) return [];
    return ALLOWED[h].slice();
  }

  function defaultFamilyContext(household) {
    var h = normalizeHousehold(household);
    var allowed = allowedFamilyContexts(h);
    if (!allowed.length) return "";
    var d = DEFAULTS[h];
    if (d && allowed.indexOf(d) >= 0) return d;
    return allowed[0];
  }

  /**
   * Sync #family_context to #household: set default, lock/hide when single-option.
   * @param {HTMLSelectElement|null} hhEl
   * @param {HTMLSelectElement|null} fcEl
   * @param {HTMLElement|null} wrapEl  optional wrapper to hide when locked
   */
  function syncFamilyContextLock(hhEl, fcEl, wrapEl) {
    if (!hhEl || !fcEl) return;
    var hh = hhEl.value;
    var allowed = allowedFamilyContexts(hh);
    var def = defaultFamilyContext(hh) || (allowed[0] || "");
    Array.prototype.forEach.call(fcEl.options, function (opt) {
      var ok = allowed.indexOf(opt.value) >= 0;
      opt.disabled = !ok;
      opt.hidden = !ok;
    });
    if (def) fcEl.value = def;
    var locked = allowed.length <= 1;
    fcEl.disabled = locked;
    if (wrapEl) {
      wrapEl.classList.toggle("hidden", locked);
      wrapEl.setAttribute("aria-hidden", locked ? "true" : "false");
    } else {
      fcEl.classList.toggle("hidden", locked);
    }
  }

  w.WeloraFamilyContext = {
    ALLOWED: ALLOWED,
    DEFAULTS: DEFAULTS,
    allowedFamilyContexts: allowedFamilyContexts,
    defaultFamilyContext: defaultFamilyContext,
    syncFamilyContextLock: syncFamilyContextLock,
    normalizeHousehold: normalizeHousehold
  };
})(window);
