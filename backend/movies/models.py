from django.db import models
from users.models import User


class Movie(models.Model):
    title = models.TextField()
    year = models.IntegerField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    cover = models.URLField(blank=True)
    summary = models.TextField(blank=True)
    magnet = models.TextField(unique=True)
    file_path = models.CharField(max_length=500, blank=True)
    length = models.IntegerField(null=True, blank=True)
    last_watched = models.DateTimeField(null=True, blank=True)
    watched_by = models.ManyToManyField(User, blank=True, related_name='watched_movies')
    folder = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return self.title


class Comment(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.author.username} on {self.movie.title}"

class WatchProgress(models.Model):
    # where a user stopped in a movie, for "continue watching"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='progress')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='progress')
    position = models.FloatField(default=0)  # seconds
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'movie')
