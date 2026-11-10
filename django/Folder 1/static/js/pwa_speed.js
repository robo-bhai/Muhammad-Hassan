/* PWA speed + storage helpers.
 * - Prefetch: user link par hath/touch rakhe ya link screen par dikhe to us page ko service worker pehle se le aata hai
 *   (sirf shop browse pages, kam internet / Data Saver par band).
 * - Storage: roz ek dafa purani cache saaf, installed app ke liye storage "persistent" ki request.
 * - Console helpers: pwaStorage()  ->  kitni jagah use hui,   pwaClearCache()  ->  saved cache saaf.
 */
(function () {
  'use strict';
  if (!('serviceWorker' in navigator)) return;

  var conn = navigator.connection || {};
  var slow = !!conn.saveData || /(^|-)2g$/.test(conn.effectiveType || '');
  var standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  // Service worker ke SHOP_PAGES jaise pages (yehi SW bhi manzoor karta hai)
  var OK = /^\/shop\/(?:|stores\/|stores\/\d+\/|product\/\d+\/|faq\/|help\/|about\/|terms\/|privacy\/|returns\/)$/;

  function send(msg) {
    var c = navigator.serviceWorker.controller;
    if (c) c.postMessage(msg);
  }

  /* ---------- Prefetch ---------- */
  var done = {}, count = 0, MAX = 8;

  function target(a) {
    if (!a || !a.href || a.target === '_blank' || a.hasAttribute('download')) return null;
    var u;
    try { u = new URL(a.href, location.href); } catch (e) { return null; }
    if (u.origin !== location.origin || u.search || u.pathname === location.pathname) return null;
    return OK.test(u.pathname) ? u.pathname : null;
  }

  function prefetch(a) {
    if (slow || count >= MAX || document.hidden) return;
    var p = target(a);
    if (!p || done[p]) return;
    done[p] = 1; count++;
    send({type: 'PREFETCH', url: p});
  }

  var timer;
  function onPoint(e) {
    var a = e.target && e.target.closest ? e.target.closest('a') : null;
    if (!target(a)) return;
    clearTimeout(timer);
    timer = setTimeout(function () { prefetch(a); }, e.type === 'touchstart' ? 0 : 80);
  }
  document.addEventListener('touchstart', onPoint, {passive: true, capture: true});
  document.addEventListener('mouseover', onPoint, {passive: true, capture: true});
  document.addEventListener('mouseout', function () { clearTimeout(timer); }, {passive: true});

  // Screen par 700ms se zyada dikhne wale pehle 4 links
  function observeVisible() {
    if (slow || !('IntersectionObserver' in window)) return;
    var seen = 0, timers = new WeakMap();
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          timers.set(en.target, setTimeout(function () {
            if (seen < 4 && target(en.target)) { seen++; prefetch(en.target); }
            io.unobserve(en.target);
          }, 700));
        } else {
          clearTimeout(timers.get(en.target));
        }
      });
    });
    var links = document.querySelectorAll('a[href]');
    for (var i = 0; i < links.length && i < 200; i++) if (target(links[i])) io.observe(links[i]);
  }
  window.addEventListener('load', function () {
    (window.requestIdleCallback || function (f) { setTimeout(f, 1500); })(observeVisible);
  });

  /* ---------- Storage ---------- */
  navigator.serviceWorker.ready.then(function () {
    try {
      var last = +localStorage.getItem('pwa_cleanup') || 0;
      if (Date.now() - last > 864e5) {            // roz ek dafa
        localStorage.setItem('pwa_cleanup', String(Date.now()));
        send({type: 'CLEANUP'});
      }
    } catch (e) {}
    if (standalone && navigator.storage && navigator.storage.persist) {
      navigator.storage.persist().catch(function () {});   // offline POS data browser delete na kare
    }
  });

  window.pwaStorage = function () {
    if (!(navigator.storage && navigator.storage.estimate)) return Promise.resolve(null);
    return navigator.storage.estimate().then(function (e) {
      var mb = function (n) { return Math.round((n || 0) / 1048576 * 10) / 10; };
      return {used_mb: mb(e.usage), quota_mb: mb(e.quota), percent: e.quota ? Math.round(e.usage / e.quota * 1000) / 10 : 0};
    });
  };
  window.pwaClearCache = function () { send({type: 'CLEAR_CACHE'}); };
})();
