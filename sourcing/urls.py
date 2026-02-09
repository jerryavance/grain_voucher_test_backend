# sourcing/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SupplierProfileViewSet, PaymentPreferenceViewSet, SourceOrderViewSet,
    SupplierInvoiceViewSet, DeliveryRecordViewSet, WeighbridgeRecordViewSet,
    SupplierPaymentViewSet, NotificationViewSet, SupplierDashboardViewSet
)

app_name = 'sourcing'

router = DefaultRouter()
router.register(r'suppliers', SupplierProfileViewSet, basename='supplier')
router.register(r'payment-preferences', PaymentPreferenceViewSet, basename='payment-preference')
router.register(r'source-orders', SourceOrderViewSet, basename='source-order')
router.register(r'supplier-invoices', SupplierInvoiceViewSet, basename='supplier-invoice')
router.register(r'deliveries', DeliveryRecordViewSet, basename='delivery')
router.register(r'weighbridge', WeighbridgeRecordViewSet, basename='weighbridge')
router.register(r'supplier-payments', SupplierPaymentViewSet, basename='supplier-payment')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'supplier-dashboard', SupplierDashboardViewSet, basename='supplier-dashboard')

urlpatterns = [
    path('', include(router.urls)),
]