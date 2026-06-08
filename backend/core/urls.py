from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('api/', include('users.urls')),
    path('api/movies/', include('movies.urls')),
    path('oauth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('oauth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/', include('api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)