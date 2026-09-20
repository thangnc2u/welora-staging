/* Welora — debt×priority + EF months locks (mirrors welora.personas form locks). */
(function (w) {
  var PRIORITY_DEBT = "debt";
  var PRIORITY_SAFETY = "safety";

  function syncDebtPriorityLock(debtEl, priorityEl) {
    if (!debtEl || !priorityEl) return;
    var debtTrue = String(debtEl.value) === "true";
    Array.prototype.forEach.call(priorityEl.options, function (opt) {
      if (opt.value === PRIORITY_DEBT) {
        opt.hidden = !debtTrue;
        opt.disabled = !debtTrue;
      }
    });
    if (!debtTrue) {
      if (priorityEl.value === PRIORITY_DEBT) priorityEl.value = PRIORITY_SAFETY;
    } else if (priorityEl.dataset.weloraLastDebt !== "true") {
      // debt flipped to true → default priority=debt (user may still pick safety)
      priorityEl.value = PRIORITY_DEBT;
    }
    priorityEl.dataset.weloraLastDebt = debtTrue ? "true" : "false";
  }

  function debtCtaAllowed(debtEl) {
    return !!(debtEl && String(debtEl.value) === "true");
  }

  function validateEmergencyFundMonths(raw) {
    if (raw === null || raw === undefined || raw === "") return { ok: false };
    var n = Number(raw);
    if (!isFinite(n) || n < 0 || n > 3) return { ok: false };
    return { ok: true, value: n };
  }

  w.WeloraFormLocks = {
    syncDebtPriorityLock: syncDebtPriorityLock,
    debtCtaAllowed: debtCtaAllowed,
    validateEmergencyFundMonths: validateEmergencyFundMonths,
    PRIORITY_DEBT: PRIORITY_DEBT,
    PRIORITY_SAFETY: PRIORITY_SAFETY
  };
})(window);
