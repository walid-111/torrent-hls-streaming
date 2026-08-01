import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')

import os
import threading
import time
import subprocess
import requests
import re
import libtorrent as lt
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

DOWNLOAD_PATH = '/app/media/videos'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

session = lt.session({'listen_interfaces': '0.0.0.0:6881', 'enable_dht': True})


@lru_cache(maxsize=2000)
def _tmdb(title):
    # rating (/10), cast, director and producer from TMDB, cached so we dont ask twice for the same title
    key = os.getenv('TMDB_API_KEY')
    if not key:
        return None, None
    try:
        results = requests.get(
            'https://api.themoviedb.org/3/search/movie',
            params={'api_key': key, 'query': title},
            timeout=3
        ).json().get('results', [])
        if not results:
            return None, None
        movie = results[0]
        credits = requests.get(
            f"https://api.themoviedb.org/3/movie/{movie['id']}/credits",
            params={'api_key': key},
            timeout=3
        ).json()
        cast = [c['name'] for c in credits.get('cast', [])[:5]]

        director = None
        producer = None
        for c in credits.get('crew', []):
            if c['job'] == 'Director':
                director = c['name']
            if c['job'] == 'Producer':
                producer = c['name']
        return movie.get('vote_average') or None, {'director': director, 'producer': producer, 'cast': cast}
    except Exception:
        return None, None


def search_archive(query, page=1, min_year=None, min_rating=None):
    # Search public domain feature films on archive.org (only mp4 so the browser can play most of them directly)
    q = "collection:(feature_films) AND mediatype:(movies) AND format:(MPEG4)"
    if query:
        q += f" AND title:({query})"
    if min_year:
        q += f" AND year:[{int(min_year)} TO 9999]"

    try:
        docs = requests.get('https://archive.org/advancedsearch.php', params={
            'q': q,
            'fl[]': ['identifier', 'title', 'year', 'avg_rating', 'description'],
            'sort[]': 'downloads desc',
            'output': 'json',
            'rows': 20,
            'page': page,
        }, timeout=10).json().get('response', {}).get('docs', [])
    except Exception:
        return []

    # TMDB calls in parallel, doing them one by one made the search really slow
    with ThreadPoolExecutor(max_workers=10) as pool:
        tmdb = list(pool.map(lambda d: _tmdb(d.get('title', '')), docs))

    results = []
    for item, (tmdb_rating, casting) in zip(docs, tmdb):
        ident = item.get('identifier')
        # TMDB rating is /10, archive.org one is /5
        rating = tmdb_rating
        if not rating and item.get('avg_rating'):
            rating = round(float(item['avg_rating']) * 2, 1)
        if min_rating and (not rating or float(rating) < float(min_rating)):
            continue
        summary = item.get('description', '')
        if isinstance(summary, list):
            summary = ' '.join(summary)
        results.append({
            'title': item.get('title', ''),
            'magnet': f"https://archive.org/download/{ident}/{ident}_archive.torrent",
            'cover': f"https://archive.org/services/img/{ident}",
            'year': item.get('year'),
            'rating': rating,
            'summary': summary,
            'casting': casting,
            'source': 'archive.org',
        })
    return results


def search_all(query, page=1, min_year=None, min_rating=None):
    if page > 20:
        return []
    results = search_archive(query, page, min_year, min_rating)
    if query:
        results.sort(key=lambda r: r['title'].lower())
    return results


def _get_duration(filepath):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', filepath],
            capture_output=True, timeout=10
        )
        return int(float(r.stdout.strip()))
    except:
        return None


def _load_torrent_info(torrent_url):
    params = lt.add_torrent_params()
    if torrent_url.startswith('magnet:'):
        params = lt.parse_magnet_uri(torrent_url)
    else:
        try:
            data = requests.get(torrent_url, timeout=10).content
            params.ti = lt.torrent_info(lt.bdecode(data))
        except Exception:
            return None, None

    params.save_path = DOWNLOAD_PATH
    params.storage_mode = lt.storage_mode_t.storage_mode_sparse
    # download pieces in order, so the start of the movie is ready first
    params.flags |= lt.torrent_flags.sequential_download
    handle = session.add_torrent(params)

    # magnet links need to fetch the metadata from peers first
    for _ in range(30):
        if handle.status().has_metadata:
            return handle, handle.torrent_file()
        time.sleep(1)
    try: session.remove_torrent(handle)
    except: pass
    return None, None


class Download:
    """
    One movie being downloaded. Keeps which file of the torrent is the video,
    so we can tell which bytes of that file are really on disk.
    (files are sparse: the file size on disk means nothing, missing parts are just zeros)
    """

    def __init__(self, handle, info, file_index):
        self.handle = handle
        self.info = info
        files = info.files()
        self.offset = files.file_offset(file_index)
        self.size = files.file_size(file_index)
        self.path = os.path.join(DOWNLOAD_PATH, files.file_path(file_index))
        self.piece_len = info.piece_length()
        self.dead = False
        self.done = False

    def _pieces(self, start, end):
        # pieces of the torrent covering bytes [start, end] of the video file
        first = (self.offset + start) // self.piece_len
        last = (self.offset + min(end, self.size - 1)) // self.piece_len
        return range(first, last + 1)

    def has_range(self, start, end):
        if self.done:
            return True
        return all(self.handle.have_piece(p) for p in self._pieces(start, end))

    def want_range(self, start, end):
        # ask libtorrent to get these pieces first (used when ffmpeg jumps somewhere, like the moov atom at the end)
        for i, p in enumerate(self._pieces(start, end)):
            if not self.handle.have_piece(p):
                self.handle.set_piece_deadline(p, 500 + i * 100)


downloads = {}  # movie_id -> Download


def _pick_video_file(info):
    files = info.files()
    for ext in ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.mpeg', '.mpg']:
        best = None
        for i in range(info.num_files()):
            if files.file_path(i).lower().endswith(ext):
                if best is None or files.file_size(i) > files.file_size(best):
                    best = i
        if best is not None:
            return best
    return None


def start_download(torrent_url, movie_id):
    from .models import Movie

    movie = Movie.objects.filter(id=movie_id).first()
    if movie and movie.file_path and os.path.exists(movie.file_path):
        return  # already fully downloaded

    current = downloads.get(movie_id)
    if current and not current.dead:
        return
    if current:
        try: session.remove_torrent(current.handle)
        except: pass
        downloads.pop(movie_id, None)

    handle, info = _load_torrent_info(torrent_url)
    if not handle or not info:
        print(f"Movie {movie_id}: failed to load torrent", flush=True)
        return

    target = _pick_video_file(info)
    if target is None:
        print(f"Movie {movie_id}: no video file in torrent", flush=True)
        try: session.remove_torrent(handle)
        except: pass
        return

    # only download the video file (0 = skip). normal priority (4) on purpose:
    # with 7 libtorrent stops downloading in order, pieces come randomly
    priorities = [0] * info.num_files()
    priorities[target] = 4
    handle.prioritize_files(priorities)

    dl = Download(handle, info, target)
    # start of the file first for playback, and the end because a lot of mp4 have their index (moov atom) there
    dl.want_range(0, 4 * 1024 * 1024)
    dl.want_range(max(0, dl.size - 4 * 1024 * 1024), dl.size - 1)
    downloads[movie_id] = dl
    Movie.objects.filter(id=movie_id).update(folder=info.name())

    def monitor():
        from django.utils import timezone
        stuck_seconds = 0
        last_done = 0
        while True:
            s = handle.status()
            done = handle.file_progress()[target]
            if done >= dl.size:
                break
            print(f"Movie {movie_id}: {done * 100 / dl.size:.1f}% ({s.download_rate / 1000:.0f} kB/s, {s.num_peers} peers)", flush=True)
            stuck_seconds = stuck_seconds + 3 if done == last_done else 0
            last_done = done
            if stuck_seconds >= 120:
                print(f"Movie {movie_id}: nothing downloaded for 2 min, dead torrent", flush=True)
                dl.dead = True
                return
            time.sleep(3)

        dl.done = True
        Movie.objects.filter(id=movie_id).update(
            file_path=dl.path, length=_get_duration(dl.path), last_watched=timezone.now()
        )
        print(f"Movie {movie_id}: complete", flush=True)

    threading.Thread(target=monitor, daemon=True).start()


def get_download(movie):
    """Returns (path, size, download or None). download is None when the file is already complete on disk."""
    if movie.file_path and os.path.exists(movie.file_path):
        return movie.file_path, os.path.getsize(movie.file_path), None
    dl = downloads.get(movie.id)
    if dl:
        return dl.path, dl.size, dl
    return None, None, None


def _srt_to_vtt(srt_text):
    def fix(m):
        h, mn, s, ms = m.group(1), m.group(2), m.group(3), m.group(4)
        ms = (ms + '000')[:3]
        return f"{h}:{mn}:{s}.{ms}"
    lines = ['WEBVTT', '']
    for line in srt_text.splitlines():
        if '-->' in line:
            line = re.sub(r'(\d{2}):(\d{2}):(\d{2})[,.](\d+)', fix, line)
        lines.append(line)
    return '\n'.join(lines)


def get_subtitle_text(identifier):
    # Get subtitles from archive.org if available, convert to VTT
    if not identifier:
        return None
    url = f"https://archive.org/download/{identifier}/{identifier}.asr.srt"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200 or not r.text.strip():
            return None
        return _srt_to_vtt(r.text)
    except:
        return None