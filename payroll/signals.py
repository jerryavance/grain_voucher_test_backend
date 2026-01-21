# payroll/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Payslip
from accounting.models import JournalEntry

@receiver(post_save, sender=Payslip)
def post_payroll_journal(sender, instance, created, **kwargs):
    if created:
        JournalEntry.objects.create(
            description=f"Payslip {instance.id} for {instance.period}",
            debit_account='Expenses-Payroll',
            credit_account='Cash',
            amount=instance.net_pay
        )