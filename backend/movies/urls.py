from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search),
    path('start/', views.start_stream),
    path('raw/<int:movie_id>/', views.raw_video),
    path('hls/<int:movie_id>/<str:name>', views.hls_file),
    path('<int:movie_id>/comments/', views.movie_comments),
    path('status/<int:movie_id>/', views.movie_status),
    path('<int:movie_id>/subtitles/', views.get_subtitles),
    path('<int:movie_id>/progress/', views.watch_progress),
    path('continue/', views.continue_watching),
]