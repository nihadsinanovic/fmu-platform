import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { listAllJobs } from '../api'
import type { Job, JobStatus } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '—'
  const s = new Date(start)
  const e = end ? new Date(end) : new Date()
  const ms = e.getTime() - s.getTime()
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ${secs % 60}s`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function StatusBadge({ status }: { status: JobStatus }) {
  const styles: Record<JobStatus, string> = {
    queued: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    running: 'bg-blue-50 text-blue-700 ring-1 ring-blue-200',
    completed: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    failed: 'bg-red/5 text-red ring-1 ring-red/20',
  }
  const dots: Record<JobStatus, string> = {
    queued: 'bg-amber-500',
    running: 'bg-blue-500 animate-pulse',
    completed: 'bg-emerald-500',
    failed: 'bg-red',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${styles[status]}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dots[status]}`} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}

// ── WebSocket live tracker ────────────────────────────────────────────────────

function useJobWebSocket(jobId: string | null, onUpdate: (msg: { status: string; progress?: number; message?: string }) => void) {
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!jobId) return
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/jobs/${jobId}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string) as { status: string; progress?: number; message?: string }
        onUpdate(data)
      } catch { /* ignore parse errors */ }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [jobId, onUpdate])
}

// ── Live job detail ───────────────────────────────────────────────────────────

function LiveJobRow({ job: initial, onViewResults }: { job: Job; onViewResults: (id: string) => void }) {
  const [job, setJob] = useState<Job>(initial)
  const isActive = initial.status === 'queued' || initial.status === 'running'

  const handleWsMessage = useCallback((msg: { status: string; progress?: number; message?: string }) => {
    setJob((prev) => ({ ...prev, status: msg.status as JobStatus }))
  }, [])

  useJobWebSocket(isActive ? initial.id : null, handleWsMessage)

  // Update when parent refreshes
  useEffect(() => { setJob(initial) }, [initial])

  return (
    <tr className="hover:bg-off-white transition-colors group">
      <td className="px-5 py-4">
        <div>
          <p className="text-sm font-medium text-off-black">{job.project_name}</p>
          <p className="text-xs font-mono text-brown mt-0.5">{job.id.slice(0, 8)}…</p>
        </div>
      </td>
      <td className="px-5 py-4">
        <StatusBadge status={job.status} />
      </td>
      <td className="px-5 py-4 text-sm text-brown">
        {formatTime(job.queued_at)}
      </td>
      <td className="px-5 py-4 text-sm text-brown">
        {job.status === 'running' && job.started_at
          ? <span className="text-brand-blue font-mono text-xs">{formatDuration(job.started_at, null)}</span>
          : job.status === 'completed'
            ? <span className="font-mono text-xs">{formatDuration(job.started_at, job.completed_at)}</span>
            : '—'}
      </td>
      <td className="px-5 py-4 text-right">
        {job.status === 'completed' && (
          <button
            onClick={() => onViewResults(job.id)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-navy hover:text-white bg-navy/10 hover:bg-navy rounded-lg transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
            </svg>
            View Results
          </button>
        )}
        {job.status === 'failed' && job.error_message && (
          <span
            title={job.error_message}
            className="inline-flex items-center gap-1.5 text-xs text-red cursor-help"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            Error (hover)
          </span>
        )}
      </td>
    </tr>
  )
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function StatsBar({ jobs }: { jobs: Job[] }) {
  const counts = jobs.reduce(
    (acc, j) => ({ ...acc, [j.status]: (acc[j.status] ?? 0) + 1 }),
    {} as Partial<Record<JobStatus, number>>,
  )

  const stats = [
    { label: 'Queued', value: counts.queued ?? 0, color: 'text-amber-600' },
    { label: 'Running', value: counts.running ?? 0, color: 'text-brand-blue' },
    { label: 'Completed', value: counts.completed ?? 0, color: 'text-emerald-600' },
    { label: 'Failed', value: counts.failed ?? 0, color: 'text-red' },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 md:gap-4 mb-6 md:mb-8">
      {stats.map(({ label, value, color }) => (
        <div key={label} className="bg-white border border-beige rounded-xl px-4 py-3 md:px-5 md:py-4">
          <p className={`text-xl md:text-2xl font-bold ${color}`}>{value}</p>
          <p className="text-xs text-brown mt-1">{label}</p>
        </div>
      ))}
    </div>
  )
}

// ── Filter bar ────────────────────────────────────────────────────────────────

const FILTER_OPTIONS: Array<{ label: string; value: JobStatus | 'all' }> = [
  { label: 'All', value: 'all' },
  { label: 'Queued', value: 'queued' },
  { label: 'Running', value: 'running' },
  { label: 'Completed', value: 'completed' },
  { label: 'Failed', value: 'failed' },
]

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SimulationJobs() {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<JobStatus | 'all'>('all')
  const [autoRefresh, setAutoRefresh] = useState(true)

  async function load(silent = false) {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const data = await listAllJobs()
      setJobs(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs')
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  // Auto-refresh when there are active jobs
  useEffect(() => {
    if (!autoRefresh) return
    const hasActive = jobs.some((j) => j.status === 'queued' || j.status === 'running')
    if (!hasActive) return
    const interval = setInterval(() => void load(true), 5000)
    return () => clearInterval(interval)
  }, [jobs, autoRefresh])

  const filtered = filter === 'all' ? jobs : jobs.filter((j) => j.status === filter)

  return (
    <div className="p-4 sm:p-6 md:p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-off-black">Simulation Jobs</h1>
          <p className="text-sm text-brown mt-1">All composition and simulation runs</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-brown cursor-pointer select-none">
            <div
              onClick={() => setAutoRefresh((v) => !v)}
              className={`w-9 h-5 rounded-full relative transition-colors ${autoRefresh ? 'bg-navy' : 'bg-beige'}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${autoRefresh ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </div>
            Auto-refresh
          </label>
          <button
            onClick={() => void load()}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-brown hover:text-off-black bg-white hover:bg-beige border border-beige rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Stats */}
      {jobs.length > 0 && <StatsBar jobs={jobs} />}

      {/* Filter tabs */}
      <div className="flex gap-1 mb-6 bg-white border border-beige rounded-lg p-1 w-fit">
        {FILTER_OPTIONS.map(({ label, value }) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              filter === value
                ? 'bg-navy text-white'
                : 'text-brown hover:text-off-black'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 bg-red/5 border border-red/20 rounded-lg px-4 py-3 text-sm text-red">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-16 bg-beige/50 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty */}
      {!loading && !error && filtered.length === 0 && (
        <div className="text-center py-24 text-brown">
          <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
          </svg>
          <p className="text-sm">
            {filter === 'all' ? 'No simulation jobs yet.' : `No ${filter} jobs.`}
          </p>
        </div>
      )}

      {/* Table */}
      {!loading && filtered.length > 0 && (
        <div className="bg-white border border-beige rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-beige">
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-brown uppercase tracking-wider">Project</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-brown uppercase tracking-wider">Status</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-brown uppercase tracking-wider">Queued At</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-brown uppercase tracking-wider">Duration</th>
                <th className="text-right px-5 py-3.5 text-xs font-semibold text-brown uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-beige">
              {filtered.map((job) => (
                <LiveJobRow
                  key={job.id}
                  job={job}
                  onViewResults={(id) => navigate(`/results/${id}`)}
                />
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  )
}
