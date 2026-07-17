from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView
from .auth_views import SafeTokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', TokenObtainPairView.as_view()),
    path('api/token/refresh/', SafeTokenRefreshView.as_view()),
    path('api/', include('apps.chat.urls')),
]

# B2: /media/ não é mais servido publicamente — anexos e fotos saem
# pelos endpoints autenticados em apps/chat (api/media/...), em dev e em prod.
