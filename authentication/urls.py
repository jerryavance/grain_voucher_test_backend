from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')

app_name = 'authentication'

urlpatterns = [
    path('', include(router.urls)),
    path('request-otp/', views.request_otp, name='request_otp'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('register/', views.register, name='register'),
    path('login/', views.login_with_phone, name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]