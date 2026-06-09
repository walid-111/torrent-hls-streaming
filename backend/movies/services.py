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


def search_publicdomain_torrents(query, page=1, min_year=None, min_rating=None):
    """
    Simple scraper pour PublicDomainTorrents.
    Pas de vraie pagination côté site, donc on fait une pagination maison.
    """
    base = "https://www.publicdomaintorrents.info"
    list_url = f"{base}/nshowcat.html?category=ALL"

    try:
        html = requests.get(list_url, timeout=10).text
    except Exception:
        return []

    soup = BeautifulSoup(html, 'html.parser')

    # Récupère tous les liens vers nshowmovie.html
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'nshowmovie.html' in href:
            title = a.get_text(strip=True)
            if not title:
                continue
            # Si query fournie, filtrer côté titre
            if query and query.lower() not in title.lower():
                continue
            links.append({
                'title': title,
                'url': href if href.startswith('http') else base + '/' + href.lstrip('/'),
            })

    if not links:
        return []

    # Pagination "maison"
    per_page = 10
    start = (page - 1) * per_page
    end = start + per_page
    subset = links[start:end]

    results = []
    for item in subset:
        detail_url = item['url']
        title = item['title']

        try:
            detail_html = requests.get(detail_url, timeout=10).text
        except Exception:
            continue

        detail = BeautifulSoup(detail_html, 'html.parser')

        # Cherche lien .torrent
        torrent_url = None
        for a in detail.find_all('a', href=True):
            href = a['href']
            if href.lower().endswith('.torrent'):
                torrent_url = href if href.startswith('http') else base + '/' + href.lstrip('/')
                break
        if not torrent_url:
            continue

        # Résumé / année très basique (le HTML du site est old-school)
        summary = ''
        year = None

        # Exemple : souvent le synopsis est dans des <p> ou <font>
        paras = detail.find_all('p')
        if paras:
            summary = paras[0].get_text(strip=True)

        # Si tu veux tenter d'extraire une année du titre ou du texte :
        if not year:
            import re
            m = re.search(r'\b(19\d{2}|20\d{2})\b', title)
            if m:
                year = m.group(1)

        rating, casting = _tmdb(title)
        if min_rating and (not rating or float(rating) < float(min_rating)):
            continue
        if min_year and year and str(year).isdigit() and int(year) < int(min_year):
            continue

        results.append({
            'title': title,
            'magnet': torrent_url,  # c'est une URL .torrent, pas un magnet
            'cover': None,          # pas d'image fiable sur ce site
            'year': year,
            'rating': rating,
            'summary': summary,
            'casting': casting,
            'source': 'publicdomaintorrents',
        })

    return results


def search_all(query, page=1, min_year=None, min_rating=None):
    if page > 20:
        return []
    results = search_archive(query, page, min_year, min_rating)
    if page <= 3:
        results += search_archive(query, page, min_year, min_rating)
        results += search_publicdomain_torrents(query, page, min_year, min_rating)
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


def _load_torrent_info(torrent_url):
    """Load torrent_info from .torrent file URL"""
    if torrent_url.startswith('magnet:'):
        params = lt.parse_magnet_uri(torrent_url)
        params.save_path = DOWNLOAD_PATH
        handle = session.add_torrent(params)
        for _ in range(30):
            if handle.status().has_metadata:
                return handle, handle.torrent_file()
            time.sleep(1)
        try: session.remove_torrent(handle)
        except: pass
        return None, None

    try:
        data = requests.get(torrent_url, timeout=10).content
        info = lt.torrent_info(lt.bdecode(data))
        handle = session.add_torrent({
            'ti': info,
            'save_path': DOWNLOAD_PATH,
            'storage_mode': lt.storage_mode_t.storage_mode_sparse,
        })
        return handle, info
    except:
        return None, None


def start_download(torrent_url, movie_id):
    from .models import Movie

    movie = Movie.objects.filter(id=movie_id).first()
    if movie and movie.file_path and not os.path.exists(movie.file_path):
        Movie.objects.filter(id=movie_id).update(file_path='')
        old = active_downloads.pop(torrent_url, None)
        if old:
            try: session.remove_torrent(old)
            except: pass

    if torrent_url in active_downloads:
        return

    handle, info = _load_torrent_info(torrent_url)
    if not handle or not info:
        print(f"Movie {movie_id}: failed to load torrent", flush=True)
        return

    # Pick largest video file
    files = info.files()
    preferred = ['.mp4', '.webm', '.mkv', '.avi', '.mov']
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

        # Head + tail pieces priority (moov atom often at end)
        file_offset = files.file_offset(target)
        file_size = files.file_size(target)
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
        stuck_seconds = 0
        last_progress = handle.status().progress
        while handle.status().progress < 0.999:
            s = handle.status()
            print(f"Movie {movie_id}: {s.progress*100:.1f}% ({s.download_rate/1000:.0f} kB/s)", flush=True)
            if s.progress <= last_progress + 0.001 and s.download_rate < 1000:
                stuck_seconds += 3
            else:
                stuck_seconds = 0
                last_progress = s.progress
            if stuck_seconds >= 60 and s.progress >= 0.90:
                print(f"Movie {movie_id}: stuck at {s.progress*100:.1f}%, marking complete", flush=True)
                break
            if stuck_seconds >= 180:
                print(f"Movie {movie_id}: dead torrent", flush=True)
                active_downloads.pop(torrent_url, None)
                try: session.remove_torrent(handle)
                except: pass
                return
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