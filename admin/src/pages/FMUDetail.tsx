import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getFMUManifest, runFMUTest } from '../api'
import type { FMUManifest, FMUTestRunResult } from '../types'

// ── Plotly chart for test-run results ─────────────────────────────────────────

function TestRunChart({ result }: { result: FMUTestRunResult }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const outputNames = Object.keys(result.outputs)
    if (outputNames.length === 0) return

    void import('plotly.js-dist-min').then((Plotly) => {
      if (!containerRef.current) return

      const traces = outputNames.map((name) => ({
        x: result.time,
        y: result.outputs[name],
        type: 'scatter' as const,
        mode: 'lines' as const,
        name,
        line: { width: 1.5 },
      }))

      const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'rgb(17, 24, 39)',
        font: { color: '#9ca3af', size: 11, family: 'ui-monospace, monospace' },
        xaxis: {
          title: { text: 'Time (s)', font: { color: '#6b7280' } },
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

      void Plotly.default.react(containerRef.current, traces, layout, {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'] as never[],
        displaylogo: false,
      })
    })
  }, [result])

  return <div ref={containerRef} className="w-full" style={{ height: 350 }} />
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function FMUDetail() {
  const { typeName } = useParams<{ typeName: string }>()
  const navigate = useNavigate()

  const [manifest, setManifest] = useState<FMUManifest | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Test run state
  const [inputValues, setInputValues] = useState<Record<string, string>>({})
  const [startTime, setStartTime] = useState('0')
  const [endTime, setEndTime] = useState('10')
  const [ncp, setNcp] = useState('100')
  const [runLoading, setRunLoading] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runResult, setRunResult] = useState<FMUTestRunResult | null>(null)

  useEffect(() => {
    if (!typeName) return
    setLoading(true)
    setError(null)
    getFMUManifest(typeName)
      .then((m) => {
        setManifest(m)
        const defaults: Record<string, string> = {}
        m.inputs.forEach((p) => { defaults[p.name] = '0.0' })
        setInputValues(defaults)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load manifest'))
      .finally(() => setLoading(false))
  }, [typeName])

  async function handleRunTest() {
    if (!typeName || !manifest) return
    setRunLoading(true)
    setRunError(null)
    setRunResult(null)
    try {
      const inputs: Record<string, number> = {}
      manifest.inputs.forEach((p) => {
        inputs[p.name] = parseFloat(inputValues[p.name] ?? '0') || 0
      })
      const result = await runFMUTest(typeName, {
        inputs,
        start_time: parseFloat(startTime) || 0,
        end_time: parseFloat(endTime) || 10,
        ncp: parseInt(ncp, 10) || 100,
      })
      setRunResult(result)
    } catch (err) {
      setRunError(err instanceof Error ? err.message : 'Test run failed')
    } finally {
      setRunLoading(false)
    }
  }

  const outputCount = runResult ? Object.keys(runResult.outputs).length : 0

  return (
    <div className="p-4 sm:p-6 md:p-8">
      {/* Back button + header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/fmu-library')}
          className="p-2 text-gray-500 hover:text-gray-300 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors flex-shrink-0"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
        </button>
        <div className="min-w-0">
          <p className="text-xs text-gray-500">FMU Library</p>
          <h1 className="text-xl font-bold text-white font-mono truncate">{typeName}</h1>
        </div>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-gray-800/50 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-rose-950/60 border border-rose-800 rounded-lg px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {manifest && (
        <div className="space-y-5">
          {/* ── Metadata ── */}
          <section className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">Metadata</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {([
                ['FMI Version', manifest.fmi_version],
                ['FMI Type', manifest.fmi_type],
                ['Version', manifest.version],
                ['Generation Tool', manifest.generation_tool],
              ] as [string, string][]).map(([label, value]) => (
                <div key={label} className="bg-gray-800 rounded-lg px-3 py-2.5">
                  <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                  <p className="text-sm text-gray-200 font-medium truncate">{value || '—'}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <div className="bg-gray-800/60 rounded-lg px-3 py-2">
                <p className="text-xs text-gray-500 mb-0.5">Model Identifier</p>
                <p className="text-xs font-mono text-gray-300 break-all">{manifest.model_identifier || '—'}</p>
              </div>
              <div className="bg-gray-800/60 rounded-lg px-3 py-2">
                <p className="text-xs text-gray-500 mb-0.5">GUID</p>
                <p className="text-xs font-mono text-gray-300 break-all">{manifest.guid || '—'}</p>
              </div>
            </div>
          </section>

          {/* ── Ports ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <section className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
                Inputs ({manifest.inputs.length})
              </h2>
              {manifest.inputs.length === 0 ? (
                <p className="text-gray-600 text-xs">No inputs</p>
              ) : (
                <div className="space-y-2">
                  {manifest.inputs.map((p) => (
                    <div key={p.name} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-indigo-400 flex-shrink-0" />
                      <span className="text-xs font-mono text-indigo-300 truncate">{p.name}</span>
                      <span className="text-xs text-gray-600 ml-auto flex-shrink-0">{p.type}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
                Outputs ({manifest.outputs.length})
              </h2>
              {manifest.outputs.length === 0 ? (
                <p className="text-gray-600 text-xs">No outputs</p>
              ) : (
                <div className="space-y-2">
                  {manifest.outputs.map((p) => (
                    <div key={p.name} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
                      <span className="text-xs font-mono text-emerald-300 truncate">{p.name}</span>
                      <span className="text-xs text-gray-600 ml-auto flex-shrink-0">{p.type}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* ── Test Run ── */}
          <section className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-5">Test Run</h2>

            {/* Input variables */}
            {manifest.inputs.length > 0 && (
              <div className="mb-5">
                <p className="text-xs text-gray-500 mb-3">Input Values (constant throughout simulation)</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {manifest.inputs.map((p) => (
                    <div key={p.name}>
                      <label className="block text-xs font-medium text-indigo-400 mb-1 font-mono truncate">
                        {p.name}
                      </label>
                      <input
                        type="number"
                        step="any"
                        value={inputValues[p.name] ?? '0.0'}
                        onChange={(e) =>
                          setInputValues((prev) => ({ ...prev, [p.name]: e.target.value }))
                        }
                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Simulation time controls */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Start Time (s)</label>
                <input
                  type="number"
                  step="any"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">End Time (s)</label>
                <input
                  type="number"
                  step="any"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Communication Points</label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={ncp}
                  onChange={(e) => setNcp(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
                />
              </div>
            </div>

            {/* Run button */}
            <button
              onClick={() => void handleRunTest()}
              disabled={runLoading}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed rounded-lg transition-colors"
            >
              {runLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Running…
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                  </svg>
                  Run Test
                </>
              )}
            </button>

            {/* Error */}
            {runError && (
              <div className="mt-4 bg-rose-950/60 border border-rose-800 rounded-lg px-4 py-3 text-sm text-rose-300">
                {runError}
              </div>
            )}

            {/* Results chart */}
            {runResult && !runLoading && (
              <div className="mt-6">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                  Results — {outputCount} output variable{outputCount !== 1 ? 's' : ''}
                </p>
                {outputCount === 0 ? (
                  <p className="text-gray-600 text-sm">No output variables returned.</p>
                ) : (
                  <div className="bg-gray-800/50 rounded-xl p-3 overflow-hidden">
                    <TestRunChart result={runResult} />
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
