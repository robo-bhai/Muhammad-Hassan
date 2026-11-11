URDU IN ALL APPS - professional update

NEW / CHANGED FILES (copy over project, same paths)
  static/fonts/JameelNooriNastaleeq.woff            Jameel Noori Nastaleeq font (subset, local, no internet needed)
  static/fonts/JameelNooriNastaleeq-readme.html     font readme
  templates/components/i18n.html                    Urdu typography (size, line-height, no fake bold, controls, tables, numbers) + RTL
  templates/components/lang_switch.html             English / اردو / العربية switch
  templates/customer_portal/base_shop.html          Shop portal
  templates/customer_portal/rider/{base,login,register}.html   Rider app
  templates/shareholders/portal/base.html           Shareholder portal
  ceo_module/templates/ceo/base_executive.html      CEO portal
  templates/auth/login.html                         Login page
  app/i18n/i18n_default.py                          ~980 more words: Shop, Seller, Rider, FAQ/Help, Shareholder, CEO, Login
  app/i18n/i18n_service.py                          "Load defaults" now also refreshes old default words (manual edits are never touched)

AFTER COPYING
  1) python manage.py collectstatic --noinput   (if you use it)
  2) Admin -> Settings -> Translations -> "Load defaults"
  3) Hard refresh (Ctrl+F5) and click اردو

TERMINOLOGY USED (consistent everywhere)
  Customer = گاہک | Order = آرڈر | Delivery = ڈیلیوری | Payment = ادائیگی | Status = حیثیت
  History = ہسٹری | Wallet = والیٹ | Rider = رائیڈر | Store = اسٹور | Products = مصنوعات
  Login = لاگ ان | Sign out = سائن آؤٹ | Dividend = ڈیویڈنڈ | Share = شیئر
