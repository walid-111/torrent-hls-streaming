# torrent-hls-streaming

A streaming web app that plays movies directly from torrents. You pick a movie, playback starts after a few seconds while the rest keeps downloading in the background.

All content comes from the [Internet Archive](https://archive.org/details/feature_films) feature films collection, so everything is public domain and legal to stream. Ratings, cast and director come from TMDB.

Stack: Django + Django REST Framework, PostgreSQL, libtorrent, ffmpeg, Next.js with hls.js, all in Docker.

## How streaming works

```
archive.org torrent ──> libtorrent (sequential) ──> raw endpoint ──> ffmpeg ──> HLS segments ──> hls.js
                         webseeds + peers          waits for pieces   copy or      .m3u8 + .ts
                                                                     transcode
```

The torrent is downloaded in order, starting with the beginning of the video file. Files on disk are sparse, so the size on disk doesn't say what's actually there. The backend checks which pieces are downloaded and never serves bytes that aren't there yet.

ffmpeg reads the movie through an internal endpoint that waits for the requested bytes to arrive. If the video is already H.264 it's just cut into segments without re-encoding, otherwise it's transcoded to H.264/AAC (720p max). The output is an HLS playlist that grows as the download goes, and the player starts as soon as there are two segments.

Some mp4 files have their index (moov atom) at the end, and ffmpeg needs it before anything else. Archive.org torrents have HTTP webseeds, so in that case the backend fetches that small range directly over HTTP instead of waiting for the whole download. With regular peers it uses libtorrent piece deadlines instead.

On a test 6 minute 720p movie with a 1.5 MB/s source, playback starts after about 3 seconds, with 7% of the file downloaded.

## Features

Search with infinite scroll, filters (year, rating) and sorting. Watched movies are marked. Playback resumes where you stopped, and the library has a "Continue watching" row. Comments, subtitles when archive.org has them, user profiles with avatars. Login with username/password, GitHub or 42 OAuth, plus password reset by email. When the backend starts, movies not watched for a month are deleted with their segments.

There's also a small REST API (`/api/`) with token auth (`/oauth/token/`).

## Run it

```
cp .env.example .env
docker compose up --build
```

Then open http://localhost:3000. In `.env`, the secret key and Postgres variables are required, the TMDB key is needed for ratings and cast, OAuth and email are optional.
