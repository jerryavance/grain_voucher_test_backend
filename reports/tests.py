# reports/tests.py
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from datetime import timedelta
from decimal import Decimal

from authentication.models import GrainUser
from hubs.models import Hub
from .models import ReportExport, ReportSchedule
from .utils import (
    generate_supplier_report,
    calculate_aging,
    export_to_csv,
    format_currency,
)


class ReportExportModelTest(TestCase):
    """Test ReportExport model"""
    
    def setUp(self):
        self.user = GrainUser.objects.create_user(
            phone_number='+256700000001',
            password='testpass123',
            role='finance'
        )
    
    def test_create_report_export(self):
        """Test creating a report export"""
        report = ReportExport.objects.create(
            report_type='supplier',
            format='pdf',
            generated_by=self.user,
            filters={'start_date': '2024-01-01'}
        )
        
        self.assertEqual(report.status, 'pending')
        self.assertIsNotNone(report.expires_at)
        self.assertFalse(report.is_expired())
    
    def test_mark_completed(self):
        """Test marking report as completed"""
        report = ReportExport.objects.create(
            report_type='trade',
            format='excel',
            generated_by=self.user
        )
        
        report.mark_completed('/path/to/file.xlsx', 100)
        
        self.assertEqual(report.status, 'completed')
        self.assertEqual(report.file_path, '/path/to/file.xlsx')
        self.assertEqual(report.record_count, 100)
        self.assertIsNotNone(report.completed_at)
    
    def test_mark_failed(self):
        """Test marking report as failed"""
        report = ReportExport.objects.create(
            report_type='invoice',
            format='csv',
            generated_by=self.user
        )
        
        report.mark_failed('Error generating report')
        
        self.assertEqual(report.status, 'failed')
        self.assertEqual(report.error_message, 'Error generating report')
    
    def test_expiry(self):
        """Test report expiry"""
        report = ReportExport.objects.create(
            report_type='payment',
            format='pdf',
            generated_by=self.user
        )
        
        # Set expiry to past
        report.expires_at = timezone.now() - timedelta(days=1)
        report.save()
        
        self.assertTrue(report.is_expired())


class ReportScheduleModelTest(TestCase):
    """Test ReportSchedule model"""
    
    def setUp(self):
        self.user = GrainUser.objects.create_user(
            phone_number='+256700000002',
            password='testpass123',
            role='super_admin'
        )
        self.hub = Hub.objects.create(
            name='Test Hub',
            location='Test Location'
        )
    
    def test_create_schedule(self):
        """Test creating a report schedule"""
        schedule = ReportSchedule.objects.create(
            name='Daily Trade Report',
            report_type='trade',
            format='pdf',
            frequency='daily',
            created_by=self.user,
            hub=self.hub
        )
        
        self.assertTrue(schedule.is_active)
        self.assertEqual(schedule.frequency, 'daily')
    
    def test_weekly_schedule_validation(self):
        """Test weekly schedule requires day_of_week"""
        schedule = ReportSchedule.objects.create(
            name='Weekly Report',
            report_type='supplier',
            format='excel',
            frequency='weekly',
            day_of_week=1,  # Tuesday
            created_by=self.user
        )
        
        self.assertEqual(schedule.day_of_week, 1)


class ReportUtilsTest(TestCase):
    """Test report utility functions"""
    
    def test_format_currency(self):
        """Test currency formatting"""
        from .utils import format_currency
        
        result = format_currency(Decimal('1000.50'))
        self.assertEqual(result, 'UGX 1,000.50')
    
    def test_format_percentage(self):
        """Test percentage formatting"""
        from .utils import format_percentage
        
        result = format_percentage(25.5)
        self.assertEqual(result, '25.50%')
    
    def test_export_to_csv(self):
        """Test CSV export"""
        data = [
            {'name': 'Test', 'value': 100},
            {'name': 'Test 2', 'value': 200}
        ]
        columns = ['name', 'value']
        
        result = export_to_csv(data, columns)
        
        self.assertIn('name,value', result)
        self.assertIn('Test,100', result)
    
    def test_calculate_aging(self):
        """Test aging calculation"""
        from accounting.models import Invoice, Account
        from trade.models import Buyer
        
        # Create test data
        buyer = Buyer.objects.create(
            company_name='Test Buyer',
            phone_number='+256700000003'
        )
        account = Account.objects.create(
            account_name='Test Account',
            buyer=buyer
        )
        
        # Create invoices with different due dates
        today = timezone.now().date()
        
        invoice1 = Invoice.objects.create(
            account=account,
            invoice_number='INV001',
            total_amount=Decimal('1000'),
            due_date=today + timedelta(days=5),
            payment_status='unpaid'
        )
        
        invoice2 = Invoice.objects.create(
            account=account,
            invoice_number='INV002',
            total_amount=Decimal('2000'),
            due_date=today - timedelta(days=15),
            payment_status='unpaid'
        )
        
        invoices = [invoice1, invoice2]
        aging = calculate_aging(invoices)
        
        self.assertEqual(aging['current'], Decimal('1000'))
        self.assertEqual(aging['1-30_days'], Decimal('2000'))


class ReportAPITest(APITestCase):
    """Test Report API endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create users
        self.admin_user = GrainUser.objects.create_user(
            phone_number='+256700000004',
            password='testpass123',
            role='super_admin'
        )
        
        self.finance_user = GrainUser.objects.create_user(
            phone_number='+256700000005',
            password='testpass123',
            role='finance'
        )
        
        self.regular_user = GrainUser.objects.create_user(
            phone_number='+256700000006',
            password='testpass123',
            role='buyer'
        )
    
    def test_generate_report_permission(self):
        """Test report generation permission"""
        # Finance user can generate
        self.client.force_authenticate(user=self.finance_user)
        response = self.client.post('/api/reports/generate/supplier/', {
            'format': 'pdf',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31'
        })
        
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED])
        
        # Regular user cannot generate
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post('/api/reports/generate/supplier/', {
            'format': 'pdf'
        })
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_list_report_exports(self):
        """Test listing report exports"""
        # Create test reports
        ReportExport.objects.create(
            report_type='supplier',
            format='pdf',
            generated_by=self.finance_user,
            status='completed'
        )
        
        self.client.force_authenticate(user=self.finance_user)
        response = self.client.get('/api/reports/exports/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_create_schedule(self):
        """Test creating a report schedule"""
        self.client.force_authenticate(user=self.admin_user)
        
        data = {
            'name': 'Daily Supplier Report',
            'report_type': 'supplier',
            'format': 'pdf',
            'frequency': 'daily',
            'time_of_day': '09:00:00',
            'filters': {'grain_type_id': 'some-uuid'}
        }
        
        response = self.client.post('/api/reports/schedules/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Daily Supplier Report')
    
    def test_schedule_validation(self):
        """Test schedule validation"""
        self.client.force_authenticate(user=self.admin_user)
        
        # Weekly schedule without day_of_week should fail
        data = {
            'name': 'Weekly Report',
            'report_type': 'trade',
            'format': 'excel',
            'frequency': 'weekly',
            'time_of_day': '09:00:00'
        }
        
        response = self.client.post('/api/reports/schedules/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('day_of_week', str(response.data))
    
    def test_dashboard_stats(self):
        """Test dashboard stats endpoint"""
        self.client.force_authenticate(user=self.finance_user)
        
        response = self.client.get('/api/reports/dashboard/stats/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('trades', response.data)
        self.assertIn('invoices', response.data)
        self.assertIn('payments', response.data)


class ReportGenerationTest(TestCase):
    """Test report generation logic"""
    
    def setUp(self):
        from trade.models import Buyer, Supplier, GrainType
        from hubs.models import Hub
        
        # Create test data
        self.hub = Hub.objects.create(
            name='Test Hub',
            location='Test Location'
        )
        
        self.buyer = Buyer.objects.create(
            company_name='Test Buyer',
            phone_number='+256700000007'
        )
        
        self.supplier = Supplier.objects.create(
            first_name='John',
            last_name='Doe',
            phone_number='+256700000008'
        )
        
        self.grain_type = GrainType.objects.create(
            name='Maize',
            code='MZ'
        )
    
    def test_generate_supplier_report(self):
        """Test supplier report generation"""
        from trade.models import Trade
        
        # Create test trades
        Trade.objects.create(
            buyer=self.buyer,
            supplier=self.supplier,
            grain_type=self.grain_type,
            hub=self.hub,
            quantity_kg=Decimal('1000'),
            buying_price=Decimal('2500'),
            status='completed'
        )
        
        filters = {
            'start_date': timezone.now().date() - timedelta(days=30),
            'end_date': timezone.now().date()
        }
        
        result = generate_supplier_report(filters)
        
        self.assertGreater(len(result), 0)
        self.assertIn('total_trades', result[0])
        self.assertIn('total_quantity_kg', result[0])