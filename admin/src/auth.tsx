import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface AuthState {
  token: string | null
  username: string | null
}

interface AuthContextValue extends AuthState {
  login: (token: string, username: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const STORAGE_KEY = 'fmu_auth'

function loadAuth(): AuthState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as AuthState
  } catch { /* ignore */ }
  return { token: null, username: null }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadAuth)

  useEffect(() => {
    if (state.token) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [state])

  const login = (token: string, username: string) => setState({ token, username })
  const logout = () => setState({ token: null, username: null })

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
