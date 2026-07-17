from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from .models import Message, Conversation, ConversationInvite, Event, MessageRead, DeviceToken, Notification, Child, EmailVerificationCode, PasswordResetCode, UserProfile
from .serializers import MessageSerializer, EventSerializer, MessageDetailSerializer, DeviceTokenSerializer, NotificationSerializer, ChildSerializer
from django.utils import timezone
from django.core.mail import send_mail
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import EmailValidator
from core.pdf_generator import generate_conversation_pdf
from core.error_handler import ValidationError, NotFoundError, ForbiddenError, ServerError, RateLimitError, handle_exception
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.utils.dateparse import parse_datetime, parse_date
from datetime import date, datetime, timedelta
import logging
import re
import secrets

logger = logging.getLogger(__name__)

# Regras de negócio do convite (decisões de 2026-07-16):
# conversa 1:1, código expira em 7 dias, novo código invalida o anterior.
MAX_CONVERSATION_PARTICIPANTS = 2
INVITE_TTL_DAYS = 7
INVITE_CODE_LENGTH = 8
# Sem 0/O/1/I/L para o código sobreviver a ditado por telefone.
INVITE_CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
INVITE_LINK_BASE = 'https://coparent.app/convite/'

# Códigos por e-mail — reset de senha e confirmação de e-mail compartilham
# as regras (decisões de 2026-07-16): 6 dígitos, 15 minutos, 5 tentativas,
# 3 pedidos por janela.
RESET_CODE_TTL_MINUTES = 15
RESET_CODE_MAX_ATTEMPTS = 5
RESET_REQUESTS_PER_WINDOW = 3


# AUTH

def ensure_user_conversation(user):
    """Return the user's workspace, creating one for accounts without one."""
    conversation = Conversation.objects.filter(participants=user).order_by('created_at').first()
    if conversation is None:
        conversation = Conversation.objects.create()
        conversation.participants.add(user)
    return conversation


@api_view(['POST'])
def register_user(request):
    """Register a new user and return JWT tokens."""
    try:
        username = request.data.get('username', '').strip()
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        birth_date_value = request.data.get('birth_date', '').strip()
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '')

        if not first_name:
            return ValidationError("Nome \u00e9 obrigat\u00f3rio").to_response()

        if not last_name:
            return ValidationError("Sobrenome \u00e9 obrigat\u00f3rio").to_response()

        if not username or len(username) < 5:
            return ValidationError("Nome de usu\u00e1rio deve ter pelo menos 5 caracteres").to_response()

        if not re.fullmatch(r'[a-zA-Z0-9._]+', username):
            return ValidationError("Nome de usu\u00e1rio: use apenas letras, n\u00fameros, . ou _").to_response()

        if not email:
            return ValidationError("Email \u00e9 obrigat\u00f3rio").to_response()

        try:
            EmailValidator()(email)
        except DjangoValidationError:
            return ValidationError("Email inv\u00e1lido").to_response()

        try:
            birth_date = date.fromisoformat(birth_date_value)
        except ValueError:
            return ValidationError("Data de nascimento inv\u00e1lida").to_response()

        if birth_date > date.today():
            return ValidationError("Data de nascimento n\u00e3o pode estar no futuro").to_response()

        if not password or len(password) < 8:
            return ValidationError("Senha deve ter pelo menos 8 caracteres").to_response()

        try:
            validate_password(password, user=User(
                username=username, email=email,
                first_name=first_name, last_name=last_name,
            ))
        except DjangoValidationError as e:
            return ValidationError(" ".join(e.messages)).to_response()

        if User.objects.filter(username=username).exists():
            return ValidationError("Nome de usu\u00e1rio j\u00e1 existe").to_response()

        if User.objects.filter(email__iexact=email).exists():
            return ValidationError("Email j\u00e1 cadastrado").to_response()

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        UserProfile.objects.create(user=user, birth_date=birth_date)
        conversation = ensure_user_conversation(user)
        _issue_email_verification(user)

        # Generate tokens
        refresh = RefreshToken.for_user(user)

        return Response({
            'status': 'ok',
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'birth_date': birth_date.isoformat(),
            'conversation_id': conversation.id,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=201)

    except Exception as e:
        return handle_exception(e)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """Get or update the authenticated user's profile."""
    try:
        user = request.user

        if request.method == 'GET':
            profile = UserProfile.objects.filter(user=user).first()
            return Response({
                'id': user.id,
                'username': user.username,
                'email': user.email or '',
                'first_name': user.first_name,
                'last_name': user.last_name,
                'birth_date': profile.birth_date.isoformat() if profile else '',
                'email_verified': bool(profile and profile.email_verified_at),
            })

        # PUT
        first_name = request.data.get('first_name', user.first_name)
        last_name = request.data.get('last_name', user.last_name)
        email = request.data.get('email', user.email)

        email_changed = bool(email) and email != user.email
        if email_changed:
            try:
                EmailValidator()(email)
            except DjangoValidationError:
                return ValidationError("Email inv\u00e1lido").to_response()
            if User.objects.filter(email__iexact=email).exclude(id=user.id).exists():
                return ValidationError("Email j\u00e1 cadastrado por outro usu\u00e1rio").to_response()

        user.first_name = first_name
        user.last_name = last_name
        user.email = email or ''
        user.save()

        # Trocou de e-mail: a confirma\u00e7\u00e3o anterior deixa de valer.
        if email_changed:
            profile = UserProfile.objects.filter(user=user).first()
            if profile is not None and profile.email_verified_at is not None:
                profile.email_verified_at = None
                profile.save(update_fields=['email_verified_at'])
            _issue_email_verification(user)

        return Response({
            'status': 'ok',
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        })

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    """Encerra a sessão: blacklista o refresh e remove o token do aparelho."""
    try:
        refresh = str(request.data.get('refresh', '')).strip()
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # já expirado ou inválido — nada a revogar

        device_token = str(request.data.get('device_token', '')).strip()
        if device_token:
            DeviceToken.objects.filter(user=request.user, token=device_token).delete()

        return Response({'status': 'ok'})

    except Exception as e:
        return handle_exception(e)


# PASSWORD RESET

def _find_user_by_identifier(identifier):
    return (
        User.objects.filter(username__iexact=identifier).first()
        or User.objects.filter(email__iexact=identifier).first()
    )


def _get_active_reset_code(user):
    """Somente o código não usado mais recente vale."""
    return (
        PasswordResetCode.objects
        .filter(user=user, used_at__isnull=True)
        .order_by('-created_at')
        .first()
    )


def _validate_timed_code(code_obj, code_value):
    """Regras comuns aos códigos de reset e de confirmação de e-mail.

    Retorna (code_obj, error_response): exatamente um dos dois é None.
    """
    if code_obj is None:
        return None, ValidationError("Código inválido ou expirado").to_response()

    if code_obj.attempts >= RESET_CODE_MAX_ATTEMPTS:
        return None, RateLimitError().to_response()

    if code_obj.expires_at < timezone.now():
        return None, ValidationError("Código inválido ou expirado").to_response()

    if code_obj.code != code_value:
        code_obj.attempts += 1
        code_obj.save(update_fields=['attempts'])
        if code_obj.attempts >= RESET_CODE_MAX_ATTEMPTS:
            return None, RateLimitError().to_response()
        return None, ValidationError("Código inválido ou expirado").to_response()

    return code_obj, None


def _validate_reset_code(user, code_value):
    return _validate_timed_code(_get_active_reset_code(user), code_value)


def _generate_numeric_code():
    return ''.join(secrets.choice('0123456789') for _ in range(6))


def _parse_event_datetime(value):
    """Aceita ISO datetime ou data pura; retorna datetime aware ou None."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value)
        parsed = parse_datetime(text)
        if parsed is None:
            as_date = parse_date(text)
            if as_date is not None:
                parsed = datetime(as_date.year, as_date.month, as_date.day)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


@api_view(['POST'])
def request_password_reset(request):
    """Envia o código de redefinição. Resposta neutra: não revela contas."""
    try:
        identifier = str(request.data.get('identifier', '')).strip()
        if not identifier:
            return ValidationError("Informe usuário ou email").to_response()

        neutral = Response({'status': 'ok'})

        user = _find_user_by_identifier(identifier)
        if user is None or not user.email:
            return neutral

        window_start = timezone.now() - timedelta(minutes=RESET_CODE_TTL_MINUTES)
        recent_requests = PasswordResetCode.objects.filter(
            user=user, created_at__gte=window_start
        ).count()
        if recent_requests >= RESET_REQUESTS_PER_WINDOW:
            return RateLimitError().to_response()

        code = _generate_numeric_code()
        PasswordResetCode.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=RESET_CODE_TTL_MINUTES),
        )

        try:
            send_mail(
                subject='CoParent Lite — Código de redefinição de senha',
                message=(
                    f'Olá, {user.first_name or user.username}!\n\n'
                    f'Seu código de redefinição de senha é: {code}\n\n'
                    f'Ele vale por {RESET_CODE_TTL_MINUTES} minutos e pode ser usado uma única vez.\n'
                    'Se você não pediu a redefinição, ignore este e-mail.'
                ),
                from_email=None,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            logger.error(f"Falha ao enviar e-mail de reset para user {user.id}: {e}")

        return neutral

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
def verify_password_reset(request):
    """Confere o código antes da tela de nova senha."""
    try:
        identifier = str(request.data.get('identifier', '')).strip()
        code_value = str(request.data.get('code', '')).strip()
        if not identifier or not code_value:
            return ValidationError("Código inválido ou expirado").to_response()

        user = _find_user_by_identifier(identifier)
        if user is None:
            return ValidationError("Código inválido ou expirado").to_response()

        _, error = _validate_reset_code(user, code_value)
        if error is not None:
            return error

        return Response({'status': 'ok'})

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
def confirm_password_reset(request):
    """Troca a senha, consome o código e derruba as sessões existentes."""
    try:
        identifier = str(request.data.get('identifier', '')).strip()
        code_value = str(request.data.get('code', '')).strip()
        new_password = request.data.get('new_password', '')

        if not identifier or not code_value:
            return ValidationError("Código inválido ou expirado").to_response()

        user = _find_user_by_identifier(identifier)
        if user is None:
            return ValidationError("Código inválido ou expirado").to_response()

        reset_code, error = _validate_reset_code(user, code_value)
        if error is not None:
            return error

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as e:
            return ValidationError(" ".join(e.messages)).to_response()

        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=['password'])
            reset_code.used_at = timezone.now()
            reset_code.save(update_fields=['used_at'])

            # Sessões antigas caem: refresh tokens emitidos até aqui são
            # colocados na blacklist.
            for token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=token)

        return Response({'status': 'ok'})

    except Exception as e:
        return handle_exception(e)


# EMAIL VERIFICATION

def _issue_email_verification(user):
    """Cria e envia o código de confirmação; nunca derruba o fluxo chamador."""
    code = _generate_numeric_code()
    EmailVerificationCode.objects.create(
        user=user,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=RESET_CODE_TTL_MINUTES),
    )
    try:
        send_mail(
            subject='CoParent Lite — Confirme seu e-mail',
            message=(
                f'Olá, {user.first_name or user.username}!\n\n'
                f'Seu código de confirmação de e-mail é: {code}\n\n'
                f'Ele vale por {RESET_CODE_TTL_MINUTES} minutos.\n'
                'Se você não criou uma conta no CoParent Lite, ignore este e-mail.'
            ),
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"Falha ao enviar e-mail de verificação para user {user.id}: {e}")


def _get_active_verification_code(user):
    return (
        EmailVerificationCode.objects
        .filter(user=user, used_at__isnull=True)
        .order_by('-created_at')
        .first()
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_email(request):
    """Confirma o e-mail da conta com o código recebido."""
    try:
        code_value = str(request.data.get('code', '')).strip()
        if not code_value:
            return ValidationError("Código é obrigatório").to_response()

        profile = UserProfile.objects.filter(user=request.user).first()
        if profile is not None and profile.email_verified_at is not None:
            return ValidationError("E-mail já confirmado").to_response()

        code_obj, error = _validate_timed_code(
            _get_active_verification_code(request.user), code_value
        )
        if error is not None:
            return error

        code_obj.used_at = timezone.now()
        code_obj.save(update_fields=['used_at'])
        if profile is None:
            profile = UserProfile.objects.create(user=request.user, birth_date=date.today())
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=['email_verified_at'])

        return Response({'status': 'ok', 'email_verified': True})

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resend_email_verification(request):
    """Reenvia o código de confirmação, com o mesmo rate limit do reset."""
    try:
        user = request.user
        if not user.email:
            return ValidationError("Conta sem e-mail cadastrado").to_response()

        profile = UserProfile.objects.filter(user=user).first()
        if profile is not None and profile.email_verified_at is not None:
            return ValidationError("E-mail já confirmado").to_response()

        window_start = timezone.now() - timedelta(minutes=RESET_CODE_TTL_MINUTES)
        recent = EmailVerificationCode.objects.filter(
            user=user, created_at__gte=window_start
        ).count()
        if recent >= RESET_REQUESTS_PER_WINDOW:
            return RateLimitError().to_response()

        _issue_email_verification(user)
        return Response({'status': 'ok'})

    except Exception as e:
        return handle_exception(e)


# CONVERSATIONS

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_conversations(request):
    """Lista conversas do usuÃ¡rio com participantes e filhos."""
    try:
        ensure_user_conversation(request.user)
        conversations = Conversation.objects.filter(participants=request.user)
        result = []
        for conv in conversations:
            participants = []
            for p in conv.participants.all():
                participants.append({
                    'id': p.id,
                    'username': p.username,
                    'is_me': p.id == request.user.id
                })
            children = Child.objects.filter(conversation=conv)
            children_data = ChildSerializer(children, many=True, context={'request': request}).data
            result.append({
                'id': conv.id,
                'created_at': conv.created_at,
                'participants': participants,
                'children': children_data
            })
        # Conversa compartilhada primeiro: o app usa a primeira da lista
        # como workspace ativo.
        result.sort(key=lambda c: (-len(c['participants']), c['id']))
        return Response(result)
    except Exception as e:
        return handle_exception(e)


# INVITES

def _generate_invite_code():
    while True:
        code = ''.join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
        if not ConversationInvite.objects.filter(code=code).exists():
            return code


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_invite(request):
    """Gera o código de convite da conversa, invalidando o anterior."""
    try:
        conversation_id = request.data.get('conversation_id')
        if not conversation_id:
            return ValidationError("conversation_id é obrigatório").to_response()

        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("Você não faz parte dessa conversa").to_response()

        if conversation.participants.count() >= MAX_CONVERSATION_PARTICIPANTS:
            return ValidationError("Esta conversa já tem dois responsáveis").to_response()

        ConversationInvite.objects.filter(
            conversation=conversation, accepted_by__isnull=True
        ).delete()

        invite = ConversationInvite.objects.create(
            conversation=conversation,
            created_by=request.user,
            code=_generate_invite_code(),
            expires_at=timezone.now() + timedelta(days=INVITE_TTL_DAYS),
        )

        return Response({
            'status': 'ok',
            'code': invite.code,
            'invite_url': f'{INVITE_LINK_BASE}{invite.code}',
            'expires_at': invite.expires_at,
        }, status=201)

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_invite(request):
    """Entra na conversa do convite e migra o workspace solo do convidado."""
    try:
        code = str(request.data.get('code', '')).strip().upper()
        if not code:
            return ValidationError("Código é obrigatório").to_response()

        try:
            invite = ConversationInvite.objects.get(code=code)
        except ConversationInvite.DoesNotExist:
            return NotFoundError("Convite").to_response()

        if invite.accepted_by is not None:
            return ValidationError("Este convite já foi utilizado").to_response()

        if invite.expires_at < timezone.now():
            return ValidationError("Convite expirado. Peça um novo código").to_response()

        conversation = invite.conversation

        if conversation.participants.filter(id=request.user.id).exists():
            return ValidationError("Você já faz parte dessa conversa").to_response()

        if conversation.participants.count() >= MAX_CONVERSATION_PARTICIPANTS:
            return ValidationError("Esta conversa já tem dois responsáveis").to_response()

        with transaction.atomic():
            conversation.participants.add(request.user)
            invite.accepted_by = request.user
            invite.accepted_at = timezone.now()
            invite.save(update_fields=['accepted_by', 'accepted_at'])

            # O convidado ganhou um workspace solo no cadastro; filhos e
            # eventos registrados lá migram para a conversa da família.
            solo_conversations = Conversation.objects.filter(
                participants=request.user
            ).exclude(id=conversation.id)
            for solo in solo_conversations:
                if solo.participants.count() != 1:
                    continue
                Child.objects.filter(conversation=solo).update(conversation=conversation)
                Event.objects.filter(conversation=solo).update(conversation=conversation)
                if not Message.objects.filter(conversation=solo).exists():
                    solo.delete()

        participants = [
            {'id': p.id, 'username': p.username, 'is_me': p.id == request.user.id}
            for p in conversation.participants.all()
        ]
        return Response({
            'status': 'ok',
            'conversation_id': conversation.id,
            'participants': participants,
        })

    except Exception as e:
        return handle_exception(e)

# MESSAGES

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message(request):
    try:
        conversation_id = request.data.get('conversation_id')
        content = request.data.get('content')

        # Validate input
        if not conversation_id or not content:
            return ValidationError("conversation_id e content sÃ£o obrigatÃ³rios").to_response()

        if len(content.strip()) == 0:
            return ValidationError("Mensagem nÃ£o pode estar vazia").to_response()

        if len(content) > 5000:
            return ValidationError("Mensagem muito longa (mÃ¡x 5000 caracteres)").to_response()

        # Get conversation
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        # Check authorization
        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Create message
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content
        )

        return Response({
            "status": "ok",
            "message_id": message.id,
            "created_at": message.created_at
        })

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def send_message_with_attachment(request):
    """Send a message with a file attachment (image/document)."""
    try:
        conversation_id = request.data.get('conversation_id')
        content = request.data.get('content', '')
        attachment = request.FILES.get('attachment')

        if not conversation_id:
            return ValidationError("conversation_id Ã© obrigatÃ³rio").to_response()

        if not content and not attachment:
            return ValidationError("Mensagem ou anexo Ã© obrigatÃ³rio").to_response()

        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Determine attachment type
        attachment_type = ''
        if attachment:
            content_type = attachment.content_type or ''
            if content_type.startswith('image/'):
                attachment_type = 'image'
            elif content_type == 'application/pdf':
                attachment_type = 'pdf'
            else:
                attachment_type = 'document'

            # Limit file size (10MB)
            if attachment.size > 10 * 1024 * 1024:
                return ValidationError("Arquivo muito grande (mÃ¡x 10MB)").to_response()

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content,
            attachment=attachment,
            attachment_type=attachment_type
        )

        serializer = MessageSerializer(message, context={'request': request})
        return Response(serializer.data, status=201)

    except Exception as e:
        return handle_exception(e)


# CHILDREN

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_children(request, conversation_id):
    try:
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        children = Child.objects.filter(conversation_id=conversation_id)
        serializer = ChildSerializer(children, many=True, context={'request': request})
        return Response(serializer.data)

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_child(request):
    try:
        conversation_id = request.data.get('conversation_id')
        name = request.data.get('name')
        birth_date = request.data.get('birth_date')  # required, format YYYY-MM-DD

        if not conversation_id:
            return ValidationError("conversation_id Ã© obrigatÃ³rio").to_response()

        if not name or len(name.strip()) == 0:
            return ValidationError("Nome do filho Ã© obrigatÃ³rio").to_response()

        if len(name) > 100:
            return ValidationError("Nome muito longo (mÃ¡x 100 caracteres)").to_response()

        if not birth_date:
            return ValidationError("Data de nascimento é obrigatória").to_response()

        try:
            parsed_birth_date = date.fromisoformat(str(birth_date))
        except ValueError:
            return ValidationError("Data de nascimento inválida").to_response()

        if parsed_birth_date > date.today():
            return ValidationError("Data de nascimento não pode estar no futuro").to_response()

        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("Você não faz parte dessa conversa").to_response()

        child = Child.objects.create(
            conversation=conversation,
            created_by=request.user,
            name=name.strip(),
            birth_date=parsed_birth_date,
            cpf=request.data.get('cpf', ''),
            rg=request.data.get('rg', ''),
            has_custody=request.data.get('has_custody', False)
        )
        serializer = ChildSerializer(child, context={'request': request})
        return Response(serializer.data, status=201)

    except Exception as e:
        return handle_exception(e)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def update_child(request, child_id):
    try:
        try:
            child = Child.objects.get(id=child_id)
        except Child.DoesNotExist:
            return NotFoundError("Filho").to_response()

        if not child.conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("Voc\u00ea n\u00e3o faz parte dessa conversa").to_response()

        name = request.data.get('name', child.name)
        if not name or not str(name).strip():
            return ValidationError("Nome do filho \u00e9 obrigat\u00f3rio").to_response()

        name = str(name).strip()
        if len(name) > 100:
            return ValidationError("Nome muito longo (m\u00e1x 100 caracteres)").to_response()

        birth_date = request.data.get('birth_date', child.birth_date)
        if not birth_date:
            return ValidationError("Data de nascimento \u00e9 obrigat\u00f3ria").to_response()

        if isinstance(birth_date, date):
            parsed_birth_date = birth_date
        else:
            try:
                parsed_birth_date = date.fromisoformat(str(birth_date))
            except ValueError:
                return ValidationError("Data de nascimento inv\u00e1lida").to_response()

        child.name = name
        child.birth_date = parsed_birth_date
        if 'cpf' in request.data:
            child.cpf = request.data.get('cpf') or ''
        if 'rg' in request.data:
            child.rg = request.data.get('rg') or ''
        if 'has_custody' in request.data:
            custody_value = request.data.get('has_custody')
            if isinstance(custody_value, bool):
                child.has_custody = custody_value
            elif str(custody_value).lower() in ('true', '1'):
                child.has_custody = True
            elif str(custody_value).lower() in ('false', '0'):
                child.has_custody = False
            else:
                return ValidationError("Valor de guarda inv\u00e1lido").to_response()

        photo = request.FILES.get('photo')
        if photo is not None:
            if photo.size > 5 * 1024 * 1024:
                return ValidationError("Foto muito grande (m\u00e1x 5MB)").to_response()
            if not (photo.content_type or '').startswith('image/'):
                return ValidationError("Arquivo da foto inv\u00e1lido").to_response()
            child.photo = photo
        child.save()

        serializer = ChildSerializer(child, context={'request': request})
        return Response(serializer.data)

    except Exception as e:
        return handle_exception(e)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_child(request, child_id):
    try:
        try:
            child = Child.objects.get(id=child_id)
        except Child.DoesNotExist:
            return NotFoundError("Filho").to_response()

        if not child.conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        child.delete()
        return Response({'status': 'ok'})

    except Exception as e:
        return handle_exception(e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_messages(request, conversation_id):
    try:
        # Validate conversation exists
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        # Verify authorization
        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Pagination: returns the most recent page by default; `before=<message_id>`
        # walks backwards through history. Response stays in chronological order.
        MAX_PAGE_SIZE = 100
        try:
            limit = int(request.query_params.get('limit', MAX_PAGE_SIZE))
        except (TypeError, ValueError):
            return ValidationError("limit inválido").to_response()
        limit = max(1, min(limit, MAX_PAGE_SIZE))

        queryset = Message.objects.filter(conversation_id=conversation_id).prefetch_related(
            'messageread_set__reader'
        )

        before = request.query_params.get('before')
        if before is not None:
            try:
                before_id = int(before)
            except (TypeError, ValueError):
                return ValidationError("before inválido").to_response()
            queryset = queryset.filter(id__lt=before_id)

        # ids are append-only, so ordering by -id == newest first without
        # created_at ties. Slice the page, then restore chronological order.
        messages = list(queryset.order_by('-id')[:limit])
        messages.reverse()

        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)

    except Exception as e:
        return handle_exception(e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def message_detail(request, message_id):
    try:
        # Validate message exists
        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return NotFoundError("Mensagem").to_response()

        # Verify authorization
        if not message.conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        serializer = MessageDetailSerializer(message)
        return Response(serializer.data)

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_message_read(request, message_id):
    try:
        # Validate message exists
        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return NotFoundError("Mensagem").to_response()

        # Verify user is conversation participant
        if not message.conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Mark as read
        read, _ = MessageRead.objects.get_or_create(
            message=message,
            reader=request.user
        )
        return Response({'status': 'ok', 'read_at': read.read_at})

    except Exception as e:
        return handle_exception(e)


# EVENTS

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_event(request):
    try:
        conversation_id = request.data.get('conversation_id')
        title = request.data.get('title')
        event_date = request.data.get('event_date')
        event_type = request.data.get('event_type')
        notes = request.data.get('notes', '')
        event_date_end = request.data.get('event_date_end', None)
        # Validate input
        if not conversation_id:
            return ValidationError("conversation_id Ã© obrigatÃ³rio").to_response()

        if not title or len(title.strip()) == 0:
            return ValidationError("TÃ­tulo do evento Ã© obrigatÃ³rio").to_response()

        if len(title) > 255:
            return ValidationError("TÃ­tulo muito longo (mÃ¡x 255 caracteres)").to_response()

        if not event_date:
            return ValidationError("Data do evento é obrigatória").to_response()

        if not event_type:
            return ValidationError("Tipo de evento é obrigatório").to_response()

        parsed_event_date = _parse_event_datetime(event_date)
        if parsed_event_date is None:
            return ValidationError("Data do evento inválida").to_response()

        parsed_event_date_end = None
        if event_date_end:
            parsed_event_date_end = _parse_event_datetime(event_date_end)
            if parsed_event_date_end is None:
                return ValidationError("Data de fim do evento inválida").to_response()

        # Verify conversation exists
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        # Check authorization
        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("Você não faz parte dessa conversa").to_response()

        # Create event
        event = Event.objects.create(
            conversation=conversation,
            created_by=request.user,
            title=title.strip(),
            event_date=parsed_event_date,
            event_date_end=parsed_event_date_end,
            event_type=event_type,
            notes=notes
        )
        serializer = EventSerializer(event)
        return Response(serializer.data, status=201)

    except Exception as e:
        return handle_exception(e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_events(request, conversation_id):
    try:
        # Verify conversation exists
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        # Check authorization
        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Get events
        events = Event.objects.filter(conversation_id=conversation_id).order_by('event_date')
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data)

    except Exception as e:
        return handle_exception(e)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_event(request, event_id):
    try:
        # Verify event exists
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return NotFoundError("Evento").to_response()

        # Check authorization (only creator or conversation admin can delete)
        if not event.conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Delete event
        event.delete()
        return Response({'status': 'ok'})

    except Exception as e:
        return handle_exception(e)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_event(request, event_id):
    """Update an existing event."""
    try:
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return NotFoundError("Evento").to_response()

        if not event.conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("Voc\u00ea n\u00e3o faz parte dessa conversa").to_response()

        title = request.data.get('title', event.title)
        event_date = request.data.get('event_date', None)
        event_date_end = request.data.get('event_date_end', event.event_date_end)
        event_type = request.data.get('event_type', event.event_type)
        notes = request.data.get('notes', event.notes)

        if title and len(title.strip()) == 0:
            return ValidationError("T\u00edtulo n\u00e3o pode estar vazio").to_response()

        parsed_event_date = None
        if event_date:
            parsed_event_date = _parse_event_datetime(event_date)
            if parsed_event_date is None:
                return ValidationError("Data do evento inv\u00e1lida").to_response()

        parsed_event_date_end = event_date_end
        if event_date_end and not isinstance(event_date_end, datetime):
            parsed_event_date_end = _parse_event_datetime(event_date_end)
            if parsed_event_date_end is None:
                return ValidationError("Data de fim do evento inv\u00e1lida").to_response()

        event.title = title.strip() if title else event.title
        if parsed_event_date:
            event.event_date = parsed_event_date
        event.event_date_end = parsed_event_date_end
        event.event_type = event_type
        event.notes = notes
        event.save()

        serializer = EventSerializer(event)
        return Response(serializer.data)

    except Exception as e:
        return handle_exception(e)


# NOTIFICATIONS

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_device_token(request):
    try:
        token = request.data.get('token')

        # Validate input
        if not token or len(token.strip()) == 0:
            return ValidationError("Token do dispositivo Ã© obrigatÃ³rio").to_response()

        if len(token) > 1000:
            return ValidationError("Token muito longo").to_response()

        # B7: chave é o token (aparelho); trocar de conta reatribui o device.
        device, _ = DeviceToken.objects.update_or_create(
            token=token.strip(),
            defaults={'user': request.user}
        )
        return Response({'status': 'ok', 'token_id': device.id})

    except Exception as e:
        return handle_exception(e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_notifications(request):
    try:
        # B9: paginação por cursor, mesmo contrato do list_messages.
        MAX_PAGE_SIZE = 100
        try:
            limit = int(request.query_params.get('limit', 50))
        except (TypeError, ValueError):
            return ValidationError("limit inválido").to_response()
        limit = max(1, min(limit, MAX_PAGE_SIZE))

        queryset = Notification.objects.filter(recipient=request.user)

        before = request.query_params.get('before')
        if before is not None:
            try:
                queryset = queryset.filter(id__lt=int(before))
            except (TypeError, ValueError):
                return ValidationError("before inválido").to_response()

        notifications = queryset.order_by('-id')[:limit]

        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    """
    Bulk mark all unread notifications as read for the authenticated user.
    Uses QuerySet.update() â€” single SQL query, not N queries in a loop.
    """
    try:
        now = timezone.now()
        updated_count = Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True
        ).update(read_at=now)

        return Response({
            'status': 'ok',
            'marked_count': updated_count,
            'read_at': now
        })

    except Exception as e:
        return handle_exception(e)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_all_notifications(request):
    try:
        deleted_count, _ = Notification.objects.filter(
            recipient=request.user
        ).delete()

        return Response({
            'status': 'ok',
            'deleted_count': deleted_count
        })

    except Exception as e:
        return handle_exception(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, notification_id):
    """
    Mark a single notification as read.
    """
    try:
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=request.user
            )
        except Notification.DoesNotExist:
            return NotFoundError("NotificaÃ§Ã£o").to_response()

        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=['read_at'])

        return Response({
            'status': 'ok',
            'read_at': notification.read_at
        })

    except Exception as e:
        return handle_exception(e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_notifications_count(request):
    """
    Returns the count of unread notifications for the authenticated user.
    Lightweight endpoint for badge/polling.
    """
    try:
        count = Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True
        ).count()

        return Response({
            'unread_count': count
        })

    except Exception as e:
        return handle_exception(e)


# MEDIA (B2): arquivos sensíveis saem por endpoint autenticado,
# nunca por /media/ público.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def serve_message_attachment(request, message_id):
    try:
        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return NotFoundError("Anexo").to_response()

        if not message.conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("Você não faz parte dessa conversa").to_response()

        if not message.attachment:
            return NotFoundError("Anexo").to_response()

        return FileResponse(message.attachment.open('rb'))

    except Exception as e:
        return handle_exception(e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def serve_child_photo(request, child_id):
    try:
        try:
            child = Child.objects.get(id=child_id)
        except Child.DoesNotExist:
            return NotFoundError("Foto").to_response()

        if not child.conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("Você não faz parte dessa conversa").to_response()

        if not child.photo:
            return NotFoundError("Foto").to_response()

        return FileResponse(child.photo.open('rb'))

    except Exception as e:
        return handle_exception(e)


# PDF EXPORT

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_conversation_pdf(request, conversation_id):
    """
    Export conversation (messages + events) as PDF

    Args:
        conversation_id: ID of conversation to export

    Returns:
        PDF file for download
    """
    try:
        # Verify conversation exists
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        # Verify user is participant
        if not conversation.participants.filter(id=request.user.id).exists():
            return ForbiddenError("Você não faz parte dessa conversa").to_response()

        # B6: o front envia ?type=messages|events; sem o parâmetro exporta tudo.
        export_type = request.query_params.get('type', 'all')
        if export_type not in ('messages', 'events', 'all'):
            return ValidationError("type deve ser messages, events ou all").to_response()

        messages = Message.objects.none()
        events = Event.objects.none()
        if export_type in ('messages', 'all'):
            messages = Message.objects.filter(conversation_id=conversation_id).order_by('created_at')
        if export_type in ('events', 'all'):
            events = Event.objects.filter(conversation_id=conversation_id).order_by('event_date')

        pdf_buffer = generate_conversation_pdf(messages, events, conversation_id)

        return FileResponse(
            pdf_buffer,
            as_attachment=True,
            filename=f'coparent_{export_type}_{conversation_id}.pdf',
            content_type='application/pdf'
        )

    except Exception as e:
        return handle_exception(e)
