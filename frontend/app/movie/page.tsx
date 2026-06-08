'use client'

import { useState, useEffect, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'

function MovieContent() {
  const router = useRouter()
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
  const [ready, setReady] = useState(false)
  const [buffering, setBuffering] = useState(false)
  const [videoKey, setVideoKey] = useState(0)
  const [comments, setComments] = useState<any[]>([])
  const [comment, setComment] = useState('')
  const [subtitles, setSubtitles] = useState<any[]>([])

  function getCsrf() {
    return document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1] || ''
  }

  useEffect(() => {
    if (!magnet) return
    fetch('http://localhost:8000/api/movies/start/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      credentials: 'include',
      body: JSON.stringify({ magnet, title }),
    })
      .then(res => res.json())
      .then(data => {
        if (data.movie_id) {
          setMovieId(data.movie_id)
          loadComments(data.movie_id)
          loadSubtitles(data.movie_id)
        }
      })
  }, [magnet])

  useEffect(() => {
    if (!movieId || ready) return
    const interval = setInterval(() => {
      fetch(`http://localhost:8000/api/movies/status/${movieId}/`, { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
          if (data.ready) {
            setReady(true)
            clearInterval(interval)
          }
        })
    }, 2000)
    return () => clearInterval(interval)
  }, [movieId, ready])

  function loadComments(id: number) {
    fetch(`http://localhost:8000/api/movies/${id}/comments/`, { credentials: 'include' })
      .then(res => res.json())
      .then(setComments)
  }

  function loadSubtitles(id: number) {
    fetch(`http://localhost:8000/api/movies/${id}/subtitles/`, { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        const list = (data.subtitles || []).map((s: any) => {
          const blob = new Blob([s.content], { type: 'text/vtt' })
          return { lang: s.lang, url: URL.createObjectURL(blob) }
        })
        setSubtitles(list)
      })
  }

  // If playback catches up to the download, the stream cuts off.
  // Show a buffering loader and reload the player after a short wait.
  function handleVideoError() {
    setBuffering(true)
    setTimeout(() => {
      setBuffering(false)
      setVideoKey(k => k + 1)
    }, 4000)
  }

  async function postComment(e: React.SyntheticEvent) {
    e.preventDefault()
    if (!movieId || !comment) return
    await fetch(`http://localhost:8000/api/movies/${movieId}/comments/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      credentials: 'include',
      body: JSON.stringify({ content: comment }),
    })
    setComment('')
    loadComments(movieId)
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <button onClick={() => router.back()} className="link mb-4">← Back</button>

      <div className="flex gap-5 mb-6">
        {cover && (
          <img
            src={cover}
            alt={title || ''}
            className="rounded card object-contain self-start"
            style={{ width: '140px', height: 'auto' }}
          />
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="muted text-sm mb-2">
            {year} {rating && `· ${rating}/10`} {source && `· ${source}`}
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

      {(!ready || buffering) && movieId && (
        <div className="card p-12 text-center mb-6 flex flex-col items-center gap-4">
          <div className="spinner" />
          <p className="muted">
            {buffering ? 'Buffering, please wait...' : 'Preparing video, download in progress...'}
          </p>
        </div>
      )}

      {ready && !buffering && movieId && (
        <video key={videoKey} className="w-full rounded mb-6 card" controls onError={handleVideoError}>
          <source src={`http://localhost:8000/api/movies/stream/${movieId}/`} />
          {subtitles.map((s, i) => (
            <track key={i} kind="subtitles" src={s.url} srcLang={s.lang}
              label={s.lang === 'en' ? 'English' : s.lang} />
          ))}
        </video>
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
  return (
    <Suspense>
      <MovieContent />
    </Suspense>
  )
}