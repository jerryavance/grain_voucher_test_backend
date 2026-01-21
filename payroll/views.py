# payroll/views.py
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Employee, Payslip
from .serializers import EmployeeSerializer, PayslipSerializer
from utils.permissions import IsSuperAdmin, IsFinance

class EmployeeViewSet(ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsFinance]

class PayslipViewSet(ModelViewSet):
    queryset = Payslip.objects.all()
    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsFinance]

    @action(detail=False, methods=['post'])
    def generate_monthly(self, request):
        # Trigger Celery task
        from .tasks import generate_payslips
        generate_payslips.delay(request.data.get('period'))
        return Response({"message": "Payslip generation started"})