from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register),
    path('login/', views.login_view),
    path('logout/', views.logout_view),
    path('profile/', views.profile),
    path('auth/42/', views.auth_42),
    path('auth/42/callback/', views.auth_42_callback),
    path('auth/github/', views.auth_github),
    path('auth/github/callback/', views.auth_github_callback),
    path('password-reset/', views.password_reset_request),
    path('password-reset/confirm/', views.password_reset_confirm),
]