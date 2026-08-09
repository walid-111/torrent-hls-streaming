import os
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from movies.models import Movie
from movies import hls


class Command(BaseCommand):
    help = 'Delete movies (video + hls segments) unwatched for more than 1 month'

    def handle(self, *args, **kwargs):
        cutoff = timezone.now() - timedelta(days=30)
        old_movies = Movie.objects.filter(last_watched__lt=cutoff)
        for movie in old_movies:
            if movie.file_path and os.path.exists(movie.file_path):
                os.remove(movie.file_path)
            hls.remove(movie.id)
            if movie.file_path:
                movie.file_path = ''
                movie.save()
