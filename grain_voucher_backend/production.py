from .settings import *  # import all defaults

import os

# Production overrides
DEBUG = False

SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-production-key")

ALLOWED_HOSTS = [
    "157.245.165.113",        # server IP
    "api.grainvoucher.com",
    'grainvoucher.com',  # your frontend
    "127.0.0.1:8000",
]

CSRF_TRUSTED_ORIGINS = [
    "https://grainvoucher.com",
    "http://157.245.165.113",
    "https://157.245.165.113",
    "http://localhost:3000/",
]

CORS_ALLOWED_ORIGINS = [
    "https://grainvoucher.com",
    "http://localhost:3000/",
]

# Add these for HTTPS security
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# Static files in production
STATIC_ROOT = os.path.join(BASE_DIR, "static")
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
