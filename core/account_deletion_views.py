import logging

from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import EmailValidator
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.chat.account_deletion import (
    DELETION_WINDOW_DAYS,
    confirm_deletion_request,
    issue_deletion_code,
    normalize_email,
)

logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    local, separator, domain = email.partition('@')
    if not separator:
        return email
    visible_local = local[:1] if local else ''
    return f'{visible_local}***@{domain}'


def _render(request, **context):
    return render(request, 'legal/account_deletion.html', context)


@require_http_methods(['GET', 'POST'])
@never_cache
def account_deletion(request):
    stage = 'request'
    email = ''
    error = ''
    notice = ''

    if request.method == 'POST':
        action = request.POST.get('action', '')
        email = normalize_email(request.POST.get('email', ''))

        try:
            EmailValidator()(email)
        except ValidationError:
            error = 'Informe um endereço de e-mail válido.'
        else:
            if action == 'send_code':
                issue_deletion_code(email)
                stage = 'verify'
                notice = (
                    'Se houver uma conta com esse e-mail, enviaremos um código de '
                    'confirmação. Verifique também a caixa de spam.'
                )
            elif action == 'confirm':
                stage = 'verify'
                code = request.POST.get('code', '').strip()
                if request.POST.get('confirm_deletion') != 'yes':
                    error = 'Confirme que deseja solicitar a exclusão da conta.'
                else:
                    result = confirm_deletion_request(email, code)
                    if result is None:
                        error = 'Código inválido ou expirado. Solicite um novo código.'
                    else:
                        deletion_request, recipient, created = result
                        if created:
                            try:
                                send_mail(
                                    subject='CoParent Lite — Exclusão solicitada',
                                    message=(
                                        'Recebemos e confirmamos seu pedido de exclusão. '
                                        'O acesso à conta foi bloqueado imediatamente. '
                                        f'A remoção será concluída em até {DELETION_WINDOW_DAYS} dias.'
                                    ),
                                    from_email=None,
                                    recipient_list=[recipient],
                                    fail_silently=False,
                                )
                            except Exception:
                                logger.error(
                                    'Falha ao enviar confirmação de exclusão (registro %s)',
                                    deletion_request.pk,
                                )
                        stage = 'complete'
                        email = ''
                        notice = (
                            'Pedido confirmado. O acesso à conta foi bloqueado. '
                            f'A exclusão será concluída em até {DELETION_WINDOW_DAYS} dias.'
                        )
            else:
                error = 'Não foi possível processar o pedido. Tente novamente.'

    return _render(
        request,
        stage=stage,
        email=email,
        masked_email=_mask_email(email) if email else '',
        error=error,
        notice=notice,
    )
