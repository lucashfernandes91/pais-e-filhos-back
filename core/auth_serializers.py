from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Authenticate using either the configured username field or an email address."""

    def validate(self, attrs):
        identifier = attrs.get(self.username_field, "").strip()

        if "@" in identifier:
            user_model = get_user_model()
            try:
                user = user_model.objects.get(email__iexact=identifier)
            except (user_model.DoesNotExist, user_model.MultipleObjectsReturned):
                pass
            else:
                attrs[self.username_field] = getattr(user, user_model.USERNAME_FIELD)

        data = super().validate(attrs)
        data["username"] = self.user.get_username()
        return data
