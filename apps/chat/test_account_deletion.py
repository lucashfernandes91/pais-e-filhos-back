import re
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import (
    AccountDeletionCode,
    AccountDeletionRequest,
    Child,
    ChildLegalDeclaration,
    Conversation,
    DeviceToken,
    Event,
    LegalAcceptance,
    Message,
)
from .serializers import MessageSerializer


class AccountDeletionFlowTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.user = User.objects.create_user(
            username='parent_one',
            email='parent@example.com',
            password='StrongPass123!',
            first_name='Parent',
        )

    def _request_code(self, email=None):
        return self.client.post(
            '/account-deletion',
            {'action': 'send_code', 'email': email or self.user.email},
        )

    def _code_from_email(self):
        match = re.search(r'código para solicitar a exclusão da conta é: (\d{6})', mail.outbox[-1].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def _confirm(self, code, email=None):
        return self.client.post(
            '/account-deletion',
            {
                'action': 'confirm',
                'email': email or self.user.email,
                'code': code,
                'confirm_deletion': 'yes',
            },
        )

    def test_public_page_is_discoverable_and_does_not_cache_personal_data(self):
        response = self.client.get('/account-deletion')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'max-age=0, no-cache, no-store, must-revalidate, private')
        self.assertContains(response, 'Solicitar exclusão da conta')
        self.assertContains(self.client.get('/privacy'), '/account-deletion')

    def test_code_request_has_generic_response_and_sends_only_for_an_existing_email(self):
        existing = self._request_code()
        unknown = self._request_code('missing@example.com')

        self.assertEqual(existing.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertContains(existing, 'Se houver uma conta com esse e-mail')
        self.assertContains(unknown, 'Se houver uma conta com esse e-mail')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertFalse(AccountDeletionCode.objects.filter(email_digest=self.user.email).exists())

    def test_code_confirmation_blocks_account_and_revokes_sessions(self):
        token = RefreshToken.for_user(self.user)
        device = DeviceToken.objects.create(user=self.user, token='device-token')
        self._request_code()
        response = self._confirm(self._code_from_email())

        self.user.refresh_from_db()
        deletion_request = AccountDeletionRequest.objects.get(user=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'acesso à conta foi bloqueado')
        self.assertFalse(self.user.is_active)
        self.assertEqual(deletion_request.status, AccountDeletionRequest.PENDING)
        self.assertGreaterEqual(deletion_request.delete_after, timezone.now() + timedelta(days=29))
        self.assertFalse(DeviceToken.objects.filter(pk=device.pk).exists())
        self.assertTrue(BlacklistedToken.objects.filter(token__user=self.user).exists())
        denied = self.client.get(
            '/api/profile/',
            HTTP_AUTHORIZATION=f'Bearer {token.access_token}',
        )
        self.assertEqual(denied.status_code, 401)
        self.assertFalse(AccountDeletionCode.objects.filter(used_at__isnull=True).exists())

        duplicate = self._request_code()
        repeated = self._confirm(self._code_from_email())
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(AccountDeletionRequest.objects.filter(user=self.user).count(), 1)
        self.assertEqual(repeated.status_code, 200)

    def test_email_codes_are_limited_per_address(self):
        for _ in range(4):
            self._request_code('missing@example.com')

        self.assertEqual(
            AccountDeletionCode.objects.filter(email_digest__isnull=False).count(),
            3,
        )
        self.assertEqual(mail.outbox, [])

    def test_invalid_codes_stop_working_after_five_attempts(self):
        with patch('apps.chat.account_deletion.secrets.randbelow', return_value=1234):
            self._request_code()

        for _ in range(5):
            self._confirm('000000')

        code_record = AccountDeletionCode.objects.get(email_digest__isnull=False)
        self.assertEqual(code_record.attempts, 5)
        self.assertIsNotNone(code_record.used_at)
        self.assertFalse(AccountDeletionRequest.objects.exists())
        self.assertTrue(User.objects.filter(pk=self.user.pk, is_active=True).exists())

    def test_due_deletion_preserves_shared_messages_anonymized_and_cleans_owned_data(self):
        other = User.objects.create_user(username='parent_two', password='password123')
        conversation = Conversation.objects.create()
        conversation.participants.add(self.user, other)

        child = Child.objects.create(
            conversation=conversation,
            name='Child One',
            birth_date='2020-01-01',
            created_by=self.user,
        )
        child.photo.save('child.jpg', ContentFile(b'child photo'), save=True)
        photo_name = child.photo.name
        declaration = ChildLegalDeclaration.objects.create(
            child=child,
            declared_by=self.user,
            declaration_version='1',
        )
        shared_child = Child.objects.create(
            conversation=conversation,
            name='Child Two',
            birth_date='2021-01-01',
            created_by=other,
        )
        shared_declaration = ChildLegalDeclaration.objects.create(
            child=shared_child,
            declared_by=self.user,
            declaration_version='1',
        )

        own_message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content='Mensagem compartilhada',
        )
        own_message.attachment.save('document.txt', ContentFile(b'attachment'), save=True)
        attachment_name = own_message.attachment.name
        other_message = Message.objects.create(
            conversation=conversation,
            sender=other,
            content='Mensagem do outro responsável',
        )
        Event.objects.create(
            conversation=conversation,
            created_by=self.user,
            title='Evento do usuário',
            event_date=timezone.now(),
            event_type=Event.OTHER,
        )
        surviving_event = Event.objects.create(
            conversation=conversation,
            created_by=other,
            title='Evento do outro responsável',
            event_date=timezone.now(),
            event_type=Event.OTHER,
        )
        acceptance = LegalAcceptance.objects.create(
            user=self.user,
            terms_version='1',
            privacy_version='1',
        )
        deletion_request = AccountDeletionRequest.objects.create(
            user=self.user,
            delete_after=timezone.now() - timedelta(seconds=1),
        )
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        call_command('process_account_deletions')

        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        deletion_request.refresh_from_db()
        self.assertIsNone(deletion_request.user_id)
        self.assertEqual(deletion_request.status, AccountDeletionRequest.COMPLETED)
        own_message.refresh_from_db()
        self.assertIsNone(own_message.sender_id)
        self.assertEqual(own_message.content, 'Mensagem compartilhada')
        self.assertFalse(own_message.attachment)
        self.assertEqual(MessageSerializer(own_message).data['sender'], 'Conta excluída')
        self.assertTrue(Message.objects.filter(pk=other_message.pk).exists())
        self.assertTrue(Conversation.objects.filter(pk=conversation.pk).exists())
        self.assertFalse(Child.objects.filter(pk=child.pk).exists())
        self.assertTrue(Child.objects.filter(pk=shared_child.pk).exists())
        declaration.refresh_from_db()
        shared_declaration.refresh_from_db()
        self.assertIsNone(declaration.child_id)
        self.assertIsNone(declaration.declared_by_id)
        self.assertEqual(shared_declaration.child_id, shared_child.pk)
        self.assertIsNone(shared_declaration.declared_by_id)
        acceptance.refresh_from_db()
        self.assertIsNone(acceptance.user_id)
        self.assertFalse(Event.objects.filter(title='Evento do usuário').exists())
        self.assertTrue(Event.objects.filter(pk=surviving_event.pk).exists())
        self.assertFalse(Path(self.media_directory.name, photo_name).exists())
        self.assertFalse(Path(self.media_directory.name, attachment_name).exists())

    def test_due_deletion_removes_last_active_family_space(self):
        conversation = Conversation.objects.create()
        conversation.participants.add(self.user)
        Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content='Mensagem privada',
        )
        Event.objects.create(
            conversation=conversation,
            created_by=self.user,
            title='Evento privado',
            event_date=timezone.now(),
            event_type=Event.OTHER,
        )
        deletion_request = AccountDeletionRequest.objects.create(
            user=self.user,
            delete_after=timezone.now() - timedelta(seconds=1),
        )
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        call_command('process_account_deletions')

        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Conversation.objects.filter(pk=conversation.pk).exists())
        deletion_request.refresh_from_db()
        self.assertEqual(deletion_request.status, AccountDeletionRequest.COMPLETED)
