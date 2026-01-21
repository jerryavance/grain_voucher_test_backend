# from django.urls import path, include
# from rest_framework.routers import DefaultRouter
# from . import views

# router = DefaultRouter()
# router.register(r'', views.HubViewSet, basename='hub')
# router.register(r'memberships', views.HubMembershipViewSet, basename='membership')

# app_name = 'hubs'

# urlpatterns = [
#     path('', include(router.urls)),
#     path('search-hubs/', views.search_hubs, name='search_hubs'),
#     path('my-hubs/', views.my_hubs, name='my_hubs'),
# ]

# hubs/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HubViewSet, HubMembershipViewSet, search_hubs, my_hubs

router = DefaultRouter()
router.register(r'', HubViewSet, basename='hub')
# router.register(r'memberships', HubMembershipViewSet, basename='hub-membership')
router.register(r'hubs/memberships', HubMembershipViewSet, basename='hubmembership')
urlpatterns = [
    path('', include(router.urls)),
    path('search-hubs/', search_hubs, name='search_hubs'),
    path('my-hubs/', my_hubs, name='my_hubs'),
]
