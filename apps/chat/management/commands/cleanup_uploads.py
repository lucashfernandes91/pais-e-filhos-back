from django.core.management.base import BaseCommand

from apps.chat.upload_lifecycle import purge_expired_attachments, remove_orphaned_attachments


class Command(BaseCommand):
    help = "Remove anexos órfãos e anexos além da retenção configurada."

    def handle(self, *args, **options):
        expired = purge_expired_attachments()
        orphaned = remove_orphaned_attachments()
        self.stdout.write(
            self.style.SUCCESS(f"Anexos expirados: {expired}; órfãos: {orphaned}.")
        )
