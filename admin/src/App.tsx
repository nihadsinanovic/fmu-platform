import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import Layout from './components/Layout'
import FMULibrary from './pages/FMULibrary'
import FMUDetail from './pages/FMUDetail'
import SimulationJobs from './pages/SimulationJobs'
import ResultsViewer from './pages/ResultsViewer'
import Accounts from './pages/Accounts'
import Login from './pages/Login'

function ProtectedRoutes() {
  const { token, isAdmin } = useAuth()
  if (!token) return <Navigate to="/login" replace />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/fmu-library" replace />} />
        <Route path="fmu-library" element={<FMULibrary />} />
        <Route path="fmu-library/:typeName" element={<FMUDetail />} />
        <Route path="jobs" element={<SimulationJobs />} />
        <Route path="results/:jobId?" element={<ResultsViewer />} />
        {isAdmin && <Route path="accounts" element={<Accounts />} />}
        <Route path="*" element={<Navigate to="/fmu-library" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename="/admin">
        <Routes>
          <Route path="/login" element={<LoginGuard />} />
          <Route path="/*" element={<ProtectedRoutes />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

function LoginGuard() {
  const { token } = useAuth()
  if (token) return <Navigate to="/fmu-library" replace />
  return <Login />
}
