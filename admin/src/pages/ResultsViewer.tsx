import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { listAllJobs, getResultData } from '../api'
import type { Job, ResultsData } from '../types'

// ── Plotly chart wrapper ──────────────────────────────────────────────────────

interface PlotProps {
  variables: string[]
  selected: string[]
  data: ResultsData
}

function TimeSeriesPlot({ variables, selected, data }: PlotProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || selected.length === 0) return

    const timeKey = variables.includes('time') ? 'time' : variables[0]
    const timeData = data.data[timeKey] ?? []

    // Convert time (seconds) to hours for readability
    const xData = timeData.map((t) => t / 3600)

    void import('plotly.js-dist-min').then((Plotly) => {
      if (!containerRef.current) return

      const traces = selected
        .filter((v) => v !== timeKey)
        .map((varName) => ({
          x: xData,
          y: data.data[varName] ?? [],
          type: 'scatter' as const,
          mode: 'lines' as const,
          name: varName,
          line: { width: 1.5 },
        }))

      const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'rgb(17, 24, 39)',
        font: { color: '#9ca3af', size: 11, family: 'ui-monospace, monospace' },
        xaxis: {
          title: { text: 'Time (hours)', font: { color: '#6b7280' } },
          gridcolor: '#1f2937',
          linecolor: '#374151',
          tickcolor: '#374151',
          zerolinecolor: '#374151',
        },
        yaxis: {
          gridcolor: '#1f2937',
          linecolor: '#374151',
          tickcolor: '#374151',
          zerolinecolor: '#374151',
        },
        legend: {
          bgcolor: 'rgba(17,24,39,0.8)',
          bordercolor: '#374151',
          borderwidth: 1,
          font: { color: '#d1d5db', size: 10 },
        },
        margin: { t: 20, r: 20, b: 50, l: 60 },
        hovermode: 'x unified' as const,
        hoverlabel: { bgcolor: '#1f2937', bordercolor: '#374151', font: { color: '#e5e7eb' } },
      }

      const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'] as never[],
        displaylogo: false,
      }

      void Plotly.default.react(containerRef.current, traces, layout, config)
    })
  }, [selected, data, variables])

  if (selected.length === 0) {
    return (
      <div className="flex items-center justify-center h-80 text-gray-600 text-sm">
        Select variables on the left to plot them
      </div>
    )
  }

  return <div ref={containerRef} className="w-full" style={{ height: 400 }} />
}

// ── Variable selector ─────────────────────────────────────────────────────────

function VariableSelector({
  variables,
  selected,
  onToggle,
  onSelectAll,
  onClearAll,
}: {
  variables: string[]
  selected: string[]
  onToggle: (v: string) => void
  onSelectAll: () => void
  onClearAll: () => void
}) {
  const [search, setSearch] = useState('')
  const filtered = variables.filter((v) =>
    v !== 'time' && v.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Variables</p>
        <div className="flex gap-2">
          <button onClick={onSelectAll} className="text-xs text-indigo-400 hover:text-indigo-300">All</button>
          <span className="text-gray-700">·</span>
          <button onClick={onClearAll} className="text-xs text-gray-500 hover:text-gray-300">None</button>
        </div>
      </div>

      <input
        type="text"
        placeholder="Filter…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 mb-3"
      />

      <div className="flex-1 overflow-y-auto space-y-0.5 min-h-0">
        {filtered.map((v) => {
          const isSelected = selected.includes(v)
          return (
            <label
              key={v}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors ${
                isSelected ? 'bg-indigo-900/30 text-indigo-300' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
              }`}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggle(v)}
                className="rounded border-gray-600 bg-gray-800 text-indigo-600 focus:ring-indigo-600 focus:ring-offset-0 w-3 h-3"
              />
              <span className="text-xs font-mono truncate">{v}</span>
            </label>
          )
        })}
        {filtered.length === 0 && (
          <p className="text-xs text-gray-600 px-2 py-2">No variables match</p>
        )}
      </div>
    </div>
  )
}

// ── Job picker ────────────────────────────────────────────────────────────────

function JobPicker({ jobs, selectedId, onSelect }: {
  jobs: Job[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const completed = jobs.filter((j) => j.status === 'completed')
  if (completed.length === 0) return null

  return (
    <div className="mb-6">
      <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        Select Simulation Run
      </label>
      <select
        value={selectedId ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-600 w-full max-w-lg"
      >
        <option value="" disabled>Choose a completed job…</option>
        {completed.map((j) => (
          <option key={j.id} value={j.id}>
            {j.project_name} — {j.id.slice(0, 8)} —{' '}
            {j.completed_at ? new Date(j.completed_at).toLocaleString() : ''}
          </option>
        ))}
      </select>
    </div>
  )
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function SummaryCards({ data }: { data: ResultsData }) {
  const timeArr = data.data['time'] ?? []
  const durationH = timeArr.length > 1
    ? ((timeArr[timeArr.length - 1] - timeArr[0]) / 3600).toFixed(1)
    : '—'
  const steps = timeArr.length

  const nonTimeVars = data.variables.filter((v) => v !== 'time')

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      {[
        { label: 'Simulation Duration', value: `${durationH} h` },
        { label: 'Time Steps', value: steps.toLocaleString() },
        { label: 'Output Variables', value: nonTimeVars.length },
      ].map(({ label, value }) => (
        <div key={label} className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
          <p className="text-xl font-bold text-white">{value}</p>
          <p className="text-xs text-gray-500 mt-0.5">{label}</p>
        </div>
      ))}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ResultsViewer() {
  const { jobId: routeJobId } = useParams<{ jobId?: string }>()
  const navigate = useNavigate()

  const [jobs, setJobs] = useState<Job[]>([])
  const [jobsLoading, setJobsLoading] = useState(true)

  const [selectedJobId, setSelectedJobId] = useState<string | null>(routeJobId ?? null)
  const [resultsData, setResultsData] = useState<ResultsData | null>(null)
  const [resultsLoading, setResultsLoading] = useState(false)
  const [resultsError, setResultsError] = useState<string | null>(null)

  const [selectedVars, setSelectedVars] = useState<string[]>([])

  // Load job list
  useEffect(() => {
    listAllJobs()
      .then(setJobs)
      .finally(() => setJobsLoading(false))
  }, [])

  // Sync route param
  useEffect(() => {
    if (routeJobId) setSelectedJobId(routeJobId)
  }, [routeJobId])

  // Load results when job selected
  useEffect(() => {
    if (!selectedJobId) return
    setResultsLoading(true)
    setResultsError(null)
    setResultsData(null)
    setSelectedVars([])

    getResultData(selectedJobId)
      .then((d) => {
        setResultsData(d)
        // Auto-select first 4 non-time variables
        const nonTime = d.variables.filter((v) => v !== 'time')
        setSelectedVars(nonTime.slice(0, 4))
      })
      .catch((err) => {
        setResultsError(err instanceof Error ? err.message : 'Failed to load results')
      })
      .finally(() => setResultsLoading(false))
  }, [selectedJobId])

  function handleSelectJob(id: string) {
    setSelectedJobId(id)
    navigate(`/results/${id}`, { replace: true })
  }

  function toggleVar(v: string) {
    setSelectedVars((prev) =>
      prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v],
    )
  }

  const nonTimeVars = resultsData?.variables.filter((v) => v !== 'time') ?? []

  return (
    <div className="p-8 h-full flex flex-col">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Results Viewer</h1>
        <p className="text-sm text-gray-500 mt-1">Time-series simulation output</p>
      </div>

      {/* Job picker */}
      {!jobsLoading && (
        <JobPicker jobs={jobs} selectedId={selectedJobId} onSelect={handleSelectJob} />
      )}

      {/* No completed jobs */}
      {!jobsLoading && jobs.filter((j) => j.status === 'completed').length === 0 && (
        <div className="text-center py-24 text-gray-600">
          <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
          </svg>
          <p className="text-sm">No completed simulations yet.</p>
        </div>
      )}

      {/* Loading results */}
      {resultsLoading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-gray-500">
            <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-sm">Loading results…</p>
          </div>
        </div>
      )}

      {/* Error */}
      {resultsError && (
        <div className="bg-rose-950/60 border border-rose-800 rounded-xl px-5 py-4 text-sm text-rose-300">
          {resultsError}
        </div>
      )}

      {/* Results */}
      {resultsData && !resultsLoading && (
        <>
          <SummaryCards data={resultsData} />

          <div className="flex gap-6 flex-1 min-h-0">
            {/* Variable selector */}
            <div className="w-56 flex-shrink-0 bg-gray-900 border border-gray-800 rounded-xl p-4 overflow-hidden flex flex-col">
              <VariableSelector
                variables={resultsData.variables}
                selected={selectedVars}
                onToggle={toggleVar}
                onSelectAll={() => setSelectedVars(nonTimeVars)}
                onClearAll={() => setSelectedVars([])}
              />
            </div>

            {/* Chart */}
            <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl p-4 overflow-hidden">
              <TimeSeriesPlot
                variables={resultsData.variables}
                selected={selectedVars}
                data={resultsData}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
