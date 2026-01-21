# investors/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InvestorAccountViewSet, InvestorDepositViewSet, InvestorWithdrawalViewSet,
    ProfitSharingAgreementViewSet
)

router = DefaultRouter()
router.register(r'accounts', InvestorAccountViewSet, basename='investor-account')
router.register(r'deposits', InvestorDepositViewSet, basename='investor-deposit')
router.register(r'withdrawals', InvestorWithdrawalViewSet, basename='investor-withdrawal')
router.register(r'profit-agreements', ProfitSharingAgreementViewSet, basename='profit-agreement')

app_name = 'investors'
urlpatterns = [
    path('', include(router.urls)),
]