# accounting/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InvoiceViewSet, PaymentViewSet, JournalEntryViewSet, BudgetViewSet

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoices')
router.register(r'payments', PaymentViewSet, basename='payments')
router.register(r'journal-entries', JournalEntryViewSet, basename='journal-entries')
router.register(r'budgets', BudgetViewSet, basename='budgets')

app_name = 'accounting'
urlpatterns = [
    path('', include(router.urls)),
]