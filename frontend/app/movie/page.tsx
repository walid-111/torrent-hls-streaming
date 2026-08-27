'use client'
import { useState, useEffect, useRef, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useAuth } from '../components/useAuth'
import Hls from 'hls.js'

const API = 'http://localhost:8000'

function VideoPlayer({ movieId, subtitles }: { movieId: number, subtitles: any[] }) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const url = `${API}/internal/movies/hls/${movieId}/index.m3u8`

    // chrome/firefox: hls.js. safari plays hls natively
    if (Hls.isSupported()) {
      const hls = new Hls({
        xhrSetup: xhr => { xhr.withCredentials = true }, // send the session cookie
      })
      hls.loadSource(url)
      hls.attachMedia(video)
      hls.on(Hls.Events.ERROR, (_, data) => {
        // segment not there yet or network hiccup: try again instead of dying
        if (data.fatal && data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad()
        else if (data.fatal && data.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError()
      })
      return () => hls.destroy()
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url
    }
  }, [movieId])

  return (
    <video ref={videoRef} key={movieId} className="w-full rounded mb-6 card" controls autoPlay crossOrigin="use-credentials">
      {subtitles.map((s, i) => (
        <track key={i} kind="subtitles" src={s.url} srcLang={s.lang}
          label={s.lang === 'en' ? 'English' : s.lang} default={s.lang === 'en'} />
      ))}
    </video>
  )
}


function MovieContent() {
  const router = useRouter()
  const ready = useAuth()
  const params = useSearchParams()
  const magnet = params.get('magnet')
  const title = params.get('title')
  const cover = params.get('cover')
  const summary = params.get('summary')
  const rating = params.get('rating')
  const year = params.get('year')
  const source = params.get('source')

  let casting = null
  try { casting = JSON.parse(params.get('casting') || 'null') } catch {}

  const [movieId, setMovieId] = useState<number | null>(null)
  const [streamReady, setStreamReady] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [noSeeders, setNoSeeders] = useState(false)
  const [comments, setComments] = useState<any[]>([])
  const [comment, setComment] = useState('')
  const [subtitles, setSubtitles] = useState<any[]>([])
  const startedRef = useRef(false)

  function getCsrf() {
    return document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1] || ''
  }

  useEffect(() => {
    if (!ready || !magnet || startedRef.current) return
    startedRef.current = true
    fetch(`${API}/internal/movies/start/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      credentials: 'include',
      body: JSON.stringify({ magnet, title }),
    })
      .then(r => {
        if (r.status === 503) { setNoSeeders(true); return null }
        return r.json()
      })
      .then(data => {
        if (!data) return
        if (data.movie_id) {
          setMovieId(data.movie_id)
          loadComments(data.movie_id)
          loadSubtitles(data.movie_id)
        }
      })
  }, [ready, magnet])

  useEffect(() => {
    if (!movieId || streamReady) return
    const interval = setInterval(() => {
      fetch(`${API}/internal/movies/status/${movieId}/`, { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
          if (data.progress != null) setProgress(data.progress)
          if (data.ready) { setStreamReady(true); clearInterval(interval) }
          if (data.failed) { setNoSeeders(true); clearInterval(interval) }
        })
        .catch(() => {})
    }, 2000)
    return () => clearInterval(interval)
  }, [movieId, streamReady])

  function loadComments(id: number) {
    fetch(`${API}/internal/movies/${id}/comments/`, { credentials: 'include' })
      .then(r => r.json()).then(setComments).catch(() => {})
  }

  function loadSubtitles(id: number) {
    fetch(`${API}/internal/movies/${id}/subtitles/`, { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        const list = (data.subtitles || []).map((s: any) => {
          const blob = new Blob([s.content], { type: 'text/vtt' })
          return { lang: s.lang, url: URL.createObjectURL(blob) }
        })
        setSubtitles(list)
      })
      .catch(() => {})
  }

  async function postComment(e: React.SyntheticEvent) {
    e.preventDefault()
    if (!movieId || !comment.trim()) return
    await fetch(`${API}/internal/movies/${movieId}/comments/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      credentials: 'include',
      body: JSON.stringify({ content: comment }),
    })
    setComment('')
    loadComments(movieId)
  }

  if (!ready) return <p className="p-8 muted">Loading...</p>

  return (
    <div className="max-w-4xl mx-auto p-6">
      <button onClick={() => router.back()} className="link mb-4">← Back</button>

      <div className="flex gap-5 mb-6">
        {cover && (
          <img src={cover} alt={title || ''} className="rounded card object-contain self-start"
            style={{ width: '140px', height: 'auto' }}
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="muted text-sm mb-2">
            {year}{rating && ` · ${rating}/10`}{source && ` · ${source}`}
          </p>
          {summary && <p className="text-sm">{summary}</p>}
          {casting && (
            <div className="mt-3 text-sm muted">
              {casting.director && <p>Director: {casting.director}</p>}
              {casting.producer && <p>Producer: {casting.producer}</p>}
              {casting.cast?.length > 0 && <p>Cast: {casting.cast.join(', ')}</p>}
            </div>
          )}
        </div>
      </div>

      {noSeeders && (
        <div className="card p-12 text-center mb-6">
          <p style={{ color: 'var(--accent)' }}>No seeders available for this torrent. Try another movie.</p>
          <button className="btn mt-4" onClick={() => router.back()}>← Back</button>
        </div>
      )}

      {!noSeeders && !streamReady && movieId && (
        <div className="card p-12 text-center mb-6 flex flex-col items-center gap-4">
          <div className="spinner" />
          <p className="muted">Preparing stream, downloading...{progress != null && ` ${progress}%`}</p>
        </div>
      )}

      {streamReady && movieId && (
        <VideoPlayer movieId={movieId} subtitles={subtitles} />
      )}

      <div className="card p-5">
        <h2 className="text-lg font-bold mb-3">Comments</h2>
        <form onSubmit={postComment} className="flex gap-2 mb-4">
          <input className="input flex-1" placeholder="Leave a comment..."
            value={comment} onChange={e => setComment(e.target.value)} />
          <button className="btn" type="submit">Post</button>
        </form>
        {comments.map((c, i) => (
          <div key={i} className="border-t py-2" style={{ borderColor: 'var(--border)' }}>
            <p className="font-semibold text-sm">{c.author}</p>
            <p className="text-sm">{c.content}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function MoviePage() {
  return <Suspense><MovieContent /></Suspense>
}