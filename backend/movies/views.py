import os
import time
import subprocess
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Movie, Comment
from .services import search_all, start_download, get_playable_file, get_subtitle_text


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search(request):
    query = request.GET.get('q', '')
    page = int(request.GET.get('page', 1))
    min_year = request.GET.get('min_year')
    min_rating = request.GET.get('min_rating')

    results = search_all(query, page, min_year, min_rating)

    watched = set(Movie.objects.filter(watched_by=request.user).values_list('magnet', flat=True))
    for r in results:
        r['watched'] = r['magnet'] in watched
    return Response(results)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_stream(request):
    magnet = request.data.get('magnet')
    title = request.data.get('title', 'Unknown')
    if not magnet:
        return Response({'error': 'magnet required'}, status=400)

    movie, _ = Movie.objects.get_or_create(magnet=magnet, defaults={'title': title})
    movie.watched_by.add(request.user)
    movie.last_watched = timezone.now()
    movie.save()

    start_download(magnet, movie.id)
    return Response({'movie_id': movie.id})


def _needs_reencode(filepath):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', filepath],
            capture_output=True, timeout=10
        )
        return r.stdout.strip().decode().lower() != 'h264'
    except:
        return True


def _ffmpeg_stream(filepath):
    # Always re-encode: ffmpeg reads the source frame by frame from the start,
    # so it never needs the source moov atom. This makes streaming work
    # progressively while the file is still downloading, for any format.
    cmd = [
        'ffmpeg',
        '-i', filepath,
        '-c:v', 'libx264', '-preset', 'ultrafast',
        '-c:a', 'aac',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
        '-f', 'mp4',
        '-loglevel', 'error',
        'pipe:1',
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    first_chunk = b''
    for _ in range(150):
        chunk = process.stdout.read(8192)
        if chunk:
            first_chunk = chunk
            break
        if process.poll() is not None:
            break
        time.sleep(0.1)

    if not first_chunk:
        process.kill()
        return None

    def stream():
        try:
            yield first_chunk
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                yield chunk
        finally:
            process.kill()

    return stream


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stream_video(request, movie_id):
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    filepath = None
    if movie.file_path and os.path.exists(movie.file_path):
        filepath = movie.file_path
    else:
        f = get_playable_file(movie.folder)
        if f and os.path.exists(f):
            filepath = f

    if not filepath or not os.path.exists(filepath):
        return Response({'error': 'File not ready'}, status=404)

    stream = _ffmpeg_stream(filepath)
    if stream is None:
        return Response({'error': 'Stream not ready'}, status=503)

    return StreamingHttpResponse(stream(), content_type='video/mp4')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def movie_status(request, movie_id):
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return Response({'ready': False})

    if movie.file_path and os.path.exists(movie.file_path):
        return Response({'ready': True})

    # Ready as soon as a few MB exist; ffmpeg reads progressively from the start.
    f = get_playable_file(movie.folder)
    if f and os.path.exists(f) and os.path.getsize(f) > 5 * 1024 * 1024:
        return Response({'ready': True})
    return Response({'ready': False})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subtitles(request, movie_id):
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    subs = []
    vtt = get_subtitle_text(movie.folder)
    if vtt:
        subs.append({'lang': 'en', 'content': vtt})

    return Response({'subtitles': subs})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def movie_comments(request, movie_id):
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        comments = movie.comments.order_by('-created_at')
        return Response([{
            'id': c.id,
            'author': c.author.username,
            'content': c.content,
            'created_at': c.created_at,
        } for c in comments])

    content = request.data.get('content')
    if not content:
        return Response({'error': 'content required'}, status=400)
    comment = Comment.objects.create(movie=movie, author=request.user, content=content)
    return Response({
        'id': comment.id,
        'author': comment.author.username,
        'content': comment.content,
        'created_at': comment.created_at,
    }, status=201)