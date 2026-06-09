'use client'
import { useState, useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'

const PUBLIC_PATHS = ['/login', '/register', '/reset-password', '/reset-password/confirm']

export default function Nav() {
  const router = useRouter()
  const pathname = usePathname()
  const [loggedIn, setLoggedIn] = useState(false)

  useEffect(() => {
    if (PUBLIC_PATHS.includes(pathname)) { setLoggedIn(false); return }
    fetch('http://localhost:8000/internal/auth/profile/', { credentials: 'include' })
      .then(res => setLoggedIn(res.ok))
  }, [pathname])

  function handleLogout() {
    const csrf = document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1] || ''
    fetch('http://localhost:8000/internal/auth/logout/', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf },
      credentials: 'include',
    }).finally(() => {
      setLoggedIn(false)
      router.push('/login')
    })
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