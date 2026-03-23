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
        plot_bgcolor: '#FFFFFF',
        font: { color: '#232222', size: 11, family: '"Host Grotesk", system-ui, sans-serif' },
        xaxis: {
          title: { text: 'Time (hours)', font: { color: '#91877A' } },
          gridcolor: '#E5E6DF',
          linecolor: '#E5E6DF',
          tickcolor: '#91877A',
          zerolinecolor: '#E5E6DF',
        },
        yaxis: {
          gridcolor: '#E5E6DF',
          linecolor: '#E5E6DF',
          tickcolor: '#91877A',
          zerolinecolor: '#E5E6DF',
        },
        legend: {
          bgcolor: 'rgba(255,255,255,0.9)',
          bordercolor: '#E5E6DF',
          borderwidth: 1,
          font: { color: '#232222', size: 10 },
        },
        margin: { t: 20, r: 20, b: 50, l: 60 },
        hovermode: 'x unified' as const,
        hoverlabel: { bgcolor: '#FFFFFF', bordercolor: '#E5E6DF', font: { color: '#232222' } },
        colorway: ['#002656', '#3164FD', '#4AA1FF', '#C41230', '#FF8D5A', '#F7E36E', '#91877A'],
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
      <div className="flex items-center justify-center h-80 text-brown text-sm">
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
        <p className="text-xs font-semibold text-brown uppercase tracking-wider">Variables</p>
        <div className="flex gap-2">
          <button onClick={onSelectAll} className="text-xs text-navy hover:text-navy/80">All</button>
          <span className="text-beige">·</span>
          <button onClick={onClearAll} className="text-xs text-brown hover:text-off-black">None</button>
        </div>
      </div>

      <input
        type="text"
        placeholder="Filter…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full bg-off-white border border-beige rounded-lg px-3 py-2 text-xs text-off-black placeholder-brown/40 focus:outline-none focus:ring-1 focus:ring-navy mb-3"
      />

      <div className="flex-1 overflow-y-auto space-y-0.5 min-h-0">
        {filtered.map((v) => {
          const isSelected = selected.includes(v)
          return (
            <label
              key={v}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors ${
                isSelected ? 'bg-navy/10 text-navy' : 'text-brown hover:bg-off-white hover:text-off-black'
              }`}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggle(v)}
                className="rounded border-beige bg-off-white text-navy focus:ring-navy focus:ring-offset-0 w-3 h-3"
              />
              <span className="text-xs font-mono truncate">{v}</span>
            </label>
          )
        })}
        {filtered.length === 0 && (
          <p className="text-xs text-brown/50 px-2 py-2">No variables match</p>
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
      <label className="block text-xs font-semibold text-brown uppercase tracking-wider mb-2">
        Select Simulation Run
      </label>
      <select
        value={selectedId ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        className="bg-white border border-beige rounded-lg px-3 py-2 text-sm text-off-black focus:outline-none focus:ring-2 focus:ring-navy w-full max-w-lg"
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
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4 mb-6">
      {[
        { label: 'Simulation Duration', value: `${durationH} h` },
        { label: 'Time Steps', value: steps.toLocaleString() },
        { label: 'Output Variables', value: nonTimeVars.length },
      ].map(({ label, value }) => (
        <div key={label} className="bg-white border border-beige rounded-xl px-4 py-3">
          <p className="text-xl font-bold text-off-black">{value}</p>
          <p className="text-xs text-brown mt-0.5">{label}</p>
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
    <div className="p-4 sm:p-6 md:p-8 h-full flex flex-col">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-off-black">Results Viewer</h1>
        <p className="text-sm text-brown mt-1">Time-series simulation output</p>
      </div>

      {/* Job picker */}
      {!jobsLoading && (
        <JobPicker jobs={jobs} selectedId={selectedJobId} onSelect={handleSelectJob} />
      )}

      {/* No completed jobs */}
      {!jobsLoading && jobs.filter((j) => j.status === 'completed').length === 0 && (
        <div className="text-center py-24 text-brown">
          <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
          </svg>
          <p className="text-sm">No completed simulations yet.</p>
        </div>
      )}

      {/* Loading results */}
      {resultsLoading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-brown">
            <div className="w-8 h-8 border-2 border-navy border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-sm">Loading results…</p>
          </div>
        </div>
      )}

      {/* Error */}
      {resultsError && (
        <div className="bg-red/5 border border-red/20 rounded-xl px-5 py-4 text-sm text-red">
          {resultsError}
        </div>
      )}

      {/* Results */}
      {resultsData && !resultsLoading && (
        <>
          <SummaryCards data={resultsData} />

          <div className="flex flex-col md:flex-row gap-4 md:gap-6 flex-1 min-h-0">
            {/* Variable selector */}
            <div className="md:w-56 md:flex-shrink-0 bg-white border border-beige rounded-xl p-4 overflow-hidden flex flex-col md:h-full h-48">
              <VariableSelector
                variables={resultsData.variables}
                selected={selectedVars}
                onToggle={toggleVar}
                onSelectAll={() => setSelectedVars(nonTimeVars)}
                onClearAll={() => setSelectedVars([])}
              />
            </div>

            {/* Chart */}
            <div className="flex-1 bg-white border border-beige rounded-xl p-4 overflow-hidden">
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
