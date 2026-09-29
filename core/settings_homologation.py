"""Configura\u00e7\u00e3o isolada para a homolog\u00e7\u00e3o do CoParent."""

import os
from pathlib import Path

from .settings import *


PUBLIC_HOST = "coparent-hml.originstudios.com.br"
PUBLIC_ORIGIN = f"https://{PUBLIC_HOST}"

DEBUG = False
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = [PUBLIC_HOST]
CSRF_TRUSTED_ORIGINS = [PUBLIC_ORIGIN]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5433"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [os.environ["REDIS_URL"]]},
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ["REDIS_URL"],
    }
}

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ["COPARENT_MEDIA_ROOT"])

CORS_ALLOWED_ORIGINS = [PUBLIC_ORIGIN]
CORS_ALLOW_CREDENTIALS = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "CoParent Homologa\u00e7\u00e3o <no-reply@originstudios.com.br>"
)
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
INVITE_LINK_BASE = f"{PUBLIC_ORIGIN}/convite/"
