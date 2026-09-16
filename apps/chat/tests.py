from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from .models import Child, ChildLegalDeclaration, Conversation, ConversationInvite, DeviceToken, EmailVerificationCode, Event, LegalAcceptance, Message, Notification, PasswordResetCode, UserProfile
from .legal import CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION
from core.firebase_helpers import MESSAGE_NOTIFICATION_BODY, MESSAGE_NOTIFICATION_TITLE, send_message_push_notification
from datetime import date, timedelta
import shutil
import tempfile


class PublicLegalDocumentsTests(SimpleTestCase):
    def test_privacy_policy_is_public_and_current(self):
        response = self.client.get('/privacy')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Política de Privacidade e LGPD')
        self.assertContains(response, '68.303.469/0001-33')

    def test_terms_of_use_are_public_and_current(self):
        response = self.client.get('/terms')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Termos de Uso')
        self.assertContains(response, 'Santo Antônio da Patrulha')
        self.assertContains(response, 'direito de escolher outro foro competente')


class TokenRefreshTests(APITestCase):
    def test_refresh_token_for_deleted_user_returns_unauthorized(self):
        user = User.objects.create_user(username="removed_user", password="password123")
        refresh_token = str(RefreshToken.for_user(user))
        user.delete()

        response = self.client.post(
            "/api/token/refresh/",
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TokenLoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="parent_one",
            email="parent@example.com",
            password="SenhaForte!42",
        )

    def test_login_accepts_username(self):
        response = self.client.post(
            "/api/token/",
            {"username": "parent_one", "password": "SenhaForte!42"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.user.username)

    def test_login_accepts_email_case_insensitively(self):
        response = self.client.post(
            "/api/token/",
            {"username": "PARENT@example.com", "password": "SenhaForte!42"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.user.username)


class ConversationInitializationTests(APITestCase):
    def test_registration_creates_and_returns_initial_conversation(self):
        response = self.client.post(
            "/api/register/",
            {
                "first_name": "Ana",
                "last_name": "Silva",
                "username": "new_parent",
                "birth_date": "1990-04-18",
                "email": "parent@example.com",
                "password": "SenhaForte!42",
                "terms_version": CURRENT_TERMS_VERSION,
                "privacy_version": CURRENT_PRIVACY_VERSION,
                "accept_terms": True,
                "accept_privacy": True,
                "declare_adult": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        conversation = Conversation.objects.get(id=response.data["conversation_id"])
        self.assertTrue(conversation.participants.filter(username="new_parent").exists())
        self.assertEqual(UserProfile.objects.get(user__username="new_parent").birth_date.isoformat(), "1990-04-18")
        acceptance = LegalAcceptance.objects.get(user__username="new_parent")
        self.assertEqual(acceptance.terms_version, CURRENT_TERMS_VERSION)
        self.assertEqual(acceptance.privacy_version, CURRENT_PRIVACY_VERSION)
        self.assertIsNotNone(acceptance.accepted_at)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        for endpoint in ("messages", "events", "children"):
            result = self.client.get(f"/api/{endpoint}/{conversation.id}/")
            self.assertEqual(result.status_code, status.HTTP_200_OK)
            self.assertEqual(result.data, [])

    def test_list_conversations_initializes_legacy_account(self):
        user = User.objects.create_user(username="legacy_parent", password="password123")
        access_token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.get("/api/conversations/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        conversation = Conversation.objects.get(id=response.data[0]["id"])
        self.assertTrue(conversation.participants.filter(id=user.id).exists())

    def test_registration_rejects_username_shorter_than_five_characters(self):
        response = self.client.post(
            "/api/register/",
            {
                "first_name": "Ana",
                "last_name": "Silva",
                "username": "ana",
                "birth_date": "1990-04-18",
                "email": "ana@example.com",
                "password": "SenhaForte!42",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_requires_legal_acceptance(self):
        response = self.client.post(
            "/api/register/",
            {
                "first_name": "Ana",
                "last_name": "Silva",
                "username": "without_acceptance",
                "birth_date": "1990-04-18",
                "email": "without@example.com",
                "password": "SenhaForte!42",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="without_acceptance").exists())

    def test_registration_rejects_minor(self):
        response = self.client.post(
            "/api/register/",
            {
                "first_name": "Ana",
                "last_name": "Silva",
                "username": "minor_parent",
                "birth_date": "2010-04-18",
                "email": "minor@example.com",
                "password": "SenhaForte!42",
                "terms_version": CURRENT_TERMS_VERSION,
                "privacy_version": CURRENT_PRIVACY_VERSION,
                "accept_terms": True,
                "accept_privacy": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="minor_parent").exists())

    def test_registration_requires_adult_declaration(self):
        response = self.client.post(
            "/api/register/",
            {
                "first_name": "Ana",
                "last_name": "Silva",
                "username": "adult_parent",
                "birth_date": "1990-04-18",
                "email": "adult@example.com",
                "password": "SenhaForte!42",
                "terms_version": CURRENT_TERMS_VERSION,
                "privacy_version": CURRENT_PRIVACY_VERSION,
                "accept_terms": True,
                "accept_privacy": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="adult_parent").exists())

    def test_existing_account_can_check_and_record_current_acceptance(self):
        user = User.objects.create_user(username="legacy_parent", password="password123")
        access_token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        status_response = self.client.get("/api/legal/acceptance/")
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertTrue(status_response.data["required"])
        self.assertFalse(status_response.data["accepted"])

        accept_response = self.client.post(
            "/api/legal/acceptance/",
            {
                "terms_version": CURRENT_TERMS_VERSION,
                "privacy_version": CURRENT_PRIVACY_VERSION,
                "accept_terms": True,
                "accept_privacy": True,
            },
            format="json",
        )
        self.assertEqual(accept_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(LegalAcceptance.objects.filter(user=user).exists())

        status_response = self.client.get("/api/legal/acceptance/")
        self.assertFalse(status_response.data["required"])
        self.assertTrue(status_response.data["accepted"])

    def test_acceptance_rejects_outdated_document_versions(self):
        user = User.objects.create_user(username="legacy_parent", password="password123")
        access_token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.post(
            "/api/legal/acceptance/",
            {
                "terms_version": "0.0",
                "privacy_version": CURRENT_PRIVACY_VERSION,
                "accept_terms": True,
                "accept_privacy": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(LegalAcceptance.objects.filter(user=user).exists())


class ChildUpdateTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)
        self.user = User.objects.create_user(username="parent_one", password="password123")
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.user)
        self.child = Child.objects.create(
            conversation=self.conversation,
            created_by=self.user,
            name="Clara",
            birth_date="2021-05-26",
            has_custody=True,
        )
        access_token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_patch_child_updates_editable_fields(self):
        response = self.client.patch(
            f"/api/children/{self.child.id}/update/",
            {
                "name": "Clara Silva",
                "birth_date": "2021-05-27",
                "has_custody": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "Clara Silva")
        self.assertEqual(self.child.birth_date.isoformat(), "2021-05-27")
        self.assertFalse(self.child.has_custody)

    def test_patch_child_rejects_non_participant(self):
        outsider = User.objects.create_user(username="outsider", password="password123")
        access_token = str(RefreshToken.for_user(outsider).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.patch(
            f"/api/children/{self.child.id}/update/",
            {"name": "Sem permissao"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_child_rejects_invalid_birth_date(self):
        response = self.client.patch(
            f"/api/children/{self.child.id}/update/",
            {"birth_date": "31/05/2021"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_child_uploads_photo(self):
        photo = SimpleUploadedFile(
            "clara.jpg",
            b"photo-content",
            content_type="image/jpeg",
        )

        response = self.client.patch(
            f"/api/children/{self.child.id}/update/",
            {"photo": photo},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.child.refresh_from_db()
        self.assertTrue(self.child.photo.name.startswith("children_photos/"))
        self.assertIsNotNone(response.data["photo_url"])

        list_response = self.client.get(f"/api/children/{self.conversation.id}/")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertTrue(list_response.data[0]["photo_url"].startswith("http://testserver/"))


class EventCreationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="parent_one", password="password123")
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.user)
        access_token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_create_event_without_city(self):
        response = self.client.post(
            "/api/events/",
            {
                "conversation_id": self.conversation.id,
                "title": "Consulta pediatrica",
                "event_date": "2026-06-10T15:00:00",
                "event_type": "MEDICAL",
                "notes": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Consulta pediatrica")


class NotificationBulkActionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="parent_one", password="password123")
        self.other_user = User.objects.create_user(username="parent_two", password="password123")
        access_token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_delete_all_notifications_only_removes_current_user_notifications(self):
        Notification.objects.create(recipient=self.user, title="Mensagem", body="Oi")
        Notification.objects.create(recipient=self.user, title="Evento", body="Consulta")
        other_notification = Notification.objects.create(
            recipient=self.other_user,
            title="Outro",
            body="Nao apagar",
        )

        response = self.client.delete("/api/notifications/delete-all/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_count"], 2)
        self.assertFalse(Notification.objects.filter(recipient=self.user).exists())
        self.assertTrue(Notification.objects.filter(id=other_notification.id).exists())


class MessageNotificationPrivacyTests(APITestCase):
    def setUp(self):
        self.sender = User.objects.create_user(username="sender", password="password123")
        self.recipient = User.objects.create_user(username="recipient", password="password123")
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.sender, self.recipient)
        DeviceToken.objects.create(user=self.recipient, token="recipient-device-token")

    @patch("core.firebase_helpers.send_message_push_notification", return_value=True)
    def test_message_notification_uses_generic_copy_without_message_preview(self, mock_push):
        Message.objects.create(
            conversation=self.conversation,
            sender=self.sender,
            content="Conteúdo privado que não pode aparecer na notificação",
        )

        notification = Notification.objects.get(recipient=self.recipient)
        self.assertEqual(notification.title, MESSAGE_NOTIFICATION_TITLE)
        self.assertEqual(notification.body, MESSAGE_NOTIFICATION_BODY)
        self.assertNotIn("Conteúdo privado", notification.body)
        self.assertNotIn(self.sender.username, notification.title)
        mock_push.assert_called_once_with("recipient-device-token")

    def test_message_push_contains_only_its_notification_type(self):
        with patch("core.firebase_helpers.FIREBASE_INITIALIZED", True), patch(
            "core.firebase_helpers.messaging.send", return_value="message-id"
        ) as mock_send:
            self.assertTrue(send_message_push_notification("recipient-device-token"))

        push_message = mock_send.call_args.args[0]
        self.assertEqual(push_message.data, {"notification_type": "message"})
        self.assertIsNone(push_message.notification)


class MessageListPaginationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="parent_one", password="password123")
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.user)
        access_token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def _create_messages(self, count):
        return [
            Message.objects.create(
                conversation=self.conversation,
                sender=self.user,
                content=f"msg {i}",
            )
            for i in range(1, count + 1)
        ]

    def test_returns_most_recent_page_in_chronological_order(self):
        self._create_messages(150)

        response = self.client.get(f"/api/messages/{self.conversation.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 100)
        contents = [m["content"] for m in response.data]
        self.assertEqual(contents[0], "msg 51")
        self.assertEqual(contents[-1], "msg 150")
        self.assertEqual(contents, sorted(contents, key=lambda c: int(c.split()[1])))

    def test_before_walks_backwards_through_history(self):
        messages = self._create_messages(150)

        first_page = self.client.get(f"/api/messages/{self.conversation.id}/")
        oldest_returned_id = first_page.data[0]["id"]
        self.assertEqual(oldest_returned_id, messages[50].id)

        second_page = self.client.get(
            f"/api/messages/{self.conversation.id}/",
            {"before": oldest_returned_id},
        )

        self.assertEqual(second_page.status_code, status.HTTP_200_OK)
        contents = [m["content"] for m in second_page.data]
        self.assertEqual(contents[0], "msg 1")
        self.assertEqual(contents[-1], "msg 50")

    def test_limit_is_respected_and_capped(self):
        self._create_messages(30)

        response = self.client.get(
            f"/api/messages/{self.conversation.id}/", {"limit": 10}
        )
        self.assertEqual(len(response.data), 10)
        self.assertEqual(response.data[-1]["content"], "msg 30")

        capped = self.client.get(
            f"/api/messages/{self.conversation.id}/", {"limit": 9999}
        )
        self.assertEqual(len(capped.data), 30)

    def test_invalid_pagination_params_return_400(self):
        self._create_messages(1)

        invalid_before = self.client.get(
            f"/api/messages/{self.conversation.id}/", {"before": "abc"}
        )
        self.assertEqual(invalid_before.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_limit = self.client.get(
            f"/api/messages/{self.conversation.id}/", {"limit": "abc"}
        )
        self.assertEqual(invalid_limit.status_code, status.HTTP_400_BAD_REQUEST)


class ConversationInviteTests(APITestCase):
    def setUp(self):
        self.inviter = User.objects.create_user(username="parent_one", password="password123")
        self.invitee = User.objects.create_user(username="parent_two", password="password123")
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.inviter)
        self.inviter_token = str(RefreshToken.for_user(self.inviter).access_token)
        self.invitee_token = str(RefreshToken.for_user(self.invitee).access_token)

    def _as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _create_invite(self):
        self._as(self.inviter_token)
        return self.client.post(
            "/api/invites/", {"conversation_id": self.conversation.id}, format="json"
        )

    def test_participant_creates_invite_with_url_and_expiry(self):
        response = self._create_invite()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["code"]), 8)
        self.assertTrue(response.data["invite_url"].endswith(response.data["code"]))
        invite = ConversationInvite.objects.get(code=response.data["code"])
        self.assertGreater(invite.expires_at, timezone.now() + timedelta(days=6))

    def test_new_invite_invalidates_previous_code(self):
        first = self._create_invite().data["code"]
        second = self._create_invite().data["code"]

        self.assertNotEqual(first, second)
        self.assertFalse(ConversationInvite.objects.filter(code=first).exists())

    def test_non_participant_cannot_create_invite(self):
        self._as(self.invitee_token)
        response = self.client.post(
            "/api/invites/", {"conversation_id": self.conversation.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_accept_joins_conversation_and_migrates_solo_workspace(self):
        code = self._create_invite().data["code"]

        solo = Conversation.objects.create()
        solo.participants.add(self.invitee)
        child = Child.objects.create(
            conversation=solo,
            created_by=self.invitee,
            name="Filho",
            birth_date="2020-01-01",
        )
        event = Event.objects.create(
            conversation=solo,
            created_by=self.invitee,
            title="Consulta",
            event_date=timezone.now(),
            event_type=Event.MEDICAL,
        )

        self._as(self.invitee_token)
        response = self.client.post("/api/invites/accept/", {"code": code}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["conversation_id"], self.conversation.id)
        self.assertEqual(self.conversation.participants.count(), 2)
        child.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(child.conversation_id, self.conversation.id)
        self.assertEqual(event.conversation_id, self.conversation.id)
        self.assertFalse(Conversation.objects.filter(id=solo.id).exists())

    def test_accept_is_case_insensitive_and_single_use(self):
        code = self._create_invite().data["code"]

        self._as(self.invitee_token)
        first = self.client.post(
            "/api/invites/accept/", {"code": code.lower()}, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        third_user = User.objects.create_user(username="parent_three", password="password123")
        self._as(str(RefreshToken.for_user(third_user).access_token))
        second = self.client.post("/api/invites/accept/", {"code": code}, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_rejects_expired_unknown_and_own_invite(self):
        code = self._create_invite().data["code"]

        self._as(self.invitee_token)
        unknown = self.client.post(
            "/api/invites/accept/", {"code": "XXXXXXXX"}, format="json"
        )
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)

        self._as(self.inviter_token)
        own = self.client.post("/api/invites/accept/", {"code": code}, format="json")
        self.assertEqual(own.status_code, status.HTTP_400_BAD_REQUEST)

        ConversationInvite.objects.filter(code=code).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self._as(self.invitee_token)
        expired = self.client.post("/api/invites/accept/", {"code": code}, format="json")
        self.assertEqual(expired.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expirado", expired.data["error"]["message"].lower())

    def test_full_conversation_rejects_new_invite_and_accept(self):
        code = self._create_invite().data["code"]
        self._as(self.invitee_token)
        self.client.post("/api/invites/accept/", {"code": code}, format="json")

        self._as(self.inviter_token)
        full = self.client.post(
            "/api/invites/", {"conversation_id": self.conversation.id}, format="json"
        )
        self.assertEqual(full.status_code, status.HTTP_400_BAD_REQUEST)

    def test_shared_conversation_listed_first(self):
        code = self._create_invite().data["code"]

        solo = Conversation.objects.create()
        solo.participants.add(self.invitee)
        Message.objects.create(conversation=solo, sender=self.invitee, content="nota")

        self._as(self.invitee_token)
        self.client.post("/api/invites/accept/", {"code": code}, format="json")

        response = self.client.get("/api/conversations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["id"], self.conversation.id)
        self.assertEqual(len(response.data[0]["participants"]), 2)


class PasswordResetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="parent_one",
            password="SenhaAntiga!42",
            email="parent@example.com",
            first_name="Ana",
        )

    def _request_reset(self, identifier="parent_one"):
        return self.client.post(
            "/api/password-reset/request/", {"identifier": identifier}, format="json"
        )

    def _latest_code(self):
        return PasswordResetCode.objects.filter(user=self.user).latest("created_at")

    def test_unknown_identifier_returns_neutral_response(self):
        response = self._request_reset("nao_existe")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(PasswordResetCode.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_creates_code_and_sends_email(self):
        response = self._request_reset()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        code = self._latest_code()
        self.assertEqual(len(code.code), 6)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(code.code, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["parent@example.com"])

    def test_request_accepts_email_identifier_case_insensitive(self):
        response = self._request_reset("PARENT@EXAMPLE.COM")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(PasswordResetCode.objects.filter(user=self.user).count(), 1)

    def test_full_flow_changes_password_and_old_stops_working(self):
        self._request_reset()
        code = self._latest_code().code

        verify = self.client.post(
            "/api/password-reset/verify/",
            {"identifier": "parent_one", "code": code},
            format="json",
        )
        self.assertEqual(verify.status_code, status.HTTP_200_OK)

        confirm = self.client.post(
            "/api/password-reset/confirm/",
            {"identifier": "parent_one", "code": code, "new_password": "SenhaNova!77"},
            format="json",
        )
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)

        old_login = self.client.post(
            "/api/token/",
            {"username": "parent_one", "password": "SenhaAntiga!42"},
            format="json",
        )
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)

        new_login = self.client.post(
            "/api/token/",
            {"username": "parent_one", "password": "SenhaNova!77"},
            format="json",
        )
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)

    def test_wrong_code_hits_429_after_max_attempts(self):
        self._request_reset()

        for attempt in range(4):
            response = self.client.post(
                "/api/password-reset/verify/",
                {"identifier": "parent_one", "code": "000000"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        fifth = self.client.post(
            "/api/password-reset/verify/",
            {"identifier": "parent_one", "code": "000000"},
            format="json",
        )
        self.assertEqual(fifth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        correct = self._latest_code().code
        blocked = self.client.post(
            "/api/password-reset/verify/",
            {"identifier": "parent_one", "code": correct},
            format="json",
        )
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_expired_code_is_rejected(self):
        self._request_reset()
        PasswordResetCode.objects.filter(user=self.user).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        code = self._latest_code().code

        response = self.client.post(
            "/api/password-reset/verify/",
            {"identifier": "parent_one", "code": code},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_code_is_single_use(self):
        self._request_reset()
        code = self._latest_code().code

        first = self.client.post(
            "/api/password-reset/confirm/",
            {"identifier": "parent_one", "code": code, "new_password": "SenhaNova!77"},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self.client.post(
            "/api/password-reset/confirm/",
            {"identifier": "parent_one", "code": code, "new_password": "OutraSenha!88"},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_request_supersedes_previous_code(self):
        self._request_reset()
        old_code = self._latest_code().code
        self._request_reset()

        response = self.client.post(
            "/api/password-reset/verify/",
            {"identifier": "parent_one", "code": old_code},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_is_rejected_by_django_validators(self):
        self._request_reset()
        code = self._latest_code().code

        response = self.client.post(
            "/api/password-reset/confirm/",
            {"identifier": "parent_one", "code": code, "new_password": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_request_rate_limited_per_window(self):
        for _ in range(3):
            self.assertEqual(self._request_reset().status_code, status.HTTP_200_OK)

        fourth = self._request_reset()
        self.assertEqual(fourth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_confirm_revokes_existing_refresh_tokens(self):
        login = self.client.post(
            "/api/token/",
            {"username": "parent_one", "password": "SenhaAntiga!42"},
            format="json",
        )
        old_refresh = login.data["refresh"]

        self._request_reset()
        code = self._latest_code().code
        self.client.post(
            "/api/password-reset/confirm/",
            {"identifier": "parent_one", "code": code, "new_password": "SenhaNova!77"},
            format="json",
        )

        refresh_attempt = self.client.post(
            "/api/token/refresh/", {"refresh": old_refresh}, format="json"
        )
        self.assertEqual(refresh_attempt.status_code, status.HTTP_401_UNAUTHORIZED)


class EmailVerificationTests(APITestCase):
    def _register(self, username="parent_one", email="parent@example.com"):
        return self.client.post(
            "/api/register/",
            {
                "first_name": "Ana",
                "last_name": "Silva",
                "username": username,
                "birth_date": "1990-04-18",
                "email": email,
                "password": "SenhaForte!42",
                "terms_version": CURRENT_TERMS_VERSION,
                "privacy_version": CURRENT_PRIVACY_VERSION,
                "accept_terms": True,
                "accept_privacy": True,
                "declare_adult": True,
            },
            format="json",
        )

    def _auth(self, access_token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_register_rejects_invalid_email_format(self):
        response = self._register(email="nao-e-email")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_duplicate_email_case_insensitive(self):
        self._register()
        response = self._register(username="parent_two", email="PARENT@example.com")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_sends_verification_code_and_profile_reports_unverified(self):
        register = self._register()
        self._auth(register.data["access"])

        user = User.objects.get(username="parent_one")
        code = EmailVerificationCode.objects.get(user=user)
        self.assertEqual(len(code.code), 6)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(code.code, mail.outbox[0].body)

        profile = self.client.get("/api/profile/")
        self.assertFalse(profile.data["email_verified"])

    def test_verify_email_marks_profile_verified_and_is_single_use(self):
        register = self._register()
        self._auth(register.data["access"])
        user = User.objects.get(username="parent_one")
        code = EmailVerificationCode.objects.get(user=user).code

        response = self.client.post("/api/email/verify/", {"code": code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        profile = self.client.get("/api/profile/")
        self.assertTrue(profile.data["email_verified"])

        again = self.client.post("/api/email/verify/", {"code": code}, format="json")
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_verification_code_hits_429_after_max_attempts(self):
        register = self._register()
        self._auth(register.data["access"])

        for _ in range(4):
            response = self.client.post(
                "/api/email/verify/", {"code": "000000"}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        fifth = self.client.post("/api/email/verify/", {"code": "000000"}, format="json")
        self.assertEqual(fifth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_resend_supersedes_previous_code_and_rate_limits(self):
        register = self._register()
        self._auth(register.data["access"])
        user = User.objects.get(username="parent_one")
        first_code = EmailVerificationCode.objects.get(user=user).code

        resend = self.client.post("/api/email/verify/resend/")
        self.assertEqual(resend.status_code, status.HTTP_200_OK)

        old = self.client.post("/api/email/verify/", {"code": first_code}, format="json")
        self.assertEqual(old.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.post("/api/email/verify/resend/")
        limited = self.client.post("/api/email/verify/resend/")
        self.assertEqual(limited.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_resend_after_verified_returns_400(self):
        register = self._register()
        self._auth(register.data["access"])
        user = User.objects.get(username="parent_one")
        code = EmailVerificationCode.objects.get(user=user).code
        self.client.post("/api/email/verify/", {"code": code}, format="json")

        response = self.client.post("/api/email/verify/resend/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_changing_email_resets_verification_and_sends_new_code(self):
        register = self._register()
        self._auth(register.data["access"])
        user = User.objects.get(username="parent_one")
        code = EmailVerificationCode.objects.get(user=user).code
        self.client.post("/api/email/verify/", {"code": code}, format="json")

        update = self.client.put(
            "/api/profile/", {"email": "novo@example.com"}, format="json"
        )
        self.assertEqual(update.status_code, status.HTTP_200_OK)

        profile = self.client.get("/api/profile/")
        self.assertFalse(profile.data["email_verified"])
        self.assertEqual(
            EmailVerificationCode.objects.filter(user=user, used_at__isnull=True).count(), 1
        )
        self.assertIn("novo@example.com", mail.outbox[-1].to)


class BackendValidationTests(APITestCase):
    """B3: entradas inválidas devem virar 400, nunca 500."""

    def setUp(self):
        self.user = User.objects.create_user(username="parent_one", password="password123")
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.user)
        access_token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def _register(self, **overrides):
        payload = {
            "first_name": "Ana",
            "last_name": "Silva",
            "username": "new_parent",
            "birth_date": "1990-04-18",
            "email": "new@example.com",
            "password": "SenhaForte!42",
            "terms_version": CURRENT_TERMS_VERSION,
            "privacy_version": CURRENT_PRIVACY_VERSION,
            "accept_terms": True,
            "accept_privacy": True,
            "declare_adult": True,
        }
        payload.update(overrides)
        return self.client.post("/api/register/", payload, format="json")

    def test_register_rejects_username_with_invalid_chars(self):
        response = self._register(username="ana silva!")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_runs_django_password_validators(self):
        common = self._register(password="password123")
        self.assertEqual(common.status_code, status.HTTP_400_BAD_REQUEST)

        numeric = self._register(password="1234567890")
        self.assertEqual(numeric.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_child_invalid_and_future_birth_date_return_400(self):
        invalid = self.client.post(
            "/api/children/",
            {"conversation_id": self.conversation.id, "name": "Filho", "birth_date": "31/12/2020"},
            format="json",
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

        future = self.client.post(
            "/api/children/",
            {"conversation_id": self.conversation.id, "name": "Filho", "birth_date": "2999-01-01"},
            format="json",
        )
        self.assertEqual(future.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_child_requires_legal_declaration(self):
        response = self.client.post(
            "/api/children/",
            {
                "conversation_id": self.conversation.id,
                "name": "Filho",
                "birth_date": "2020-01-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Child.objects.filter(name="Filho").exists())

        accepted = self.client.post(
            "/api/children/",
            {
                "conversation_id": self.conversation.id,
                "name": "Filho",
                "birth_date": "2020-01-01",
                "declare_legal_responsibility": True,
            },
            format="json",
        )

        self.assertEqual(accepted.status_code, status.HTTP_201_CREATED)
        child = Child.objects.get(name="Filho")
        declaration = ChildLegalDeclaration.objects.get(child=child)
        self.assertEqual(declaration.declared_by, self.user)
        self.assertIsNotNone(declaration.declared_at)

    def test_create_event_invalid_dates_return_400(self):
        payload = {
            "conversation_id": self.conversation.id,
            "title": "Consulta",
            "event_type": "MEDICAL",
        }

        invalid_start = self.client.post(
            "/api/events/", {**payload, "event_date": "amanhã"}, format="json"
        )
        self.assertEqual(invalid_start.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_end = self.client.post(
            "/api/events/",
            {**payload, "event_date": "2026-06-10T15:00:00", "event_date_end": "16h"},
            format="json",
        )
        self.assertEqual(invalid_end.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_event_accepts_date_only_string(self):
        response = self.client.post(
            "/api/events/",
            {
                "conversation_id": self.conversation.id,
                "title": "Aniversário",
                "event_type": "OTHER",
                "event_date": "2026-06-10",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_update_event_invalid_date_returns_400(self):
        event = Event.objects.create(
            conversation=self.conversation,
            created_by=self.user,
            title="Consulta",
            event_date=timezone.now(),
            event_type=Event.MEDICAL,
        )

        response = self.client.put(
            f"/api/events/{event.id}/update/",
            {"event_date": "data inválida"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AuthenticatedMediaTests(APITestCase):
    """B2: mídia sensível exige autenticação e participação na conversa."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        self.user = User.objects.create_user(username="parent_one", password="password123")
        self.outsider = User.objects.create_user(username="outsider", password="password123")
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.user)

        photo = SimpleUploadedFile("foto.jpg", b"fake-image-bytes", content_type="image/jpeg")
        self.child = Child.objects.create(
            conversation=self.conversation,
            created_by=self.user,
            name="Filho",
            birth_date="2020-01-01",
            photo=photo,
        )

        attachment = SimpleUploadedFile("doc.pdf", b"fake-pdf-bytes", content_type="application/pdf")
        self.message = Message.objects.create(
            conversation=self.conversation,
            sender=self.user,
            content="com anexo",
            attachment=attachment,
            attachment_type="pdf",
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _auth_as(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_media_requires_authentication(self):
        photo = self.client.get(f"/api/media/children/{self.child.id}/photo/")
        self.assertEqual(photo.status_code, status.HTTP_401_UNAUTHORIZED)

        attachment = self.client.get(f"/api/media/attachments/{self.message.id}/")
        self.assertEqual(attachment.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_participant_cannot_access_media(self):
        self._auth_as(self.outsider)

        photo = self.client.get(f"/api/media/children/{self.child.id}/photo/")
        self.assertEqual(photo.status_code, status.HTTP_403_FORBIDDEN)

        attachment = self.client.get(f"/api/media/attachments/{self.message.id}/")
        self.assertEqual(attachment.status_code, status.HTTP_403_FORBIDDEN)

    def test_participant_downloads_media(self):
        self._auth_as(self.user)

        photo = self.client.get(f"/api/media/children/{self.child.id}/photo/")
        self.assertEqual(photo.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(photo.streaming_content), b"fake-image-bytes")

        attachment = self.client.get(f"/api/media/attachments/{self.message.id}/")
        self.assertEqual(attachment.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(attachment.streaming_content), b"fake-pdf-bytes")

    def test_serializers_point_to_authenticated_endpoints(self):
        self._auth_as(self.user)

        messages = self.client.get(f"/api/messages/{self.conversation.id}/")
        self.assertIn(
            f"/api/media/attachments/{self.message.id}/",
            messages.data[0]["attachment_url"],
        )
        self.assertNotIn("/media/", messages.data[0]["attachment_url"].replace("/api/media/", ""))

        children = self.client.get(f"/api/children/{self.conversation.id}/")
        self.assertIn(
            f"/api/media/children/{self.child.id}/photo/",
            children.data[0]["photo_url"],
        )

    def test_public_media_url_is_gone(self):
        response = self.client.get(f"/media/{self.child.photo.name}")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ExportPdfTypeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="parent_one", password="password123")
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.user)
        Message.objects.create(conversation=self.conversation, sender=self.user, content="oi")
        Event.objects.create(
            conversation=self.conversation,
            created_by=self.user,
            title="Consulta",
            event_date=timezone.now(),
            event_type=Event.MEDICAL,
        )
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def _export(self, params=None):
        return self.client.get(
            f"/api/export/pdf/{self.conversation.id}/", params or {}
        )

    def test_each_type_generates_pdf_with_typed_filename(self):
        for export_type in ("messages", "events", "all"):
            response = self._export({"type": export_type})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn(
                f"coparent_{export_type}_{self.conversation.id}.pdf",
                response["Content-Disposition"],
            )

    def test_default_is_all_and_invalid_type_returns_400(self):
        default = self._export()
        self.assertEqual(default.status_code, status.HTTP_200_OK)
        self.assertIn("coparent_all_", default["Content-Disposition"])

        invalid = self._export({"type": "tudo"})
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)


class DeviceTokenMultiDeviceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="parent_one", password="password123")
        self.other = User.objects.create_user(username="parent_two", password="password123")
        self.access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_user_keeps_tokens_from_multiple_devices(self):
        self.client.post("/api/device-token/", {"token": "device-a"}, format="json")
        self.client.post("/api/device-token/", {"token": "device-b"}, format="json")

        tokens = set(
            DeviceToken.objects.filter(user=self.user).values_list("token", flat=True)
        )
        self.assertEqual(tokens, {"device-a", "device-b"})

    def test_same_device_switching_accounts_reassigns_token(self):
        self.client.post("/api/device-token/", {"token": "shared-device"}, format="json")

        other_access = str(RefreshToken.for_user(self.other).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {other_access}")
        self.client.post("/api/device-token/", {"token": "shared-device"}, format="json")

        device = DeviceToken.objects.get(token="shared-device")
        self.assertEqual(device.user, self.other)
        self.assertEqual(DeviceToken.objects.filter(token="shared-device").count(), 1)

    def test_logout_blacklists_refresh_and_removes_device_token(self):
        login = self.client.post(
            "/api/token/",
            {"username": "parent_one", "password": "password123"},
            format="json",
        )
        refresh = login.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.client.post("/api/device-token/", {"token": "device-a"}, format="json")

        response = self.client.post(
            "/api/logout/",
            {"refresh": refresh, "device_token": "device-a"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(DeviceToken.objects.filter(token="device-a").exists())

        refresh_attempt = self.client.post(
            "/api/token/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(refresh_attempt.status_code, status.HTTP_401_UNAUTHORIZED)


class NotificationPaginationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="parent_one", password="password123")
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        for i in range(1, 61):
            Notification.objects.create(
                recipient=self.user, title=f"notif {i}", body="corpo"
            )

    def test_default_returns_50_most_recent(self):
        response = self.client.get("/api/notifications/")
        self.assertEqual(len(response.data), 50)
        self.assertEqual(response.data[0]["title"], "notif 60")

    def test_before_cursor_walks_backwards(self):
        first_page = self.client.get("/api/notifications/")
        oldest_id = first_page.data[-1]["id"]

        second_page = self.client.get("/api/notifications/", {"before": oldest_id})
        self.assertEqual(len(second_page.data), 10)
        self.assertEqual(second_page.data[-1]["title"], "notif 1")
