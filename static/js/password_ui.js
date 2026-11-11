/* Password UI: show/hide button + strength meter (forms jin mein "confirm" wala password field ho).
   Sirf display hai - asal check server par hota hai (app/utils/password_policy.py). */
(function () {
  function score(pw) {
    var s = 0;
    if (pw.length >= 8) s++;
    if (pw.length >= 12) s++;
    if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
    if (/\d/.test(pw)) s++;
    if (/[^A-Za-z0-9]/.test(pw)) s++;
    if (/^(.)\1+$/.test(pw) || /^\d+$/.test(pw)) s = Math.min(s, 1);
    return Math.min(s, 4);
  }
  var LABELS = ['Bohat kamzor', 'Kamzor', 'Theek', 'Achha', 'Mazboot'];
  var COLORS = ['#dc2626', '#ea580c', '#d97706', '#65a30d', '#16a34a'];

  function enhance(input) {
    if (input.dataset.pwUi) return;
    input.dataset.pwUi = '1';
    var form = input.form;
    var wrap = document.createElement('span');
    wrap.style.cssText = 'position:relative;display:block;width:100%';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    input.style.paddingRight = '44px';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Password dikhayein/chhupayein');
    btn.textContent = '👁';
    btn.style.cssText = 'position:absolute;right:6px;top:50%;transform:translateY(-50%);border:0;background:none;' +
      'cursor:pointer;font-size:18px;line-height:1;padding:4px 8px;opacity:.7';
    btn.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.textContent = show ? '🙈' : '👁';
    });
    wrap.appendChild(btn);

    var isNewName = /^(password|new_password|password1|new_password1)$/i.test(input.name || '');
    var isNew = isNewName && form && Array.prototype.some.call(form.querySelectorAll('input[type=password],input[type=text]'),
      function (el) { return el !== input && /confirm/i.test(el.name || ''); }) && !/confirm/i.test(input.name || '');
    if (!isNew) return;

    var meter = document.createElement('div');
    meter.style.cssText = 'margin-top:6px;font-size:12.5px;display:none';
    meter.innerHTML = '<div style="height:5px;background:#e5e7eb;border-radius:4px;overflow:hidden">' +
      '<div data-bar style="height:100%;width:0;transition:width .2s,background .2s"></div></div>' +
      '<div data-txt style="margin-top:3px;font-weight:600"></div>' +
      '<div style="color:#6b7280;margin-top:2px">Kam az kam 8 characters, harf aur number. Apna naam ya phone na rakhein.</div>';
    wrap.parentNode.insertBefore(meter, wrap.nextSibling);
    var bar = meter.querySelector('[data-bar]'), txt = meter.querySelector('[data-txt]');
    input.addEventListener('input', function () {
      var pw = input.value;
      meter.style.display = pw ? 'block' : 'none';
      var s = score(pw);
      bar.style.width = (s + 1) * 20 + '%';
      bar.style.background = COLORS[s];
      txt.style.color = COLORS[s];
      txt.textContent = LABELS[s];
    });
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll('input[type=password]'), enhance);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
