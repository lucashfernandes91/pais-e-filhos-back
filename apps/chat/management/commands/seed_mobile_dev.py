from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.chat.models import Child, Conversation, Event, Message, UserProfile


class Command(BaseCommand):
    help = "Cria dados idempotentes para executar o aplicativo Android em debug."

    USERNAME = "pai_demo"
    PASSWORD = "PaisEFilhos!2026"
    COPARENT_USERNAME = "mae_demo"

    @transaction.atomic
    def handle(self, *args, **options):
        parent = self._upsert_user(
            username=self.USERNAME,
            email="pai.demo@example.com",
            first_name="Rafael",
            last_name="Demo",
            birth_date=date(1988, 5, 12),
        )
        coparent = self._upsert_user(
            username=self.COPARENT_USERNAME,
            email="mae.demo@example.com",
            first_name="Ana",
            last_name="Demo",
            birth_date=date(1990, 9, 23),
        )

        conversation = (
            Conversation.objects.filter(participants=parent)
            .filter(participants=coparent)
            .annotate(participant_count=Count("participants"))
            .filter(participant_count=2)
            .first()
        )
        if conversation is None:
            conversation = Conversation.objects.create()
        conversation.participants.set([parent, coparent])

        Child.objects.update_or_create(
            conversation=conversation,
            name="Sofia Demo",
            defaults={
                "birth_date": date(2018, 3, 15),
                "has_custody": True,
                "created_by": parent,
            },
        )

        tomorrow = timezone.localdate() + timedelta(days=1)
        event_start = timezone.make_aware(
            timezone.datetime.combine(tomorrow, time(hour=9))
        )
        Event.objects.update_or_create(
            conversation=conversation,
            title="Reuniao escolar - Demo",
            defaults={
                "created_by": coparent,
                "event_date": event_start,
                "event_date_end": event_start + timedelta(hours=1),
                "event_type": Event.SCHOOL,
                "notes": "Evento criado automaticamente para o ambiente mobile.",
            },
        )

        demo_messages = (
            (coparent, "Oi! Estes sao os dados de demonstracao do aplicativo."),
            (parent, "Perfeito. O acesso pelo celular esta funcionando."),
        )
        for sender, content in demo_messages:
            Message.objects.get_or_create(
                conversation=conversation,
                sender=sender,
                content=content,
            )

        self.stdout.write(self.style.SUCCESS("Dados mobile de desenvolvimento prontos."))
        self.stdout.write(f"Usuario: {self.USERNAME}")
        self.stdout.write(f"Senha: {self.PASSWORD}")
        self.stdout.write(f"Conversa: {conversation.id}")

    def _upsert_user(
        self,
        *,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        birth_date: date,
    ) -> User:
        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
            },
        )
        user.set_password(self.PASSWORD)
        user.save(update_fields=["password"])
        UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "birth_date": birth_date,
                "email_verified_at": timezone.now(),
            },
        )
        return user
