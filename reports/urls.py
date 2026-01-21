# reports/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ReportExportViewSet,
    ReportScheduleViewSet,
    GenerateSupplierReportView,
    GenerateTradeReportView,
    GenerateInvoiceReportView,
    GeneratePaymentReportView,
    GenerateDepositorReportView,
    GenerateVoucherReportView,
    GenerateInventoryReportView,
    GenerateInvestorReportView,
    DashboardStatsView,
)

app_name = 'reports'

router = DefaultRouter()
router.register(r'exports', ReportExportViewSet, basename='export')
router.register(r'schedules', ReportScheduleViewSet, basename='schedule')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),
    
    # Report generation endpoints
    path('generate/supplier/', GenerateSupplierReportView.as_view(), name='generate-supplier'),
    path('generate/trade/', GenerateTradeReportView.as_view(), name='generate-trade'),
    path('generate/invoice/', GenerateInvoiceReportView.as_view(), name='generate-invoice'),
    path('generate/payment/', GeneratePaymentReportView.as_view(), name='generate-payment'),
    path('generate/depositor/', GenerateDepositorReportView.as_view(), name='generate-depositor'),
    path('generate/voucher/', GenerateVoucherReportView.as_view(), name='generate-voucher'),
    path('generate/inventory/', GenerateInventoryReportView.as_view(), name='generate-inventory'),
    path('generate/investor/', GenerateInvestorReportView.as_view(), name='generate-investor'),
    # Dashboard stats
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
]