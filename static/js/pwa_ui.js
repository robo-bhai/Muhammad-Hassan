/* PWA UI helpers (sab 5 apps):
 *  1. Pull-to-refresh        - installed app mein (standalone) page ke upar se kheench kar reload.
 *  2. Skeleton loaders       - link dabane par page slow ho to shimmer placeholder (sirf installed app mein);
 *                              AJAX ke liye: pwaSkeleton.show(el, rows) / pwaSkeleton.hide(el).
 *  3. Offline / online bar   - net jaane par chhota bar, wapas aane par "Back online".
 *  4. pwaToast(msg, ms)      - chhota message (update/offline-ready ke liye bhi use hota hai).
 *  5. Alert awaaz            - app khuli ho aur vendor/rider ko naye order ki push aaye to foran tez ring (pwaAlert / pwaAlert.stop).
 *                              Band ho to awaaz phone ki notification setting se aati hai (web push custom awaaz nahi deta).
 * Band karne ke liye (kisi page par):   window.PWA_UI = {ptr: false, skeleton: false}   (script se pehle)
 * Kisi hisse par PTR band:  data-no-ptr    |   kisi link par skeleton band:  data-no-skeleton
 */
(function () {
  'use strict';
  var CFG = window.PWA_UI || {};
  var standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  var path = location.pathname;
  var ur = /^ur/i.test(document.documentElement.lang || '');
  function T(en, urdu) { return ur ? urdu : en; }

  // POS / chat jaisi screens par kuch nahi (apna scroll, unsaved data)
  var SKIP_PAGE = /^\/(?:sales\/pos|admin-chat)\//.test(path);

  /* ---------- CSS ---------- */
  var css = [
    ':root{--pwa-sk-bg:#f4f6fa;--pwa-sk-a:#e3e8f0;--pwa-sk-b:#f1f4f9;--pwa-card:#fff;--pwa-ink:#111827;--pwa-accent:#0d6efd}',
    '@media(prefers-color-scheme:dark){:root:not([data-bs-theme="light"]):not([data-theme="light"]){--pwa-sk-bg:#0f1624;--pwa-sk-a:#1b2538;--pwa-sk-b:#243049;--pwa-card:#16203a;--pwa-ink:#e5ecff}}',
    '[data-bs-theme="dark"],[data-theme="dark"]{--pwa-sk-bg:#0f1624;--pwa-sk-a:#1b2538;--pwa-sk-b:#243049;--pwa-card:#16203a;--pwa-ink:#e5ecff}',
    '.pwa-sk{display:block;border-radius:10px;background:linear-gradient(90deg,var(--pwa-sk-a) 25%,var(--pwa-sk-b) 50%,var(--pwa-sk-a) 75%);background-size:200% 100%;animation:pwa-shimmer 1.3s linear infinite;color:transparent!important;pointer-events:none;user-select:none}',
    '@keyframes pwa-shimmer{from{background-position:200% 0}to{background-position:-200% 0}}',
    '#pwa-nav-bar{position:fixed;top:0;left:0;height:3px;width:0;background:var(--pwa-accent);z-index:100002;opacity:0;transition:width .25s ease,opacity .2s;pointer-events:none;padding-top:env(safe-area-inset-top,0)}',
    '#pwa-sk-overlay{position:fixed;inset:0;z-index:100001;background:var(--pwa-sk-bg);padding:calc(14px + env(safe-area-inset-top,0px)) 14px 14px;opacity:0;transition:opacity .2s;overflow:hidden;pointer-events:all}',
    '#pwa-sk-overlay.on{opacity:1}',
    '#pwa-sk-overlay .row{background:var(--pwa-card);border-radius:14px;padding:12px;margin-top:12px;display:flex;gap:12px;align-items:center}',
    '#pwa-sk-overlay .row .pwa-sk.t{height:64px;width:64px;flex:none;border-radius:12px}',
    '#pwa-sk-overlay .row .col{flex:1;display:flex;flex-direction:column;gap:9px}',
    '#pwa-ptr{position:fixed;left:50%;top:0;width:38px;height:38px;margin-left:-19px;border-radius:50%;background:var(--pwa-card);color:var(--pwa-accent);box-shadow:0 4px 16px rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center;font:700 20px/1 system-ui;z-index:100003;transform:translateY(-60px);pointer-events:none;opacity:0}',
    '#pwa-ptr.spin span{animation:pwa-spin .8s linear infinite}',
    '@keyframes pwa-spin{to{transform:rotate(360deg)}}',
    '#pwa-toast{position:fixed;left:50%;bottom:calc(76px + env(safe-area-inset-bottom,0px));transform:translate(-50%,20px);background:#111827;color:#fff;padding:10px 16px;border-radius:12px;font:14px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;z-index:100004;opacity:0;transition:opacity .2s,transform .2s;max-width:90vw;text-align:center;pointer-events:none}',
    '#pwa-toast.on{opacity:1;transform:translate(-50%,0)}',
    '#pwa-offline{position:fixed;left:0;right:0;top:0;background:#92400e;color:#fff;text-align:center;padding:calc(5px + env(safe-area-inset-top,0px)) 10px 5px;font:13px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;z-index:100005}',
    '@media(prefers-reduced-motion:reduce){.pwa-sk,#pwa-ptr.spin span{animation:none}}'
  ].join('\n');
  var st = document.createElement('style');
  st.id = 'pwa-ui-css';
  st.textContent = css;
  (document.head || document.documentElement).appendChild(st);

  function ready(fn) { if (document.body) fn(); else document.addEventListener('DOMContentLoaded', fn); }
  function el(tag, id, html) { var e = document.createElement(tag); if (id) e.id = id; if (html) e.innerHTML = html; return e; }

  /* ---------- 4. Toast ---------- */
  var toastTimer;
  window.pwaToast = function (msg, ms) {
    ready(function () {
      var t = document.getElementById('pwa-toast');
      if (!t) { t = el('div', 'pwa-toast'); t.setAttribute('role', 'status'); document.body.appendChild(t); }
      t.textContent = msg;
      void t.offsetWidth;
      t.classList.add('on');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { t.classList.remove('on'); }, ms || 2500);
    });
  };

  /* ---------- 3. Offline / online ---------- */
  function offlineBar(on) {
    ready(function () {
      var b = document.getElementById('pwa-offline');
      if (on && !b) document.body.appendChild(el('div', 'pwa-offline', '📡 ' + T('You are offline', 'آپ آف لائن ہیں')));
      if (!on && b) b.remove();
    });
  }
  if (standalone) {
    if (navigator.onLine === false) offlineBar(true);
    window.addEventListener('offline', function () { offlineBar(true); });
    window.addEventListener('online', function () { offlineBar(false); window.pwaToast('✅ ' + T('Back online', 'انٹرنیٹ واپس آ گیا')); });
  }

  /* ---------- 2. Skeleton loaders ---------- */
  var barTimer, skTimer, safety;
  var NO_SKELETON_PATH = /(export|pdf|download|csv|xlsx|print|backup|logout|barcode|\.(?:pdf|csv|xlsx?|zip|docx?|png|jpe?g))/i;

  function navBar(start) {
    var b = document.getElementById('pwa-nav-bar');
    if (!b) { b = el('div', 'pwa-nav-bar'); document.body.appendChild(b); }
    if (start) {
      b.style.transition = 'none'; b.style.width = '0'; void b.offsetWidth;
      b.style.transition = ''; b.style.opacity = '1'; b.style.width = '70%';
      clearTimeout(barTimer);
      barTimer = setTimeout(function () { b.style.transition = 'width 8s ease-out'; b.style.width = '92%'; }, 300);
    } else { clearTimeout(barTimer); b.style.opacity = '0'; b.style.width = '0'; }
  }

  function skRows(n) {
    var h = '<div class="pwa-sk" style="height:46px;border-radius:12px"></div>';
    for (var i = 0; i < n; i++) {
      h += '<div class="row"><span class="pwa-sk t"></span><span class="col">' +
           '<span class="pwa-sk" style="height:14px;width:' + (60 + (i * 13) % 35) + '%"></span>' +
           '<span class="pwa-sk" style="height:12px;width:' + (35 + (i * 17) % 30) + '%"></span>' +
           '<span class="pwa-sk" style="height:12px;width:25%"></span></span></div>';
    }
    return h;
  }

  function showOverlay() {
    if (document.getElementById('pwa-sk-overlay')) return;
    var o = el('div', 'pwa-sk-overlay', skRows(Math.max(4, Math.min(8, Math.floor(window.innerHeight / 110)))));
    o.setAttribute('aria-hidden', 'true');
    document.body.appendChild(o);
    void o.offsetWidth; o.classList.add('on');
  }
  function clearNav() {
    clearTimeout(skTimer); clearTimeout(safety);
    var o = document.getElementById('pwa-sk-overlay'); if (o) o.remove();
    navBar(false);
  }
  function startNav(withSkeleton) {
    navBar(true);
    clearTimeout(skTimer); clearTimeout(safety);
    if (withSkeleton) skTimer = setTimeout(showOverlay, 400);     // tez page par skeleton dikhta hi nahi
    safety = setTimeout(clearNav, 12000);                         // download jaisi navigation jo page nahi badalti
  }

  function linkOk(a, e) {
    if (!a || e.defaultPrevented || e.button > 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
    if ((a.target && a.target !== '_self') || a.hasAttribute('download') || a.hasAttribute('data-no-skeleton')) return false;
    if (a.closest('[data-no-skeleton]')) return false;
    var u;
    try { u = new URL(a.href, location.href); } catch (err) { return false; }
    if (u.origin !== location.origin || !/^https?:$/.test(u.protocol)) return false;
    if (u.pathname === location.pathname && u.search === location.search) return false;   // #anchor / same page
    if (NO_SKELETON_PATH.test(u.pathname)) return false;
    if (/^\/(?:sales\/pos|admin-chat)\//.test(u.pathname)) return false;
    return true;
  }

  if (standalone && CFG.skeleton !== false && !SKIP_PAGE) {
    document.addEventListener('click', function (e) {
      var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
      if (!linkOk(a, e)) return;
      // click handler (bootstrap dropdown/JS) agar default rok de to kuch nahi
      setTimeout(function () { if (!e.defaultPrevented) ready(function () { startNav(true); }); }, 0);
    }, true);
    document.addEventListener('submit', function (e) {
      var f = e.target;
      if (e.defaultPrevented || !f || f.target === '_blank' || f.hasAttribute('data-no-skeleton')) return;
      setTimeout(function () { if (!e.defaultPrevented) ready(function () { startNav(false); }); }, 0);   // sirf progress bar
    }, true);
    window.addEventListener('pageshow', function () { clearNav(); });   // back button (bfcache) par overlay na rahe
  }

  // AJAX ke liye: pwaSkeleton.show(container, rows) ... pwaSkeleton.hide(container)
  window.pwaSkeleton = {
    show: function (container, rows) {
      if (!container) return;
      container.setAttribute('data-sk-prev', container.innerHTML);
      container.innerHTML = skRows(rows || 4);
      container.setAttribute('aria-busy', 'true');
    },
    hide: function (container) {
      if (!container) return;
      var prev = container.getAttribute('data-sk-prev');
      if (prev !== null && container.querySelector('.pwa-sk')) container.innerHTML = prev;   // data nahi aaya to purana wapas
      container.removeAttribute('data-sk-prev'); container.removeAttribute('aria-busy');
    }
  };
  // .row sirf overlay mein styled hai: container ke liye bhi wahi look
  var st2 = document.createElement('style');
  st2.textContent = '[aria-busy="true"] .row{background:var(--pwa-card);border-radius:14px;padding:12px;margin-top:12px;display:flex;gap:12px;align-items:center}' +
    '[aria-busy="true"] .row .pwa-sk.t{height:64px;width:64px;flex:none;border-radius:12px}' +
    '[aria-busy="true"] .row .col{flex:1;display:flex;flex-direction:column;gap:9px}';
  (document.head || document.documentElement).appendChild(st2);

  /* ---------- 1. Pull-to-refresh ---------- */
  if (standalone && CFG.ptr !== false && !SKIP_PAGE && 'ontouchstart' in window) {
    var TH = 72, MAXPULL = 110;
    var startY = 0, startX = 0, pulling = false, armed = false, dy = 0, dirty = false, busyPtr = false, ind, ptrOn = false;

    // Native (Android) pull-to-refresh band kar ke apna wahi kaam karta hai: har jagah ek jaisa
    var s3 = document.createElement('style');
    s3.textContent = 'html,body{overscroll-behavior-y:contain}';
    (document.head || document.documentElement).appendChild(s3);

    // Form mein kuch likha ho to refresh nahi (data na jaye)
    document.addEventListener('input', function (e) {
      var t = e.target;
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && t.type !== 'search') dirty = true;
    }, true);

    function blocked(t) {
      if (dirty || busyPtr || document.body.classList.contains('modal-open')) return true;
      for (var n = t; n && n !== document.documentElement; n = n.parentElement) {
        if (n.nodeType !== 1) continue;
        if (n.hasAttribute && n.hasAttribute('data-no-ptr')) return true;
        if (/^(INPUT|TEXTAREA|SELECT)$/.test(n.tagName) || n.isContentEditable) return true;
        if (n.classList && (n.classList.contains('leaflet-container') || n.classList.contains('modal'))) return true;
        if (n !== document.body && n.scrollHeight > n.clientHeight + 1) {     // apna scroll wala box (list, chat) - upar nahi hai to PTR nahi
          var oy = getComputedStyle(n).overflowY;
          if ((oy === 'auto' || oy === 'scroll') && n.scrollTop > 0) return true;
        }
      }
      return false;
    }
    function indicator() {
      if (!ind) { ind = el('div', 'pwa-ptr', '<span>↻</span>'); ind.setAttribute('aria-hidden', 'true'); document.body.appendChild(ind); }
      return ind;
    }
    function reset(animate) {
      if (!ind) return;
      ind.style.transition = animate ? 'transform .2s, opacity .2s' : 'none';
      ind.style.transform = 'translateY(-60px)'; ind.style.opacity = '0';
      ind.classList.remove('spin'); ptrOn = false;
    }

    document.addEventListener('touchstart', function (e) {
      pulling = false; armed = false; dy = 0;
      if (e.touches.length !== 1 || (window.scrollY || document.documentElement.scrollTop) > 0) return;
      if (blocked(e.target)) return;
      startY = e.touches[0].clientY; startX = e.touches[0].clientX; ptrOn = true;
    }, {passive: true});

    document.addEventListener('touchmove', function (e) {
      if (!ptrOn || busyPtr) return;
      if ((window.scrollY || document.documentElement.scrollTop) > 0) { ptrOn = false; reset(false); return; }
      var d = e.touches[0].clientY - startY, dx = Math.abs(e.touches[0].clientX - startX);
      if (!pulling) {
        if (d < 10) return;
        if (dx > d) { ptrOn = false; return; }        // side ko scroll (carousel)
        pulling = true;
      }
      if (e.cancelable) e.preventDefault();           // iOS rubber-band roko
      dy = Math.min(MAXPULL, d * 0.5);
      var i = indicator();
      i.style.transition = 'none';
      i.style.opacity = String(Math.min(1, dy / 40));
      i.style.transform = 'translateY(' + (dy - 32) + 'px) rotate(' + (dy * 4) + 'deg)';
      i.style.top = 'env(safe-area-inset-top,0px)';
      var now = dy >= TH / 2;                         // dy = finger ka aadha (resistance), is liye 72px kheenchna parta hai
      if (now && !armed) { armed = true; try { navigator.vibrate && navigator.vibrate(8); } catch (err) {} }
      if (!now && armed) armed = false;
    }, {passive: false});

    function end() {
      if (!pulling) { ptrOn = false; return; }
      pulling = false;
      if (armed && ind) {
        busyPtr = true;
        ind.style.transition = 'transform .15s';
        ind.style.transform = 'translateY(' + (TH / 2) + 'px)';
        ind.classList.add('spin');
        if (window.pwaBadge) { try { window.pwaBadge.refresh(); } catch (err) {} }
        setTimeout(function () { location.reload(); }, 150);
        setTimeout(function () { busyPtr = false; reset(true); }, 8000);   // reload na ho paye (offline) to wapas
      } else reset(true);
      armed = false;
    }
    document.addEventListener('touchend', end, {passive: true});
    document.addEventListener('touchcancel', end, {passive: true});
  }
  /* ---------- 5. Alert awaaz (app khuli ho) ---------- */
  var actx = null, ringTimer = null, ringing = false;
  function ctx() {
    try {
      var C = window.AudioContext || window.webkitAudioContext;
      if (!C) return null;
      actx = actx || new C();
      if (actx.state === 'suspended') actx.resume();
      return actx;
    } catch (e) { return null; }
  }
  // Browser awaaz tab chalne deta hai jab user ne page ko ek dafa chhua ho
  ['touchstart', 'click', 'keydown'].forEach(function (ev) {
    document.addEventListener(ev, function () { ctx(); }, {once: true, passive: true, capture: true});
  });
  function tone(c, t, freq, dur, vol) {
    var o = c.createOscillator(), g = c.createGain();
    o.type = 'triangle'; o.frequency.value = freq;
    o.connect(g); g.connect(c.destination);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.start(t); o.stop(t + dur + 0.02);
  }
  function stopRing() { ringing = false; clearTimeout(ringTimer); }
  // pwaAlert('vendor'|'rider'): do-sur ki ring, ~5 second (screen ko chhuo to ruk jati hai)
  window.pwaAlert = function (kind) {
    var c = ctx();
    if (!c || ringing) return false;
    window.__pwaAlertAt = Date.now();          // page ki apni beep (poll wali) is ke baad 20 sec chup rahe
    ringing = true;
    var cycles = kind === 'rider' ? 3 : 5, n = 0;
    (function once() {
      if (!ringing || n >= cycles) { ringing = false; return; }
      n++;
      var t = c.currentTime + 0.02;
      tone(c, t, 988, 0.22, 0.55); tone(c, t + 0.25, 1319, 0.22, 0.55); tone(c, t + 0.5, 988, 0.22, 0.55); tone(c, t + 0.75, 1319, 0.3, 0.55);
      try { navigator.vibrate && navigator.vibrate([250, 100, 250]); } catch (e) {}
      ringTimer = setTimeout(once, 1100);
    })();
    return true;
  };
  window.pwaAlert.stop = stopRing;
  document.addEventListener('touchstart', stopRing, {passive: true, capture: true});
  document.addEventListener('click', stopRing, true);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', function (e) {
      var d = e.data || {};
      if (d.type === 'PUSH' && !document.hidden && (d.kind === 'vendor' || d.kind === 'rider')) window.pwaAlert(d.kind);
    });
  }
})();
