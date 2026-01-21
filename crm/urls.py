# crm/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LeadViewSet, AccountViewSet, ContactViewSet, OpportunityViewSet, ContractViewSet

router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='leads')
router.register(r'accounts', AccountViewSet, basename='accounts')
router.register(r'contacts', ContactViewSet, basename='contacts')
router.register(r'opportunities', OpportunityViewSet, basename='opportunities')
router.register(r'contracts', ContractViewSet, basename='contracts')

app_name = 'crm'
urlpatterns = [
    path('', include(router.urls)),
]