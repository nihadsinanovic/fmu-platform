import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Login failed')
      }
      const data = await res.json()
      // Fetch user info to get is_admin flag
      const meRes = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      })
      const me = meRes.ok ? await meRes.json() : { is_admin: false }
      login(data.access_token, username, me.is_admin)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-off-white px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img src="/admin/qvantum-symbol.png" alt="Qvantum" className="w-12 h-12 mb-4" />
          <h1 className="text-xl font-semibold text-off-black">FMU Platform</h1>
          <p className="text-sm text-brown mt-1">Admin Panel</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white border border-beige rounded-xl p-6 space-y-5">
          {error && (
            <div className="bg-red/5 border border-red/20 text-red text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="username" className="block text-sm font-medium text-off-black mb-1.5">
              Username
            </label>
            <input
              id="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg bg-off-white border border-beige px-3 py-2.5 text-sm text-off-black placeholder-brown/40 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
              placeholder="Enter username"
              autoComplete="username"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-off-black mb-1.5">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg bg-off-white border border-beige px-3 py-2.5 text-sm text-off-black placeholder-brown/40 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
              placeholder="Enter password"
              autoComplete="current-password"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-navy hover:bg-navy/90 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg py-2.5 transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
