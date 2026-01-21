# vouchers/management/commands/update_voucher_values.py
from django.core.management.base import BaseCommand
from vouchers.models import Voucher

class Command(BaseCommand):
    help = 'Updates the current value of all vouchers based on latest price feeds'

    def handle(self, *args, **kwargs):
        vouchers = Voucher.objects.all()
        for voucher in vouchers:
            voucher.update_value()
        self.stdout.write(self.style.SUCCESS(f'Updated {len(vouchers)} vouchers'))