import django_filters
from vouchers.models import Deposit, Voucher
from django.db.models import Q

class DepositFilterSet(django_filters.FilterSet):
    farmer_name = django_filters.CharFilter(method='filter_by_farmer_name')
    hub = django_filters.CharFilter(field_name='hub__slug')
    grain_type = django_filters.CharFilter(field_name='grain_type__name')

    class Meta:
        model = Deposit
        fields = ['validated', 'deposit_date', 'grain_type', 'quality_grade']

    def filter_by_farmer_name(self, queryset, name, value):
        return queryset.filter(
            Q(farmer__first_name__icontains=value) | Q(farmer__last_name__icontains=value)
        )

class VoucherFilterSet(django_filters.FilterSet):
    holder_name = django_filters.CharFilter(method='filter_by_holder_name')
    status = django_filters.ChoiceFilter(choices=Voucher.STATUS_CHOICES)

    class Meta:
        model = Voucher
        fields = ['status', 'issue_date']

    def filter_by_holder_name(self, queryset, name, value):
        return queryset.filter(
            Q(holder__first_name__icontains=value) | Q(holder__last_name__icontains=value)
        )