import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')

import os
import threading
import time
import subprocess
import requests
import re
import libtorrent as lt
from bs4 import BeautifulSoup

DOWNLOAD_PATH = '/app/media/videos'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

session = lt.session({'listen_interfaces': '0.0.0.0:6881', 'enable_dht': True})
active_downloads = {}


def _tmdb(title):
    try:
        res = requests.get(
            'https://api.themoviedb.org/3/search/movie',
            params={'api_key': os.getenv('TMDB_API_KEY'), 'query': title},
            timeout=3
        )
        results = res.json().get('results', [])
        if not results:
            return None, None
        movie = results[0]
        credits = requests.get(
            f"https://api.themoviedb.org/3/movie/{movie['id']}/credits",
            params={'api_key': os.getenv('TMDB_API_KEY')},
            timeout=3
        ).json()
        cast = [c['name'] for c in credits.get('cast', [])[:5]]
        crew = credits.get('crew', [])
        director = next((c['name'] for c in crew if c['job'] == 'Director'), None)
        producer = next((c['name'] for c in crew if c['job'] == 'Producer'), None)
        return movie.get('vote_average'), {'director': director, 'producer': producer, 'cast': cast}
    except:
        return None, None


def search_archive(query, page=1, min_year=None, min_rating=None):
    if query:
        q = f"title:({query})+AND+mediatype:(movies)+AND+format:(MPEG4)"
    else:
        q = "collection:(feature_films)+AND+mediatype:(movies)+AND+format:(MPEG4)"
    if min_year:
        q += f"+AND+year:[{min_year}+TO+9999]"

    url = (
        f"https://archive.org/advancedsearch.php?q={q}"
        f"&fl[]=identifier,title,year,avg_rating,description"
        f"&sort[]=downloads+desc&output=json&rows=20&page={page}"
    )
    try:
        docs = requests.get(url, timeout=10).json().get('response', {}).get('docs', [])
    except:
        return []

    results = []
    for item in docs:
        ident = item.get('identifier')
        title = item.get('title', '')
        rating = item.get('avg_rating')
        _, casting = _tmdb(title)
        if not rating:
            rating, _ = _tmdb(title)
        if min_rating and (not rating or float(rating) < float(min_rating)):
            continue
        results.append({
            'title': title,
            'magnet': f"https://archive.org/download/{ident}/{ident}_archive.torrent",
            'cover': f"https://archive.org/services/img/{ident}",
            'year': item.get('year'),
            'rating': rating,
            'summary': item.get('description', ''),
            'casting': casting,
            'source': 'archive.org',
        })
    return results


def search_publicdomain(query):
    base = "https://www.publicdomaintorrents.info"
    cats = ['scifi', 'horror', 'action', 'comedy', 'drama', 'westerns']
    results = []
    seen = set()

    for cat in cats:
        try:
            r = requests.get(f"{base}/nshowcat.html?category={cat}", timeout=8)
            soup = BeautifulSoup(r.text, 'html.parser')
        except:
            continue

        for link in soup.select('a[href*="nshowmovie.html?movieid="]'):
            title = link.get_text(strip=True)
            if not title or title.lower() in seen:
                continue
            if query and query.lower() not in title.lower():
                continue
            seen.add(title.lower())

            movie_url = base + '/' + link['href'].lstrip('/')
            try:
                page = BeautifulSoup(requests.get(movie_url, timeout=8).text, 'html.parser')
            except:
                continue

            torrent = None
            for a in page.select('a[href*="btdownload.php"]'):
                if '.mp4.torrent' in a['href'].lower():
                    torrent = a['href']
                    break
            if not torrent:
                continue

            rating, casting = _tmdb(title)
            results.append({
                'title': title,
                'magnet': torrent,
                'cover': '',
                'year': None,
                'rating': rating,
                'summary': '',
                'casting': casting,
                'source': 'publicdomaintorrents',
            })
            if len(results) >= 12:
                return results
    return results


def search_all(query, page=1, min_year=None, min_rating=None):
    results = search_archive(query, page, min_year, min_rating)
    if page == 1 and query:
        results += search_publicdomain(query)
    if query:
        results.sort(key=lambda r: r['title'].lower())
    return results


def _find_video(folder):
    preferred = ('.mp4', '.webm', '.mkv', '.avi', '.mov', '.mpeg', '.mpg')
    found = {}
    for root, _, files in os.walk(folder):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in preferred:
                full = os.path.join(root, f)
                # keep the biggest of each extension
                if ext not in found or os.path.getsize(full) > os.path.getsize(found[ext]):
                    found[ext] = full
    for ext in preferred:
        if ext in found:
            return found[ext]
    return None


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


def start_download(torrent_url, movie_id):
    from .models import Movie

    movie = Movie.objects.filter(id=movie_id).first()
    file_missing = movie and movie.file_path and not os.path.exists(movie.file_path)

    if file_missing:
        Movie.objects.filter(id=movie_id).update(file_path='')
        old = active_downloads.pop(torrent_url, None)
        if old:
            try:
                session.remove_torrent(old)
            except:
                pass

    if torrent_url in active_downloads:
        return

    try:
        data = requests.get(torrent_url, timeout=10).content
        info = lt.torrent_info(lt.bdecode(data))
    except:
        return

    handle = session.add_torrent({
        'ti': info,
        'save_path': DOWNLOAD_PATH,
        'storage_mode': lt.storage_mode_t.storage_mode_sparse,
    })
    # Sequential download: pieces arrive in order, from start to end,
    # so ffmpeg can read the file progressively as it grows.
    handle.set_sequential_download(True)

    files = info.files()
    preferred = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.mpeg', '.mpg']
    target = None
    for ext in preferred:
        for i in range(info.num_files()):
            if files.file_path(i).lower().endswith(ext):
                if target is None or files.file_size(i) > files.file_size(target):
                    target = i
        if target is not None:
            break

    if target is not None:
            priorities = [0] * info.num_files()
            priorities[target] = 7
            handle.prioritize_files(priorities)

            # Prioritize the head AND tail pieces of the target file.
            # Many mp4s have the moov atom (the index ffmpeg needs) at the very END,
            # so without this the file is unplayable until 100% download.
            fs = info.files()
            file_offset = fs.file_offset(target)
            file_size = fs.file_size(target)
            piece_len = info.piece_length()

            first_piece = file_offset // piece_len
            last_piece = (file_offset + file_size - 1) // piece_len

            for p in range(first_piece, min(first_piece + 5, last_piece + 1)):
                handle.piece_priority(p, 7)
            for p in range(max(last_piece - 9, first_piece), last_piece + 1):
                handle.piece_priority(p, 7)

    active_downloads[torrent_url] = handle
    Movie.objects.filter(id=movie_id).update(folder=info.name())

    def monitor():
        from .models import Movie
        from django.utils import timezone
        while handle.status().progress < 0.999:
            s = handle.status()
            print(f"Movie {movie_id}: {s.progress*100:.1f}% ({s.download_rate/1000:.0f} kB/s)", flush=True)
            time.sleep(3)
        path = _find_video(os.path.join(DOWNLOAD_PATH, info.name()))
        if path:
            Movie.objects.filter(id=movie_id).update(
                file_path=path, length=_get_duration(path), last_watched=timezone.now()
            )
        print(f"Movie {movie_id}: complete", flush=True)

    threading.Thread(target=monitor, daemon=True).start()

def get_playable_file(folder_name):
    if not folder_name:
        return None
    folder = os.path.join(DOWNLOAD_PATH, folder_name)
    if not os.path.exists(folder):
        return None
    return _find_video(folder)


def _srt_to_vtt(srt_text):
    # Browser <track> only reads WebVTT. Convert the srt timestamps
    def fix_timestamp(match):
        h, m, s, ms = match.group(1), match.group(2), match.group(3), match.group(4)
        ms = (ms + '000')[:3]
        return f"{h}:{m}:{s}.{ms}"

    lines = ['WEBVTT', '']
    for line in srt_text.splitlines():
        if '-->' in line:
            line = re.sub(r'(\d{2}):(\d{2}):(\d{2})[,.](\d+)', fix_timestamp, line)
        lines.append(line)
    return '\n'.join(lines)


def get_subtitle_text(identifier):
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