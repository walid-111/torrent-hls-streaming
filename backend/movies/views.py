import os
import re
import time
from django.http import HttpResponse, FileResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from .models import Movie, Comment
from . import hls
from .services import search_all, start_download, get_download, get_subtitle_text


def _get_range(request):
    range_header = request.META.get('HTTP_RANGE', '')
    m = re.match(r'bytes=(?P<start>\d+)-(?P<end>\d+)?', range_header)
    if m:
        start = int(m.group('start'))
        end = int(m.group('end')) if m.group('end') else None
        return start, end
    return 0, None


def _wait_for_range(dl, start, end, timeout=60):
    # block until these bytes are really downloaded (sparse file = zeros where pieces are missing)
    if dl is None:
        return True
    dl.want_range(start, end)
    deadline = time.time() + timeout
    while not dl.has_range(start, end):
        if dl.dead or time.time() > deadline:
            return False
        time.sleep(0.2)
    return True


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
    if hls.has_failed(movie.id):
        hls.remove(movie.id)  # try again from scratch
    start_download(magnet, movie.id)
    return Response({'movie_id': movie.id})


@api_view(['GET'])
@permission_classes([AllowAny])
def raw_video(request, movie_id):
    # only for our own ffmpeg (signed token), gives the video bytes once they are downloaded
    if not hls.check_raw_token(request.GET.get('token', ''), movie_id):
        return Response({'error': 'Forbidden'}, status=403)
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    filepath, size, dl = get_download(movie)
    if not filepath:
        return Response({'error': 'Not downloading'}, status=503)
    start, end = _get_range(request)
    if start >= size:
        resp = HttpResponse(status=416)
        resp['Content-Range'] = f'bytes */{size}'
        return resp
    end = size - 1 if end is None else min(end, size - 1)

    def chunks():
        # send the range piece by piece, waiting for each part to be downloaded
        # (ffmpeg takes a short answer as the end of the file, so we cant just send what we have)
        pos = start
        while pos <= end:
            stop = min(pos + 256 * 1024, end + 1)
            data = None
            # far ahead of the download (ex: mp4 index at the end of the file): get it over http right away
            if dl and not dl.has_range(pos, stop - 1) and pos > dl.downloaded_until() + 4 * 1024 * 1024:
                data = dl.fetch_http(pos, stop - 1)
            if data is None:
                if not _wait_for_range(dl, pos, stop - 1, timeout=600):
                    return
                with open(filepath, 'rb') as f:
                    f.seek(pos)
                    data = f.read(stop - pos)
            yield data
            pos = stop

    resp = StreamingHttpResponse(chunks(), status=206, content_type='video/mp4')
    resp['Content-Range'] = f'bytes {start}-{end}/{size}'
    resp['Content-Length'] = str(end - start + 1)
    resp['Accept-Ranges'] = 'bytes'
    return resp


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def hls_file(request, movie_id, name):
    if not hls.FILE_RE.match(name):
        return Response({'error': 'Not found'}, status=404)
    path = os.path.join(hls.folder(movie_id), name)
    if not os.path.exists(path):
        return Response({'error': 'Not found'}, status=404)
    if name.endswith('.m3u8'):
        resp = FileResponse(open(path, 'rb'), content_type='application/vnd.apple.mpegurl')
        resp['Cache-Control'] = 'no-cache'  # playlist changes while ffmpeg runs
    else:
        resp = FileResponse(open(path, 'rb'), content_type='video/mp2t')
    return resp


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def movie_status(request, movie_id):
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return Response({'ready': False})

    filepath, size, dl = get_download(movie)
    if not filepath and not hls.is_complete(movie_id):
        return Response({'ready': False})
    if (dl and dl.dead) or hls.has_failed(movie_id):
        return Response({'ready': False, 'failed': True})

    hls.start(movie_id)
    # 2 segments = enough buffer to start playing
    ready = hls.is_complete(movie_id) or hls.segment_count(movie_id) >= 2
    progress = None
    if dl and not dl.done:
        progress = round(dl.handle.file_progress()[dl.index] * 100 / dl.size)
    return Response({'ready': ready, 'progress': progress})


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