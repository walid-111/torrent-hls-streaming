import os
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from movies.models import Movie


class Command(BaseCommand):
    help = 'Delete movies unwatched for more than 1 month'

    def handle(self, *args, **kwargs):
        cutoff = timezone.now() - timedelta(days=30)
        old_movies = Movie.objects.filter(last_watched__lt=cutoff, file_path__gt='')
        for movie in old_movies:
            if os.path.exists(movie.file_path):
                os.remove(movie.file_path)
            movie.file_path = ''
            movie.save()