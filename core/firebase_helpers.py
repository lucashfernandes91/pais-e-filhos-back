"""
Firebase Cloud Messaging helper functions
"""

import firebase_admin
from firebase_admin import credentials, messaging
import os
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase (only if credentials file exists)
# For now, we'll mock the functionality
FIREBASE_INITIALIZED = False

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    global FIREBASE_INITIALIZED

    try:
        # Try to load service account key
        cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', None)
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            FIREBASE_INITIALIZED = True
            logger.info("Firebase initialized successfully")
        else:
            logger.warning("Firebase credentials not found - running in mock mode")
            FIREBASE_INITIALIZED = False
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        FIREBASE_INITIALIZED = False

def send_push_notification(device_token, title, body):
    """
    Send push notification via Firebase Cloud Messaging

    Args:
        device_token: Firebase device token
        title: Notification title
        body: Notification body

    Returns:
        bool: Success status
    """
    if not FIREBASE_INITIALIZED:
        logger.warning(f"Firebase not initialized - skipping notification to {device_token}")
        return False

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=device_token,
        )
        response = messaging.send(message)
        logger.info(f"Notification sent: {response}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return False

def send_message_notification(message_obj):
    """
    Send notification when a new message is created

    Args:
        message_obj: Message instance
    """
    try:
        conversation = message_obj.conversation
        sender = message_obj.sender

        # Get all participants except sender
        recipients = conversation.participants.exclude(id=sender.id)

        title = f"Mensagem de {sender.first_name or sender.username}"
        body = message_obj.content[:100]  # First 100 chars

        # Send notification to each recipient
        for recipient in recipients:
            try:
                # Always create notification record (offline-first)
                from apps.chat.models import Notification
                Notification.objects.create(
                    recipient=recipient,
                    title=title,
                    body=body
                )

                # Try to send via Firebase (if available)
                try:
                    device_token = recipient.device_token.token
                    send_push_notification(device_token, title, body)
                except Exception as e:
                    logger.debug(f"Firebase push for {recipient.username} failed: {e}")
            except Exception as e:
                logger.warning(f"Could not create notification for {recipient.username}: {e}")

    except Exception as e:
        logger.error(f"Error in send_message_notification: {e}")

def send_event_notification(event_obj):
    """
    Send notification when a new event is created

    Args:
        event_obj: Event instance
    """
    try:
        conversation = event_obj.conversation
        creator = event_obj.created_by

        # Get all participants except creator
        recipients = conversation.participants.exclude(id=creator.id)

        title = f"Novo compromisso: {event_obj.title}"
        body = f"Tipo: {event_obj.get_event_type_display()}"

        # Send notification to each recipient
        for recipient in recipients:
            try:
                # Always create notification record (offline-first)
                from apps.chat.models import Notification
                Notification.objects.create(
                    recipient=recipient,
                    title=title,
                    body=body
                )

                # Try to send via Firebase (if available)
                try:
                    device_token = recipient.device_token.token
                    send_push_notification(device_token, title, body)
                except Exception as e:
                    logger.debug(f"Firebase push for {recipient.username} failed: {e}")
            except Exception as e:
                logger.warning(f"Could not create event notification for {recipient.username}: {e}")

    except Exception as e:
        logger.error(f"Error in send_event_notification: {e}")
