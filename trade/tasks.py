# trade/tasks.py
from celery import shared_task
from .models import Trade
from django.core.mail import send_mail  # Assume email setup

@shared_task
def notify_approval(trade_id):
    trade = Trade.objects.get(id=trade_id)
    send_mail(
        'Trade Approval Needed',
        f'Trade {trade.id} pending approval.',
        'from@example.com',
        [trade.initiated_by.email],
    )