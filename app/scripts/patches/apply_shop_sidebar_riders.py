"""
Adds a RIDER section to the shop sidebar (templates/customer_portal/base_shop.html), below VENDOR.
  - logged-in rider  -> "Rider Home" + "Rider Logout"
  - everyone else    -> "Rider Login"  (shown only while Settings > Shop > Riders > Rider login is ON;
                        if it is OFF and nobody is logged in as rider, the whole RIDER section is hidden)

Run from the project root:   python scripts/patches/apply_shop_sidebar_riders.py
Safe to run twice.
"""
import sys
from pathlib import Path

rel = 'templates/customer_portal/base_shop.html'
p = Path.cwd() / rel
if not p.exists():
    sys.exit('MISSING FILE: %s (run from the project root)' % rel)
t = p.read_text(encoding='utf-8')

if 'bi-bicycle' in t and 'RIDER' in t and "url 'rider_login'" in t:
    print('skip', rel)
    sys.exit(0)

marker = '<i class="bi bi-headset"></i> SUPPORT'
if t.count(marker) != 1:
    sys.exit('ANCHOR PROBLEM: SUPPORT section title found %d times (need 1)' % t.count(marker))
div = '<div class="sidebar-divider"></div>'
d = t.rfind(div, 0, t.index(marker))
if d == -1:
    sys.exit('ANCHOR PROBLEM: no sidebar-divider before the SUPPORT section')
at = t.rfind('\n', 0, d) + 1

block = '''        {% if user.is_authenticated and user.rider_profile or SHOP.rider_login_enabled %}
        <div class="sidebar-divider"></div>
        
        <div class="sidebar-section">
            <div class="sidebar-section-title">
                <div class="title-text">
                    <i class="bi bi-bicycle"></i> RIDER
                </div>
            </div>
            
            {% if user.is_authenticated and user.rider_profile %}
                <a href="{% url 'rider_home' %}" class="sidebar-menu-item">
                    <div class="menu-icon-box primary">
                        <i class="bi bi-speedometer2"></i>
                    </div>
                    <div class="menu-text">
                        Rider Home
                        <span class="menu-subtitle">Your deliveries</span>
                    </div>
                </a>
                
                <a href="{% url 'rider_logout' %}" class="sidebar-menu-item">
                    <div class="menu-icon-box danger">
                        <i class="bi bi-box-arrow-right"></i>
                    </div>
                    <div class="menu-text">
                        Rider Logout
                        <span class="menu-subtitle">Sign out safely</span>
                    </div>
                </a>
            {% else %}
                <a href="{% url 'rider_login' %}" class="sidebar-menu-item">
                    <div class="menu-icon-box primary">
                        <i class="bi bi-box-arrow-in-right"></i>
                    </div>
                    <div class="menu-text">
                        Rider Login
                        <span class="menu-subtitle">Deliver orders</span>
                    </div>
                </a>
            {% endif %}
        </div>
        {% endif %}
        
'''
t = t[:at] + block + t[at:]
p.write_text(t, encoding='utf-8')
print('ok ', rel)
