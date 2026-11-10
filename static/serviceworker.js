// PWA service worker (root scope).
// - Navigations: network-first; internet na ho to /offline/ page dikhata hai.
// - Shop browse pages (home, stores, store/product detail, info pages): network-first, offline mein saved copy.
// - Rider pages (orders list, history, earnings, order detail): network-first, offline mein saved copy (sirf dekhne ke liye).
// - Product images (/media/): stale-while-revalidate, limited.
// - /static/: stale-while-revalidate.  Tesseract (OCR): cache-first.
// - POS screen (/sales/pos/) + CDN scripts/styles (bootstrap etc.): offline POS ke liye save hotay hain.
// - POST / admin / api / cart / checkout / account / login kabhi cache nahi hotay.
// - Logout par saved pages foran delete ho jati hain (shared phone par data na rahe).
var VERSION = 'v5';   // har release par badlein (cache refresh)
var SHELL = 'bms-shell-' + VERSION;
var STATIC = 'bms-static-' + VERSION;
var SHOP = 'bms-shop-' + VERSION;
var RIDER = 'bms-rider-' + VERSION;
var MEDIA = 'bms-media-' + VERSION;
var POS = 'bms-pos-' + VERSION;
var CDN = 'bms-cdn-' + VERSION;
var CDN_HOSTS = ['cdn.jsdelivr.net', 'code.jquery.com', 'unpkg.com', 'cdnjs.cloudflare.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];
var TESS_CACHE = 'tesseract-v1';
var OFFLINE_URL = '/offline/';
var KEEP = [SHELL, STATIC, SHOP, RIDER, MEDIA, POS, CDN];

// Sirf yehi pages offline save hotay hain (exact patterns).
var SHOP_PAGES = /^\/shop\/(?:|stores\/|stores\/\d+\/|product\/\d+\/|faq\/|help\/|about\/|terms\/|privacy\/|returns\/)$/;
var RIDER_PAGES = /^\/shop\/rider\/(?:|history\/|earnings\/|manage\/|manage\/\d+\/)$/;
var LOGOUT = /^\/(?:logout|logout-redirect|shop\/(?:rider|vendor|customer)\/logout|shop\/logout|accounts\/logout|investor\/logout)\/?$/;

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(SHELL).then(function (c) { return c.add(new Request(OFFLINE_URL, {cache: 'reload'})); })
      .catch(function () {})
    // skipWaiting yahan nahi: naya version tab lagta hai jab user page par "Refresh" dabaye.
  );
});

self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
  if (event.data && event.data.type === 'CLEAR_PAGES') clearPages();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return (k.indexOf('bms-') === 0 && KEEP.indexOf(k) === -1) ||
               (k.indexOf('tesseract-') === 0 && k !== TESS_CACHE);
      }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

function clearPages() {
  return Promise.all([caches.delete(SHOP), caches.delete(RIDER), caches.delete(POS)]);
}

function trim(name, max) {
  return caches.open(name).then(function (c) {
    return c.keys().then(function (keys) {
      if (keys.length > max) return c.delete(keys[0]).then(function () { return trim(name, max); });
    });
  });
}

function isHtml(res) {
  var ct = res.headers.get('Content-Type') || '';
  return ct.indexOf('text/html') !== -1;
}

function offlineCopy(res, noBar) {   // saved page + chhota "Offline" bar
  if (noBar) return res.text().then(function (t) { return new Response(t, {status: 200, headers: {'Content-Type': 'text/html; charset=utf-8'}}); });
  return res.text().then(function (t) {
    var bar = '<div style="position:sticky;top:0;z-index:99999;background:#92400e;color:#fff;text-align:center;' +
      'padding:6px 10px;font:13px system-ui,sans-serif">📡 Offline — saved copy dikh rahi hai</div>';
    t = /<body[^>]*>/i.test(t) ? t.replace(/<body[^>]*>/i, function (m) { return m + bar; }) : bar + t;
    return new Response(t, {status: 200, headers: {'Content-Type': 'text/html; charset=utf-8'}});
  });
}

// Network-first page with saved-copy fallback.
function pageStrategy(req, cacheName, max, noBar) {
  return fetch(req).then(function (res) {
    if (res && res.ok && !res.redirected && res.type === 'basic' && isHtml(res)) {
      var copy = res.clone();
      caches.open(cacheName).then(function (c) { return c.put(req, copy); }).then(function () { return trim(cacheName, max); });
    }
    return res;
  }).catch(function () {
    return caches.open(cacheName).then(function (c) { return c.match(req); }).then(function (hit) {
      return hit ? offlineCopy(hit, noBar) : caches.match(OFFLINE_URL);
    });
  });
}

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) {
    // CDN files (bootstrap, icons, jquery...): stale-while-revalidate, taake POS offline bhi sahi dikhe
    if (CDN_HOSTS.indexOf(url.hostname) !== -1) {
      event.respondWith(caches.open(CDN).then(function (cache) {
        return cache.match(req).then(function (hit) {
          var net = fetch(req).then(function (res) {
            if (res && (res.ok || res.type === 'opaque')) cache.put(req, res.clone());
            return res;
          }).catch(function () { return hit; });
          return hit || net;
        });
      }));
    }
    return;
  }
  var path = url.pathname;

  // Logout: saved pages delete, request normal chale
  if (LOGOUT.test(path)) { event.waitUntil(clearPages()); return; }

  // OCR files: cache-first
  if (path.indexOf('/tesseract/') !== -1) {
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
  if (path.indexOf('/static/') === 0) {
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

  // Product images: stale-while-revalidate (limit 150)
  if (path.indexOf('/media/') === 0 && req.destination === 'image') {
    event.respondWith(caches.open(MEDIA).then(function (cache) {
      return cache.match(req).then(function (hit) {
        var net = fetch(req).then(function (res) {
          if (res && res.ok) { cache.put(req, res.clone()); trim(MEDIA, 150); }
          return res;
        }).catch(function () { return hit; });
        return hit || net;
      });
    }));
    return;
  }

  if (req.mode !== 'navigate') return;

  // Rider pages / Shop browse pages: saved copy offline
  if (path === '/sales/pos/') { event.respondWith(pageStrategy(req, POS, 3, true)); return; }
  if (RIDER_PAGES.test(path)) { event.respondWith(pageStrategy(req, RIDER, 30)); return; }
  if (SHOP_PAGES.test(path)) { event.respondWith(pageStrategy(req, SHOP, 60)); return; }

  // Baqi pages: network, warna offline page
  if (!/^\/(admin|api|ajax|login|logout|security|media)\//.test(path) && path !== '/login/') {
    event.respondWith(fetch(req).catch(function () { return caches.match(OFFLINE_URL); }));
  }
});
