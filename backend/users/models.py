from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    preferred_language = models.CharField(max_length=10, default='en')
    fortytwo_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    github_id = models.CharField(max_length=50, null=True, blank=True, unique=True)

    def __str__(self):
        return self.username