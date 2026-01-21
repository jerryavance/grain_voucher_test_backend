# payroll/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmployeeViewSet, PayslipViewSet

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='employees')
router.register(r'payslips', PayslipViewSet, basename='payslips')

app_name = 'payroll'
urlpatterns = [
    path('', include(router.urls)),
]