# investors/serializers.py
from rest_framework import serializers
from django.utils import timezone
from decimal import Decimal
from authentication.models import GrainUser
from authentication.serializers import UserSerializer
from .models import (
    InvestorAccount, InvestorDeposit, InvestorWithdrawal, ProfitSharingAgreement
)
from django.db.models import Sum, Q
from dateutil.relativedelta import relativedelta


class InvestorDepositSerializer(serializers.ModelSerializer):
    investor = UserSerializer(source='investor_account.investor', read_only=True)
    investor_account_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = InvestorDeposit
        fields = ['id', 'investor', 'investor_account_id', 'amount', 'deposit_date', 'notes', 'created_at']
        read_only_fields = ['id', 'investor', 'deposit_date', 'created_at']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Deposit amount must be positive")
        return value

    def validate_investor_account_id(self, value):
        if not InvestorAccount.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid investor account ID.")
        return value

    # def create(self, validated_data):
    #     investor_account_id = validated_data.pop('investor_account_id')
    #     investor_account = InvestorAccount.objects.get(id=investor_account_id)
    #     validated_data['investor_account'] = investor_account
    #     return super().create(validated_data)

    def create(self, validated_data):
        investor_account_id = validated_data.pop('investor_account_id')
        investor_account = InvestorAccount.objects.get(id=investor_account_id)
        validated_data['investor_account'] = investor_account
        deposit = super().create(validated_data)
        # Update account balances
        investor_account.update_balance(validated_data['amount'], is_deposit=True)
        return deposit


class InvestorWithdrawalSerializer(serializers.ModelSerializer):
    investor = UserSerializer(source='investor_account.investor', read_only=True)
    investor_account_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = InvestorWithdrawal
        fields = [
            'id', 'investor', 'investor_account_id', 'amount', 'withdrawal_date',
            'status', 'notes', 'approved_by', 'approved_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'withdrawal_date', 'status', 'approved_by', 'approved_at', 'created_at', 'updated_at']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Withdrawal amount must be positive")
        return value
    
    def validate_investor_account_id(self, value):
        if not InvestorAccount.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid investor account ID.")
        return value

    def validate(self, data):
        investor_account_id = data.get('investor_account_id')
        amount = data.get('amount')
        if investor_account_id:
            account = InvestorAccount.objects.get(id=investor_account_id)
            if amount > account.available_balance:
                raise serializers.ValidationError({
                    "amount": "Withdrawal amount exceeds available balance"
                })
        return data

    def create(self, validated_data):
        investor_account_id = validated_data.pop('investor_account_id')
        investor_account = InvestorAccount.objects.get(id=investor_account_id)
        validated_data['investor_account'] = investor_account
        return super().create(validated_data)


class ProfitSharingAgreementSerializer(serializers.ModelSerializer):
    investor = UserSerializer(source='investor_account.investor', read_only=True)
    investor_account_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ProfitSharingAgreement
        fields = [
            'id', 'investor', 'investor_account_id', 'profit_threshold',
            'investor_share', 'bennu_share', 'effective_date', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'investor', 'created_at', 'updated_at']

    def validate(self, data):
        investor_share = data.get('investor_share', 0)
        bennu_share = data.get('bennu_share', 0)
        if investor_share + bennu_share != 100:
            raise serializers.ValidationError({
                "non_field_errors": "Investor and bennu shares must sum to 100%"
            })
        return data

    def validate_investor_account_id(self, value):
        if not InvestorAccount.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid investor account ID.")
        return value

    def create(self, validated_data):
        investor_account_id = validated_data.pop('investor_account_id')
        investor_account = InvestorAccount.objects.get(id=investor_account_id)
        validated_data['investor_account'] = investor_account
        return super().create(validated_data)


class InvestorAccountSerializer(serializers.ModelSerializer):
    investor = UserSerializer(read_only=True)
    investor_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainUser.objects.filter(role='investor'),
        source='investor',
        write_only=True
    )
    profit_agreement = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()

    class Meta:
        model = InvestorAccount
        fields = [
            'id', 'investor', 'investor_id',
            'total_deposited', 'total_utilized', 'available_balance',
            'total_margin_earned', 'total_margin_paid', 'total_interest_earned',
            'total_value', 'profit_agreement',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_deposited', 'total_utilized', 'available_balance',
            'total_margin_earned', 'total_margin_paid', 'total_interest_earned',
            'created_at', 'updated_at'
        ]

    def get_profit_agreement(self, obj):
        agreement = obj.profit_agreements.order_by('-effective_date').first()
        return ProfitSharingAgreementSerializer(agreement).data if agreement else None

    def get_total_value(self, obj):
        return obj.get_total_value()


class InvestorDashboardSerializer(serializers.ModelSerializer):
    balance_sheet = serializers.SerializerMethodField()
    receivables_aging = serializers.SerializerMethodField()
    profit_and_loss = serializers.SerializerMethodField()
    monthly_returns = serializers.SerializerMethodField()
    trade_summary = serializers.SerializerMethodField()
    financing_summary = serializers.SerializerMethodField()
    loan_summary = serializers.SerializerMethodField()

    class Meta:
        model = InvestorAccount
        fields = [
            'id',
            'total_deposited', 'total_utilized', 'available_balance',
            'total_margin_earned', 'total_margin_paid', 'total_interest_earned',
            'balance_sheet', 'receivables_aging', 'profit_and_loss',
            'monthly_returns', 'trade_summary', 'financing_summary', 'loan_summary'
        ]

    def get_balance_sheet(self, obj):
        """Calculate balance sheet for investor"""
        # Get active loans outstanding
        from trade.models import TradeLoan
        outstanding_loans = sum(
            loan.get_outstanding_balance() 
            for loan in obj.trade_loans.filter(status='active')
        )
        
        return {
            'cash_available': obj.available_balance,
            'funds_in_trades': obj.total_utilized,
            'loans_outstanding': outstanding_loans,
            'total_assets': obj.available_balance + obj.total_utilized + outstanding_loans,
            'total_earnings': obj.total_margin_earned + obj.total_interest_earned,
            'earnings_withdrawn': obj.total_margin_paid,
            'net_earnings': obj.total_margin_earned + obj.total_interest_earned - obj.total_margin_paid
        }

    def get_receivables_aging(self, obj):
        """Track aging of loans and trade returns"""
        from trade.models import TradeLoan
        from datetime import timedelta
        
        current_date = timezone.now().date()
        aging = {
            '0-3_days': Decimal('0.00'),
            '4-7_days': Decimal('0.00'),
            '8-14_days': Decimal('0.00'),
            '15-30_days': Decimal('0.00'),
            'above_30_days': Decimal('0.00'),
            'total': Decimal('0.00')
        }
        
        # Check loans
        for loan in obj.trade_loans.filter(status='active'):
            days_overdue = (current_date - loan.due_date).days if current_date > loan.due_date else 0
            amount_due = loan.get_outstanding_balance()
            
            if days_overdue <= 0:
                continue  # Not yet due
            elif days_overdue <= 3:
                aging['0-3_days'] += amount_due
            elif days_overdue <= 7:
                aging['4-7_days'] += amount_due
            elif days_overdue <= 14:
                aging['8-14_days'] += amount_due
            elif days_overdue <= 30:
                aging['15-30_days'] += amount_due
            else:
                aging['above_30_days'] += amount_due
            aging['total'] += amount_due
        
        return aging

    def get_profit_and_loss(self, obj):
        """✅ FIXED: Calculate P&L from all investor activities"""
        from trade.models import TradeFinancing
        from accounting.models import Invoice
        
        # Get all financings where at least one invoice is paid
        completed_financings = obj.trade_financings.filter(
            trade__invoices__payment_status='paid'
        ).distinct()
        
        total_invested = sum(f.allocated_amount for f in completed_financings)
        total_returns = sum(f.investor_margin for f in completed_financings)
        
        # Add interest from loans
        total_interest = obj.total_interest_earned
        
        # Total revenue
        total_revenue = total_returns + total_interest
        
        # Calculate ROI
        roi = (total_revenue / total_invested * 100) if total_invested > 0 else Decimal('0.00')
        
        return {
            'total_invested': float(total_invested),
            'trade_profits': float(total_returns),
            'loan_interest': float(total_interest),
            'total_revenue': float(total_revenue),
            'profit_withdrawn': float(obj.total_margin_paid),
            'net_profit': float(total_revenue - obj.total_margin_paid),
            'overall_roi': float(roi)
        }


    def get_monthly_returns(self, obj):
        """✅ FIXED: Calculate returns for last 12 months"""
        from trade.models import TradeFinancing
        from accounting.models import Payment
        from dateutil.relativedelta import relativedelta
        
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        
        current_date = timezone.now().date()
        months = []
        for i in range(12):
            month_date = current_date - relativedelta(months=i)
            month_str = month_date.strftime('%b %Y')
            months.append(month_str)
        months.reverse()
        
        returns = {}
        for month in months:
            month_name, year = month.split()
            month_num = month_map[month_name]
            
            # Get financings where trade has completed payments in this month
            # Use subquery to check if trade has any invoice with payment in this month
            financings = obj.trade_financings.filter(
                trade__invoices__payments__payment_date__month=month_num,
                trade__invoices__payments__payment_date__year=int(year),
                trade__invoices__payments__status='completed'
            ).distinct().aggregate(
                total_margin=Sum('investor_margin'),
                total_invested=Sum('allocated_amount')
            )
            
            total_margin = financings['total_margin'] or Decimal('0.00')
            total_invested = financings['total_invested'] or Decimal('0.00')
            roi = (total_margin / total_invested * 100) if total_invested > 0 else Decimal('0.00')
            returns[month] = float(roi)
        
        return returns


    def get_trade_summary(self, obj):
        """✅ FIXED: Summary of trades investor has financed"""
        from trade.models import TradeFinancing
        from accounting.models import Invoice
        
        # Count trades where at least one invoice is paid
        paid_trades = obj.trade_financings.filter(
            trade__invoices__payment_status='paid'
        ).distinct()
        
        total_trades = paid_trades.count()
        total_value = sum(f.allocated_amount for f in paid_trades)
        
        if total_trades > 0:
            avg_investment = total_value / total_trades
        else:
            avg_investment = Decimal('0.00')
        
        return {
            'number_of_trades': total_trades,
            'total_value_invested': float(total_value),
            'average_investment': float(avg_investment),
            'active_trades': obj.trade_financings.filter(
                trade__status__in=['approved', 'allocated', 'in_transit', 'delivered']
            ).count()
        }

    def get_financing_summary(self, obj):
        """Summary of equity financing"""
        from trade.models import TradeFinancing
        
        return {
            'total_financings': obj.trade_financings.count(),
            'active_financings': obj.trade_financings.filter(
                trade__status__in=['approved', 'allocated', 'in_transit', 'delivered']
            ).count(),
            'completed_financings': obj.trade_financings.filter(
                trade__status='completed'
            ).count(),
            'total_allocated': sum(f.allocated_amount for f in obj.trade_financings.all()),
            'total_earnings': sum(f.investor_margin for f in obj.trade_financings.all())
        }

    def get_loan_summary(self, obj):
        """Summary of loans issued"""
        from trade.models import TradeLoan
        
        loans = obj.trade_loans.all()
        active_loans = loans.filter(status='active')
        
        return {
            'total_loans': loans.count(),
            'active_loans': active_loans.count(),
            'total_loaned': sum(loan.amount for loan in loans),
            'total_outstanding': sum(loan.get_outstanding_balance() for loan in active_loans),
            'total_interest_earned': obj.total_interest_earned,
            'overdue_loans': active_loans.filter(due_date__lt=timezone.now().date()).count()
        }