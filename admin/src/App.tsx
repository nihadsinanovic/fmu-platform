import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import FMULibrary from './pages/FMULibrary'
import FMUDetail from './pages/FMUDetail'
import SimulationJobs from './pages/SimulationJobs'
import ResultsViewer from './pages/ResultsViewer'

export default function App() {
  return (
    <BrowserRouter basename="/admin">
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/fmu-library" replace />} />
          <Route path="fmu-library" element={<FMULibrary />} />
          <Route path="fmu-library/:typeName" element={<FMUDetail />} />
          <Route path="jobs" element={<SimulationJobs />} />
          <Route path="results/:jobId?" element={<ResultsViewer />} />
          <Route path="*" element={<Navigate to="/fmu-library" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
