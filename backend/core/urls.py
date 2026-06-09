from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def not_found(request, *args, **kwargs):
    return JsonResponse({'error': 'Not found'}, status=404)


urlpatterns = [
    path('oauth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('oauth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('internal/auth/', include('users.urls')),
    path('internal/movies/', include('movies.urls')),
    path('api/', include('api.urls')),
    re_path(r'^api/.*$', not_found),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)