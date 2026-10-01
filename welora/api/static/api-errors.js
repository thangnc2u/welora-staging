/* Welora — API error → Vietnamese text (P0 follow-up 2, item 2).
   FastAPI returns `detail` as a string, an object ({error_code, message} / {error} / {reply}) or a
   validation LIST ([{loc, msg, type}]); some routes return {error: "..."} or {error: {…}}.
   Never render "[object Object]": WeloraErrors.message(body, fallback, status) always returns text. */
(function (w) {
  var FIELD_VI = {
    user_id: "người dùng",
    session_id: "phiên",
    household: "hoàn cảnh gia đình",
    life_stage: "giai đoạn sống",
    income_stability: "độ ổn định thu nhập",
    family_context: "bối cảnh gia đình",
    essential_expense_monthly: "chi tiêu thiết yếu mỗi tháng",
    emergency_fund_months_self: "số tháng quỹ hiện có",
    has_dangerous_debt_self: "nợ nguy hiểm",
    near_term_priority: "ưu tiên gần",
    surplus_habit: "thói quen tiền dư",
    risk_tolerance: "mức chấp nhận rủi ro",
    agent_role_preference: "vai trò trợ lý",
    current_amount: "số tiền hiện có",
    type: "loại mục tiêu",
    email: "email",
    phone: "số điện thoại",
    password: "mật khẩu"
  };
  var KNOWN = [
    [/session not found/i, "Không tìm thấy phiên onboarding — vui lòng bắt đầu lại."],
    [/steps 1 and 2 required/i, "Cần hoàn tất bước 1 và 2 trước khi tạo kết quả."],
    [/session already completed/i, "Phiên onboarding này đã hoàn tất."],
    [/must be a number/i, "Giá trị phải là số."],
    [/must be one of/i, "Lựa chọn chưa hợp lệ — vui lòng chọn lại."],
    [/invalid or expired token|missing token/i, "Phiên đã hết hạn — vui lòng tải lại trang."],
    [/already has emergency_fund goal/i, "Bạn đã có quỹ khẩn cấp."],
    [/not found/i, "Không tìm thấy dữ liệu."]
  ];
  var CODES = {
    TOKEN_EXPIRED: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
    AUTH_REQUIRED: "Vui lòng đăng nhập để tiếp tục.",
    RATE_LIMITED: "Bạn đã thử quá nhiều lần. Vui lòng thử lại sau ít phút.",
    FORBIDDEN: "Bạn không có quyền với dữ liệu này."
  };
  var TYPE_VI = {
    missing: "còn thiếu",
    int_parsing: "phải là số nguyên",
    float_parsing: "phải là số",
    bool_parsing: "phải là có/không",
    string_too_short: "quá ngắn",
    string_too_long: "quá dài",
    enum: "chưa đúng lựa chọn",
    literal_error: "chưa đúng lựa chọn",
    greater_than_equal: "quá nhỏ",
    greater_than: "quá nhỏ",
    less_than_equal: "quá lớn"
  };

  function fromString(s) {
    var t = String(s || "").trim();
    if (!t) return "";
    for (var i = 0; i < KNOWN.length; i++) if (KNOWN[i][0].test(t)) return KNOWN[i][1];
    return t;
  }

  function fromValidationList(list) {
    var parts = [];
    for (var i = 0; i < list.length && parts.length < 3; i++) {
      var it = list[i] || {};
      if (typeof it === "string") { parts.push(fromString(it)); continue; }
      var loc = Array.isArray(it.loc) ? it.loc : [];
      var field = "";
      for (var j = loc.length - 1; j >= 0; j--) {
        if (typeof loc[j] === "string" && loc[j] !== "body" && loc[j] !== "query") { field = loc[j]; break; }
      }
      var label = FIELD_VI[field] || field || "dữ liệu";
      var why = TYPE_VI[it.type] || (it.type && String(it.type).indexOf("enum") >= 0 ? TYPE_VI.enum : "chưa hợp lệ");
      parts.push(label + " " + why);
    }
    return parts.length ? "Thông tin chưa hợp lệ: " + parts.join("; ") + "." : "";
  }

  function fromAny(d) {
    if (d === null || d === undefined) return "";
    if (typeof d === "string") return fromString(d);
    if (Array.isArray(d)) return fromValidationList(d);
    if (typeof d === "object") {
      if (d.error_code && CODES[d.error_code] && !d.message) return CODES[d.error_code];
      return fromAny(d.message) || fromAny(d.reply) || fromAny(d.error) || fromAny(d.detail) ||
        (d.error_code && CODES[d.error_code]) || "";
    }
    return String(d);
  }

  function message(body, fallback, status) {
    var m = "";
    try {
      m = body && typeof body === "object" ? fromAny(body.detail) || fromAny(body.error) || fromAny(body.message) || fromAny(body.reply) : fromAny(body);
    } catch (_e) { m = ""; }
    if (!m || m === "[object Object]") {
      if (status === 429) m = CODES.RATE_LIMITED;
      else if (status === 401) m = CODES.AUTH_REQUIRED;
      else if (status === 403) m = CODES.FORBIDDEN;
      else if (status >= 500) m = "Hệ thống đang bận — vui lòng thử lại sau.";
    }
    return m || fallback || "Đã có lỗi — vui lòng thử lại.";
  }

  async function fromResponse(r, fallback) {
    var body = null;
    try { body = await r.clone().json(); } catch (_e) { body = null; }
    return message(body, fallback, r && r.status);
  }

  w.WeloraErrors = { message: message, fromResponse: fromResponse };
})(typeof window !== "undefined" ? window : this);
