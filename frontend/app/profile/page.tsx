'use client'
import { useState, useEffect } from 'react'
import { useAuth } from '../components/useAuth'

export default function ProfilePage() {
  const ready = useAuth()
  const [user, setUser] = useState<any>(null)
  const [form, setForm] = useState({ email: '', bio: '', preferred_language: 'en', avatar: null as File | null })
  const [preview, setPreview] = useState<string | null>(null)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('http://localhost:8000/internal/auth/profile/', { credentials: 'include' })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (!data) return
        setUser(data)
        setForm({ email: data.email, bio: data.bio || '', preferred_language: data.preferred_language || 'en', avatar: null })
      })
  }, [])

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] || null
    if (file) {
      if (!file.type.startsWith('image/')) { setError('File must be an image'); return }
      if (file.size > 5 * 1024 * 1024) { setError('Image too large (max 5MB)'); return }
      setError('')
      setPreview(URL.createObjectURL(file))
    }
    setForm({ ...form, avatar: file })
  }

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault()
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) { setError('Invalid email address'); return }
    setError('')
    const csrf = document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1] || ''
    const data = new FormData()
    data.append('email', form.email)
    data.append('bio', form.bio)
    data.append('preferred_language', form.preferred_language)
    if (form.avatar) data.append('avatar', form.avatar)

    const res = await fetch('http://localhost:8000/internal/auth/profile/', {
      method: 'PATCH',
      headers: { 'X-CSRFToken': csrf },
      credentials: 'include',
      body: data,
    })
    if (res.ok) {
      const updated = await res.json()
      setUser(updated)
      setPreview(null)
      setSuccess('Profile updated')
    } else {
      const d = await res.json()
      setError(Object.values(d).flat().join(' '))
    }
  }

  if (!ready || !user) return <p className="p-8 muted">Loading...</p>

  return (
    <div className="max-w-md mx-auto mt-16 p-8 card">
      <h1 className="text-2xl font-bold mb-1">Profile</h1>
      <p className="muted mb-5">@{user.username}</p>
      {success && <p className="text-green-700 mb-3 text-sm">{success}</p>}
      {error && <p className="text-red-600 mb-3 text-sm">{error}</p>}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
        <div className="flex flex-col items-center gap-3">
          {(preview || user.avatar) && (
            <img src={preview || `http://localhost:8000${user.avatar}`}
              className="w-24 h-24 rounded-full object-cover" style={{ background: '#ece7dc' }} alt="" />
          )}
          <label className="btn cursor-pointer text-sm">
            Choose photo
            <input type="file" accept="image/*" className="hidden" onChange={handleFile} />
          </label>
        </div>
        <input className="input" type="email" placeholder="Email" value={form.email}
          onChange={e => setForm({ ...form, email: e.target.value })} />
        <textarea className="input" placeholder="Bio" value={form.bio}
          onChange={e => setForm({ ...form, bio: e.target.value })} />
        <select className="input" value={form.preferred_language}
          onChange={e => setForm({ ...form, preferred_language: e.target.value })}>
          <option value="en">English</option>
          <option value="fr">French</option>
        </select>
        <button className="btn" type="submit">Save</button>
      </form>
    </div>
  )
}