# trade/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TradeViewSet, TradeFinancingViewSet, TradeLoanViewSet,
    TradeCostViewSet, BrokerageViewSet, GoodsReceivedNoteViewSet
)

router = DefaultRouter()
router.register(r'trades', TradeViewSet, basename='trade')
router.register(r'financing', TradeFinancingViewSet, basename='trade-financing')
router.register(r'loans', TradeLoanViewSet, basename='trade-loan')
router.register(r'costs', TradeCostViewSet, basename='trade-cost')
router.register(r'brokerages', BrokerageViewSet, basename='brokerage')
router.register(r'grns', GoodsReceivedNoteViewSet, basename='grn')

app_name = 'trade'
urlpatterns = [
    path('', include(router.urls)),
]