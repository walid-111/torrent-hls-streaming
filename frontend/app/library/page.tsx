'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../components/useAuth'

interface Movie {
  title: string
  magnet: string
  cover: string
  year: number | null
  rating: number | null
  summary: string
  watched?: boolean
  source?: string
  casting?: any
}

export default function LibraryPage() {
  const ready = useAuth()
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [minYear, setMinYear] = useState('')
  const [minRating, setMinRating] = useState('')
  const [movies, setMovies] = useState<Movie[]>([])
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  async function fetchMovies(pageNum: number, reset: boolean, signal?: AbortSignal) {
    setLoading(true)
    const params = new URLSearchParams({ q: query, page: String(pageNum) })
    if (minYear) params.append('min_year', minYear)
    if (minRating) params.append('min_rating', minRating)
    try {
      const res = await fetch(`http://localhost:8000/internal/movies/search/?${params}`, {
        credentials: 'include',
        signal,
      })
      if (res.status === 401 || res.status === 403) { router.push('/login'); return }
      const data = await res.json()
      const list = Array.isArray(data) ? data : []
      setMovies(prev => reset ? list : [...prev, ...list])
      setHasMore(list.length > 0)
    } catch (err: any) {
      if (signal?.aborted) return
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!ready) return
    const controller = new AbortController()
    fetchMovies(1, true, controller.signal).catch(() => {})
    return () => controller.abort()
  }, [ready])

  useEffect(() => {
    const controller = new AbortController()
    const observer = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasMore && !loading) {
        const next = page + 1
        setPage(next)
        fetchMovies(next, false, controller.signal).catch(() => {})
      }
    })
    if (bottomRef.current) observer.observe(bottomRef.current)
    return () => { observer.disconnect(); controller.abort() }
  }, [page, hasMore, loading])

  function handleSearch(e: React.SyntheticEvent) {
    e.preventDefault()
    setPage(1)
    setHasMore(true)
    fetchMovies(1, true).catch(() => {})
  }

  function openMovie(m: Movie) {
    const q = new URLSearchParams({
      magnet: m.magnet,
      title: m.title,
      cover: m.cover || '',
      summary: m.summary || '',
      rating: m.rating?.toString() || '',
      year: m.year?.toString() || '',
      casting: m.casting ? JSON.stringify(m.casting) : '',
      source: m.source || '',
    }).toString()
    router.push(`/movie?${q}`)
  }

  if (!ready) return <p className="p-8 muted">Loading...</p>

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <form onSubmit={handleSearch} className="flex flex-wrap gap-2 mb-8 items-center">
        <input className="input flex-1 min-w-[200px]" placeholder="Search a movie..."
          value={query} onChange={e => setQuery(e.target.value)} />
        <input type="number" placeholder="Min year" className="input w-28"
          value={minYear} onChange={e => setMinYear(e.target.value)} />
        <input type="number" step="0.1" placeholder="Min rating" className="input w-28"
          value={minRating} onChange={e => setMinRating(e.target.value)} />
        <button className="btn" type="submit">Search</button>
        {loading && <div className="spinner" />}
      </form>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5">
        {movies.map((m, i) => (
          <div key={i} onClick={() => openMovie(m)}
            className={`card cursor-pointer overflow-hidden ${m.watched ? 'opacity-50' : ''}`}>
            <div className="flex items-center justify-center" style={{ height: '220px', background: '#ece7dc' }}>
              {m.cover
                ? <img src={m.cover} alt={m.title} className="max-h-full max-w-full object-contain" />
                : <span className="muted text-sm">No cover</span>}
            </div>
            <div className="p-3">
              <p className="font-semibold text-sm truncate">{m.watched && '✓ '}{m.title}</p>
              <p className="text-xs muted">{m.year} {m.rating ? `· ${m.rating.toFixed(1)}/10` : ''}</p>
              {m.source && <p className="text-xs muted mt-1">{m.source}</p>}
            </div>
          </div>
        ))}
      </div>

      {loading && movies.length > 0 && (
        <div className="flex justify-center py-6"><div className="spinner" /></div>
      )}
      <div ref={bottomRef} className="h-10" />
    </div>
  )
}