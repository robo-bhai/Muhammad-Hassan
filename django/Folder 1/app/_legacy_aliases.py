"""
Old import names -> new folder locations.

The files that used to sit loose in app/ now live in folders (see docs/STRUCTURE.md).
So that nothing breaks (settings.py strings, migrations, mock.patch("app.x.y"), old
`from app.posting import ...` lines), `app.<old_name>` is served by the module in its
new folder. It is the SAME module object, not a copy.

New code: import from the new location, e.g.  from app.ledger import posting
To add a rename: add one line to ALIASES.
"""
import importlib
import importlib.abc
import importlib.util
import sys

ALIASES = {
    'ai_board_room': 'ai.ai_board_room',
    'ai_cash_engine': 'ai.ai_cash_engine',
    'ai_cso_tech': 'ai.ai_cso_tech',
    'ai_engine': 'ai.ai_engine',
    'ai_operations_engine': 'ai.ai_operations_engine',
    'ai_purchase_planner': 'ai.ai_purchase_planner',
    'ai_shareholder_engine': 'ai.ai_shareholder_engine',
    'auto_tester': 'testing_qa.auto_tester',
    'backup_service': 'backup.backup_service',
    'barcode_utils': 'utils.barcode_utils',
    'batch_report_logic': 'utils.batch_report_logic',
    'business_ratios': 'ai.business_ratios',
    'certificate_utils': 'utils.certificate_utils',
    'chatbot_engine': 'ai.chatbot_engine',
    'context_processors': 'config.context_processors',
    'custom_storage': 'config.custom_storage',
    'decorators': 'security.decorators',
    'email_helper': 'utils.chat_email_helper',
    'i18n_default': 'i18n.i18n_default',
    'i18n_lang': 'i18n.i18n_lang',
    'i18n_service': 'i18n.i18n_service',
    'lite_edition': 'module_config.lite_edition',
    'module_access': 'middleware.module_access',
    'module_catalog': 'module_config.module_catalog',
    'module_gate': 'security.module_gate',
    'posting': 'ledger.posting',
    'posting_core': 'ledger.posting_core',
    'posting_gaps': 'ledger.posting_gaps',
    'posting_step5': 'ledger.posting_step5',
    'posting_stock': 'ledger.posting_stock',
    'push_service': 'utils.push_service',
    'report_exports': 'store.store_exports',
    'security_2fa': 'middleware.security_2fa',
    'security_utils': 'security.security_utils',
    'settings_catalog': 'module_config.settings_catalog',
    'shop_flags': 'module_config.shop_flags',
    'signals_gl': 'ledger.signals_gl',
    'signals_security': 'security.signals_security',
    'store_access': 'store.store_access',
    'store_accounting': 'store.store_accounting',
    'store_exports': 'store.store_exports',
    'store_issue_service': 'store.store_issue_service',
    'store_ops_service': 'store.store_ops_service',
    'store_receive': 'store.store_receive',
    'store_transfer_service': 'store.store_transfer_service',
    'subledger': 'ledger.subledger',
    'vendor_commission': 'customer.vendor_commission',
    'views_admin_otp': 'security.views_admin_otp',
    'views_bi': 'backoffice.views_bi',
    'views_customer_auth': 'customer.views_customer_auth',
    'views_customer_portal': 'customer.views_customer_portal',
    'views_delivery': 'customer.views_delivery',
    'views_document': 'backoffice.views_document',
    'views_loan': 'backoffice.views_loan',
    'views_order_tracking': 'customer.views_order_tracking',
    'views_security': 'security.views_security',
    'views_subscription': 'backoffice.views_subscription',
    'views_testing': 'backoffice.views_testing',
    'whatsapp_utils': 'utils.whatsapp_utils',
}


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target):
        self.target = target
        self.real_spec = None

    def create_module(self, spec):
        module = importlib.import_module("app." + self.target)
        self.real_spec = getattr(module, "__spec__", None)
        return module

    def exec_module(self, module):
        # the import system stamped the alias spec on the module; put the real one back
        if self.real_spec is not None:
            module.__spec__ = self.real_spec


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        head, _, name = fullname.partition(".")
        if head != "app" or not name or "." in name:
            return None
        new = ALIASES.get(name)
        if new is None:
            return None
        return importlib.util.spec_from_loader(fullname, _AliasLoader(new))


def install():
    if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())
