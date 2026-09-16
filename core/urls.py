from django.contrib import admin
from django.urls import path, include
from .auth_views import SafeTokenRefreshView
from .auth_views import EmailOrUsernameTokenObtainPairView
from .legal_views import privacy_policy, terms_of_use

urlpatterns = [
    path('privacy', privacy_policy, name='privacy-policy'),
    path('terms', terms_of_use, name='terms-of-use'),
    path('admin/', admin.site.urls),
    path('api/token/', EmailOrUsernameTokenObtainPairView.as_view()),
    path('api/token/refresh/', SafeTokenRefreshView.as_view()),
    path('api/', include('apps.chat.urls')),
]

# B2: /media/ não é mais servido publicamente — anexos e fotos saem
# pelos endpoints autenticados em apps/chat (api/media/...), em dev e em prod.
