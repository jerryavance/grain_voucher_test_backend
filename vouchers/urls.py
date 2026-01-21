# vouchers/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GrainTypeViewSet, QualityGradeViewSet, PriceFeedViewSet,
    DepositViewSet, VoucherViewSet, RedemptionViewSet,
    PurchaseOfferViewSet, InventoryViewSet, LedgerEntryViewSet
)

router = DefaultRouter()
router.register(r'grain-types', GrainTypeViewSet, basename='grain-types')
router.register(r'quality-grades', QualityGradeViewSet, basename='quality-grades')
router.register(r'price-feeds', PriceFeedViewSet, basename='price-feeds')
router.register(r'deposits', DepositViewSet, basename='deposits')
router.register(r'vouchers', VoucherViewSet, basename='vouchers')
router.register(r'redemptions', RedemptionViewSet, basename='redemptions')
router.register(r'purchase-offers', PurchaseOfferViewSet, basename='purchase-offers')
router.register(r'inventories', InventoryViewSet, basename='inventories')
router.register(r'ledger-entries', LedgerEntryViewSet, basename='ledger-entries')

app_name = 'vouchers'
urlpatterns = [
    path('', include(router.urls)),
]