'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function LoginPage() {
  const router = useRouter()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault()
    if (!form.username || !form.password) { setError('All fields are required'); return }
    setError('')
    const res = await fetch('http://localhost:8000/internal/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(form),
    })
    if (res.ok) router.push('/library')
    else setError('Invalid username or password')
  }

  async function handle42() {
    const res = await fetch('http://localhost:8000/internal/auth/auth/42/')
    const data = await res.json()
    window.location.href = data.url
  }

  async function handleGithub() {
    const res = await fetch('http://localhost:8000/internal/auth/auth/github/')
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
      <div className="flex flex-col gap-2 mt-4">
        <button onClick={handle42} className="btn">Login with 42</button>
        <button onClick={handleGithub} className="btn">Login with GitHub</button>
      </div>
      <a href="/register" className="link text-sm mt-5 block">No account? Register</a>
      <a href="/reset-password" className="link text-sm mt-2 block">Forgot password?</a>
    </div>
  )
}