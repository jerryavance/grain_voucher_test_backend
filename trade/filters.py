import django_filters
from .models import Trade, TradeCost, Brokerage, GoodsReceivedNote
from django.db.models import Q


class TradeFilterSet(django_filters.FilterSet):
    """Comprehensive filters for trades"""

    # Date filters
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    delivery_after = django_filters.DateFilter(field_name='expected_delivery_date', lookup_expr='gte')
    delivery_before = django_filters.DateFilter(field_name='expected_delivery_date', lookup_expr='lte')

    # Value filters
    min_revenue = django_filters.NumberFilter(field_name='total_revenue', lookup_expr='gte')
    max_revenue = django_filters.NumberFilter(field_name='total_revenue', lookup_expr='lte')
    min_profit = django_filters.NumberFilter(field_name='gross_profit', lookup_expr='gte')
    max_profit = django_filters.NumberFilter(field_name='gross_profit', lookup_expr='lte')
    min_roi = django_filters.NumberFilter(field_name='roi_percentage', lookup_expr='gte')

    # Quantity filters
    min_quantity_kg = django_filters.NumberFilter(field_name='quantity_kg', lookup_expr='gte')
    max_quantity_kg = django_filters.NumberFilter(field_name='quantity_kg', lookup_expr='lte')

    # Boolean filters
    allocated = django_filters.BooleanFilter(field_name='allocation_complete')

    # Custom multi-status filter - use BaseInFilter to handle comma-separated values
    status = django_filters.BaseInFilter(field_name='status', lookup_expr='in')

    # Search
    #search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Trade
        fields = [
            'status', 'hub', 'buyer', 'grain_type', 'quality_grade',
            'initiated_by', 'payment_terms', 'is_active'
        ]


class BrokerageFilterSet(django_filters.FilterSet):
    """Filters for brokerage commissions"""
    
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    min_amount = django_filters.NumberFilter(field_name='amount', lookup_expr='gte')
    max_amount = django_filters.NumberFilter(field_name='amount', lookup_expr='lte')
    
    class Meta:
        model = Brokerage
        fields = ['trade', 'agent', 'commission_type']


class GoodsReceivedNoteFilterSet(django_filters.FilterSet):
    """Filters for GRNs"""
    
    delivery_after = django_filters.DateFilter(field_name='delivery_date', lookup_expr='gte')
    delivery_before = django_filters.DateFilter(field_name='delivery_date', lookup_expr='lte')
    loading_after = django_filters.DateFilter(field_name='loading_date', lookup_expr='gte')
    loading_before = django_filters.DateFilter(field_name='loading_date', lookup_expr='lte')
    
    # search = django_filters.CharFilter(method='filter_search')
    
    class Meta:
        model = GoodsReceivedNote
        fields = ['trade']
    