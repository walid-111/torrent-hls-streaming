from django.urls import path
from . import views

urlpatterns = [
    path('users/', views.users_list),
    path('users/<int:pk>/', views.user_detail),
    path('movies/', views.movies_list),
    path('movies/<int:pk>/', views.movie_detail),
    path('movies/<int:movie_id>/comments/', views.movie_comments),
    path('comments/', views.comments_list),
    path('comments/<int:pk>/', views.comment_detail),
]