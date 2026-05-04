from django.contrib import admin
from .models import Conversation, Message, Event, MessageRead, DeviceToken, Notification, Child

admin.site.register(Conversation)
admin.site.register(Message)
admin.site.register(Event)
admin.site.register(MessageRead)
admin.site.register(DeviceToken)
admin.site.register(Notification)
admin.site.register(Child)