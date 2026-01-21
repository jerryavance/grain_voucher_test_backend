from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

schema_view = get_schema_view(
    openapi.Info(
        title="Grain Voucher API",
        default_version='v1',
        description="API for Grain Voucher",
        terms_of_service="https://www.grainvoucher.com/terms/",
        contact=openapi.Contact(email="support@grainvoucher.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    # public=False,  # Restrict to authenticated users
    # permission_classes=(permissions.IsAuthenticated,),  # Require authentication
)

urlpatterns = [
    path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    # Add these for additional documentation formats:
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('swagger.json', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger.yaml', schema_view.without_ui(cache_timeout=0), name='schema-yaml'),

    path('admin/', admin.site.urls),
    path('api/auth/', include('authentication.urls')),
    path('api/hubs/', include('hubs.urls')),
    path('api/vouchers/', include('vouchers.urls', namespace='vouchers')),
    
    path('api/crm/', include('crm.urls', namespace='crm')),
    path('api/trade/', include('trade.urls', namespace='trade')),
    path('api/accounting/', include('accounting.urls', namespace='accounting')),
    path('api/payroll/', include('payroll.urls', namespace='payroll')),

    path('api/investors/', include('investors.urls', namespace='investors')),

    path('api/reports/', include('reports.urls')),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)