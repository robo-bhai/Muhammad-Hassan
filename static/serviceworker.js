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
// - Push: notification (vibration, action buttons, urgent order alerts) + icon par badge; click par sahi app window khulti hai.
// - Storage hisaab: purani cache entries khud delete; jagah kam ho to media/pages kam kar deta hai.
var VERSION = 'v11';   // har release par badlein (cache refresh)
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

// ---- Server restart (Cloudflare 502/503/504/52x/530) ----------------------
// Server restart ke dauran tunnel network error nahi deta, balkay ek error response deta hai.
// Isay pakar kar "restart ho raha hai" page dikhate hain jo server wapas aate hi khud reload karta hai.
function isServerDown(res) {
  var c = res && res.status;
  return c === 502 || c === 503 || c === 504 || (c >= 520 && c <= 530);
}

var RESTART_HTML = "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"theme-color\" content=\"#0d6efd\">\n<title>Updating...</title><style>\n:root{--bg1:#eef3ff;--bg2:#f8fbff;--tx:#0f172a;--mu:#64748b;--card:rgba(255,255,255,.8);--pri:#0d6efd;--pri2:#6ea8fe}\n@media(prefers-color-scheme:dark){:root{--bg1:#0b1220;--bg2:#111a2e;--tx:#e5ecff;--mu:#94a3b8;--card:rgba(22,33,58,.8);--pri:#6ea8fe;--pri2:#0d6efd}}\n*{box-sizing:border-box}\nbody{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;overflow:hidden;position:relative;font-family:system-ui,-apple-system,\"Segoe UI\",Roboto,sans-serif;color:var(--tx);background:linear-gradient(135deg,var(--bg1),var(--bg2))}\n.blob{position:absolute;border-radius:50%;filter:blur(60px);opacity:.35;animation:float 9s ease-in-out infinite}\n.b1{width:260px;height:260px;background:var(--pri);top:-60px;left:-60px}\n.b2{width:300px;height:300px;background:var(--pri2);bottom:-90px;right:-70px;animation-delay:-4s}\n@keyframes float{50%{transform:translate(30px,25px) scale(1.1)}}\n.card{position:relative;z-index:1;width:100%;max-width:380px;text-align:center;padding:34px 26px 24px;border-radius:24px;background:var(--card);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border:1px solid rgba(127,150,200,.25);box-shadow:0 20px 50px rgba(13,110,253,.15);animation:rise .6s ease both}\n@keyframes rise{from{opacity:0;transform:translateY(16px)}}\n.orb{position:relative;width:112px;height:112px;margin:0 auto 16px}\n.orb i{position:absolute;inset:0;border-radius:50%;border:3px solid transparent}\n.orb i:nth-child(1){border-top-color:var(--pri);animation:spin 1.2s linear infinite}\n.orb i:nth-child(2){inset:11px;border-right-color:var(--pri2);animation:spin 1.8s linear infinite reverse}\n.orb i:nth-child(3){inset:22px;border-bottom-color:var(--pri);opacity:.6;animation:spin 2.4s linear infinite}\n.orb b{position:absolute;inset:40px;border-radius:50%;background:radial-gradient(circle,var(--pri2),var(--pri));box-shadow:0 0 22px var(--pri);animation:pulse 1.6s ease-in-out infinite}\n@keyframes spin{to{transform:rotate(360deg)}}\n@keyframes pulse{50%{transform:scale(.7);opacity:.7}}\n.logo{position:absolute;left:32px;top:32px;width:48px;height:48px;border-radius:50%;object-fit:contain;background:#fff;padding:4px;box-shadow:0 0 22px var(--pri);animation:breathe 2s ease-in-out infinite}\n@keyframes breathe{50%{transform:scale(.92)}}\n.brand{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mu);margin:0 0 8px}\nh1{font-size:21px;margin:0 0 6px}\n.sub{color:var(--mu);font-size:14px;line-height:1.55;margin:0 0 16px}\n.msg{height:20px;font-size:14px;font-weight:600;color:var(--pri);transition:opacity .35s}\n.bar{height:6px;border-radius:99px;background:rgba(127,150,200,.2);margin:14px 0 8px;overflow:hidden}\n.bar span{display:block;height:100%;width:40%;border-radius:99px;background:linear-gradient(90deg,var(--pri),var(--pri2));animation:slide 1.5s ease-in-out infinite}\n@keyframes slide{0%{transform:translateX(-110%)}100%{transform:translateX(280%)}}\n.time{font-size:12px;color:var(--mu)}\nbutton{margin-top:14px;background:transparent;color:var(--pri);border:1px solid var(--pri);border-radius:10px;padding:9px 20px;font-size:14px;cursor:pointer}\n@media(prefers-reduced-motion:reduce){*{animation-duration:.01ms!important;animation-iteration-count:1!important}}\n</style></head><body>\n<div class=\"blob b1\"></div><div class=\"blob b2\"></div>\n<div class=\"card\">\n<div class=\"orb\"><i></i><i></i><i></i>__CORE__</div>\n__NAME__\n<h1>System update ho raha hai</h1>\n<p class=\"sub\">Chand lamhon mein dobara hazir. Ye page khud khul jayega, refresh ki zaroorat nahi.</p>\n<div class=\"msg\" id=\"m\">Server tayyar ho raha hai...</div>\n<div class=\"bar\"><span></span></div>\n<div class=\"time\" id=\"t\">Intezar: 0:00</div>\n<button onclick=\"location.reload()\">Abhi try karein</button>\n</div>\n<script>(function(){\nvar M=[\"Server tayyar ho raha hai...\",\"Connection check ho raha hai...\",\"Data load ho raha hai...\",\"Bas thori der aur...\"];\nvar i=0,ok=false,t0=Date.now(),m=document.getElementById(\"m\"),tm=document.getElementById(\"t\");\nsetInterval(function(){if(ok)return;m.style.opacity=0;setTimeout(function(){if(ok)return;i=(i+1)%M.length;m.textContent=M[i];m.style.opacity=1;},350);},3000);\nsetInterval(function(){var s=Math.floor((Date.now()-t0)/1000);tm.textContent=\"Intezar: \"+Math.floor(s/60)+\":\"+(\"0\"+s%60).slice(-2);},1000);\nfunction ping(){fetch(\"/offline/?ping=\"+Date.now(),{cache:\"no-store\",credentials:\"same-origin\"}).then(function(r){\nif(r.status<500){ok=true;m.style.opacity=1;m.textContent=\"Server wapas aa gaya!\";setTimeout(function(){location.reload();},500);}else wait();}).catch(wait);}\nfunction wait(){setTimeout(ping,4000);}\nwindow.addEventListener(\"online\",function(){location.reload();});\nwait();})();</script></body></html>";

// Company logo + naam: server chalta ho tab cache mein rakh lete hain, restart page par dikhate hain.
var BRAND_DONE = {};
function portalOf(path) {   // app/pwa_portals.py ki PORTALS ke mutabiq
  if (/^\/shop\/rider\//.test(path)) return 'rider';
  if (/^\/shop\/vendor\//.test(path)) return 'vendor';
  if (/^\/shop\//.test(path)) return 'shop';
  if (/^\/(?:investor|shareholder|shareholders\/portal)\//.test(path)) return 'investor';
  return 'erp';
}

function warmBrand(portal) {   // har SW session mein har portal ke liye ek dafa
  if (BRAND_DONE[portal]) return Promise.resolve();
  BRAND_DONE[portal] = 1;
  var mUrl = '/pwa/manifest/' + portal + '.json', iUrl = '/pwa/icon/' + portal + '/192.png';
  return caches.open(SHELL).then(function (c) {
    return Promise.all([
      fetch(mUrl, {credentials: 'same-origin'}).then(function (r) { if (r && r.ok) return c.put(mUrl, r); }),
      fetch(iUrl, {credentials: 'same-origin'}).then(function (r) { if (r && r.ok) return c.put(iUrl, r); })
    ]);
  }).catch(function () { BRAND_DONE[portal] = 0; });
}

function brandInfo(portal) {
  var out = {name: '', logo: ''};
  return caches.open(SHELL).then(function (c) {
    return Promise.all([c.match('/pwa/manifest/' + portal + '.json'), c.match('/pwa/icon/' + portal + '/192.png')]);
  }).then(function (a) {
    var p1 = a[0] ? a[0].json().then(function (j) { out.name = String((j && j.name) || ''); }).catch(function () {}) : Promise.resolve();
    var p2 = (a[1] && (a[1].headers.get('Content-Type') || '').indexOf('image/') === 0)
      ? a[1].arrayBuffer().then(function (buf) {
          var b = new Uint8Array(buf), s = '';
          for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
          out.logo = 'data:image/png;base64,' + btoa(s);
        }).catch(function () {}) : Promise.resolve();
    return Promise.all([p1, p2]);
  }).then(function () { return out; }, function () { return out; });
}

function escHtml(t) {
  return String(t).replace(/[&<>"']/g, function (ch) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch];
  });
}

function restartingPage(req) {   // promise -> Response
  var path = '/';
  try { path = new URL(req.url).pathname; } catch (e) {}
  return brandInfo(portalOf(path)).then(function (b) {
    var core = b.logo ? '<img class="logo" alt="" src="' + b.logo + '">' : '<b></b>';
    var name = b.name ? '<div class="brand">' + escHtml(b.name) + '</div>' : '';
    var html = RESTART_HTML.replace('__CORE__', function () { return core; })
                           .replace('__NAME__', function () { return name; });
    return new Response(html, {status: 503, headers: {
      'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Retry-After': '10'}});
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
    if (isServerDown(res)) {   // restart: POS saved copy dikhaye, baqi pages par auto-reload wala page
      if (cacheName !== POS) return restartingPage(req);
      return caches.open(cacheName).then(function (c) { return c.match(req); }).then(function (hit) {
        return hit ? offlineCopy(hit, noBar) : restartingPage(req);
      });
    }
    if (res && res.ok && !res.redirected && res.type === 'basic' && isHtml(res)) {
      try { warmBrand(portalOf(new URL(req.url).pathname)); } catch (e) {}
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
      .then(function (res) {
        if (isServerDown(res)) return restartingPage(req);
        if (res && res.ok) event.waitUntil(warmBrand(portalOf(path)));   // logo/naam restart page ke liye save
        return res;
      })
      .catch(function () { return caches.match(OFFLINE_URL); }));
  }
});


// ---- Rider location queue (Background Sync) --------------------------------
// Offline mein page ne point IndexedDB 'rider-loc' mein rakhi; internet aate hi browser 'sync' chalata hai.
// Server sirf aakhri location rakhta hai, isliye sab se nayi point bheji jati hai.
var LOC_DB = 'rider-loc', LOC_ST = 'q', LOC_TAG = 'rider-loc-sync';

function locLatest() {
  return new Promise(function (res) {
    var r = indexedDB.open(LOC_DB, 1);
    r.onupgradeneeded = function () { r.result.createObjectStore(LOC_ST, {autoIncrement: true}); };
    r.onerror = function () { res(null); };
    r.onsuccess = function () {
      var db = r.result, cur = db.transaction(LOC_ST).objectStore(LOC_ST).openCursor(null, 'prev');
      cur.onsuccess = function () { var k = cur.result; res(k ? {db: db, key: k.key, item: k.value} : null); };
      cur.onerror = function () { res(null); };
    };
  });
}

function locFlush() {
  return locLatest().then(function (x) {
    if (!x || !x.item || !x.item.url) return;
    var b = new URLSearchParams();
    b.append('lat', x.item.lat); b.append('lng', x.item.lng); b.append('at', x.item.at);
    return fetch(x.item.url, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {'X-CSRFToken': x.item.csrf || '', 'Content-Type': 'application/x-www-form-urlencoded'}, body: b
    }).then(function (r) {
      if (r.status >= 500) throw new Error('retry');   // reject = browser baad mein dobara sync chalayega
      return new Promise(function (res) {
        var tx = x.db.transaction(LOC_ST, 'readwrite');
        tx.objectStore(LOC_ST).delete(IDBKeyRange.upperBound(x.key));
        tx.oncomplete = tx.onerror = function () { res(); };
      });
    });
  });
}

self.addEventListener('sync', function (event) {
  if (event.tag === LOC_TAG) event.waitUntil(locFlush());
});


// ---- Web Push (root scope: ERP/Investor; /shop/ ka push-sw.js bhi isi file ko importScripts karta hai) -----
var BADGE_URL = '/shop/push/badge/';

function refreshBadge(portal) {   // icon par number (Android/desktop Chrome/Edge, installed iOS 16.4+)
  var nav = self.navigator;
  if (!(nav && nav.setAppBadge)) return Promise.resolve();
  return fetch(BADGE_URL + '?p=' + encodeURIComponent(portal || ''), {credentials: 'same-origin', cache: 'no-store'})
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) {
      if (!j) return;
      var n = (j.count | 0);
      return n > 0 ? nav.setAppBadge(n) : nav.clearAppBadge();
    }).catch(function () {});
}

self.addEventListener('push', function (event) {
  var d = {};
  try { d = event.data ? event.data.json() : {}; }
  catch (err) { d = {title: 'Notification', body: event.data ? event.data.text() : ''}; }
  var url = d.url || '/shop/';
  var portal = portalOf(url);
  var actions = (d.actions || []).slice(0, 2).map(function (a) { return {action: a.action, title: a.title}; });
  var opts = {
    body: d.body || '',
    icon: '/pwa/icon/' + portal + '/192.png',
    data: {url: url, actions: d.actions || [], portal: portal},
    tag: d.tag || url,
    renotify: !!d.tag,            // same tag par bhi dobara awaaz/vibration
    requireInteraction: !!d.interaction,
    vibrate: d.vibrate || [150]
  };
  if (actions.length) opts.actions = actions;
  event.waitUntil(Promise.all([
    self.registration.showNotification(d.title || 'Notification', opts),
    refreshBadge(portal),
    // App khuli ho to page ko batao (wo alert tone bajata hai)
    self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(function (list) {
      list.forEach(function (c) { c.postMessage({type: 'PUSH', kind: d.kind || '', title: d.title || '', url: url}); });
    })
  ]));
});

// Notification ke button (Accept/Reject/Decline) se seedha server par action. Natija ek chhoti notification mein.
function resultNote(title, body, data) {
  return self.registration.showNotification(title, {
    body: body || '', icon: '/pwa/icon/' + (data.portal || 'erp') + '/192.png',
    tag: 'pwa-action-result', renotify: true, silent: true, data: {url: data.url || '/'}
  });
}

function runAction(btn, data) {
  return fetch('/shop/push/action/', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token: btn.token})
  }).then(function (r) {
    return r.json().catch(function () { return {ok: false, message: 'Server ne jawab nahi diya.'}; });
  }).then(function (j) {
    return resultNote(j.ok ? '\u2705 ' + (j.message || 'Done') : '\u26A0\uFE0F ' + (j.message || 'Nahi ho saka'),
                      j.ok ? '' : 'Tap karke app kholein.', data);
  }).catch(function () {   // internet nahi
    return resultNote('\uD83D\uDCE1 Internet nahi', 'Action nahi gaya. Tap karke app kholein aur wahan se karein.', data);
  }).then(function () { return refreshBadge(data.portal); });
}

self.addEventListener('notificationclick', function (event) {
  var n = event.notification;
  var data = n.data || {};
  n.close();
  if (event.action === 'later') return;   // sirf band karo
  var url = data.url || '/shop/';
  if (event.action) {   // button ka apna url ho to wahan
    var btn = null;
    (data.actions || []).forEach(function (a) { if (a.action === event.action) btn = a; });
    if (btn && btn.token) { event.waitUntil(runAction(btn, data)); return; }   // Accept / Reject: app khole baghair
    if (btn && btn.url) url = btn.url;
  }
  var target;
  try { target = new URL(url, self.location.origin); } catch (e) { target = new URL('/', self.location.origin); }
  if (target.origin !== self.location.origin) target = new URL('/', self.location.origin);   // bahari link kabhi nahi
  event.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      var c = list[i];
      try {
        if (new URL(c.url).origin === target.origin && 'focus' in c) {
          return c.focus().then(function (w) { return (w && 'navigate' in w) ? w.navigate(target.href) : w; });
        }
      } catch (e) {}
    }
    return self.clients.openWindow(target.href);
  }));
});
