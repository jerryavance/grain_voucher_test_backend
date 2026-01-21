# payroll/serializers.py
from rest_framework import serializers
from authentication.models import GrainUser
from .models import Employee, Payslip
from authentication.serializers import UserSerializer

class EmployeeSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(queryset=GrainUser.objects.all(), source='user', write_only=True)

    class Meta:
        model = Employee
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class PayslipSerializer(serializers.ModelSerializer):
    employee = EmployeeSerializer(read_only=True)
    employee_id = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all(), source='employee', write_only=True)

    class Meta:
        model = Payslip
        fields = '__all__'
        read_only_fields = ['id', 'net_pay', 'created_at']