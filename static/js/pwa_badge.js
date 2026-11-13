/* App icon badge (installed PWA): vendor = naye orders, rider = offers + assigned,
 * shop = chalu orders, investor/erp = unread notifications.
 * Server: /shop/push/badge/?p=<portal>  ->  {count}.  Service worker bhi push aane par isi ko poochta hai.
 * Ye sirf installed app (standalone) mein chalta hai; browser tab mein koi request nahi jati.
 */
(function () {
  'use strict';
  if (!('setAppBadge' in navigator)) return;            // iOS < 16.4, Firefox: kuch nahi karna
  var standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  if (!standalone) return;

  var p = location.pathname, portal;
  if (/^\/shop\/rider\//.test(p)) portal = 'rider';
  else if (/^\/shop\/vendor\//.test(p)) portal = 'vendor';
  else if (/^\/shop\//.test(p)) portal = 'shop';
  else if (/^\/(?:investor|shareholder|shareholders\/portal)\//.test(p)) portal = 'investor';
  else portal = 'erp';

  var busy = false, last = -1;

  function apply(n) {
    if (n === last) return;
    last = n;
    try { (n > 0 ? navigator.setAppBadge(n) : navigator.clearAppBadge()).catch(function () {}); } catch (e) {}
  }

  function refresh() {
    if (busy || document.hidden || navigator.onLine === false) return;
    busy = true;
    fetch('/shop/push/badge/?p=' + portal, {credentials: 'same-origin', cache: 'no-store', headers: {'Accept': 'application/json'}})
      .then(function (r) {
        var ct = r.headers.get('Content-Type') || '';
        if (!r.ok || ct.indexOf('json') === -1) return null;   // login par redirect, server restart, etc.
        return r.json();
      })
      .then(function (j) { if (j && typeof j.count === 'number') apply(j.count); })
      .catch(function () {})
      .then(function () { busy = false; });
  }

  refresh();
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
  window.addEventListener('online', refresh);
  window.addEventListener('pageshow', function (e) { if (e.persisted) refresh(); });
  setInterval(refresh, 60 * 1000);                           // app khuli ho to har minute

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', function (e) {
      if (e.data && e.data.type === 'PUSH') {
        last = -1; refresh();
        // Page ko batao (jaise orders list reload kar sakti hai): window.addEventListener('pwa:push', ...)
        try { window.dispatchEvent(new CustomEvent('pwa:push', {detail: e.data})); } catch (err) {}
      }
    });
  }
  window.pwaBadge = {refresh: refresh};
})();
