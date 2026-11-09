# app/settings_catalog.py
"""
ONE SINGLE LIST OF ALL PROJECT SETTINGS (single source of truth).

Settings Center (/settings/center/) builds tabs and form fields from this list.
To add a new setting, just write one field here; no need to change the view/template.

Tab keys:
  key, label, icon, desc : tab ka naam aur tafseel
  access   : 'superuser' | 'admin' (superuser ya staff) | 'owner' (superuser, Owner ya CEO)
  store    : where the data is saved ('system' | 'security' | 'delivery' | 'company' | None)
  fields   : generic fields (neeche)
  special  : a special part that is not built by the generic form ('modules' | 'shareholders' | 'city_charges' | 'logo' | 'voice')
  links    : [(label, url_name)] - tab ke neeche quick buttons

Field keys:
  name, label, type, default, help, group
  type   : bool | int | decimal | text | textarea | email | url | select
  min/max: limits for int/decimal
  choices: for select [(value, label), ...]
  prefix/suffix: input ke aage/peeche ka text (Rs., %, Days ...)
  required: if True it cannot be empty

NOTE ('system' store): SystemSetting.set_value lowercases the value, so in this store
keep only bool / number / select (lowercase values). Use a dedicated model for free text.
"""

from django.conf import settings as _dj_settings

TABS = [
    # ------------------------------------------------------------------ Modules
    {
        'key': 'modules', 'label': 'Modules', 'icon': 'bi-toggles',
        'desc': 'Choose Full ERP or Lite and switch each module on or off',
        'access': 'superuser', 'store': 'system', 'special': 'modules',
        'fields': [],
    },
    # ------------------------------------------------------- Shareholders / Dividends
    {
        'key': 'shareholders', 'label': 'Shareholders', 'icon': 'bi-people',
        'desc': 'Purchase deduction and dividend rules',
        'access': 'superuser', 'store': 'system', 'special': 'shareholders',
        'links': [('Bulk Process Deductions', 'bulk_process_deductions'),
                  ('Deduction Report', 'shareholder_deduction_report'),
                  ('Balance Dividend Reports', 'balance_dividend_report'),
                  ('All Balance Dividends', 'balance_dividend_list')],
        'fields': [
            {'name': 'enable_shareholder_purchase_deduction', 'label': 'Purchase par shareholder deduction', 'type': 'bool',
             'default': True, 'group': 'Purchase Deduction',
             'help': 'If ON, the purchase amount is deducted from the shareholders cash balance.'},
            {'name': 'shareholder_deduction_type', 'label': 'Deduction Type', 'type': 'select', 'default': 'proportional',
             'choices': [('proportional', 'Proportional (by balance)'), ('equal', 'Equal (same for everyone)')],
             'group': 'Purchase Deduction',
             'help': 'Proportional: the higher the balance, the higher the deduction. Equal: same for everyone.'},

            {'name': 'enable_balance_dividend', 'label': 'Balance-based dividend', 'type': 'bool',
             'default': True, 'group': 'Dividends',
             'help': 'When turned OFF, the balance-based dividend options are disabled.'},
            {'name': 'default_dividend_type', 'label': 'Default Dividend Type', 'type': 'select', 'default': 'both',
             'choices': [('share', 'Share-based'), ('balance', 'Balance-based'), ('both', 'Both (admin chune)')],
             'group': 'Dividends'},
            {'name': 'default_dividend_percentage', 'label': 'Default Dividend Percentage', 'type': 'decimal',
             'default': '50', 'min': 1, 'max': 100, 'suffix': '%', 'group': 'Dividends',
             'help': 'How much of the profit goes into the dividend.'},
            {'name': 'min_balance_for_dividend', 'label': 'Minimum Balance Used', 'type': 'decimal',
             'default': '0', 'min': 0, 'prefix': 'Rs.', 'group': 'Eligibility',
             'help': '0 = sab shareholders eligible.'},
            {'name': 'min_holding_months', 'label': 'Minimum Holding Period', 'type': 'int',
             'default': '0', 'min': 0, 'max': 60, 'suffix': 'Months', 'group': 'Eligibility',
             'help': '0 = no condition.'},
            {'name': 'auto_process_days', 'label': 'Auto-Process After', 'type': 'int',
             'default': '7', 'min': 0, 'max': 30, 'suffix': 'Days', 'group': 'Eligibility',
             'help': 'The dividend is processed automatically this many days after declaring (0 = manual only).'},
        ],
    },
    # ------------------------------------------------------------------ Company
    {
        'key': 'company', 'label': 'Company', 'icon': 'bi-building',
        'desc': 'Naam, contact, logo aur deposit payment details',
        'access': 'owner', 'store': 'company', 'special': 'logo',
        'fields': [
            {'name': 'name', 'label': 'Company Name', 'type': 'text', 'required': True, 'group': 'Basic Information', 'max_len': 255},
            {'name': 'email', 'label': 'Email', 'type': 'email', 'required': True, 'group': 'Basic Information'},
            {'name': 'contact_number', 'label': 'Phone', 'type': 'text', 'required': True, 'group': 'Basic Information', 'max_len': 50},
            {'name': 'website', 'label': 'Website', 'type': 'url', 'group': 'Basic Information'},
            {'name': 'address', 'label': 'Address', 'type': 'textarea', 'required': True, 'group': 'Basic Information', 'wide': True},
            {'name': 'tagline', 'label': 'Tagline', 'type': 'text', 'group': 'Basic Information', 'max_len': 255, 'wide': True},
            {'name': 'footer_note', 'label': 'Footer Note (reports)', 'type': 'text', 'group': 'Basic Information', 'max_len': 255, 'wide': True},

            {'name': 'jazzcash_number', 'label': 'JazzCash Number', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 20},
            {'name': 'easypaisa_number', 'label': 'EasyPaisa Number', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 20},
            {'name': 'bank_name', 'label': 'Bank Name', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 100},
            {'name': 'bank_account_title', 'label': 'Account Title', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 200},
            {'name': 'bank_account_number', 'label': 'Account Number', 'type': 'text', 'group': 'Deposit Payments', 'max_len': 50},
            {'name': 'deposit_instructions', 'label': 'Deposit Instructions', 'type': 'textarea', 'group': 'Deposit Payments', 'wide': True},
        ],
    },
    # ----------------------------------------------------------------- Delivery
    {
        'key': 'delivery', 'label': 'Delivery', 'icon': 'bi-truck',
        'desc': 'Delivery charges, express, pickup aur city-wise rates',
        'access': 'admin', 'store': 'delivery', 'special': 'city_charges',
        'fields': [
            {'name': 'standard_charge', 'label': 'Standard Charge', 'type': 'decimal', 'default': '100.00', 'min': 0,
             'prefix': 'Rs.', 'group': 'Standard Delivery'},
            {'name': 'standard_delivery_time', 'label': 'Standard Delivery Time', 'type': 'text', 'default': '2-4 working days',
             'required': True, 'max_len': 100, 'group': 'Standard Delivery'},

            {'name': 'express_delivery_enabled', 'label': 'Express Delivery on', 'type': 'bool', 'default': True, 'group': 'Express Delivery'},
            {'name': 'express_charge', 'label': 'Express Charge', 'type': 'decimal', 'default': '300.00', 'min': 0,
             'prefix': 'Rs.', 'group': 'Express Delivery'},
            {'name': 'express_delivery_time', 'label': 'Express Delivery Time', 'type': 'text', 'default': 'Same day (within city)',
             'required': True, 'max_len': 100, 'group': 'Express Delivery'},

            {'name': 'store_pickup_enabled', 'label': 'Store Pickup on', 'type': 'bool', 'default': True, 'group': 'Pickup & Free Delivery'},
            {'name': 'free_delivery_enabled', 'label': 'Free Delivery on', 'type': 'bool', 'default': True, 'group': 'Pickup & Free Delivery'},
            {'name': 'free_delivery_threshold', 'label': 'Free Delivery Threshold', 'type': 'decimal', 'default': '1000.00', 'min': 0,
             'prefix': 'Rs.', 'group': 'Pickup & Free Delivery', 'help': 'Delivery is free on orders above this amount.'},
        ],
    },
    # ------------------------------------------------------------------ Pricing
    {
        'key': 'pricing', 'label': 'Pricing', 'icon': 'bi-tags',
        'desc': 'Minimum profit margin allowed when setting selling prices',
        'access': 'owner', 'store': 'system',
        'links': [('Stock Batches', 'batch_list'), ('Price History', 'price_history')],
        'fields': [
            {'name': 'min_margin_percent', 'label': 'Minimum margin (company rule)', 'type': 'decimal', 'default': '0',
             'min': 0, 'max': 1000, 'suffix': '%', 'group': 'Margin Policy',
             'help': 'No selling price may be lower than cost + this %. 0 = no minimum (the price can still never be below cost). '
                     'A category can override this in Admin > Product Category > Minimum margin %.'},
        ],
    },
    # ----------------------------------------------------------------- Security
    {
        'key': 'security', 'label': 'Security', 'icon': 'bi-shield-lock',
        'desc': 'Login, password, IP, API aur alerts',
        'access': 'superuser', 'store': 'security',
        'fields': [
            {'name': 'enable_2fa', 'label': 'Two-Factor Authentication', 'type': 'bool', 'default': False, 'group': 'Login & Session'},
            {'name': 'enable_auto_logout', 'label': 'Auto logout', 'type': 'bool', 'default': True, 'group': 'Login & Session'},
            {'name': 'max_login_attempts', 'label': 'Max Login Attempts', 'type': 'int', 'default': '5', 'min': 1, 'max': 20, 'group': 'Login & Session'},
            {'name': 'lockout_time', 'label': 'Lockout Time', 'type': 'int', 'default': '30', 'min': 1, 'max': 1440, 'suffix': 'Min', 'group': 'Login & Session'},
            {'name': 'session_timeout', 'label': 'Session Timeout', 'type': 'int', 'default': '60', 'min': 1, 'max': 1440, 'suffix': 'Min', 'group': 'Login & Session'},

            {'name': 'min_password_length', 'label': 'Min Password Length', 'type': 'int', 'default': '8', 'min': 4, 'max': 64, 'group': 'Password Policy'},
            {'name': 'password_expiry_days', 'label': 'Password Expiry', 'type': 'int', 'default': '90', 'min': 0, 'max': 730, 'suffix': 'Days', 'group': 'Password Policy', 'help': '0 = never expires.'},
            {'name': 'password_history_count', 'label': 'Password History', 'type': 'int', 'default': '5', 'min': 0, 'max': 24, 'group': 'Password Policy'},
            {'name': 'require_uppercase', 'label': 'Uppercase zaroori', 'type': 'bool', 'default': True, 'group': 'Password Policy'},
            {'name': 'require_lowercase', 'label': 'Lowercase zaroori', 'type': 'bool', 'default': True, 'group': 'Password Policy'},
            {'name': 'require_numbers', 'label': 'Number zaroori', 'type': 'bool', 'default': True, 'group': 'Password Policy'},
            {'name': 'require_special_chars', 'label': 'Special character zaroori', 'type': 'bool', 'default': True, 'group': 'Password Policy'},
            {'name': 'prevent_password_reuse', 'label': 'Prevent reusing an old password', 'type': 'bool', 'default': True, 'group': 'Password Policy'},

            {'name': 'enable_ip_whitelist', 'label': 'IP Whitelist', 'type': 'bool', 'default': False, 'group': 'Access Control'},
            {'name': 'enable_ip_blacklist', 'label': 'IP Blacklist', 'type': 'bool', 'default': True, 'group': 'Access Control'},
            {'name': 'enable_api_auth', 'label': 'API Authentication', 'type': 'bool', 'default': True, 'group': 'Access Control'},
            {'name': 'api_rate_limit', 'label': 'API Rate Limit', 'type': 'int', 'default': '100', 'min': 1, 'max': 100000, 'suffix': '/min', 'group': 'Access Control'},

            {'name': 'enable_security_alerts', 'label': 'Security Alerts', 'type': 'bool', 'default': True, 'group': 'Alerts'},
            {'name': 'alert_email', 'label': 'Alert Email', 'type': 'email', 'group': 'Alerts'},
            {'name': 'alert_whatsapp', 'label': 'Alert WhatsApp', 'type': 'text', 'max_len': 20, 'group': 'Alerts'},
        ],
    },
    # --------------------------------------------------------------------- Shop
    {
        'key': 'shop', 'label': 'Shop', 'icon': 'bi-shop',
        'desc': 'Online shop: vendors (register, login, products, orders)',
        'access': 'admin', 'store': 'system',
        'links': [('Vendor approvals', 'vendor_approvals'), ('Shop banners', 'shop_banner_list')],
        'fields': [
            {'name': 'vendor_register_enabled', 'label': 'Register as a Seller', 'type': 'bool', 'default': True,
             'group': 'Vendors', 'help': 'OFF = the register page and its link are closed. Existing vendors are not affected.'},
            {'name': 'vendor_login_enabled', 'label': 'Seller Login', 'type': 'bool', 'default': True,
             'group': 'Vendors', 'help': 'OFF = vendors cannot log in (already logged-in sessions stay until they sign out).'},
            {'name': 'vendor_auto_approve_accounts', 'label': 'Auto-approve new vendor accounts', 'type': 'bool',
             'default': bool(getattr(_dj_settings, 'VENDOR_AUTO_APPROVE_ACCOUNTS', False)), 'group': 'Vendors',
             'help': 'OFF = admin approves each vendor (Vendors > Approvals).'},
            {'name': 'vendor_auto_approve_products', 'label': 'Auto-approve vendor products', 'type': 'bool',
             'default': bool(getattr(_dj_settings, 'VENDOR_AUTO_APPROVE_PRODUCTS', False)), 'group': 'Vendors',
             'help': 'OFF = every new or edited product waits for admin approval before it is live.'},
            {'name': 'vendor_can_add_products', 'label': 'Vendors can add / edit products', 'type': 'bool', 'default': True,
             'group': 'Vendors'},
            {'name': 'vendor_can_manage_orders', 'label': 'Vendors can manage orders', 'type': 'bool', 'default': True,
             'group': 'Vendors', 'help': 'OFF = vendors cannot open the orders page or accept / reject / mark ready.'},
            {'name': 'customer_register_enabled', 'label': 'Register as a Customer', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = the sign-up page and its links are closed. Existing customers are not affected.'},
            {'name': 'customer_login_enabled', 'label': 'Customer login', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = customers cannot log in (logged-in sessions stay until they sign out).'},
            {'name': 'shop_ordering_enabled', 'label': 'Online ordering (checkout / buy now)', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = browsing and cart still work, but checkout and placing orders are paused.'},
            {'name': 'order_tracking_enabled', 'label': 'Order tracking page', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = the public Track Order page and its links are closed.'},
            {'name': 'customer_can_cancel_orders', 'label': 'Customers can cancel orders', 'type': 'bool', 'default': True,
             'group': 'Customers'},
            {'name': 'customer_can_rate_orders', 'label': 'Customers can rate orders', 'type': 'bool', 'default': True,
             'group': 'Customers'},
            {'name': 'customer_can_dispute_orders', 'label': 'Customers can report a problem (dispute)', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = the "Report a problem" form on delivered orders is hidden.'},
            {'name': 'dispute_window_hours', 'label': 'Dispute window after delivery', 'type': 'decimal', 'default': '48',
             'min': 1, 'max': 720, 'suffix': 'hours', 'group': 'Customers',
             'help': 'Customers can open a dispute only this many hours after delivery.'},
            {'name': 'shop_stores_enabled', 'label': 'Stores page', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = stores list/detail pages, the "Stores near you" row and Stores links are closed.'},
            {'name': 'shop_banners_enabled', 'label': 'Banners', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = admin banners are not shown on the shop home or stores page.'},
            {'name': 'shop_push_enabled', 'label': 'Push notifications', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = no phone/browser popups for orders (in-app and email notifications still work). Needs VAPID keys in settings.'},
            {'name': 'shop_coupons_enabled', 'label': 'Coupons (promo codes)', 'type': 'bool', 'default': True,
             'group': 'Offers', 'help': 'OFF = coupon box, store offer badges and vendor coupons are hidden and ignored.'},
            {'name': 'shop_wallet_enabled', 'label': 'Wallet credit', 'type': 'bool', 'default': True,
             'group': 'Offers', 'help': 'OFF = customers cannot pay from wallet; the Wallet page is hidden.'},
            {'name': 'cashback_percent', 'label': 'Cashback on delivered orders', 'type': 'decimal', 'default': '0',
             'min': 0, 'max': 25, 'suffix': '%', 'group': 'Offers',
             'help': 'Customer gets this % of the order items back as wallet credit after delivery. 0 = off.'},
            {'name': 'cashback_max', 'label': 'Maximum cashback per order', 'type': 'decimal', 'default': '0',
             'min': 0, 'prefix': 'Rs.', 'group': 'Offers', 'help': '0 = no limit.'},
            {'name': 'shop_loyalty_enabled', 'label': 'Loyalty points', 'type': 'bool', 'default': False,
             'group': 'Offers', 'help': 'ON = customers earn points on delivered orders and can convert them to wallet credit (Wallet must also be ON).'},
            {'name': 'loyalty_points_per_100', 'label': 'Points earned per Rs. 100', 'type': 'decimal', 'default': '1',
             'min': 0, 'max': 100, 'group': 'Offers', 'help': 'On the order items total (after coupon). 1 = one point for every Rs. 100.'},
            {'name': 'loyalty_point_value', 'label': 'Value of one point', 'type': 'decimal', 'default': '1',
             'min': 0, 'prefix': 'Rs.', 'group': 'Offers', 'help': 'Wallet credit the customer gets for each point converted.'},
            {'name': 'loyalty_min_redeem', 'label': 'Minimum points to convert', 'type': 'int', 'default': '100',
             'min': 1, 'suffix': 'Points', 'group': 'Offers'},
            {'name': 'shop_pro_enabled', 'label': 'Pro membership (free delivery)', 'type': 'bool', 'default': False,
             'group': 'Offers', 'help': 'ON = customers can ask to join Pro; you activate them from Admin > Pro Memberships after you receive the payment.'},
            {'name': 'pro_price', 'label': 'Pro price', 'type': 'decimal', 'default': '0', 'min': 0,
             'prefix': 'Rs.', 'group': 'Offers', 'help': 'Shown to the customer. Payment is collected by you (cash / bank / JazzCash), not online.'},
            {'name': 'pro_days', 'label': 'Pro duration', 'type': 'int', 'default': '30', 'min': 1, 'max': 366,
             'suffix': 'Days', 'group': 'Offers'},
            {'name': 'pro_min_order', 'label': 'Pro free delivery: minimum order', 'type': 'decimal', 'default': '0',
             'min': 0, 'prefix': 'Rs.', 'group': 'Offers', 'help': 'Pro members get free delivery on orders of at least this amount. 0 = every order.'},
            {'name': 'shop_favorites_enabled', 'label': 'Favourite stores and wishlist', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = heart buttons, the Favourites page and the Favourites filter are hidden.'},
            {'name': 'shop_search_enabled', 'label': 'Product search', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = search bars are hidden and search text is ignored.'},
            {'name': 'shop_voice_search_enabled', 'label': 'Voice search (microphone)', 'type': 'bool', 'default': True,
             'group': 'Shop pages'},
            {'name': 'shop_chat_enabled', 'label': 'Customer chat', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = the chat endpoints stop answering.'},
            {'name': 'rider_login_enabled', 'label': 'Rider login', 'type': 'bool', 'default': True,
             'group': 'Riders', 'help': 'OFF = riders cannot log in (logged-in sessions stay until they sign out).'},
            {'name': 'rider_can_accept_orders', 'label': 'Riders can accept new orders', 'type': 'bool', 'default': True,
             'group': 'Riders', 'help': 'OFF = riders cannot take orders from the offers list. Orders given to them directly are not affected.'},
            {'name': 'vendor_can_assign_riders', 'label': 'Vendors can choose a rider', 'type': 'bool', 'default': True,
             'group': 'Riders', 'help': 'OFF = the "Rider do" form is hidden in vendor orders and the action is refused.'},
            {'name': 'rider_earnings_enabled', 'label': 'Rider earnings page', 'type': 'bool', 'default': True,
             'group': 'Riders'},
            {'name': 'rider_register_enabled', 'label': 'Register as a Rider', 'type': 'bool', 'default': True,
             'group': 'Riders', 'help': 'OFF = the rider sign-up page and its links are closed.'},
            {'name': 'rider_auto_approve', 'label': 'Auto-approve new riders', 'type': 'bool', 'default': False,
             'group': 'Riders', 'help': 'OFF = admin approves each new rider (Riders page > Chalu).'},
        ],
    },
    # -------------------------------------------------------------------- Voice
    {
        'key': 'voice', 'label': 'Voice', 'icon': 'bi-megaphone',
        'desc': 'Voice announcements',
        'access': 'any', 'store': None, 'special': 'voice', 'fields': [],
        'links': [('Voice Announcement Settings kholein', 'voice_announcement_settings')],
    },
]

TAB_BY_KEY = {t['key']: t for t in TABS}
