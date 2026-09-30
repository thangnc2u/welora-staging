/* PAY-05 renewal reminders via Web Push — opt-in button on /app/my-plan.
 * Hidden unless the browser supports Push and the server has VAPID keys. */
(function () {
  "use strict";
  var box = document.getElementById("pushCard");
  var btn = document.getElementById("pushBtn");
  var msg = document.getElementById("pushMsg");
  if (!box || !btn || !("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return;

  function token() { try { return localStorage.getItem("welora_token") || ""; } catch (_e) { return ""; } }
  function say(t) { msg.textContent = t || ""; }
  function keyBytes(b64) {
    var s = (b64 + "===".slice((b64.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
    var raw = atob(s), out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }
  function send(method, sub) {
    return fetch("/api/push/v1/subscriptions", {
      method: method,
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + token() },
      body: JSON.stringify(method === "DELETE" ? { endpoint: sub.endpoint } : sub.toJSON())
    }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }

  fetch("/api/push/v1/vapid-public-key").then(function (r) { return r.json(); }).then(function (cfg) {
    if (!cfg || !cfg.enabled || !cfg.public_key) return;
    box.hidden = false;
    navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" }).then(function (reg) {
      return reg.pushManager.getSubscription().then(function (existing) {
        var on = !!existing;
        btn.textContent = on ? "Tắt thông báo nhắc gia hạn" : "Bật thông báo nhắc gia hạn";
        btn.addEventListener("click", function () {
          btn.disabled = true;
          var p = on
            ? reg.pushManager.getSubscription().then(function (s) {
                if (!s) return null;
                return send("DELETE", s).then(function () { return s.unsubscribe(); });
              }).then(function () { on = false; say("Đã tắt thông báo."); })
            : Notification.requestPermission().then(function (perm) {
                if (perm !== "granted") throw new Error("Bạn chưa cho phép thông báo trong trình duyệt.");
                return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(cfg.public_key) });
              }).then(function (s) { return send("POST", s); }).then(function () { on = true; say("Đã bật: Welora sẽ nhắc trước khi gói hết hạn."); });
          p.catch(function (e) { say(e.message || "Không bật được thông báo."); }).then(function () {
            btn.disabled = false;
            btn.textContent = on ? "Tắt thông báo nhắc gia hạn" : "Bật thông báo nhắc gia hạn";
          });
        });
      });
    }).catch(function () { box.hidden = true; });
  }).catch(function () { /* push unavailable → stay hidden (email reminders still sent) */ });
})();
