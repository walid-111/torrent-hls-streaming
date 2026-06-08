'use client'

import { useState } from 'react'

export default function LoginPage() {
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault()
    if (!form.username || !form.password) {
      setError('Username and password are required')
      return
    }
    const res = await fetch('http://localhost:8000/api/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(form),
    })
    if (res.ok) window.location.href = '/library'
    else setError('Invalid username or password')
  }

  async function handleOAuth(provider: string) {
    const res = await fetch(`http://localhost:8000/api/auth/${provider}/`, { credentials: 'include' })
    const data = await res.json()
    window.location.href = data.url
  }

  return (
    <div className="max-w-md mx-auto mt-16 p-8 card">
      <h1 className="text-2xl font-bold mb-6">Login</h1>
      {error && <p className="text-red-600 mb-3 text-sm">{error}</p>}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
        <input className="input" placeholder="Username" value={form.username}
          onChange={e => setForm({ ...form, username: e.target.value })} />
        <input className="input" type="password" placeholder="Password" value={form.password}
          onChange={e => setForm({ ...form, password: e.target.value })} />
        <button className="btn" type="submit">Login</button>
      </form>
      <div className="mt-5 text-sm flex flex-col gap-2">
        <a href="/register" className="link">Create an account</a>
        <a href="/reset-password" className="link">Forgot password?</a>
        <button onClick={() => handleOAuth('42')} className="link text-left">Login with 42</button>
        <button onClick={() => handleOAuth('github')} className="link text-left">Login with GitHub</button>
      </div>
    </div>
  )
}