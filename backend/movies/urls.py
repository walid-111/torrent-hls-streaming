from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search),
    path('start/', views.start_stream),
    path('stream/<int:movie_id>/', views.stream_video),
    path('<int:movie_id>/comments/', views.movie_comments),
    path('status/<int:movie_id>/', views.movie_status),
    path('<int:movie_id>/subtitles/', views.get_subtitles),
]