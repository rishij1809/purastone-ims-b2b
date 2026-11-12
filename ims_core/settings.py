import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-pzi35xkj6m!-8i0%^d38ae&xshixvf!zc3%@!@j&9$h%27aebc')

DEBUG = os.getenv('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'inventory',
    'finance',
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

ROOT_URLCONF = 'ims_core.urls'

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

WSGI_APPLICATION = 'ims_core.wsgi.application'

import shutil

IS_VERCEL = os.getenv('VERCEL') == '1' or 'VERCEL' in os.environ

# Database configuration: PostgreSQL with SQLite fallback
DB_NAME = os.getenv('DB_NAME')
if DB_NAME:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    db_path = BASE_DIR / 'db.sqlite3'
    if IS_VERCEL:
        tmp_db = Path('/tmp/db.sqlite3')
        if not tmp_db.exists() and db_path.exists():
            try:
                shutil.copy2(db_path, tmp_db)
            except Exception:
                pass
        db_path = tmp_db

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': db_path,
            'OPTIONS': {
                'timeout': 20,
            }
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = Path('/tmp/static') if IS_VERCEL else (BASE_DIR / 'static')

MEDIA_URL = '/media/'
if IS_VERCEL:
    MEDIA_ROOT = Path('/tmp/media')
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
else:
    MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'memory://')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'cache+memory://')
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_ALWAYS_EAGER', 'True') == 'True'
CELERY_TASK_EAGER_PROPAGATES = False
