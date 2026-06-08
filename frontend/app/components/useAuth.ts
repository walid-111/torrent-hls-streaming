'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

export function useAuth() {
  const router = useRouter()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    fetch('http://localhost:8000/api/profile/', { credentials: 'include' })
      .then(res => {
        if (!res.ok) router.replace('/login')
        else setReady(true)
      })
  }, [])

  return ready
}