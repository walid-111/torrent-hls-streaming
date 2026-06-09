'use client'
import { useState, useEffect, use } from 'react'
import { useRouter } from 'next/navigation'

export default function UserProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const router = useRouter()
  const [user, setUser] = useState<any>(null)

  useEffect(() => {
    fetch(`http://localhost:8000/api/users/${id}/`, { credentials: 'include' })
      .then(res => {
        if (!res.ok) { router.push('/login'); return null }
        return res.json()
      })
      .then(data => data && setUser(data))
  }, [])

  if (!user) return <p className="p-8 muted">Loading...</p>

  const avatarUrl = user.avatar
    ? (user.avatar.startsWith('http') ? user.avatar : `http://localhost:8000${user.avatar}`)
    : null

  return (
    <div className="max-w-md mx-auto mt-16 p-8 card text-center">
      {avatarUrl ? (
        <img src={avatarUrl} className="w-24 h-24 rounded-full mx-auto mb-4 object-cover" alt=""
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
      ) : (
        <div className="w-24 h-24 rounded-full mx-auto mb-4 flex items-center justify-center muted"
          style={{ background: '#ece7dc' }}>No photo</div>
      )}
      <h1 className="text-xl font-bold mb-1">@{user.username}</h1>
      {(user.first_name || user.last_name) && (
        <p className="muted mb-4">{user.first_name} {user.last_name}</p>
      )}
      {user.bio ? <p className="text-sm">{user.bio}</p> : <p className="text-sm muted">No bio</p>}
    </div>
  )
}