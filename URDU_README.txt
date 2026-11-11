URDU IN ALL APPS - update (copy these files over your project, same paths)

Changed / new files:
  static/fonts/JameelNooriNastaleeq.woff            (NEW - Jameel Noori Nastaleeq font, subset)
  static/fonts/JameelNooriNastaleeq-readme.html     (NEW - font licence/readme)
  templates/components/i18n.html                    (font-face + Urdu Nastaleeq + portal RTL rules)
  templates/components/lang_switch.html             (NEW - English / اردو / العربية switch)
  templates/customer_portal/base_shop.html          (Shop portal: lang/dir, RTL bootstrap, i18n, switch)
  templates/customer_portal/rider/base.html         (Rider app)
  templates/customer_portal/rider/login.html
  templates/customer_portal/rider/register.html
  templates/shareholders/portal/base.html           (Shareholder portal)
  ceo_module/templates/ceo/base_executive.html      (CEO portal)
  templates/auth/login.html                         (Login page)
  app/i18n/i18n_default.py                          (+256 portal words in Urdu)

After copying:
  1) python manage.py collectstatic --noinput   (if you use collectstatic)
  2) Login as admin -> Settings -> Translations -> "Load defaults"  (adds the new portal words)
  3) Open any portal, click اردو. Missing words: admin browses the portal in Urdu and they are
     collected automatically in Translation Manager (then use auto-translate).
