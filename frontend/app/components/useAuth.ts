'use client'
import { useState, useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'

const PUBLIC_PATHS = ['/login', '/register', '/reset-password', '/reset-password/confirm']

export function useAuth() {
  const router = useRouter()
  const pathname = usePathname()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (PUBLIC_PATHS.includes(pathname)) return
    fetch('http://localhost:8000/internal/auth/profile/', { credentials: 'include' })
      .then(res => {
        if (!res.ok) router.replace('/login')
        else setReady(true)
      })
  }, [pathname])

  return ready
}