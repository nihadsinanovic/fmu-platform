import { useEffect, useState } from 'react'
import { listUsers, createUser, updateUser, deleteUser, type UserInfo } from '../api'
import { useAuth } from '../auth'

export default function Accounts() {
  const { username: currentUsername } = useAuth()
  const [users, setUsers] = useState<UserInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Create form
  const [showCreate, setShowCreate] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newIsAdmin, setNewIsAdmin] = useState(false)
  const [creating, setCreating] = useState(false)

  // Reset password
  const [resetId, setResetId] = useState<string | null>(null)
  const [resetPassword, setResetPassword] = useState('')

  async function load() {
    try {
      setUsers(await listUsers())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreating(true)
    setError('')
    try {
      await createUser(newUsername, newPassword, newIsAdmin)
      setNewUsername('')
      setNewPassword('')
      setNewIsAdmin(false)
      setShowCreate(false)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setCreating(false)
    }
  }

  async function handleToggleAdmin(user: UserInfo) {
    setError('')
    try {
      await updateUser(user.id, { is_admin: !user.is_admin })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update user')
    }
  }

  async function handleResetPassword(userId: string) {
    setError('')
    try {
      await updateUser(userId, { password: resetPassword })
      setResetId(null)
      setResetPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset password')
    }
  }

  async function handleDelete(user: UserInfo) {
    if (!confirm(`Delete user "${user.username}"? This cannot be undone.`)) return
    setError('')
    try {
      await deleteUser(user.id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete user')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-navy border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="p-6 md:p-10 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-off-black">Accounts</h1>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="bg-navy hover:bg-navy/90 text-white text-sm font-medium rounded-lg px-4 py-2 transition-colors"
        >
          {showCreate ? 'Cancel' : 'New Account'}
        </button>
      </div>

      {error && (
        <div className="bg-red/5 border border-red/20 text-red text-sm rounded-lg px-4 py-3 mb-4">
          {error}
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white border border-beige rounded-xl p-5 mb-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-off-black mb-1">Username</label>
              <input
                type="text"
                required
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                className="w-full rounded-lg bg-off-white border border-beige px-3 py-2 text-sm text-off-black placeholder-brown/40 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
                placeholder="username"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-off-black mb-1">Password</label>
              <input
                type="password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full rounded-lg bg-off-white border border-beige px-3 py-2 text-sm text-off-black placeholder-brown/40 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
                placeholder="password"
              />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-off-black cursor-pointer">
              <input
                type="checkbox"
                checked={newIsAdmin}
                onChange={(e) => setNewIsAdmin(e.target.checked)}
                className="rounded border-beige bg-off-white text-navy focus:ring-navy"
              />
              Admin privileges
            </label>
            <button
              type="submit"
              disabled={creating}
              className="bg-navy hover:bg-navy/90 disabled:opacity-50 text-white text-sm font-medium rounded-lg px-4 py-2 transition-colors"
            >
              {creating ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      )}

      {/* User list — cards on mobile, table on md+ */}
      <div className="space-y-3 md:hidden">
        {users.map((user) => {
          const isSelf = user.username.toLowerCase() === currentUsername?.toLowerCase()
          return (
            <div key={user.id} className="bg-white border border-beige rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-off-black font-medium">{user.username}</span>
                  {isSelf && <span className="text-xs text-brown">(you)</span>}
                </div>
                {user.is_admin ? (
                  <span className="text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5">
                    Admin
                  </span>
                ) : (
                  <span className="text-xs font-medium text-brown bg-beige border border-beige rounded-full px-2.5 py-0.5">
                    User
                  </span>
                )}
              </div>
              {resetId === user.id ? (
                <form
                  onSubmit={(e) => { e.preventDefault(); handleResetPassword(user.id) }}
                  className="flex items-center gap-2"
                >
                  <input
                    type="password"
                    required
                    value={resetPassword}
                    onChange={(e) => setResetPassword(e.target.value)}
                    placeholder="New password"
                    className="flex-1 rounded-lg bg-off-white border border-beige px-3 py-1.5 text-sm text-off-black placeholder-brown/40 focus:outline-none focus:ring-1 focus:ring-navy"
                  />
                  <button type="submit" className="text-xs text-navy hover:text-navy/80 transition-colors">Save</button>
                  <button type="button" onClick={() => { setResetId(null); setResetPassword('') }} className="text-xs text-brown hover:text-off-black transition-colors">Cancel</button>
                </form>
              ) : (
                <div className="flex items-center gap-3 pt-1 border-t border-beige">
                  {!isSelf && (
                    <button onClick={() => handleToggleAdmin(user)} className="text-xs text-brown hover:text-navy transition-colors">
                      {user.is_admin ? 'Revoke admin' : 'Make admin'}
                    </button>
                  )}
                  <button onClick={() => { setResetId(user.id); setResetPassword('') }} className="text-xs text-brown hover:text-navy transition-colors">
                    Reset password
                  </button>
                  {!isSelf && (
                    <button onClick={() => handleDelete(user)} className="text-xs text-brown hover:text-red transition-colors ml-auto">
                      Delete
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
        {users.length === 0 && (
          <p className="text-center text-brown py-8 text-sm">No accounts found.</p>
        )}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block bg-white border border-beige rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-beige text-brown">
              <th className="text-left px-5 py-3 font-medium">Username</th>
              <th className="text-left px-5 py-3 font-medium">Role</th>
              <th className="text-right px-5 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const isSelf = user.username.toLowerCase() === currentUsername?.toLowerCase()
              return (
                <tr key={user.id} className="border-b border-beige/50 last:border-b-0">
                  <td className="px-5 py-3 text-off-black">
                    {user.username}
                    {isSelf && <span className="ml-2 text-xs text-brown">(you)</span>}
                  </td>
                  <td className="px-5 py-3">
                    {user.is_admin ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5">
                        Admin
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-brown bg-beige border border-beige rounded-full px-2.5 py-0.5">
                        User
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      {!isSelf && (
                        <button
                          onClick={() => handleToggleAdmin(user)}
                          className="text-xs text-brown hover:text-navy transition-colors"
                        >
                          {user.is_admin ? 'Revoke admin' : 'Make admin'}
                        </button>
                      )}
                      {resetId === user.id ? (
                        <form
                          onSubmit={(e) => { e.preventDefault(); handleResetPassword(user.id) }}
                          className="flex items-center gap-1"
                        >
                          <input
                            type="password"
                            required
                            value={resetPassword}
                            onChange={(e) => setResetPassword(e.target.value)}
                            placeholder="New password"
                            className="w-32 rounded bg-off-white border border-beige px-2 py-1 text-xs text-off-black placeholder-brown/40 focus:outline-none focus:ring-1 focus:ring-navy"
                          />
                          <button type="submit" className="text-xs text-navy hover:text-navy/80 transition-colors">Save</button>
                          <button type="button" onClick={() => { setResetId(null); setResetPassword('') }} className="text-xs text-brown hover:text-off-black transition-colors">Cancel</button>
                        </form>
                      ) : (
                        <button
                          onClick={() => { setResetId(user.id); setResetPassword('') }}
                          className="text-xs text-brown hover:text-navy transition-colors"
                        >
                          Reset password
                        </button>
                      )}
                      {!isSelf && (
                        <button
                          onClick={() => handleDelete(user)}
                          className="text-xs text-brown hover:text-red transition-colors"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {users.length === 0 && (
          <p className="text-center text-brown py-8 text-sm">No accounts found.</p>
        )}
      </div>
    </div>
  )
}
