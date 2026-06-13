from django.urls import path
from .views import (
    register_user, user_profile,
    send_message, send_message_with_attachment, list_messages, message_detail, mark_message_read,
    create_event, list_events, delete_event, update_event,
    register_device_token, list_notifications,
    mark_all_notifications_read, delete_all_notifications, mark_notification_read, unread_notifications_count,
    export_conversation_pdf,
    list_children, create_child, update_child, delete_child,
    list_conversations
)

urlpatterns = [
    # Auth
    path('register/', register_user),
    path('profile/', user_profile),

    # Conversations
    path('conversations/', list_conversations),

    # Messages
    path('messages/<int:conversation_id>/', list_messages),
    path('messages/<int:message_id>/detail/', message_detail),
    path('messages/<int:message_id>/read/', mark_message_read),
    path('send-message/', send_message),
    path('send-message-attachment/', send_message_with_attachment),

    # Events
    path('events/', create_event),
    path('events/<int:conversation_id>/', list_events),
    path('events/<int:event_id>/delete/', delete_event),
    path('events/<int:event_id>/update/', update_event),

    # Notifications
    path('device-token/', register_device_token),
    path('notifications/', list_notifications),
    path('notifications/mark-all-read/', mark_all_notifications_read),
    path('notifications/delete-all/', delete_all_notifications),
    path('notifications/<int:notification_id>/read/', mark_notification_read),
    path('notifications/unread-count/', unread_notifications_count),

    # Export
    path('export/pdf/<int:conversation_id>/', export_conversation_pdf),

    # Children
    path('children/<int:conversation_id>/', list_children),
    path('children/', create_child),
    path('children/<int:child_id>/update/', update_child),
    path('children/<int:child_id>/delete/', delete_child),
]
