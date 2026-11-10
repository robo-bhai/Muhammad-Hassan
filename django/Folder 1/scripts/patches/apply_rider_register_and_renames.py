"""
Step 5: "Register as a Rider" + label renames.  Run AFTER the vendors/customers/pages/riders patches
and apply_shop_sidebar_riders.py.

Run from the project root:   python scripts/patches/apply_rider_register_and_renames.py
Safe to run twice. Every anchor is checked; on a mismatch the script stops and names it.

1. Rider self-registration  (/shop/rider/register/)
     - new switches: "Register as a Rider" (rider_register_enabled, default ON)
                     "Auto-approve new riders" (rider_auto_approve, default OFF)
     - OFF (default): the new rider waits for admin approval -> Riders page shows "Naya - approval baqi",
       admin presses "Chalu". Until then, login says "approval ka intezar".
     - link in the shop sidebar (RIDER section) and on the rider login page.
2. Renames (visible text only; URLs / switch names are unchanged)
     Vendor Login -> Seller Login,  Become a Vendor -> Register as a Seller,
     customer "Register" -> Register as a Customer
     (sidebar section VENDOR -> SELLER, Vendor Dashboard/Logout -> Seller Dashboard/Logout for consistency)
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()


def read(rel):
    p = ROOT / rel
    if not p.exists():
        sys.exit('MISSING FILE: %s  (run from the project root, after the earlier patches)' % rel)
    return p, p.read_text(encoding='utf-8')


def once(text, anchor, rel):
    n = text.count(anchor)
    if n != 1:
        sys.exit('ANCHOR PROBLEM in %s (found %d times, need 1):\n%s' % (rel, n, anchor))


def rep(t, old, new, rel):
    """Replace exactly one occurrence; skip quietly if it was already replaced."""
    if t.count(old) == 1:
        return t.replace(old, new)
    if t.count(old) == 0 and new in t:
        return t
    sys.exit('ANCHOR PROBLEM in %s (found %d times, need 1):\n%s' % (rel, t.count(old), old))


# =============================================================== 1. shop_flags.py
rel = 'app/shop_flags.py'
p, t = read(rel)
if 'rider_register_enabled' not in t:
    a = "    'rider_earnings_enabled':        (True,  'The earnings page is currently unavailable.'),\n"
    once(t, a, rel)
    t = t.replace(a, a + """    'rider_register_enabled':        (True,  'New rider registration is currently closed.'),
    'rider_auto_approve':            (False, ''),
""")
t = t.replace('New vendor registration is currently closed.', 'New seller registration is currently closed.')
t = t.replace('Vendor login is currently disabled.', 'Seller login is currently disabled.')
p.write_text(t, encoding='utf-8')
print('ok ', rel)

# =============================================================== 2. settings catalog
rel = 'app/settings_catalog.py'
p, t = read(rel)
if 'rider_register_enabled' not in t:
    a = "{'name': 'rider_earnings_enabled', 'label': 'Rider earnings page', 'type': 'bool', 'default': True,\n             'group': 'Riders'},\n"
    once(t, a, rel)
    t = t.replace(a, a + """            {'name': 'rider_register_enabled', 'label': 'Register as a Rider', 'type': 'bool', 'default': True,
             'group': 'Riders', 'help': 'OFF = the rider sign-up page and its links are closed.'},
            {'name': 'rider_auto_approve', 'label': 'Auto-approve new riders', 'type': 'bool', 'default': False,
             'group': 'Riders', 'help': 'OFF = admin approves each new rider (Riders page > Chalu).'},
""")
for old, new in (
    ("'label': 'Become a Vendor (registration)'", "'label': 'Register as a Seller'"),
    ("'label': 'Vendor Login'", "'label': 'Seller Login'"),
    ("'label': 'Customer registration'", "'label': 'Register as a Customer'"),
):
    t = rep(t, old, new, rel)
p.write_text(t, encoding='utf-8')
print('ok ', rel)

# =============================================================== 3. rider views
rel = 'app/customer/views_rider_portal.py'
p, t = read(rel)
if 'def rider_register' in t:
    print('skip', rel)
else:
    t = rep(t, 'from ..shop_flags import flag_required\n', 'from ..shop_flags import flag_required, shop_flag\n', rel)
    view = '''@flag_required('rider_register_enabled', redirect_to='shop_home')
def rider_register(request):
    """Rider khud register kare. Admin approval ke baghair login nahi (jab tak 'Auto-approve new riders' OFF ho)."""
    if request.user.is_authenticated and hasattr(request.user, 'rider_profile'):
        return redirect('rider_home')

    form = {}
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()[:100]
        phone_raw = request.POST.get('phone', '').strip()[:20]
        vehicle = request.POST.get('vehicle', '').strip()[:50]
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm', '')
        form = {'name': name, 'phone': phone_raw, 'vehicle': vehicle}
        key = 'rider_register:%s' % (get_client_ip(request) or '')

        error = None
        if cache.get(key, 0) >= 5:
            error = '🔒 Bohat zyada registrations. Thori der baad dobara try karein.'
        elif not name or not phone_raw:
            error = '❌ Naam aur phone likhein.'
        elif not is_valid_phone(phone_raw):
            error = '❌ Phone number sahi nahi.'
        elif len(password) < 6:
            error = '❌ Password kam az kam 6 harf ka ho.'
        elif password != confirm:
            error = '❌ Dono password aik jaise likhein.'

        if not error:
            phone = normalize_phone(phone_raw)
            username = 'rider_' + phone.replace('+', '')
            auto = shop_flag('rider_auto_approve')
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=username, password=password, first_name=name[:30])
                    RiderProfile.objects.create(user=user, name=name, phone=phone, vehicle=vehicle, is_active=auto)
            except IntegrityError:
                error = '❌ Is phone ka rider pehle se maujood hai.'
            else:
                cache.set(key, cache.get(key, 0) + 1, 3600)
                if auto:
                    messages.success(request, '✅ Registration ho gayi. Ab login karein.')
                else:
                    messages.success(request, '✅ Registration mil gayi. Admin ke approval ke baad aap login kar sakenge.')
                return redirect('rider_login')
        messages.error(request, error)

    return render(request, 'customer_portal/rider/register.html', {'company_name': _company_name(), 'form': form})


'''
    once(t, 'def rider_logout(request):', rel)
    t = t.replace('def rider_logout(request):', view + 'def rider_logout(request):', 1)

    a = "        user = authenticate(request, username=rider.user.username, password=password) if rider else None\n        if not user:\n"
    once(t, a, rel)
    t = t.replace(a, """        user = authenticate(request, username=rider.user.username, password=password) if rider else None
        if not rider:
            waiting = RiderProfile.objects.select_related('user').filter(phone=phone, is_active=False).first()
            if waiting and authenticate(request, username=waiting.user.username, password=password):
                messages.info(request, '⏳ Aap ki registration admin ke approval ka intezar kar rahi hai.')
                return redirect('rider_login')
        if not user:
""")
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# =============================================================== 4. urls
rel = 'app/urls.py'
p, t = read(rel)
if 'rider_register' in t:
    print('skip', rel)
else:
    m = re.search(r"^([ \t]*)path\('shop/rider/logout/'[^\n]*\n", t, re.M)
    if not m:
        sys.exit("ANCHOR PROBLEM in %s: path('shop/rider/logout/' ...) not found" % rel)
    new = "%spath('shop/rider/register/', views_rider_portal.rider_register, name='rider_register'),\n" % m.group(1)
    t = t[:m.end()] + new + t[m.end():]
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# =============================================================== 5. templates
REGISTER_HTML = '''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Register as a Rider - {{ company_name }}</title>
<style>
  body{margin:0;min-height:100vh;display:flex;flex-direction:column;justify-content:center;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:linear-gradient(160deg,#ff5a00,#ff8a3d);padding:20px}
  .c{max-width:400px;width:100%;margin:0 auto;background:#fff;border-radius:22px;padding:26px;box-shadow:0 12px 40px rgba(0,0,0,.2)}
  h2{margin:0 0 4px;font-size:24px;color:#1f2937}p{color:#6b7280;margin:0 0 18px}
  input{width:100%;padding:14px;border:1px solid #d1d5db;border-radius:12px;margin-bottom:12px;font-size:16px;box-sizing:border-box}
  button{width:100%;padding:15px;border:0;border-radius:12px;background:#ff5a00;color:#fff;font-weight:800;font-size:17px}
  .m{padding:10px 12px;border-radius:10px;margin-bottom:12px;font-size:14px;font-weight:600}
  .error{background:#fee2e2;color:#991b1b}.success{background:#dcfce7;color:#166534}.warning,.info{background:#fef3c7;color:#92400e}
  .logo{font-size:44px;text-align:center}.alt{text-align:center;margin:14px 0 0;font-size:14px}.alt a{color:#ff5a00;font-weight:700}
</style></head><body>
<div class="c">
  <div class="logo">🏍️</div>
  <h2>Register as a Rider</h2><p>{{ company_name }} ke saath delivery karein. Admin approval ke baad aap login kar sakenge.</p>
  {% for m in messages %}<div class="m {{ m.tags }}">{{ m }}</div>{% endfor %}
  <form method="post">{% csrf_token %}
    <input type="text" name="name" placeholder="Poora naam" value="{{ form.name }}" required maxlength="100" autocomplete="name">
    <input type="tel" name="phone" placeholder="03XX XXXXXXX" value="{{ form.phone }}" required inputmode="tel" autocomplete="username">
    <input type="text" name="vehicle" placeholder="Gaari (bike / car) - optional" value="{{ form.vehicle }}" maxlength="50">
    <input type="password" name="password" placeholder="Password (kam az kam 6 harf)" required minlength="6" autocomplete="new-password">
    <input type="password" name="confirm" placeholder="Password dobara likhein" required minlength="6" autocomplete="new-password">
    <button type="submit">Register as a Rider</button>
  </form>
  {% if SHOP.rider_login_enabled %}<p class="alt">Pehle se account hai? <a href="{% url 'rider_login' %}">Rider Login</a></p>{% endif %}
</div></body></html>
'''
rel = 'templates/customer_portal/rider/register.html'
if (ROOT / rel).exists():
    print('skip', rel)
else:
    (ROOT / rel).write_text(REGISTER_HTML, encoding='utf-8')
    print('ok ', rel)

rel = 'templates/customer_portal/rider/login.html'
p, t = read(rel)
if 'rider_register' in t:
    print('skip', rel)
else:
    a = '  </form>\n</div></body></html>'
    once(t, a, rel)
    t = t.replace(a, """  </form>
  {% if SHOP.rider_register_enabled %}<p style="text-align:center;margin:14px 0 0;font-size:14px">Naye rider? <a href="{% url 'rider_register' %}" style="color:#ff5a00;font-weight:700">Register as a Rider</a></p>{% endif %}
</div></body></html>""")
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

rel = 'templates/customer_portal/rider/manage.html'
p, t = read(rel)
if 'approval baqi' in t:
    print('skip', rel)
else:
    a = '{% if not r.is_active %}<span class="badge bg-secondary">Band</span>'
    once(t, a, rel)
    t = t.replace(a, '{% if not r.is_active and not r.last_login_at %}<span class="badge bg-warning text-dark">⏳ Naya — approval baqi</span>\n'
                     '                  {% elif not r.is_active %}<span class="badge bg-secondary">Band</span>')
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# --- shop sidebar: rider register link + renames
rel = 'templates/customer_portal/base_shop.html'
p, t = read(rel)
if 'rider_register' not in t:
    t = rep(t, '{% if user.is_authenticated and user.rider_profile or SHOP.rider_login_enabled %}',
            '{% if user.is_authenticated and user.rider_profile or SHOP.rider_login_enabled or SHOP.rider_register_enabled %}', rel)
    rx = re.compile(r'([ \t]*)(<a href="\{% url \'rider_login\' %\}" class="sidebar-menu-item">.*?</a>)', re.S)
    ms = list(rx.finditer(t))
    if len(ms) != 1:
        sys.exit('ANCHOR PROBLEM in %s: rider_login sidebar link found %d times' % (rel, len(ms)))
    m = ms[0]
    ind = m.group(1)
    register = '''<a href="{% url 'rider_register' %}" class="sidebar-menu-item">
    <div class="menu-icon-box success">
        <i class="bi bi-person-plus"></i>
    </div>
    <div class="menu-text">
        Register as a Rider
        <span class="menu-subtitle">Earn by delivering</span>
    </div>
</a>'''
    register = '\n'.join((ind + ln) if ln else ln for ln in register.split('\n'))
    new = ('%s{%% if SHOP.rider_login_enabled %%}\n%s%s\n%s{%% endif %%}\n\n%s{%% if SHOP.rider_register_enabled %%}\n%s\n%s{%% endif %%}'
           % (ind, ind, m.group(2), ind, ind, register, ind))
    t = t[:m.start()] + new + t[m.end():]

for old, new in (
    ('<i class="bi bi-shop"></i> VENDOR\n', '<i class="bi bi-shop"></i> SELLER\n'),
    ('                        Vendor Dashboard\n', '                        Seller Dashboard\n'),
    ('                        Vendor Logout\n', '                        Seller Logout\n'),
    ('                        Vendor Login\n', '                        Seller Login\n'),
    ('                        Become a Vendor\n', '                        Register as a Seller\n'),
    ('                        Register\n                        <span class="menu-subtitle">Create new account</span>',
     '                        Register as a Customer\n                        <span class="menu-subtitle">Create new account</span>'),
):
    t = rep(t, old, new, rel)
p.write_text(t, encoding='utf-8')
print('ok ', rel)

for rel, pairs in (
    ('templates/customer_portal/vendor/login.html', (
        ('{% block title %}Vendor Login -', '{% block title %}Seller Login -'),
        ('<h3>Vendor Login</h3>', '<h3>Seller Login</h3>'),
        ('Register as vendor</a>', 'Register as a seller</a>'))),
    ('templates/customer_portal/vendor/register.html', (
        ('{% block title %}Vendor Registration -', '{% block title %}Seller Registration -'),
        ('<h3>Become a Vendor</h3>', '<h3>Register as a Seller</h3>'),
        ('<span>Register as Vendor</span>', '<span>Register as a Seller</span>'),
        ('>Vendor login</a>', '>Seller login</a>'))),
    ('templates/customer_portal/auth/register.html', (
        ('{% block title %}Register -', '{% block title %}Register as a Customer -'),
        ('<h3>Create Account</h3>', '<h3>Register as a Customer</h3>'))),
    ('templates/customer_portal/auth/login.html', (
        ('>Register now</a>', '>Register as a customer</a>'),)),
    ('app/customer/views_vendor_portal.py', (
        ("'page_title': 'Vendor Registration',", "'page_title': 'Seller Registration',"),
        ("'page_title': 'Vendor Login',", "'page_title': 'Seller Login',"))),
):
    p, t = read(rel)
    for old, new in pairs:
        t = rep(t, old, new, rel)
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

print('\nDone. No migration needed. Restart the server.')
