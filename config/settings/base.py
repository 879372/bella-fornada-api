"""
Django settings for erp_core project.
"""

import sys
from pathlib import Path
from decouple import config
import dj_database_url
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR / 'apps'))

# SECURITY
SECRET_KEY = config('SECRET_KEY', default='django-insecure-local-bella-fornada-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    # Local apps
    'apps.core',
    'apps.produtos',
    'apps.clientes',
    'apps.vendas',
    'apps.financeiro',
    'apps.compras',
    'apps.usuarios',
    'apps.producao',
    'apps.delivery',
    'apps.fiscal',
    'drf_spectacular',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Fortaleza'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'utils.exceptions.custom_exception_handler',
}

# Documentation Spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'Bella Fornada API',
    'DESCRIPTION': 'API de PDV, estoque, produção, delivery, fiscal e gestão da Padaria Bella Fornada.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_PATCH': True,
    'COMPONENT_SPLIT_CREATING': True,
}

# JWT
# Sessão deslizante: cada renovação entrega um refresh novo com validade cheia,
# então quem usa o sistema não é deslogado. Só expira após JWT_REFRESH_DAYS
# sem nenhum acesso (ou no "Sair").
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_DAYS', default=365, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
}

# CORS
def _parse_origins(raw_str):
    if not raw_str:
        return []
    cleaned = raw_str.strip()
    if cleaned.startswith('[') and cleaned.endswith(']'):
        cleaned = cleaned[1:-1]
    return [item.strip().strip('"').strip("'").strip() for item in cleaned.split(',') if item.strip()]

CORS_ALLOWED_ORIGINS = _parse_origins(config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:5173,http://localhost:3000'
))
CORS_ALLOW_CREDENTIALS = True

# Integração fiscal (ACBr)
# Aceita os nomes novos e os nomes legados já usados no Railway. Isso permite
# migrar a configuração sem copiar, imprimir ou rotacionar segredos.
ACBR_API_URL = config(
    'ACBR_API_URL',
    default=config('FISCAL_API_URL', default=''),
)
ACBR_API_KEY = config(
    'ACBR_API_KEY',
    default=config('FISCAL_API_KEY', default=''),
)
ACBR_API_TIMEOUT = config('FISCAL_TIMEOUT_SECONDS', default=30, cast=int)
FISCAL_CNPJ_EMITENTE = config(
    'FISCAL_CNPJ_EMITENTE',
    default=config('EMPRESA_CNPJ', default=''),
)
FISCAL_AMBIENTE = config('FISCAL_AMBIENTE', default='homologacao')

# Delivery: URL pública do frontend, usada nos links de acompanhamento de pedido
FRONTEND_PUBLIC_URL = config('FRONTEND_PUBLIC_URL', default='http://localhost:5173').rstrip('/')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
