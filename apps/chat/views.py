from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from django.http import FileResponse
from django.utils import timezone
from .models import Message, Conversation, Event, MessageRead, DeviceToken, Notification, Child, UserProfile
from .serializers import MessageSerializer, EventSerializer, MessageDetailSerializer, DeviceTokenSerializer, NotificationSerializer, ChildSerializer
from django.utils import timezone
from core.pdf_generator import generate_conversation_pdf
from core.error_handler import ValidationError, NotFoundError, ForbiddenError, ServerError, handle_exception
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import date


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

        if not email:
            return ValidationError("Email \u00e9 obrigat\u00f3rio").to_response()

        try:
            birth_date = date.fromisoformat(birth_date_value)
        except ValueError:
            return ValidationError("Data de nascimento inv\u00e1lida").to_response()

        if birth_date > date.today():
            return ValidationError("Data de nascimento n\u00e3o pode estar no futuro").to_response()

        if not password or len(password) < 8:
            return ValidationError("Senha deve ter pelo menos 8 caracteres").to_response()

        if User.objects.filter(username=username).exists():
            return ValidationError("Nome de usu\u00e1rio j\u00e1 existe").to_response()

        if email and User.objects.filter(email=email).exists():
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
            })

        # PUT
        first_name = request.data.get('first_name', user.first_name)
        last_name = request.data.get('last_name', user.last_name)
        email = request.data.get('email', user.email)

        if email and email != user.email:
            if User.objects.filter(email=email).exclude(id=user.id).exists():
                return ValidationError("Email j\u00e1 cadastrado por outro usu\u00e1rio").to_response()

        user.first_name = first_name
        user.last_name = last_name
        user.email = email or ''
        user.save()

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
        return Response(result)
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
        if request.user not in conversation.participants.all():
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

        if request.user not in conversation.participants.all():
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

        if request.user not in conversation.participants.all():
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
            return ValidationError("Data de nascimento Ã© obrigatÃ³ria").to_response()

        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        if request.user not in conversation.participants.all():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        child = Child.objects.create(
            conversation=conversation,
            created_by=request.user,
            name=name.strip(),
            birth_date=birth_date,
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

        if request.user not in child.conversation.participants.all():
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

        if request.user not in child.conversation.participants.all():
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
        if request.user not in conversation.participants.all():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Get messages
        messages = Message.objects.filter(
            conversation_id=conversation_id
        ).order_by('created_at')[:100]  # Limit to 100 recent messages

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
        if request.user not in message.conversation.participants.all():
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
        if request.user not in message.conversation.participants.all():
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
            return ValidationError("Data do evento Ã© obrigatÃ³ria").to_response()

        if not event_type:
            return ValidationError("Tipo de evento Ã© obrigatÃ³rio").to_response()

        # Verify conversation exists
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return NotFoundError("Conversa").to_response()

        # Check authorization
        if request.user not in conversation.participants.all():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Create event
        event = Event.objects.create(
            conversation=conversation,
            created_by=request.user,
            title=title.strip(),
            event_date=event_date,
            event_date_end=event_date_end,
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
        if request.user not in conversation.participants.all():
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
        if request.user not in event.conversation.participants.all():
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

        if request.user not in event.conversation.participants.all():
            return ForbiddenError("Voc\u00ea n\u00e3o faz parte dessa conversa").to_response()

        title = request.data.get('title', event.title)
        event_date = request.data.get('event_date', None)
        event_date_end = request.data.get('event_date_end', event.event_date_end)
        event_type = request.data.get('event_type', event.event_type)
        notes = request.data.get('notes', event.notes)

        if title and len(title.strip()) == 0:
            return ValidationError("T\u00edtulo n\u00e3o pode estar vazio").to_response()

        event.title = title.strip() if title else event.title
        if event_date:
            event.event_date = event_date
        event.event_date_end = event_date_end
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

        # Register device token
        device, _ = DeviceToken.objects.update_or_create(
            user=request.user,
            defaults={'token': token.strip()}
        )
        return Response({'status': 'ok', 'token_id': device.id})

    except Exception as e:
        return handle_exception(e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_notifications(request):
    try:
        notifications = Notification.objects.filter(
            recipient=request.user
        ).order_by('-sent_at')[:50]

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
        if request.user not in conversation.participants.all():
            return ForbiddenError("VocÃª nÃ£o faz parte dessa conversa").to_response()

        # Get messages and events
        messages = Message.objects.filter(conversation_id=conversation_id).order_by('created_at')
        events = Event.objects.filter(conversation_id=conversation_id).order_by('event_date')

        # Generate PDF
        pdf_buffer = generate_conversation_pdf(messages, events, conversation_id)

        # Return as file download
        return FileResponse(
            pdf_buffer,
            as_attachment=True,
            filename=f'coparent_conversation_{conversation_id}.pdf',
            content_type='application/pdf'
        )

    except Exception as e:
        return handle_exception(e)
