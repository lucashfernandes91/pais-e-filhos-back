"""
Centralized error handling for CoParent API
"""

from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


class ApiError:
    """Standard API error response"""

    def __init__(self, code: str, message: str, details: str = None, status_code: int = 400):
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code

    def to_response(self):
        data = {
            'error': {
                'code': self.code,
                'message': self.message,
            }
        }
        if self.details:
            data['error']['details'] = self.details

        return Response(data, status=self.status_code)


# Common errors
class ValidationError(ApiError):
    def __init__(self, message: str = "Dados inválidos"):
        super().__init__(
            code='VALIDATION_ERROR',
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST
        )


class NotFoundError(ApiError):
    def __init__(self, resource: str = "Recurso"):
        super().__init__(
            code='NOT_FOUND',
            message=f"{resource} não encontrado",
            status_code=status.HTTP_404_NOT_FOUND
        )


class UnauthorizedError(ApiError):
    def __init__(self, message: str = "Não autorizado"):
        super().__init__(
            code='UNAUTHORIZED',
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class ForbiddenError(ApiError):
    def __init__(self, message: str = "Acesso negado"):
        super().__init__(
            code='FORBIDDEN',
            message=message,
            status_code=status.HTTP_403_FORBIDDEN
        )


class ConflictError(ApiError):
    def __init__(self, message: str = "Conflito de dados"):
        super().__init__(
            code='CONFLICT',
            message=message,
            status_code=status.HTTP_409_CONFLICT
        )


class ServerError(ApiError):
    def __init__(self, message: str = "Erro no servidor"):
        super().__init__(
            code='SERVER_ERROR',
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class RateLimitError(ApiError):
    def __init__(self):
        super().__init__(
            code='RATE_LIMIT',
            message="Muitas requisições. Tente novamente em alguns segundos",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )


def handle_exception(exception: Exception):
    """Convert exception to API error response"""
    logger.error(f"Exception: {type(exception).__name__}: {str(exception)}")

    if isinstance(exception, ValueError):
        return ValidationError(str(exception)).to_response()
    elif isinstance(exception, PermissionError):
        return ForbiddenError().to_response()
    else:
        return ServerError().to_response()
