'use client'

import { useState } from 'react'

export default function ResetPasswordPage() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault()
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setError('Invalid email address')
      return
    }
    setError('')
    await fetch('http://localhost:8000/api/password-reset/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
    setMessage('If this email exists, a reset link has been sent')
  }

  return (
    <div className="max-w-md mx-auto mt-16 p-8 card">
      <h1 className="text-2xl font-bold mb-6">Reset Password</h1>
      {message && <p className="text-green-700 mb-3 text-sm">{message}</p>}
      {error && <p className="text-red-600 mb-3 text-sm">{error}</p>}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
        <input className="input" type="email" placeholder="Your email" value={email}
          onChange={e => setEmail(e.target.value)} />
        <button className="btn" type="submit">Send reset link</button>
      </form>
      <a href="/login" className="link text-sm mt-5 block">Back to login</a>
    </div>
  )
}