"""
HLS: ffmpeg turns the movie into small .ts segments + a playlist (index.m3u8) while the torrent downloads.
The browser plays the playlist with hls.js and gets new segments as they are created.

ffmpeg doesnt read the file on disk directly (it would read zeros where pieces are missing),
it reads it through /internal/movies/raw/<id>/ which waits for the bytes to be downloaded.
"""
import os
import re
import shutil
import subprocess
import threading
from django.core import signing

HLS_PATH = '/app/media/hls'
BACKEND_URL = os.getenv('BACKEND_INTERNAL_URL', 'http://127.0.0.1:8000')
SEGMENT_TIME = 6
FILE_RE = re.compile(r'^(index\.m3u8|seg_\d{5}\.ts)$')

procs = {}  # movie_id -> ffmpeg process
lock = threading.Lock()


def raw_token(movie_id):
    return signing.dumps(movie_id, salt='hls-raw')


def check_raw_token(token, movie_id):
    try:
        return signing.loads(token, salt='hls-raw', max_age=24 * 3600) == movie_id
    except signing.BadSignature:
        return False


def folder(movie_id):
    return os.path.join(HLS_PATH, str(movie_id))


def _playlist(movie_id):
    try:
        with open(os.path.join(folder(movie_id), 'index.m3u8')) as f:
            return f.read()
    except OSError:
        return ''


def is_complete(movie_id):
    p = procs.get(movie_id)
    if p is not None and p.poll() not in (None, 0):
        return False  # ffmpeg crashed, the playlist may still have ENDLIST but it's incomplete
    return '#EXT-X-ENDLIST' in _playlist(movie_id)


def segment_count(movie_id):
    return _playlist(movie_id).count('#EXTINF')


def is_running(movie_id):
    if movie_id not in procs:
        return False
    p = procs[movie_id]
    return p is None or p.poll() is None  # None = ffprobe still checking the codecs


def has_failed(movie_id):
    p = procs.get(movie_id)
    return p is not None and p.poll() not in (None, 0)


def _codecs(url):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,codec_name', '-of', 'csv=p=0', url],
        capture_output=True, text=True, timeout=600
    )
    video, audio = None, None
    for line in r.stdout.splitlines():
        parts = line.strip().split(',')
        if len(parts) < 2:
            continue
        name, kind = parts[0], parts[1]
        if kind == 'video' and not video:
            video = name
        if kind == 'audio' and not audio:
            audio = name
    return video, audio


def _command(url, out, video, audio):
    cmd = ['ffmpeg', '-loglevel', 'error', '-rw_timeout', str(600 * 1000000), '-i', url,
           '-map', '0:v:0', '-map', '0:a:0?']

    if video == 'h264':
        # already h264: just cut it in segments, no re-encoding, almost instant
        cmd += ['-c:v', 'copy']
    else:
        # anything else gets re-encoded to h264 so every browser can play it (max 720p to keep it fast)
        cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
                '-vf', "scale=-2:'min(720,ih)'",
                '-force_key_frames', f'expr:gte(t,n_forced*{SEGMENT_TIME})']
    cmd += ['-c:a', 'copy'] if audio == 'aac' else ['-c:a', 'aac', '-ac', '2', '-b:a', '128k']

    cmd += ['-f', 'hls',
            '-hls_time', str(SEGMENT_TIME),
            '-hls_list_size', '0',            # keep every segment in the playlist
            '-hls_playlist_type', 'event',    # playlist grows, ENDLIST added at the end
            '-hls_flags', 'temp_file',        # dont list a segment before it's fully written
            '-hls_segment_filename', os.path.join(out, 'seg_%05d.ts'),
            os.path.join(out, 'index.m3u8')]
    return cmd


def start(movie_id):
    with lock:
        if is_running(movie_id) or is_complete(movie_id):
            return
        out = folder(movie_id)
        shutil.rmtree(out, ignore_errors=True)  # leftovers from a run that didnt finish
        os.makedirs(out, exist_ok=True)
        procs[movie_id] = None  # reserved, so a second request doesnt start another ffmpeg

    url = f"{BACKEND_URL}/internal/movies/raw/{movie_id}/?token={raw_token(movie_id)}"

    def run():
        try:
            video, audio = _codecs(url)
            if not video:
                print(f"Movie {movie_id}: ffprobe found no video stream", flush=True)
                procs[movie_id] = subprocess.Popen(['false'])
                return
            print(f"Movie {movie_id}: hls started ({video}/{audio}, {'copy' if video == 'h264' else 'transcode'})", flush=True)
            procs[movie_id] = subprocess.Popen(_command(url, out, video, audio))
        except Exception as e:
            print(f"Movie {movie_id}: hls failed to start: {e}", flush=True)
            procs[movie_id] = subprocess.Popen(['false'])

    threading.Thread(target=run, daemon=True).start()


def remove(movie_id):
    p = procs.pop(movie_id, None)
    if p and p.poll() is None:
        p.kill()
    shutil.rmtree(folder(movie_id), ignore_errors=True)
