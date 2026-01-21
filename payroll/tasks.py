# payroll/tasks.py
from celery import shared_task
from .models import Employee, Payslip
from decimal import Decimal
from datetime import date

@shared_task
def generate_payslips(period_str):
    period = date.fromisoformat(period_str)
    for employee in Employee.objects.all():
        gross = employee.salary
        deductions = gross * Decimal('0.10')  # Example 10% deductions
        Payslip.objects.create(
            employee=employee,
            period=period,
            gross_earnings=gross,
            deductions=deductions
        )