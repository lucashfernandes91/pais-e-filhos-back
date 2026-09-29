import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import (
    AccountDeletionCode,
    AccountDeletionRequest,
    Child,
    Conversation,
    ConversationInvite,
    DeviceToken,
    EmailVerificationCode,
    Message,
    PasswordResetCode,
)

logger = logging.getLogger(__name__)

CODE_TTL_MINUTES = 15
CODE_MAX_ATTEMPTS = 5
CODE_REQUESTS_PER_WINDOW = 3
DELETION_WINDOW_DAYS = 30


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def email_digest(email: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        normalize_email(email).encode(),
        hashlib.sha256,
    ).hexdigest()


def _code_digest(digest: str, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f'{digest}:{code}'.encode(),
        hashlib.sha256,
    ).hexdigest()


def issue_deletion_code(email: str) -> None:
    now = timezone.now()
    digest = email_digest(email)
    AccountDeletionCode.objects.filter(expires_at__lte=now).delete()

    recent_requests = AccountDeletionCode.objects.filter(
        email_digest=digest,
        created_at__gte=now - timedelta(minutes=CODE_TTL_MINUTES),
    ).count()
    if recent_requests >= CODE_REQUESTS_PER_WINDOW:
        return

    AccountDeletionCode.objects.filter(
        email_digest=digest,
        used_at__isnull=True,
    ).update(used_at=now)

    code = f'{secrets.randbelow(1_000_000):06d}'
    code_record = AccountDeletionCode.objects.create(
        email_digest=digest,
        code_digest=_code_digest(digest, code),
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    )

    matching_users = User.objects.filter(email__iexact=normalize_email(email))
    if matching_users.count() != 1:
        return
    user = matching_users.first()

    try:
        send_mail(
            subject='CoParent Lite — Pedido de exclusão da conta',
            message=(
                f'Olá, {user.first_name or user.username}.\n\n'
                f'Seu código para solicitar a exclusão da conta é: {code}\n'
                f'Ele expira em {CODE_TTL_MINUTES} minutos.\n\n'
                'Se você não fez esse pedido, ignore esta mensagem.'
            ),
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.error('Falha ao enviar código de exclusão (registro %s)', code_record.pk)


def confirm_deletion_request(email: str, code: str):
    now = timezone.now()
    digest = email_digest(email)

    with transaction.atomic():
        code_record = (
            AccountDeletionCode.objects.select_for_update()
            .filter(email_digest=digest, used_at__isnull=True)
            .order_by('-created_at')
            .first()
        )
        if code_record is None or code_record.expires_at <= now:
            return None

        expected_digest = _code_digest(digest, code)
        if not hmac.compare_digest(code_record.code_digest, expected_digest):
            code_record.attempts += 1
            update_fields = ['attempts']
            if code_record.attempts >= CODE_MAX_ATTEMPTS:
                code_record.used_at = now
                update_fields.append('used_at')
            code_record.save(update_fields=update_fields)
            return None

        code_record.used_at = now
        code_record.save(update_fields=['used_at'])

        matching_users = User.objects.select_for_update().filter(
            email__iexact=normalize_email(email)
        )
        if matching_users.count() != 1:
            return None
        user = matching_users.first()

        deletion_request = AccountDeletionRequest.objects.filter(
            user=user,
            status=AccountDeletionRequest.PENDING,
        ).first()
        if deletion_request is not None:
            return deletion_request, user.email, False

        deletion_request = AccountDeletionRequest.objects.create(
            user=user,
            delete_after=now + timedelta(days=DELETION_WINDOW_DAYS),
        )

        user.is_active = False
        user.save(update_fields=['is_active'])

        DeviceToken.objects.filter(user=user).delete()
        ConversationInvite.objects.filter(created_by=user).delete()
        EmailVerificationCode.objects.filter(user=user).delete()
        PasswordResetCode.objects.filter(user=user).delete()

        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

        return deletion_request, user.email, True


def process_deletion_request(request_id: int) -> bool:
    now = timezone.now()

    with transaction.atomic():
        deletion_request = (
            AccountDeletionRequest.objects.select_for_update()
            .filter(pk=request_id, status=AccountDeletionRequest.PENDING)
            .first()
        )
        if deletion_request is None or deletion_request.delete_after > now:
            return False

        user = deletion_request.user
        if user is None:
            deletion_request.status = AccountDeletionRequest.COMPLETED
            deletion_request.completed_at = now
            deletion_request.save(update_fields=['status', 'completed_at'])
            return True

        user = User.objects.select_for_update().get(pk=user.pk)
        conversation_ids = list(
            Conversation.objects.filter(participants=user).values_list('pk', flat=True)
        )
        active_conversations = {
            conversation.pk
            for conversation in Conversation.objects.filter(pk__in=conversation_ids)
            if conversation.participants.filter(is_active=True).exclude(pk=user.pk).exists()
        }

        messages = Message.objects.filter(sender=user)
        children = Child.objects.filter(created_by=user)
        file_names = set(
            name
            for name in [
                *messages.exclude(attachment='').values_list('attachment', flat=True),
                *children.exclude(photo='').values_list('photo', flat=True),
            ]
            if name
        )

        for conversation_id in conversation_ids:
            if conversation_id not in active_conversations:
                conversation_messages = Message.objects.filter(conversation_id=conversation_id)
                file_names.update(
                    name for name in conversation_messages.exclude(attachment='')
                    .values_list('attachment', flat=True) if name
                )
                file_names.update(
                    name for name in Conversation.objects.get(pk=conversation_id)
                    .children.exclude(photo='').values_list('photo', flat=True) if name
                )

        for name in file_names:
            default_storage.delete(name)

        for conversation_id in conversation_ids:
            if conversation_id not in active_conversations:
                Conversation.objects.filter(pk=conversation_id).delete()
            else:
                Message.objects.filter(
                    conversation_id=conversation_id,
                    sender=user,
                ).update(
                    sender=None,
                    attachment='',
                    attachment_type='',
                    attachment_size=0,
                    attachment_sha256='',
                )

        AccountDeletionCode.objects.filter(email_digest=email_digest(user.email)).delete()
        user.delete()

        deletion_request.user = None
        deletion_request.status = AccountDeletionRequest.COMPLETED
        deletion_request.completed_at = now
        deletion_request.save(update_fields=['user', 'status', 'completed_at'])

    return True
