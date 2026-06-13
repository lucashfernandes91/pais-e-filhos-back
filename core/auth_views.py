from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView


class SafeTokenRefreshView(TokenRefreshView):
    """Return an authentication failure when a refresh user was removed."""

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except get_user_model().DoesNotExist:
            return Response(
                {
                    "detail": "Sessao invalida ou usuario nao encontrado.",
                    "code": "user_not_found",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
