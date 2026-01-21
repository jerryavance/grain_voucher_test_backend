from rest_framework.filters import SearchFilter
from django_filters import rest_framework as filters

DEFAULT_FILTER_BACKENDS = [filters.DjangoFilterBackend, SearchFilter]