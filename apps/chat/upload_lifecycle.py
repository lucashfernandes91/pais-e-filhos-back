import hashlib
import logging
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

from .models import Message

logger = logging.getLogger("chat.uploads")


def content_sha256(content):
    return hashlib.sha256(content).hexdigest()


def log_upload_result(*, message_id, detected_format, size, result, sha256):
    logger.info(
        "attachment_upload id=%s format=%s size=%s result=%s sha256=%s",
        message_id or "-",
        detected_format,
        size,
        result,
        sha256,
    )


def remove_orphaned_attachments():
    referenced = {
        name for name in Message.objects.exclude(attachment="").values_list("attachment", flat=True)
    }
    media_root = Path(settings.MEDIA_ROOT)
    removed = 0
    attachment_root = media_root / "attachments"
    if not attachment_root.exists():
        return 0
    for path in attachment_root.rglob("*"):
        if path.is_file():
            relative = path.relative_to(media_root).as_posix()
            if relative not in referenced:
                default_storage.delete(relative)
                removed += 1
    return removed


def purge_expired_attachments():
    retention_days = int(getattr(settings, "ATTACHMENT_RETENTION_DAYS", 365))
    cutoff = timezone.now() - timedelta(days=retention_days)
    stale = Message.objects.filter(
        created_at__lt=cutoff,
        attachment__isnull=False,
    ).exclude(attachment="")
    deleted = 0
    for message in stale.iterator():
        if message.attachment:
            default_storage.delete(message.attachment.name)
            message.attachment = ""
            message.attachment_size = 0
            message.attachment_sha256 = ""
            message.save(update_fields=["attachment", "attachment_size", "attachment_sha256"])
            deleted += 1
    return deleted
