# app/ structure

> **Root `app/` mein sirf Django ki zaroori files hain:** `__init__.py, apps.py, urls.py, views.py, forms.py, signals.py, tests.py`.
> Baqi sab kuch folders mein hai. Purane import naam (`app.posting_core`, `app.store_access` ...) `_legacy_aliases.py`
> ki wajah se ab bhi chalte hain (wohi module, copy nahi). Naya code naye path se import karein.

## Purani file -> nayi jagah
| Folder | Files |
|---|---|
| `store/` | store_access, store_accounting, store_exports (= report_exports), store_issue_service, store_ops_service, store_receive, store_transfer_service |
| `module_config/` | module_catalog, settings_catalog, shop_flags, lite_edition |
| `security/` | decorators, module_gate (+ pehle se security_utils, views_security, ...) |
| `config/` | context_processors, custom_storage |
| `ledger/` | posting, posting_core, posting_gaps, posting_step5, posting_stock, signals_gl, subledger |
| `utils/` | batch_report_logic, push_service, barcode_utils, certificate_utils, whatsapp_utils, chat_email_helper (= purana email_helper) |
| `customer/` | vendor_commission (+ views_*) |
| `tests_suite/` | tests_coupons, tests_disputes, tests_license, tests_login_throttle, tests_no_csrf_exempt, tests_purchase_flow, tests_sale_flow, tests_security_totp, tests_stock_lock |
| `docs/` | STRUCTURE.md, PROJECT_STRUCTURE.md, PRICING_UPGRADE_PLAN.md, logo_setup.md |
| `_backups/root_leftovers/` | .bak / .bad / dead duplicate files (import nahi hotin) |

Tests chalane ka tareeqa: `python manage.py test app.tests_suite` (ya ek file: `app.tests_suite.tests_sale_flow`).
Naya rename add karna ho to `_legacy_aliases.py` ke ALIASES mein ek line.


## Logic
- ai/        AI engines + chatbots
- ledger/    posting (double-entry), GL signals, subledger, posting tests
- store/     warehouse logic: access, receive, issue (FIFO), transfer, accounting, exports, barcode
- security/  2FA, security utils/views, admin OTP, security signals, permission matrix (permission_catalog.py, permissions.py -> @perm_required, see PERMISSIONS.md)
- i18n/      languages and translation service

## Views
- views_frontend/   (urls.py: views_frontend.some_view  -> pehle jaisa kaam karta hai)
    pos_sales/ sales, pos, shift, shop_tools, returns, installments, services
    purchase/  purchases, vendors, vendor_reports, purchase_orders, grn, monthly_plans, po_pro, supply_chain
    finance/   accounting, cash, expenses, self_expenses, budgets, budget_goals, expense_masters,
               closing, subledger, profit_analysis, loans
    shareholder/ shareholders, certificates, share_transfers, meetings, terms, support_tickets,
               registration_requests, cash_balances, cash_requests, cash_deductions, cash_reports,
               shareholder_portal, dividends
    inventory/ products, warehouses, production
    people/    hr, users
    ai/        ai_insights, operations, ai_purchasing, cash_ai, shareholder_ai, board_cso
    system/    dashboard, dashboard_extras, reports, notifications, chat, backup, audit,
               language, translations, settings_center, masters_api
- customer/    customer auth, customer portal, order tracking, delivery
- backoffice/  bi, document, loan, subscription, testing
- views.py     home + 404/500 handlers (same jagah)

## Models  (app.models.X ab bhi kaam karta hai, models/__init__.py sab re-export karta hai)
- models/finance/    accounting, budgeting, gl_posting
- models/trade/      customers, sales, sale_orders, sale_returns, installments, targets,
                     vendors, purchases, purchase_orders, purchase_returns, monthly_plans,
                     customer_portal, delivery, pos_shift, supply_chain, services
- models/inventory/  catalog, production
- models/people/     hr, shareholders, shares, dividends, drip, cash, loans, discounts
- models/ai_bi/      insights, operations, purchase_ai, cash_ai, shareholder_ai, board, cso_tech, bi
- models/system/     core, security, documents, translation, constants, audit_qa

## Naye import
from app.ledger import posting_core
from app import report_exports
from app.models import Product              # pehle jaisa
Naya view/model add karne par: file sahi group mein rakho aur __init__.py ki _MODULES list mein
"group.file" likho (models/ aur views_frontend/ dono mein).
Models mein agar ek class dusre chunk ki class ko seedha use kare (ForeignKey(Class), base class), to
wahan "from .other_chunk import Class" likhna hoga (jaise people/dividends.py mein Shareholder).
