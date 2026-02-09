# sourcing/apps.py
from django.apps import AppConfig


class SourcingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sourcing'
    verbose_name = 'Sourcing & Procurement'

    def ready(self):
        """Import signal handlers when app is ready"""
        import sourcing.signals