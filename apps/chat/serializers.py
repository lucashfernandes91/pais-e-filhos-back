from rest_framework import serializers
from .models import Message, Event, MessageRead, Notification, Conversation, Child

class MessageSerializer(serializers.ModelSerializer):
    sender = serializers.StringRelatedField()
    attachment_url = serializers.SerializerMethodField()
    read_by = serializers.SerializerMethodField()

    def get_attachment_url(self, obj):
        # B2: anexos saem por endpoint autenticado, não por /media/ público.
        if obj.attachment:
            path = f'/api/media/attachments/{obj.id}/'
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(path)
            return path
        return None

    def get_read_by(self, obj):
        # B9: usa a relação (aproveitando prefetch_related da view) em vez
        # de uma query por mensagem.
        return MessageReadSerializer(obj.messageread_set.all(), many=True).data

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'content', 'attachment_url', 'attachment_type', 'created_at', 'read_by']

class MessageReadSerializer(serializers.ModelSerializer):
    reader_name = serializers.CharField(source='reader.username', read_only=True)

    class Meta:
        model = MessageRead
        fields = ['reader_name', 'read_at']

class MessageDetailSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    read_by = serializers.SerializerMethodField()

    def get_read_by(self, obj):
        return MessageReadSerializer(obj.messageread_set.all(), many=True).data

    class Meta:
        model = Message
        fields = ['id', 'content', 'created_at', 'sender', 'sender_name', 'read_by']

class EventSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    conversation = serializers.PrimaryKeyRelatedField(queryset=Conversation.objects.all())

    class Meta:
        model = Event
        fields = ['id', 'conversation', 'title', 'event_date', 'event_date_end', 'event_type', 'notes', 'created_at', 'created_by_name']

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'body', 'sent_at', 'read_at']


class ChildSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    photo_url = serializers.SerializerMethodField()

    def get_photo_url(self, obj):
        # B2: fotos de crianças saem por endpoint autenticado.
        if obj.photo:
            path = f'/api/media/children/{obj.id}/photo/'
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(path)
            return path
        return None

    class Meta:
        model = Child
        fields = ['id', 'name', 'birth_date', 'photo_url', 'has_custody', 'conversation', 'created_by_name', 'created_at']
