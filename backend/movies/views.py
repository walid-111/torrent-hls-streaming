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


def _file_is_playable(filepath):
    """ffprobe must successfully read the file. Means moov atom is present."""
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-show_entries', 'stream=codec_name',
             '-of', 'csv=p=0', filepath],
            capture_output=True, timeout=10
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


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

    if not filepath or not _file_is_playable(filepath):
        return Response({'error': 'Stream not ready'}, status=503)

    ext = os.path.splitext(filepath)[1].lower()
    needs_transcode = ext in ('.mkv', '.avi', '.mov', '.mpeg', '.mpg')

    if needs_transcode:
        return _stream_ffmpeg(filepath)
    else:
        return _stream_file(request, filepath)


def _stream_file(request, filepath):
    """Serve file directly with Range support — seek + duration work perfectly."""
    size = os.path.getsize(filepath)
    ext = os.path.splitext(filepath)[1].lower()
    content_type = 'video/mp4' if ext == '.mp4' else 'video/webm' if ext == '.webm' else 'video/mp4'

    range_header = request.META.get('HTTP_RANGE', '')
    if range_header:
        # Parse Range: bytes=start-end
        try:
            range_val = range_header.strip().replace('bytes=', '')
            parts = range_val.split('-')
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else size - 1
        except:
            start, end = 0, size - 1
    else:
        start, end = 0, size - 1

    end = min(end, size - 1)
    length = end - start + 1
    chunk_size = 1024 * 1024  # 1MB chunks

    def file_iterator():
        with open(filepath, 'rb') as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                yield data
                remaining -= len(data)

    status = 206 if range_header else 200
    resp = StreamingHttpResponse(file_iterator(), status=status, content_type=content_type)
    resp['Content-Length'] = str(length)
    resp['Content-Range'] = f'bytes {start}-{end}/{size}'
    resp['Accept-Ranges'] = 'bytes'
    resp['Cache-Control'] = 'no-cache'
    return resp


def _stream_ffmpeg(filepath):
    """For non-browser-native formats (mkv, avi...), transcode on the fly."""
    cmd = [
        'ffmpeg', '-i', filepath,
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-c:a', 'aac', '-ac', '2', '-b:a', '128k',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
        '-frag_duration', '500000',
        '-f', 'mp4', '-loglevel', 'error', 'pipe:1',
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)

    buffered = bytearray()
    deadline = time.time() + 15
    while len(buffered) < 256 * 1024 and time.time() < deadline:
        chunk = process.stdout.read(65536)
        if not chunk:
            if process.poll() is not None:
                break
            time.sleep(0.1)
            continue
        buffered.extend(chunk)

    if len(buffered) < 1024:
        try: process.kill()
        except: pass
        return Response({'error': 'Stream not ready'}, status=503)

    def stream():
        try:
            yield bytes(buffered)
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            try: process.kill()
            except: pass

    resp = StreamingHttpResponse(stream(), content_type='video/mp4')
    resp['Accept-Ranges'] = 'none'
    resp['Cache-Control'] = 'no-cache'
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def movie_status(request, movie_id):
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return Response({'ready': False})

    filepath = None
    if movie.file_path and os.path.exists(movie.file_path):
        filepath = movie.file_path
    else:
        f = get_playable_file(movie.folder)
        if f and os.path.exists(f):
            filepath = f

    if filepath and _file_is_playable(filepath):
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
            'id': c.id, 'author': c.author.username,
            'content': c.content, 'created_at': c.created_at,
        } for c in comments])

    content = request.data.get('content')
    if not content:
        return Response({'error': 'content required'}, status=400)
    comment = Comment.objects.create(movie=movie, author=request.user, content=content)
    return Response({
        'id': comment.id, 'author': comment.author.username,
        'content': comment.content, 'created_at': comment.created_at,
    }, status=201)