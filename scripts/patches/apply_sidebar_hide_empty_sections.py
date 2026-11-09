"""
Shop sidebar: hide the CUSTOMER / SELLER section (title + divider) when it would be empty.
A section is shown only if someone is logged in to it, or its login/register switch is ON
(same rule already used for the RIDER section).

Run from the project root:   python scripts/patches/apply_sidebar_hide_empty_sections.py
Safe to run twice.
"""
import re
import sys
from pathlib import Path

rel = 'templates/customer_portal/base_shop.html'
p = Path.cwd() / rel
if not p.exists():
    sys.exit('MISSING FILE: %s (run from the project root)' % rel)
t = p.read_text(encoding='utf-8')

DIV = '<div class="sidebar-divider"></div>'
SECTIONS = (
    ('<i class="bi bi-person-circle"></i> CUSTOMER',
     '{% if user.is_authenticated and user.customer_profile or SHOP.customer_login_enabled or SHOP.customer_register_enabled %}'),
    ('<i class="bi bi-shop"></i> SELLER',
     '{% if user.is_authenticated and user.vendor_profile or SHOP.vendor_login_enabled or SHOP.vendor_register_enabled %}'),
)

done = 0
for marker, cond in SECTIONS:
    if cond in t:
        continue
    if t.count(marker) != 1:
        sys.exit('ANCHOR PROBLEM: %r found %d times (need 1)' % (marker, t.count(marker)))
    mi = t.index(marker)
    d = t.rfind(DIV, 0, mi)
    if d == -1:
        sys.exit('ANCHOR PROBLEM: no sidebar-divider before %r' % marker)
    start = t.rfind('\n', 0, d) + 1                       # start of the divider's line
    close = re.compile(r'\n {8}</div>\n').search(t, mi)    # the section's own closing </div> (8-space indent)
    if not close:
        sys.exit('ANCHOR PROBLEM: closing </div> of the section %r not found' % marker)
    # insert the later position first so the earlier index stays valid
    t = t[:close.end()] + '        {% endif %}\n' + t[close.end():]
    t = t[:start] + '        ' + cond + '\n' + t[start:]
    done += 1

p.write_text(t, encoding='utf-8')
print('ok ' if done else 'skip', rel)
