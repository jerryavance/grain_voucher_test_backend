from .settings import *
import os

# Production overrides
DEBUG = False

SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-production-key")

ALLOWED_HOSTS = [
    "157.245.165.113",
    "api.grainvoucher.com",
    'grainvoucher.com',
    "grainvouchertestbackend-production.up.railway.app",
]

CSRF_TRUSTED_ORIGINS = [
    "https://grainvoucher.com",
    "https://grainvoucher.vercel.app",
    "https://grainvouchertestbackend-production.up.railway.app",
    "http://157.245.165.113",
    "https://157.245.165.113",
]

CORS_ALLOWED_ORIGINS = [
    "https://grainvoucher.com",
    "https://grainvoucher.vercel.app",
]

# HTTPS security
SECURE_SSL_REDIRECT = False  # Set to True only if you have HTTPS set up
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = False  # Set to True only with HTTPS
SESSION_COOKIE_SECURE = False  # Set to True only with HTTPS

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')






# from .settings import *  # import all defaults

# import os

# # Production overrides
# DEBUG = False

# SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-production-key")

# ALLOWED_HOSTS = [
#     "157.245.165.113",        # server IP
#     "api.grainvoucher.com",
#     'grainvoucher.com',  # your frontend
#     "127.0.0.1:8000",
# ]

# CSRF_TRUSTED_ORIGINS = [
#     "https://grainvoucher.com",
#     "http://157.245.165.113",
#     "https://157.245.165.113",
#     "http://localhost:3000/",
# ]

# CORS_ALLOWED_ORIGINS = [
#     "https://grainvoucher.com",
#     "http://localhost:3000/",
# ]

# # Add these for HTTPS security
# SECURE_SSL_REDIRECT = True
# SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# CSRF_COOKIE_SECURE = True
# SESSION_COOKIE_SECURE = True

# # Static files in production
# STATIC_ROOT = os.path.join(BASE_DIR, "static")
# MEDIA_ROOT = os.path.join(BASE_DIR, "media")
