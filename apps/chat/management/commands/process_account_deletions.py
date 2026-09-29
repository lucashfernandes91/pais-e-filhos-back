import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.chat.account_deletion import process_deletion_request
from apps.chat.models import AccountDeletionCode, AccountDeletionRequest

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remove contas e dados com pedidos de exclusão vencidos.'

    def handle(self, *args, **options):
        AccountDeletionCode.objects.filter(expires_at__lte=timezone.now()).delete()
        request_ids = list(
            AccountDeletionRequest.objects.filter(
                status=AccountDeletionRequest.PENDING,
                delete_after__lte=timezone.now(),
            ).values_list('pk', flat=True)
        )

        completed = 0
        failed = 0
        for request_id in request_ids:
            try:
                completed += int(process_deletion_request(request_id))
            except Exception:
                failed += 1
                logger.exception('Falha ao processar pedido de exclusão %s', request_id)

        self.stdout.write(
            self.style.SUCCESS(f'Pedidos finalizados: {completed}; falhas: {failed}.')
        )
