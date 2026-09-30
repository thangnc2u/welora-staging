/* Welora service worker — PAY-05 renewal push only (no caching / offline logic).
 * Served at /app/sw.js (scope /app/). Payload is decrypted by the browser
 * (RFC 8291); we only render it. Click opens same-origin URLs only. */
"use strict";

self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (event) { event.waitUntil(self.clients.claim()); });

function safeUrl(raw) {
  try {
    var u = new URL(raw || "/app/my-plan", self.location.origin);
    if (u.origin !== self.location.origin) return "/app/my-plan";
    return u.href;
  } catch (_e) {
    return "/app/my-plan";
  }
}

self.addEventListener("push", function (event) {
  var d = {};
  try { d = event.data ? event.data.json() : {}; } catch (_e) { d = { body: event.data ? event.data.text() : "" }; }
  var title = String(d.title || "Welora");
  event.waitUntil(self.registration.showNotification(title, {
    body: String(d.body || ""),
    tag: "welora-renewal",
    renotify: true,
    data: { url: safeUrl(d.url) }
  }));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var url = safeUrl(event.notification.data && event.notification.data.url);
  event.waitUntil(self.clients.openWindow(url));
});
