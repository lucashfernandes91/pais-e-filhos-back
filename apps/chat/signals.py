"""
Django signals for CoParent app
Handles notifications when messages/events are created
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Message, Event
from core.firebase_helpers import send_message_notification, send_event_notification
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Message)
def notify_on_new_message(sender, instance, created, **kwargs):
    """
    Signal handler: Send notification when a new message is created

    Args:
        sender: Message model
        instance: Message instance
        created: Boolean - True if just created
        **kwargs: Extra arguments
    """
    if created:
        logger.info(f"New message created (ID: {instance.id}) - sending notifications")
        try:
            send_message_notification(instance)
        except Exception as e:
            logger.error(f"Error sending message notifications: {e}")

@receiver(post_save, sender=Event)
def notify_on_new_event(sender, instance, created, **kwargs):
    """
    Signal handler: Send notification when a new event is created

    Args:
        sender: Event model
        instance: Event instance
        created: Boolean - True if just created
        **kwargs: Extra arguments
    """
    if created:
        logger.info(f"New event created (ID: {instance.id}) - sending notifications")
        try:
            send_event_notification(instance)
        except Exception as e:
            logger.error(f"Error sending event notifications: {e}")
