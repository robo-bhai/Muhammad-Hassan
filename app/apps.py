from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'

    def ready(self):
        import app.signals
        import app.security.signals_security  
        import app.ledger.signals_gl
        import app.customer.offers_signals
        import app.customer.stock_alerts
        import app.customer.wishlist_alerts
        from app.image_tools import connect_signals as _img_signals
        _img_signals()
