from .base import *

# DEVELOPMENT SPECIFIC SETTINGS

DEBUG = config('DEBUG', default=True, cast=bool)

# Add any development specific apps/middleware here
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']

# Allow all origins in development
CORS_ALLOW_ALL_ORIGINS = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']
