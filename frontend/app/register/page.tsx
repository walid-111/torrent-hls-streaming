'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function RegisterPage() {
  const router = useRouter()
  const [form, setForm] = useState({
    username: '', email: '', first_name: '', last_name: '', password: ''
  })
  const [error, setError] = useState('')

  function validate() {
    if (form.username.length < 3) return 'Username must be at least 3 characters'
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) return 'Invalid email address'
    if (!form.first_name) return 'First name is required'
    if (!form.last_name) return 'Last name is required'
    if (form.password.length < 8) return 'Password must be at least 8 characters'
    if (!/[A-Z]/.test(form.password)) return 'Password must contain at least one uppercase letter'
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(form.password)) return 'Password must contain at least one special character'
    return ''
  }

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault()
    const err = validate()
    if (err) { setError(err); return }
    const res = await fetch('http://localhost:8000/internal/auth/register/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    if (res.ok) router.push('/login')
    else {
      const data = await res.json()
      setError(Object.values(data).flat().join(' '))
    }
  }

  return (
    <div className="max-w-md mx-auto mt-16 p-8 card">
      <h1 className="text-2xl font-bold mb-6">Register</h1>
      {error && <p className="text-red-600 mb-3 text-sm">{error}</p>}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
        <input className="input" placeholder="Username" value={form.username}
          onChange={e => setForm({ ...form, username: e.target.value })} />
        <input className="input" type="email" placeholder="Email" value={form.email}
          onChange={e => setForm({ ...form, email: e.target.value })} />
        <input className="input" placeholder="First name" value={form.first_name}
          onChange={e => setForm({ ...form, first_name: e.target.value })} />
        <input className="input" placeholder="Last name" value={form.last_name}
          onChange={e => setForm({ ...form, last_name: e.target.value })} />
        <input className="input" type="password" placeholder="Password (min 8 chars)" value={form.password}
          onChange={e => setForm({ ...form, password: e.target.value })} />
        <button className="btn" type="submit">Register</button>
      </form>
      <a href="/login" className="link text-sm mt-5 block">Already have an account? Login</a>
    </div>
  )
}