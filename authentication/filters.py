import django_filters
from authentication.models import GrainUser
from django.db.models import Q
from utils.constants import USER_ROLES  # Import the actual roles constant


class UserFilterSet(django_filters.FilterSet):
    name = django_filters.CharFilter(method='filter_by_name')
    hub = django_filters.CharFilter(field_name='hub_memberships__hub__slug')  # Updated for many-to-many
    
    # Change ChoiceFilter to BaseInFilter to handle comma-separated values
    role = django_filters.BaseInFilter(field_name='role', lookup_expr='in')
    
    class Meta:
        model = GrainUser
        fields = ['first_name', 'last_name', 'role', 'is_active', 'phone_verified']

    def filter_by_name(self, queryset, name, value):
        return queryset.filter(
            Q(first_name__icontains=value) | Q(last_name__icontains=value)
        )