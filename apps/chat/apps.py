from django.apps import AppConfig


class ChatConfig(AppConfig):
    name = 'apps.chat'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """Import signals when app is ready"""
        import apps.chat.signals  # noqa
        from core.firebase_helpers import initialize_firebase
        initialize_firebase()
