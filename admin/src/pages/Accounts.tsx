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
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="p-6 md:p-10 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Accounts</h1>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg px-4 py-2 transition-colors"
        >
          {showCreate ? 'Cancel' : 'New Account'}
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm rounded-lg px-4 py-3 mb-4">
          {error}
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <form onSubmit={handleCreate} className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Username</label>
              <input
                type="text"
                required
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                placeholder="username"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Password</label>
              <input
                type="password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                placeholder="password"
              />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={newIsAdmin}
                onChange={(e) => setNewIsAdmin(e.target.checked)}
                className="rounded border-gray-600 bg-gray-800 text-indigo-600 focus:ring-indigo-500"
              />
              Admin privileges
            </label>
            <button
              type="submit"
              disabled={creating}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg px-4 py-2 transition-colors"
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
            <div key={user.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-white font-medium">{user.username}</span>
                  {isSelf && <span className="text-xs text-gray-500">(you)</span>}
                </div>
                {user.is_admin ? (
                  <span className="text-xs font-medium text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-full px-2.5 py-0.5">
                    Admin
                  </span>
                ) : (
                  <span className="text-xs font-medium text-gray-400 bg-gray-700/50 border border-gray-700 rounded-full px-2.5 py-0.5">
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
                    className="flex-1 rounded-lg bg-gray-800 border border-gray-700 px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  <button type="submit" className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">Save</button>
                  <button type="button" onClick={() => { setResetId(null); setResetPassword('') }} className="text-xs text-gray-500 hover:text-gray-300 transition-colors">Cancel</button>
                </form>
              ) : (
                <div className="flex items-center gap-3 pt-1 border-t border-gray-800">
                  {!isSelf && (
                    <button onClick={() => handleToggleAdmin(user)} className="text-xs text-gray-400 hover:text-indigo-400 transition-colors">
                      {user.is_admin ? 'Revoke admin' : 'Make admin'}
                    </button>
                  )}
                  <button onClick={() => { setResetId(user.id); setResetPassword('') }} className="text-xs text-gray-400 hover:text-indigo-400 transition-colors">
                    Reset password
                  </button>
                  {!isSelf && (
                    <button onClick={() => handleDelete(user)} className="text-xs text-gray-400 hover:text-red-400 transition-colors ml-auto">
                      Delete
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
        {users.length === 0 && (
          <p className="text-center text-gray-500 py-8 text-sm">No accounts found.</p>
        )}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left px-5 py-3 font-medium">Username</th>
              <th className="text-left px-5 py-3 font-medium">Role</th>
              <th className="text-right px-5 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const isSelf = user.username.toLowerCase() === currentUsername?.toLowerCase()
              return (
                <tr key={user.id} className="border-b border-gray-800/50 last:border-b-0">
                  <td className="px-5 py-3 text-white">
                    {user.username}
                    {isSelf && <span className="ml-2 text-xs text-gray-500">(you)</span>}
                  </td>
                  <td className="px-5 py-3">
                    {user.is_admin ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-full px-2.5 py-0.5">
                        Admin
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-400 bg-gray-700/50 border border-gray-700 rounded-full px-2.5 py-0.5">
                        User
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      {!isSelf && (
                        <button
                          onClick={() => handleToggleAdmin(user)}
                          className="text-xs text-gray-400 hover:text-indigo-400 transition-colors"
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
                            className="w-32 rounded bg-gray-800 border border-gray-700 px-2 py-1 text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          />
                          <button type="submit" className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">Save</button>
                          <button type="button" onClick={() => { setResetId(null); setResetPassword('') }} className="text-xs text-gray-500 hover:text-gray-300 transition-colors">Cancel</button>
                        </form>
                      ) : (
                        <button
                          onClick={() => { setResetId(user.id); setResetPassword('') }}
                          className="text-xs text-gray-400 hover:text-indigo-400 transition-colors"
                        >
                          Reset password
                        </button>
                      )}
                      {!isSelf && (
                        <button
                          onClick={() => handleDelete(user)}
                          className="text-xs text-gray-400 hover:text-red-400 transition-colors"
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
          <p className="text-center text-gray-500 py-8 text-sm">No accounts found.</p>
        )}
      </div>
    </div>
  )
}
