import os
import subprocess
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import Message


RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("UPLOAD_RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_PER_USER = int(os.getenv("UPLOAD_RATE_LIMIT_MAX_PER_USER", "10"))
RATE_LIMIT_MAX_PER_IP = int(os.getenv("UPLOAD_RATE_LIMIT_MAX_PER_IP", "30"))
DAILY_QUOTA_BYTES = int(os.getenv("UPLOAD_DAILY_QUOTA_BYTES", str(50 * 1024 * 1024)))
CLAMAV_TIMEOUT_SECONDS = int(os.getenv("CLAMAV_TIMEOUT_SECONDS", "15"))
CLAMAV_REQUIRED = os.getenv("CLAMAV_REQUIRED", "false").lower() == "true"
CLAMAV_COMMAND = os.getenv("CLAMAV_COMMAND", "clamdscan")


class UploadSecurityError(ValueError):
    pass


def _rate_limit(key, maximum):
    cache_key = f"upload-rate:{key}:{int(time.time() // RATE_LIMIT_WINDOW_SECONDS)}"
    try:
        current = cache.get(cache_key, 0)
        if current >= maximum:
            raise UploadSecurityError("Limite de uploads atingido. Tente novamente mais tarde.")
        if not cache.add(cache_key, 1, RATE_LIMIT_WINDOW_SECONDS + 1):
            current = cache.incr(cache_key)
            if current > maximum:
                raise UploadSecurityError("Limite de uploads atingido. Tente novamente mais tarde.")
    except ValueError:
        raise UploadSecurityError("Limite de uploads atingido. Tente novamente mais tarde.")


def enforce_upload_rate_limit(user_id, ip_address):
    _rate_limit(f"user:{user_id}", RATE_LIMIT_MAX_PER_USER)
    _rate_limit(f"ip:{ip_address or 'unknown'}", RATE_LIMIT_MAX_PER_IP)


def enforce_daily_quota(user_id, incoming_size):
    since = timezone.now() - timedelta(days=1)
    used = sum(
        Message.objects.filter(
            sender_id=user_id,
            attachment_status=Message.ATTACHMENT_APPROVED,
            created_at__gte=since,
        ).values_list("attachment_size", flat=True)
    )
    if used + incoming_size > DAILY_QUOTA_BYTES:
        raise UploadSecurityError("A cota diária de armazenamento foi atingida.")


def scan_with_clamav(content):
    with tempfile.NamedTemporaryFile(prefix="upload-quarantine-", delete=False) as temporary:
        temporary.write(content)
        quarantine_path = Path(temporary.name)
    try:
        try:
            result = subprocess.run(
                [CLAMAV_COMMAND, "--no-summary", str(quarantine_path)],
                capture_output=True,
                text=True,
                timeout=CLAMAV_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError as exc:
            if CLAMAV_REQUIRED:
                raise UploadSecurityError("Antivírus indisponível; upload bloqueado.") from exc
            return
        except subprocess.TimeoutExpired as exc:
            raise UploadSecurityError("Tempo limite da análise antivírus excedido.") from exc

        if result.returncode == 1:
            raise UploadSecurityError("O antivírus rejeitou o arquivo.")
        if result.returncode != 0 and CLAMAV_REQUIRED:
            raise UploadSecurityError("Não foi possível concluir a análise antivírus.")
    finally:
        quarantine_path.unlink(missing_ok=True)
