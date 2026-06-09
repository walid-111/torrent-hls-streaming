import os
import re
import subprocess
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Movie, Comment
from .services import search_all, start_download, get_playable_file, get_subtitle_text

RANGE_RE = re.compile(r'bytes=(\d+)-(\d*)')


def _video_codec(filepath):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', filepath],
            capture_output=True, timeout=15
        )
        return r.stdout.strip().decode().lower()
    except Exception:
        return ''


def _classify(filepath):
    """
    Returns:
      'native'      → mp4/webm with browser-playable codec → range-serve
      'transcode'   → .mkv or known unplayable codec → live ffmpeg pipe
      'unsupported' → cannot play, cannot transcode meaningfully
      'pending'     → can't determine yet (moov atom not downloaded)
    """
    ext = os.path.splitext(filepath)[1].lower()
    codec = _video_codec(filepath)

    if not codec:
        # ffprobe failed — usually moov atom not yet downloaded
        return 'pending'

    if ext in ('.mp4', '.webm', '.m4v') and codec in ('h264', 'vp8', 'vp9', 'av1'):
        return 'native'
    if ext == '.mkv' or codec in ('mpeg4', 'msmpeg4v3', 'wmv3', 'vc1'):
        return 'transcode'
    return 'unsupported'


def _range_response(request, filepath):
    """Serve a file with HTTP Range support. Enables seeking + satisfies Firefox ORB."""
    file_size = os.path.getsize(filepath)
    range_header = request.META.get('HTTP_RANGE', '')
    m = RANGE_RE.match(range_header)

    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1
        status = 206
    else:
        start, end, length, status = 0, file_size - 1, file_size, 200

    def chunks():
        with open(filepath, 'rb') as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                data = f.read(min(65536, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    resp = StreamingHttpResponse(chunks(), status=status, content_type='video/mp4')
    resp['Accept-Ranges'] = 'bytes'
    resp['Content-Length'] = str(length)
    if status == 206:
        resp['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    return resp


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
    if not filepath:
        return Response({'error': 'File not ready'}, status=404)

    kind = _classify(filepath)

    if kind == 'native':
        return _range_response(request, filepath)

    if kind == 'unsupported' or kind == 'pending':
        return Response({'error': 'Not ready'}, status=404)

    # mkv → live fragmented-mp4 transcode pipe
    cmd = [
        'ffmpeg',
        '-fflags', '+genpts+igndts',
        '-err_detect', 'ignore_err',
        '-i', filepath,
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-c:a', 'aac', '-ac', '2', '-b:a', '128k',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof+faststart',
        '-frag_duration', '1000000',
        '-f', 'mp4',
        '-loglevel', 'error',
        'pipe:1',
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, bufsize=0)

    def stream():
        try:
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                process.kill()
            except Exception:
                pass

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
        return Response({'ready': False, 'status': 'downloading'})

    filepath = None
    if movie.file_path and os.path.exists(movie.file_path):
        filepath = movie.file_path
    else:
        f = get_playable_file(movie.folder)
        if f and os.path.exists(f) and os.path.getsize(f) > 5 * 1024 * 1024:
            filepath = f

    if not filepath:
        return Response({'ready': False, 'status': 'downloading'})

    kind = _classify(filepath)
    if kind == 'pending':
        # File exists but moov atom not yet downloaded — keep waiting
        return Response({'ready': False, 'status': 'downloading'})
    if kind == 'unsupported':
        return Response({'ready': False, 'status': 'unsupported'})

    return Response({'ready': True, 'status': 'ready'})


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