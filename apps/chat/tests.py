from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Child, Conversation, Event, Notification, UserProfile
from datetime import timedelta
import shutil
import tempfile


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
                "password": "password123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        conversation = Conversation.objects.get(id=response.data["conversation_id"])
        self.assertTrue(conversation.participants.filter(username="new_parent").exists())
        self.assertEqual(UserProfile.objects.get(user__username="new_parent").birth_date.isoformat(), "1990-04-18")

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
                "password": "password123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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
            cpf="000.000.000-00",
            rg="123",
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
                "cpf": "",
                "rg": "",
                "has_custody": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "Clara Silva")
        self.assertEqual(self.child.birth_date.isoformat(), "2021-05-27")
        self.assertEqual(self.child.cpf, "")
        self.assertEqual(self.child.rg, "")
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
