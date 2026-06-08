#!/bin/sh
echo "Waiting for PostgreSQL..."
while ! nc -z db 5432; do
  sleep 1
done
echo "PostgreSQL is ready!"
python manage.py migrate
python manage.py cleanup
python manage.py runserver 0.0.0.0:8000