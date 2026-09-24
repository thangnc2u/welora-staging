/* Welora — shared friendly VN labels (UI/copy ONLY).
 * Never dump raw snake/tech IDs to user-visible chrome.
 * Unknown keys → "—" (not the raw key).
 */
(function (global) {
  "use strict";

  var GOAL_TYPE = {
    emergency_fund: "Quỹ khẩn cấp",
    debt_payoff: "Trả nợ",
    savings: "Tiết kiệm",
    investment: "Đầu tư",
  };

  var ACT_KIND = {
    lock_envelope: "Khóa phong bì",
    create_envelope: "Tạo phong bì",
    change_envelope_ceiling: "Đổi trần phong bì",
    schedule_bh_reminder: "Nhắc bảo hiểm",
    open_estate_checklist: "Mở checklist di sản",
    withdraw_emergency_fund: "Rút quỹ khẩn cấp",
  };

  var CATEGORY_TAG = {
    an_uong: "ăn uống",
    sieu_thi: "siêu thị",
    nha_o: "nhà ở",
    bao_hiem: "bảo hiểm",
    di_chuyen: "di chuyển",
    giai_tri: "giải trí",
    "ho-tro-gia-dinh": "hỗ trợ gia đình",
    hoc_phi: "học phí",
    hoc_phi_con: "học phí con",
    pyf: "trả cho mình trước",
    tra_no: "trả nợ",
    dien_nuoc: "điện nước",
    luong: "lương",
    mua_sam: "mua sắm",
    khac: "khác",
    quy_khan_cap: "quỹ khẩn cấp",
  };

  /* VN display → latin slug (for form input round-trip) */
  var CATEGORY_TAG_REVERSE = {};
  Object.keys(CATEGORY_TAG).forEach(function (slug) {
    CATEGORY_TAG_REVERSE[CATEGORY_TAG[slug]] = slug;
    CATEGORY_TAG_REVERSE[CATEGORY_TAG[slug].toLowerCase()] = slug;
  });

  var MODE_C = {
    chip: "Chế độ Hành động",
    confirm_summary: "Xác nhận hành động",
    cancelled: "Đã hủy hành động.",
    confirmed_prefix: "Đã xác nhận hành động — OS đã cập nhật.",
    undone: "Đã hoàn tác hành động trong 24 giờ.",
    dual_hint: "Chờ đồng kiểm 2 người — mở Điều hành · Đồng kiểm để người đồng hành xác nhận.\n→ Đồng kiểm",
    attach_hint: "→ Gắn người đồng hành tại Đồng kiểm",
    section_title: "Gợi ý chế độ Hành động",
    section_body:
      "Trong Chat (chế độ Hành động), thử: «Khóa phong bì», «Đổi trần phong bì 20000000», «Mở checklist di sản». Thiếu người đồng hành → bị từ chối; đã gắn → chờ xác nhận tại đây.",
  };

  var AUTH = {
    reset_token_label: "Mã đặt lại mật khẩu",
    reset_token_stub: "Mã đặt lại (bản staging)",
    forgot_intro:
      "Staging MVP · mã thử (không gửi email/SMS). Nhận mã đặt lại rồi đổi mật khẩu.",
    reset_intro: "Dùng mã đặt lại từ bước quên mật khẩu (bản staging thử nghiệm).",
    reset_needed: "Cần mã đặt lại mật khẩu",
    guest_demo: "Khách / demo · chỉ cần email hoặc SĐT + mật khẩu",
    auth_tabs_aria: "Thẻ đăng nhập",
  };

  var OBS = {
    open_banking: "Kết nối ngân hàng",
    split: "tách dòng",
    split_title: "Tách dòng — tuỳ chọn",
    split_add: "+ Thêm dòng tách",
    split_pill: "Tách dòng",
    rollover: "chuyển số dư",
    rollover_btn: "Đóng kỳ / chuyển số dư",
    merchant: "Cửa hàng / ứng dụng (tuỳ chọn)",
    date: "Ngày",
    pyf: "Trả cho mình trước",
    persona_demo: "Chân dung demo",
    module: "Chương",
    reviewed: "Đã duyệt",
    take_home: "thu nhập",
  };

  function _pick(map, k, fallback) {
    if (k == null || k === "") return fallback != null ? fallback : "—";
    var key = String(k);
    if (Object.prototype.hasOwnProperty.call(map, key)) return map[key];
    return fallback != null ? fallback : "—";
  }

  function labelGoalType(k) {
    return _pick(GOAL_TYPE, k, "—");
  }

  function labelActKind(k) {
    return _pick(ACT_KIND, k, "—");
  }

  function labelCategoryTag(k) {
    return _pick(CATEGORY_TAG, k, "—");
  }

  function labelCategoryTags(tags) {
    if (!tags || !tags.length) return "";
    return tags
      .map(function (t) {
        return labelCategoryTag(t);
      })
      .filter(function (x) {
        return x && x !== "—";
      })
      .join(", ");
  }

  function slugCategoryTag(displayOrSlug) {
    var s = String(displayOrSlug || "").trim();
    if (!s) return "";
    if (CATEGORY_TAG_REVERSE[s] || CATEGORY_TAG_REVERSE[s.toLowerCase()]) {
      return CATEGORY_TAG_REVERSE[s] || CATEGORY_TAG_REVERSE[s.toLowerCase()];
    }
    if (Object.prototype.hasOwnProperty.call(CATEGORY_TAG, s)) return s;
    return s;
  }

  function friendlyModeChip(chip) {
    if (!chip || /Mode\s*C/i.test(String(chip))) return MODE_C.chip;
    return String(chip);
  }

  function friendlyNote(note) {
    if (!note) return "";
    var n = String(note);
    if (/Pay Yourself First/i.test(n)) return OBS.pyf;
    return n;
  }

  var api = {
    GOAL_TYPE: GOAL_TYPE,
    ACT_KIND: ACT_KIND,
    CATEGORY_TAG: CATEGORY_TAG,
    MODE_C: MODE_C,
    AUTH: AUTH,
    OBS: OBS,
    labelGoalType: labelGoalType,
    labelActKind: labelActKind,
    labelCategoryTag: labelCategoryTag,
    labelCategoryTags: labelCategoryTags,
    slugCategoryTag: slugCategoryTag,
    friendlyModeChip: friendlyModeChip,
    friendlyNote: friendlyNote,
  };

  global.WeloraLabels = api;
  /* convenience globals for inline pages */
  global.labelGoalType = labelGoalType;
  global.labelActKind = labelActKind;
  global.labelCategoryTag = labelCategoryTag;
  global.labelCategoryTags = labelCategoryTags;
})(typeof window !== "undefined" ? window : this);
