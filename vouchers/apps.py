# vouchers/apps.py
from django.apps import AppConfig

class VouchersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vouchers'

    def ready(self):
        import vouchers.signals  # Connect signals