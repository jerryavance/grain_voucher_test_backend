# reports/management/commands/run_scheduled_reports.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from reports.models import ReportSchedule
from reports.tasks import run_scheduled_reports


class Command(BaseCommand):
    help = 'Run scheduled reports that are due'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force run all active schedules regardless of due time',
        )
    
    def handle(self, *args, **options):
        if options['force']:
            self.stdout.write('Running all active schedules...')
            schedules = ReportSchedule.objects.filter(is_active=True)
            count = schedules.count()
        else:
            self.stdout.write('Checking for due schedules...')
            run_scheduled_reports()
            schedules = ReportSchedule.objects.filter(
                is_active=True,
                next_run__lte=timezone.now()
            )
            count = schedules.count()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully triggered {count} scheduled reports')
        )