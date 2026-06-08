'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function Nav() {
  const router = useRouter()
  const [loggedIn, setLoggedIn] = useState(false)

  useEffect(() => {
    // check API for session cookie
    if (!document.cookie.includes('sessionid')) return
    fetch('http://localhost:8000/api/profile/', { credentials: 'include' })
      .then(res => setLoggedIn(res.ok))
  }, [])

  async function handleLogout() {
    const csrf = document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1] || ''
    await fetch('http://localhost:8000/api/logout/', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf },
      credentials: 'include',
    })
    setLoggedIn(false)
    router.push('/login')
  }

  if (!loggedIn) return null

  return (
    <nav className="flex gap-5 items-center text-sm">
      <a href="/library" className="link">Library</a>
      <a href="/profile" className="link">Profile</a>
      <button onClick={handleLogout} className="muted">Logout</button>
    </nav>
  )
}