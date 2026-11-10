// PWA service worker (root scope).
// - Navigations: network-first; internet na ho to /offline/ page dikhata hai.
// - Static files (/static/): stale-while-revalidate, taake app tez khule.
// - Tesseract (OCR) files: cache-first (purani behaviour).
// - POST / admin / api / login / media: kabhi cache nahi hotay, isliye data stale nahi hoga.
var VERSION = 'v2';
var SHELL = 'bms-shell-' + VERSION;
var STATIC = 'bms-static-' + VERSION;
var TESS_CACHE = 'tesseract-v1';
var OFFLINE_URL = '/offline/';

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(SHELL).then(function (c) { return c.add(new Request(OFFLINE_URL, {cache: 'reload'})); })
      .catch(function () {})
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return (k.indexOf('bms-') === 0 && k !== SHELL && k !== STATIC) ||
               (k.indexOf('tesseract-') === 0 && k !== TESS_CACHE);
      }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

function isNever(path) {
  return /^\/(admin|api|ajax|login|logout|security|media)\//.test(path) || path === '/login/';
}

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // OCR files: cache-first
  if (url.pathname.indexOf('/tesseract/') !== -1) {
    event.respondWith(caches.open(TESS_CACHE).then(function (cache) {
      return cache.match(req).then(function (hit) {
        return hit || fetch(req).then(function (res) {
          if (res && res.ok) cache.put(req, res.clone());
          return res;
        });
      });
    }));
    return;
  }

  // Static files: stale-while-revalidate
  if (url.pathname.indexOf('/static/') === 0) {
    event.respondWith(caches.open(STATIC).then(function (cache) {
      return cache.match(req).then(function (hit) {
        var net = fetch(req).then(function (res) {
          if (res && res.ok) cache.put(req, res.clone());
          return res;
        }).catch(function () { return hit; });
        return hit || net;
      });
    }));
    return;
  }

  // Page navigations: network-first, offline fallback
  if (req.mode === 'navigate' && !isNever(url.pathname)) {
    event.respondWith(fetch(req).catch(function () {
      return caches.match(OFFLINE_URL);
    }));
  }
});
