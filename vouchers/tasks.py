from celery import shared_task  # pyright: ignore[reportMissingImports]
from vouchers.models import Voucher

@shared_task
def update_all_voucher_values():
    vouchers = Voucher.objects.filter(status__in=['issued', 'transferred'])
    for voucher in vouchers:
        voucher.update_value()