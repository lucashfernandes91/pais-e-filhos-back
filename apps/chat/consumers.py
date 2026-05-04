import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth.models import User
from .models import Conversation, Message


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.user = None

        # Extract token from query string
        query_string = self.scope.get('query_string', b'').decode()
        token = None

        if 'token=' in query_string:
            token = query_string.split('token=')[1].split('&')[0]

        if not token:
            await self.close(code=4001)
            return

        # Validate JWT
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            self.user = await self._get_user(user_id)
        except (InvalidToken, TokenError):
            await self.close(code=4001)
            return

        # Verify user is participant
        is_participant = await self._verify_conversation_access(self.user, self.conversation_id)
        if not is_participant:
            await self.close(code=4003)
            return

        # Join room group
        self.room_group_name = f'chat_{self.conversation_id}'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        if self.user and hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)

            # Handle typing event
            if data.get('type') == 'typing':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'typing_indicator',
                        'sender_id': self.user.id,
                        'sender_username': self.user.username,
                        'is_typing': data.get('is_typing', True),
                    }
                )
                return

            content = data.get('content', '').strip()

            # Validate content
            if not content:
                await self.send(text_data=json.dumps({
                    'error': 'Content cannot be empty'
                }))
                return

            if len(content) > 5000:
                await self.send(text_data=json.dumps({
                    'error': 'Content too long (max 5000 chars)'
                }))
                return

            # Save message to database
            message = await self._create_message(
                conversation_id=self.conversation_id,
                sender=self.user,
                content=content
            )

            # Broadcast to group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message_id': message.id,
                    'content': message.content,
                    'sender_id': self.user.id,
                    'sender_username': self.user.username,
                    'created_at': message.created_at.isoformat(),
                }
            )
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON'
            }))

    async def chat_message(self, event):
        # Handler for group_send
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message_id': event['message_id'],
            'content': event['content'],
            'sender_id': event['sender_id'],
            'sender_username': event['sender_username'],
            'created_at': event['created_at'],
        }))

    async def typing_indicator(self, event):
        # Don't send typing indicator back to the sender
        if self.user and event['sender_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'sender_id': event['sender_id'],
                'sender_username': event['sender_username'],
                'is_typing': event['is_typing'],
            }))

    @database_sync_to_async
    def _get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def _verify_conversation_access(self, user, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            return conversation.participants.filter(id=user.id).exists()
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def _create_message(self, conversation_id, sender, content):
        conversation = Conversation.objects.get(id=conversation_id)
        return Message.objects.create(
            conversation=conversation,
            sender=sender,
            content=content
        )
