# Railway Deploy Trigger: 2026-05-14
import sentry_sdk

from .base import *
from decouple import config as env_config

# PRODUCTION SPECIFIC SETTINGS

DEBUG = False
ALLOWED_HOSTS = [
    host.strip()
    for host in env_config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')
    if host.strip()
]

# Railway injeta estes domínios em runtime. Incluí-los automaticamente evita
# que uma alteração do domínio público derrube toda a API com DisallowedHost.
for railway_host_variable in ('RAILWAY_PUBLIC_DOMAIN', 'RAILWAY_PRIVATE_DOMAIN'):
    railway_host = env_config(railway_host_variable, default='').strip()
    if railway_host and railway_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(railway_host)

def parse_origins(raw_str):
    if not raw_str:
        return []
    cleaned = raw_str.strip()
    if cleaned.startswith('[') and cleaned.endswith(']'):
        cleaned = cleaned[1:-1]
    return [item.strip().strip('"').strip("'").strip() for item in cleaned.split(',') if item.strip()]

# WhiteNoise for Static Files
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# CORS
cors_origins_env = env_config('CORS_ALLOWED_ORIGINS', default='')
if cors_origins_env:
    CORS_ALLOWED_ORIGINS = parse_origins(cors_origins_env)
else:
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:5173',
    ]

frontend_public_url = env_config('FRONTEND_PUBLIC_URL', default='').strip().rstrip('/')
if frontend_public_url and frontend_public_url not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append(frontend_public_url)

# Static Files (WhiteNoise)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
WHITENOISE_MANIFEST_STRICT = False

# CSRF & Security
csrf_origins_env = env_config('CSRF_TRUSTED_ORIGINS', default='')
if csrf_origins_env:
    CSRF_TRUSTED_ORIGINS = parse_origins(csrf_origins_env)
else:
    CSRF_TRUSTED_ORIGINS = [
        'http://localhost:5173',
    ]
if frontend_public_url and frontend_public_url not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(frontend_public_url)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_REDIRECT_EXEMPT = [r'^api/health/$']

# Security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = env_config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

# Throttling
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = [
    "rest_framework.throttling.AnonRateThrottle",
    "rest_framework.throttling.UserRateThrottle",
]
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    "anon": "50/hour",
    "user": "500/hour",
}

# Optimized DB Connections
DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['CONN_HEALTH_CHECKS'] = True  # Verifica conexão antes de reusar
DATABASES['default']['OPTIONS'] = {
    'connect_timeout': 10,
}

# Cache: Redis se disponível, senão LocMem
_redis_url = env_config('REDIS_URL', default=None)
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": _redis_url,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,  # API continua mesmo se Redis cair
            }
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# Logging estruturado (visível no painel Railway)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

SENTRY_DSN = env_config('SENTRY_DSN', default='')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env_config('SENTRY_ENVIRONMENT', default='production'),
        traces_sample_rate=env_config('SENTRY_TRACES_SAMPLE_RATE', default=0.05, cast=float),
        send_default_pii=False,
    )
