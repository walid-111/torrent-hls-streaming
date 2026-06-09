'use client'
import { useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

function ConfirmForm() {
  const router = useRouter()
  const params = useSearchParams()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault()
    if (password.length < 8) { setError('Password must be at least 8 characters'); return }
    const res = await fetch('http://localhost:8000/internal/auth/password-reset/confirm/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        uid: params.get('uid'),
        token: params.get('token'),
        new_password: password,
      }),
    })
    if (res.ok) router.push('/login')
    else setError('Invalid or expired link')
  }

  return (
    <div className="max-w-md mx-auto mt-16 p-8 card">
      <h1 className="text-2xl font-bold mb-6">New Password</h1>
      {error && <p className="text-red-600 mb-3 text-sm">{error}</p>}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
        <input className="input" type="password" placeholder="New password (min 8 chars)" value={password}
          onChange={e => setPassword(e.target.value)} />
        <button className="btn" type="submit">Reset</button>
      </form>
    </div>
  )
}

export default function ConfirmPage() {
  return <Suspense><ConfirmForm /></Suspense>
}