import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getFMUManifest, runFMUTest, listResources, uploadResource, deleteResource } from '../api'
import type { FMUManifest, FMUTestRunResult, DataFileEntry } from '../types'

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
        plot_bgcolor: '#FFFFFF',
        font: { color: '#232222', size: 11, family: '"Host Grotesk", system-ui, sans-serif' },
        xaxis: {
          title: { text: 'Time (s)', font: { color: '#91877A' } },
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

  // Data files state
  const [dataFiles, setDataFiles] = useState<DataFileEntry[]>([])
  const [dataLoading, setDataLoading] = useState(false)
  const [uploadingFile, setUploadingFile] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  // Load data files list
  useEffect(() => {
    if (!typeName) return
    setDataLoading(true)
    listResources(typeName)
      .then((r) => setDataFiles(r.resources))
      .catch(() => {})
      .finally(() => setDataLoading(false))
  }, [typeName])

  async function handleUploadDataFile(file: File) {
    if (!typeName) return
    setUploadingFile(true)
    try {
      await uploadResource(typeName, file)
      const r = await listResources(typeName)
      setDataFiles(r.resources)
    } catch {
      // ignore
    } finally {
      setUploadingFile(false)
    }
  }

  async function handleDeleteDataFile(filename: string) {
    if (!typeName) return
    try {
      await deleteResource(typeName, filename)
      setDataFiles((prev) => prev.filter((f) => f.name !== filename))
    } catch {
      // ignore
    }
  }

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
          className="p-2 text-brown hover:text-off-black bg-white hover:bg-beige border border-beige rounded-lg transition-colors flex-shrink-0"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
        </button>
        <div className="min-w-0">
          <p className="text-xs text-brown">FMU Library</p>
          <h1 className="text-xl font-bold text-off-black font-mono truncate">{typeName}</h1>
        </div>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-beige/50 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red/5 border border-red/20 rounded-lg px-4 py-3 text-sm text-red">
          {error}
        </div>
      )}

      {manifest && (
        <div className="space-y-5">
          {/* ── Metadata ── */}
          <section className="bg-white border border-beige rounded-xl p-5">
            <h2 className="text-xs font-semibold text-brown uppercase tracking-wider mb-4">Metadata</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {([
                ['FMI Version', manifest.fmi_version],
                ['FMI Type', manifest.fmi_type],
                ['Version', manifest.version],
                ['Generation Tool', manifest.generation_tool],
              ] as [string, string][]).map(([label, value]) => (
                <div key={label} className="bg-off-white rounded-lg px-3 py-2.5">
                  <p className="text-xs text-brown mb-0.5">{label}</p>
                  <p className="text-sm text-off-black font-medium truncate">{value || '—'}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <div className="bg-off-white rounded-lg px-3 py-2">
                <p className="text-xs text-brown mb-0.5">Model Identifier</p>
                <p className="text-xs font-mono text-off-black break-all">{manifest.model_identifier || '—'}</p>
              </div>
              <div className="bg-off-white rounded-lg px-3 py-2">
                <p className="text-xs text-brown mb-0.5">GUID</p>
                <p className="text-xs font-mono text-off-black break-all">{manifest.guid || '—'}</p>
              </div>
            </div>
          </section>

          {/* ── Ports ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <section className="bg-white border border-beige rounded-xl p-5">
              <h2 className="text-xs font-semibold text-brown uppercase tracking-wider mb-4">
                Inputs ({manifest.inputs.length})
              </h2>
              {manifest.inputs.length === 0 ? (
                <p className="text-brown/50 text-xs">No inputs</p>
              ) : (
                <div className="space-y-2">
                  {manifest.inputs.map((p) => (
                    <div key={p.name} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-navy flex-shrink-0" />
                      <span className="text-xs font-mono text-navy truncate">{p.name}</span>
                      <span className="text-xs text-brown ml-auto flex-shrink-0">{p.type}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="bg-white border border-beige rounded-xl p-5">
              <h2 className="text-xs font-semibold text-brown uppercase tracking-wider mb-4">
                Outputs ({manifest.outputs.length})
              </h2>
              {manifest.outputs.length === 0 ? (
                <p className="text-brown/50 text-xs">No outputs</p>
              ) : (
                <div className="space-y-2">
                  {manifest.outputs.map((p) => (
                    <div key={p.name} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0" />
                      <span className="text-xs font-mono text-emerald-700 truncate">{p.name}</span>
                      <span className="text-xs text-brown ml-auto flex-shrink-0">{p.type}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* ── Data Files ── */}
          <section className="bg-white border border-beige rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xs font-semibold text-brown uppercase tracking-wider">
                Data Files ({dataFiles.length})
              </h2>
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) void handleUploadDataFile(file)
                    e.target.value = ''
                  }}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadingFile}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-off-black bg-off-white hover:bg-beige disabled:opacity-50 border border-beige rounded-lg transition-colors"
                >
                  {uploadingFile ? (
                    <div className="w-3 h-3 border-2 border-brown/30 border-t-brown rounded-full animate-spin" />
                  ) : (
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                    </svg>
                  )}
                  Upload File
                </button>
              </div>
            </div>
            <p className="text-xs text-brown mb-3">
              External data files (weather, lookup tables, etc.) are provided to the FMU at runtime. The FMU itself is never modified.
            </p>
            {dataLoading ? (
              <div className="h-12 bg-beige/50 rounded-lg animate-pulse" />
            ) : dataFiles.length === 0 ? (
              <p className="text-brown/50 text-xs">No data files uploaded</p>
            ) : (
              <div className="space-y-3">
                {dataFiles.map((f) => (
                  <div key={f.name}>
                    <div className="flex items-center gap-2 bg-off-white rounded-lg px-3 py-2">
                      <svg className="w-4 h-4 text-brown flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                      </svg>
                      <span className="text-xs font-mono text-off-black truncate">{f.name}</span>
                      {f.validation && f.validation.format_valid && (
                        <span className="flex items-center gap-1 text-xs text-emerald-600 flex-shrink-0">
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          Valid
                        </span>
                      )}
                      {f.validation && !f.validation.format_valid && (
                        <span className="flex items-center gap-1 text-xs text-amber-600 flex-shrink-0">
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                          </svg>
                          Invalid format
                        </span>
                      )}
                      <span className="text-xs text-brown ml-auto flex-shrink-0">
                        {f.size_bytes < 1024 ? `${f.size_bytes} B` : `${(f.size_bytes / 1024).toFixed(1)} KB`}
                      </span>
                      <button
                        onClick={() => void handleDeleteDataFile(f.name)}
                        className="p-1 text-brown hover:text-red transition-colors flex-shrink-0"
                        title="Delete"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>

                    {/* Validation error for .data files */}
                    {f.validation && !f.validation.format_valid && f.validation.error && (
                      <div className="mt-1 px-3">
                        <p className="text-xs text-amber-600/70">{f.validation.error}</p>
                      </div>
                    )}

                    {/* Valid file info */}
                    {f.validation && f.validation.format_valid && (
                      <div className="mt-1 px-3">
                        <p className="text-xs text-brown">
                          {f.validation.n_points} points, {f.validation.n_columns} column{f.validation.n_columns !== 1 ? 's' : ''}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Test Run ── */}
          <section className="bg-white border border-beige rounded-xl p-5">
            <h2 className="text-xs font-semibold text-brown uppercase tracking-wider mb-5">Test Run</h2>

            {/* Input variables */}
            {manifest.inputs.length > 0 && (
              <div className="mb-5">
                <p className="text-xs text-brown mb-3">Input Values (constant throughout simulation)</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {manifest.inputs.map((p) => (
                    <div key={p.name}>
                      <label className="block text-xs font-medium text-navy mb-1 font-mono truncate">
                        {p.name}
                      </label>
                      <input
                        type="number"
                        step="any"
                        value={inputValues[p.name] ?? '0.0'}
                        onChange={(e) =>
                          setInputValues((prev) => ({ ...prev, [p.name]: e.target.value }))
                        }
                        className="w-full bg-off-white border border-beige rounded-lg px-3 py-2 text-sm text-off-black focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Simulation time controls */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
              <div>
                <label className="block text-xs font-medium text-brown mb-1">Start Time (s)</label>
                <input
                  type="number"
                  step="any"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="w-full bg-off-white border border-beige rounded-lg px-3 py-2 text-sm text-off-black focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-brown mb-1">End Time (s)</label>
                <input
                  type="number"
                  step="any"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  className="w-full bg-off-white border border-beige rounded-lg px-3 py-2 text-sm text-off-black focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-brown mb-1">Communication Points</label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={ncp}
                  onChange={(e) => setNcp(e.target.value)}
                  className="w-full bg-off-white border border-beige rounded-lg px-3 py-2 text-sm text-off-black focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
                />
              </div>
            </div>

            {/* Run button */}
            <button
              onClick={() => void handleRunTest()}
              disabled={runLoading}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-navy hover:bg-navy/90 disabled:opacity-60 disabled:cursor-not-allowed rounded-lg transition-colors"
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
              <div className="mt-4 bg-red/5 border border-red/20 rounded-lg px-4 py-3 text-sm text-red">
                {runError}
              </div>
            )}

            {/* Results chart */}
            {runResult && !runLoading && (
              <div className="mt-6">
                <p className="text-xs font-semibold text-brown uppercase tracking-wider mb-3">
                  Results — {outputCount} output variable{outputCount !== 1 ? 's' : ''}
                </p>
                {outputCount === 0 ? (
                  <p className="text-brown text-sm">No output variables returned.</p>
                ) : (
                  <div className="bg-off-white rounded-xl p-3 overflow-hidden">
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
