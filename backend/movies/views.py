import os
import re
import time
import mimetypes
import subprocess
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Movie, Comment
from .services import search_all, start_download, get_playable_file, get_subtitle_text


BUFF_SIZE = 10 * 1024 * 1024


def _file_is_playable(filepath):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name',
             '-of', 'csv=p=0', filepath],
            capture_output=True, timeout=10
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _get_range(request):
    range_header = request.META.get('HTTP_RANGE', '')
    m = re.match(r'bytes=(?P<start>\d+)-(?P<end>\d+)?', range_header)
    if m:
        start = int(m.group('start'))
        end = int(m.group('end')) if m.group('end') else None
        return start, end
    return 0, None


def _stream_ffmpeg(filepath):
    cmd = [
        'ffmpeg', '-re',
        '-i', filepath,
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-c:a', 'aac', '-ac', '2', '-b:a', '128k',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
        '-frag_duration', '2000000',
        '-f', 'mp4', '-loglevel', 'error',
        'pipe:1',
    ]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
    )

    buffered = bytearray()
    deadline = time.time() + 30
    found_ftyp = False

    while time.time() < deadline:
        chunk = process.stdout.read(4096)
        if not chunk:
            if process.poll() is not None:
                err = process.stderr.read().decode('utf-8', errors='replace')
                print(f"ffmpeg pipe died: {err}", flush=True)
                break
            time.sleep(0.05)
            continue
        buffered.extend(chunk)

        if not found_ftyp and len(buffered) >= 8:
            if b'ftyp' in buffered[:16]:
                found_ftyp = True

        if found_ftyp and len(buffered) >= 65536:
            break

    if not found_ftyp or len(buffered) < 1024:
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


def _serve_file(filepath, start, end=None):
    file_size_on_disk = os.path.getsize(filepath)

    if start >= file_size_on_disk:
        deadline = time.time() + 30
        while time.time() < deadline:
            file_size_on_disk = os.path.getsize(filepath)
            if start < file_size_on_disk:
                break
            time.sleep(1)
        else:
            start = 0
            file_size_on_disk = os.path.getsize(filepath)

    if end is None:
        end = start + BUFF_SIZE - 1
    end = min(end, file_size_on_disk - 1, start + BUFF_SIZE - 1)
    length = end - start + 1

    with open(filepath, 'rb') as f:
        f.seek(start)
        data = f.read(length)

    resp = HttpResponse(data, status=206, content_type=mimetypes.guess_type(filepath)[0] or 'video/mp4')
    resp['Content-Range'] = f'bytes {start}-{end}/{file_size_on_disk}'
    resp['Accept-Ranges'] = 'bytes'
    resp['Content-Length'] = str(length)
    return resp

def _is_h264(filepath):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_name',
             '-of', 'csv=p=0', filepath],
            capture_output=True, timeout=10
        )
        codec = r.stdout.decode().strip().lower()
        return codec in ('h264', 'hevc', 'h265', 'vp8', 'vp9', 'av1')
    except:
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
    if ext in ('.mkv', '.avi', '.mov', '.mpeg', '.mpg') or not _is_h264(filepath):
        return _stream_ffmpeg(filepath)

    start, end = _get_range(request)
    return _serve_file(filepath, start, end)


def _ffmpeg_can_stream(filepath):
    try:
        r = subprocess.run(
            [
                'ffmpeg', '-v', 'error',
                '-i', filepath,
                '-frames:v', '1',
                '-f', 'null', '-'
            ],
            capture_output=True, timeout=15
        )
        return r.returncode == 0
    except Exception:
        return False


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

    if not filepath or not _file_is_playable(filepath):
        return Response({'ready': False})

    if os.path.getsize(filepath) < 50 * 1024 * 1024:
        return Response({'ready': False})

    if not _ffmpeg_can_stream(filepath):
        return Response({'ready': False})

    return Response({'ready': True})


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