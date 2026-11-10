// PWA service worker (root scope).
// - Navigations: network-first; internet na ho to /offline/ page dikhata hai.
// - Shop browse pages (home, stores, store/product detail, info pages): network-first, offline mein saved copy.
// - Rider pages (orders list, history, earnings, order detail): network-first, offline mein saved copy (sirf dekhne ke liye).
// - Product images (/media/): stale-while-revalidate, limited.
// - /static/: stale-while-revalidate.  Tesseract (OCR): cache-first.
// - POS screen (/sales/pos/) + CDN scripts/styles (bootstrap etc.): offline POS ke liye save hotay hain.
// - POST / admin / api / cart / checkout / account / login kabhi cache nahi hotay.
// - Logout par saved pages foran delete ho jati hain (shared phone par data na rahe).
// - Navigation preload: page ki request SW start hone ke saath hi chal padti hai (tez load).
// - Prefetch: user jis link par hath/touch rakhe uska page pehle se 60 sec ke liye save (sirf shop browse pages).
// - Storage hisaab: purani cache entries khud delete; jagah kam ho to media/pages kam kar deta hai.
var VERSION = 'v6';   // har release par badlein (cache refresh)
var SHELL = 'bms-shell-' + VERSION;
var STATIC = 'bms-static-' + VERSION;
var SHOP = 'bms-shop-' + VERSION;
var RIDER = 'bms-rider-' + VERSION;
var MEDIA = 'bms-media-' + VERSION;
var POS = 'bms-pos-' + VERSION;
var CDN = 'bms-cdn-' + VERSION;
var PREFETCH = 'bms-prefetch-' + VERSION;
var PREFETCH_TTL = 60 * 1000;
var CDN_HOSTS = ['cdn.jsdelivr.net', 'code.jquery.com', 'unpkg.com', 'cdnjs.cloudflare.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];
var TESS_CACHE = 'tesseract-v1';
var OFFLINE_URL = '/offline/';
var KEEP = [SHELL, STATIC, SHOP, RIDER, MEDIA, POS, CDN, PREFETCH];

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
  if (event.data && event.data.type === 'CLEANUP') event.waitUntil(cleanup());
  if (event.data && event.data.type === 'CLEAR_CACHE') event.waitUntil(clearAll());
  if (event.data && event.data.type === 'PREFETCH') event.waitUntil(prefetchPage(event.data.url));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return (k.indexOf('bms-') === 0 && KEEP.indexOf(k) === -1) ||
               (k.indexOf('tesseract-') === 0 && k !== TESS_CACHE);
      }).map(function (k) { return caches.delete(k); }));
    }).then(function () {
      return self.registration.navigationPreload ? self.registration.navigationPreload.enable() : null;
    }).then(function () { return cleanup().catch(function () {}); })
      .then(function () { return self.clients.claim(); })
  );
});

function clearPages() {
  return Promise.all([caches.delete(SHOP), caches.delete(RIDER), caches.delete(POS), caches.delete(PREFETCH)]);
}

function clearAll() {   // "Cache saaf karein" - offline page (SHELL) rehta hai
  return Promise.all([caches.delete(SHOP), caches.delete(RIDER), caches.delete(POS), caches.delete(PREFETCH),
                      caches.delete(MEDIA), caches.delete(STATIC), caches.delete(CDN)]);
}

// ---- Storage hisaab ------------------------------------------------------
function ageOf(res) {
  var d = res.headers.get('date');
  var t = d ? Date.parse(d) : 0;
  return t ? Date.now() - t : 0;
}

function purgeOld(name, maxAge) {   // maxAge (ms) se purani entries delete
  return caches.open(name).then(function (c) {
    return c.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        return c.match(k).then(function (r) { if (r && ageOf(r) > maxAge) return c.delete(k); });
      }));
    });
  });
}

function storageUsage() {
  if (!(navigator.storage && navigator.storage.estimate)) return Promise.resolve({usage: 0, quota: 0});
  return navigator.storage.estimate().then(function (e) { return {usage: e.usage || 0, quota: e.quota || 0}; });
}

function cleanup() {
  var DAY = 864e5;
  return Promise.all([
    purgeOld(MEDIA, 14 * DAY), purgeOld(SHOP, 7 * DAY), purgeOld(RIDER, 3 * DAY),
    purgeOld(STATIC, 30 * DAY), purgeOld(POS, 30 * DAY), purgeOld(PREFETCH, 5 * 60 * 1000)
  ]).then(storageUsage).then(function (u) {
    if (!u.quota) return;
    var used = u.usage / u.quota;
    if (used > 0.9) return Promise.all([caches.delete(MEDIA), caches.delete(SHOP), caches.delete(RIDER), trim(STATIC, 100)]);
    if (used > 0.7) return Promise.all([trim(MEDIA, 60), trim(SHOP, 20), trim(RIDER, 10), trim(STATIC, 150)]);
  });
}

// ---- Prefetch (shop browse pages) -----------------------------------------
function prefetchPage(rawUrl) {
  var u;
  try { u = new URL(rawUrl, self.location.origin); } catch (e) { return Promise.resolve(); }
  if (u.origin !== self.location.origin || u.search || !SHOP_PAGES.test(u.pathname)) return Promise.resolve();
  var key = new Request(u.pathname);
  return caches.open(PREFETCH).then(function (c) {
    return c.match(key).then(function (hit) {
      if (hit && Date.now() - (+hit.headers.get('X-Prefetched-At') || 0) < PREFETCH_TTL) return;
      return fetch(u.pathname, {credentials: 'same-origin', headers: {'X-Purpose': 'prefetch'}}).then(function (res) {
        if (!res || !res.ok || res.redirected || res.type !== 'basic' || !isHtml(res)) return;
        return res.blob().then(function (b) {
          return c.put(key, new Response(b, {status: 200, headers: {
            'Content-Type': res.headers.get('Content-Type'), 'X-Prefetched-At': String(Date.now())}}));
        }).then(function () { return trim(PREFETCH, 8); });
      });
    });
  }).catch(function () {});
}

function prefetched(path) {   // 60 sec ke andar ka saved page (ek hi dafa use hota hai)
  return caches.open(PREFETCH).then(function (c) {
    var key = new Request(path);
    return c.match(key).then(function (hit) {
      if (!hit) return null;
      return c.delete(key).then(function () {
        return Date.now() - (+hit.headers.get('X-Prefetched-At') || 0) < PREFETCH_TTL ? hit : null;
      });
    });
  }).catch(function () { return null; });
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
function pageStrategy(req, cacheName, max, noBar, preload) {
  return Promise.resolve(preload).then(function (p) { return p || fetch(req); }).then(function (res) {
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
  if (req.method !== 'GET') { event.waitUntil(caches.delete(PREFETCH)); return; }   // cart/order badla - pehle se load page purana ho sakta hai
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
  if ((path.indexOf('/media/') === 0 || path.indexOf('/img/') === 0) && req.destination === 'image') {
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
  var pre = event.preloadResponse;   // navigation preload (agar browser support kare)
  if (path === '/sales/pos/') { event.respondWith(pageStrategy(req, POS, 3, true, pre)); return; }
  if (RIDER_PAGES.test(path)) { event.respondWith(pageStrategy(req, RIDER, 30, false, pre)); return; }
  if (SHOP_PAGES.test(path)) {
    event.respondWith(prefetched(path).then(function (hit) {
      if (hit) { event.waitUntil(Promise.resolve(pre).catch(function () {})); return hit; }
      return pageStrategy(req, SHOP, 60, false, pre);
    }));
    return;
  }

  // Baqi pages: network, warna offline page
  if (!/^\/(admin|api|ajax|login|logout|security|media)\//.test(path) && path !== '/login/') {
    event.respondWith(Promise.resolve(pre).then(function (p) { return p || fetch(req); })
      .catch(function () { return caches.match(OFFLINE_URL); }));
  }
});
