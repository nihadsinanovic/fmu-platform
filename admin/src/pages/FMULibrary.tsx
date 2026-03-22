import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listFMUs, getFMUManifest, uploadFMU, uploadResource, deleteFMU } from '../api'
import type { FMUListItem, FMUManifest, FMUUploadResponse } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function Badge({ children, color = 'gray' }: { children: React.ReactNode; color?: 'gray' | 'indigo' | 'emerald' | 'amber' | 'rose' }) {
  const colors = {
    gray: 'bg-gray-700 text-gray-300',
    indigo: 'bg-indigo-900/60 text-indigo-300 ring-1 ring-indigo-700/50',
    emerald: 'bg-emerald-900/60 text-emerald-300 ring-1 ring-emerald-700/50',
    amber: 'bg-amber-900/60 text-amber-300 ring-1 ring-amber-700/50',
    rose: 'bg-rose-900/60 text-rose-300 ring-1 ring-rose-700/50',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[color]}`}>
      {children}
    </span>
  )
}

function PortList({ ports, causality }: { ports: FMUManifest['inputs'] | FMUManifest['outputs']; causality: 'input' | 'output' }) {
  if (!ports.length) return <span className="text-gray-600 text-xs">none</span>
  return (
    <div className="flex flex-wrap gap-1">
      {ports.map((p) => (
        <Badge key={p.name} color={causality === 'input' ? 'indigo' : 'emerald'}>
          {p.name}
        </Badge>
      ))}
    </div>
  )
}

// ── Upload Modal ──────────────────────────────────────────────────────────────

function UploadModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: (r: FMUUploadResponse) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [typeName, setTypeName] = useState('')
  const [version, setVersion] = useState('1.0.0')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file || !typeName) return
    setLoading(true)
    setError(null)
    try {
      const result = await uploadFMU(file, typeName, version)
      onSuccess(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <h2 className="text-base font-semibold text-white">Upload FMU</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          {/* File picker */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">FMU File</label>
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-gray-700 hover:border-indigo-600 rounded-lg px-4 py-6 text-center cursor-pointer transition-colors"
            >
              {file ? (
                <p className="text-sm text-indigo-400 font-medium">{file.name}</p>
              ) : (
                <>
                  <p className="text-sm text-gray-400">Click to select a <span className="font-medium text-gray-300">.fmu</span> file</p>
                  <p className="text-xs text-gray-600 mt-1">Max 100 MB</p>
                </>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".fmu"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>

          {/* Type name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">Type Name</label>
            <input
              type="text"
              value={typeName}
              onChange={(e) => setTypeName(e.target.value)}
              placeholder="e.g. apartment_heatpump"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
            />
          </div>

          {/* Version */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">Version</label>
            <input
              type="text"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
            />
          </div>

          {error && (
            <div className="bg-rose-950/60 border border-rose-800 rounded-lg px-4 py-3 text-sm text-rose-300">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-sm font-medium text-gray-400 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!file || !typeName || loading}
              className="flex-1 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
            >
              {loading ? 'Uploading…' : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Upload Result Toast ───────────────────────────────────────────────────────

function UploadResult({ result, onClose }: { result: FMUUploadResponse; onClose: () => void }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 w-full max-w-sm bg-gray-900 border border-gray-700 rounded-xl shadow-2xl">
      <div className="flex items-start justify-between px-5 py-4 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm font-semibold text-white">FMU Registered</p>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 ml-2">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="px-5 py-4 space-y-2 text-sm">
        <p className="text-gray-300"><span className="text-gray-500">Type:</span> <span className="font-mono">{result.type_name}</span></p>
        <p className="text-gray-300"><span className="text-gray-500">FMI:</span> {result.fmi_version} / {result.fmi_type}</p>
        <p className="text-gray-300"><span className="text-gray-500">Tool:</span> {result.generation_tool}</p>
        {result.patched && <Badge color="amber">Patched needsExecutionTool</Badge>}
        {result.warnings.map((w, i) => (
          <p key={i} className="text-amber-400 text-xs">{w}</p>
        ))}
      </div>
    </div>
  )
}

// ── Manifest Drawer ───────────────────────────────────────────────────────────

function ManifestDrawer({ typeName, onClose }: { typeName: string; onClose: () => void }) {
  const [manifest, setManifest] = useState<FMUManifest | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [resourceFile, setResourceFile] = useState<File | null>(null)
  const [resourceLoading, setResourceLoading] = useState(false)
  const [resourceMsg, setResourceMsg] = useState<string | null>(null)
  const resourceRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    getFMUManifest(typeName)
      .then(setManifest)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed'))
      .finally(() => setLoading(false))
  }, [typeName])

  async function handleResourceUpload() {
    if (!resourceFile) return
    setResourceLoading(true)
    setResourceMsg(null)
    try {
      const res = await uploadResource(typeName, resourceFile)
      setResourceMsg(res.message)
      setResourceFile(null)
    } catch (err) {
      setResourceMsg(err instanceof Error ? err.message : 'Failed')
    } finally {
      setResourceLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <div className="w-full max-w-lg bg-gray-900 border-l border-gray-800 overflow-y-auto flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-800 flex-shrink-0">
          <div>
            <p className="text-xs text-gray-500 mb-0.5">FMU Manifest</p>
            <h2 className="text-base font-semibold text-white font-mono">{typeName}</h2>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 px-6 py-5 space-y-6">
          {loading && <p className="text-gray-500 text-sm">Loading manifest…</p>}
          {error && <p className="text-rose-400 text-sm">{error}</p>}

          {manifest && (
            <>
              {/* Meta */}
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['FMI Version', manifest.fmi_version],
                  ['FMI Type', manifest.fmi_type],
                  ['Version', manifest.version],
                  ['Generation Tool', manifest.generation_tool],
                ].map(([label, value]) => (
                  <div key={label} className="bg-gray-800 rounded-lg px-3 py-2.5">
                    <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                    <p className="text-sm text-gray-200 font-medium">{value || '—'}</p>
                  </div>
                ))}
              </div>

              {/* Inputs */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Inputs ({manifest.inputs.length})
                </p>
                <PortList ports={manifest.inputs} causality="input" />
              </div>

              {/* Outputs */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Outputs ({manifest.outputs.length})
                </p>
                <PortList ports={manifest.outputs} causality="output" />
              </div>

              {/* GUID / model identifier */}
              <div className="space-y-2">
                <div className="bg-gray-800/60 rounded-lg px-3 py-2">
                  <p className="text-xs text-gray-500 mb-0.5">Model Identifier</p>
                  <p className="text-xs font-mono text-gray-300 break-all">{manifest.model_identifier || '—'}</p>
                </div>
                <div className="bg-gray-800/60 rounded-lg px-3 py-2">
                  <p className="text-xs text-gray-500 mb-0.5">GUID</p>
                  <p className="text-xs font-mono text-gray-300 break-all">{manifest.guid || '—'}</p>
                </div>
              </div>

              {/* Resource injection */}
              <div className="border-t border-gray-800 pt-5">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                  Inject Resource File
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => resourceRef.current?.click()}
                    className="flex-1 px-3 py-2 text-sm text-gray-300 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg transition-colors truncate text-left"
                  >
                    {resourceFile ? resourceFile.name : 'Choose file…'}
                  </button>
                  <button
                    onClick={handleResourceUpload}
                    disabled={!resourceFile || resourceLoading}
                    className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors flex-shrink-0"
                  >
                    {resourceLoading ? '…' : 'Inject'}
                  </button>
                </div>
                <input
                  ref={resourceRef}
                  type="file"
                  className="hidden"
                  onChange={(e) => setResourceFile(e.target.files?.[0] ?? null)}
                />
                {resourceMsg && (
                  <p className="mt-2 text-xs text-emerald-400">{resourceMsg}</p>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function FMULibrary() {
  const navigate = useNavigate()
  const [fmus, setFmus] = useState<FMUListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showUpload, setShowUpload] = useState(false)
  const [uploadResult, setUploadResult] = useState<FMUUploadResponse | null>(null)
  const [selectedFMU, setSelectedFMU] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await listFMUs()
      setFmus(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load FMUs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  function handleUploadSuccess(result: FMUUploadResponse) {
    setShowUpload(false)
    setUploadResult(result)
    void load()
    setTimeout(() => setUploadResult(null), 8000)
  }

  return (
    <div className="p-4 sm:p-6 md:p-8">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6 md:mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">FMU Library</h1>
          <p className="text-sm text-gray-500 mt-1">Atomic FMU components available for composition</p>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
          Upload FMU
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 bg-rose-950/60 border border-rose-800 rounded-lg px-4 py-3 text-sm text-rose-300 flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          {error}
          <button onClick={load} className="ml-auto text-rose-400 hover:text-rose-200 font-medium text-xs underline">Retry</button>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-gray-800/50 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && fmus.length === 0 && (
        <div className="text-center py-24 text-gray-600">
          <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375" />
          </svg>
          <p className="text-sm">No FMUs registered yet. Upload one to get started.</p>
        </div>
      )}

      {/* FMU table */}
      {!loading && fmus.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Type Name</th>
                  <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Version</th>
                  <th className="text-right px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {fmus.map((fmu) => (
                  <tr
                    key={fmu.type_name}
                    onClick={() => navigate(`/fmu-library/${fmu.type_name}`)}
                    className="hover:bg-gray-800/50 transition-colors group cursor-pointer"
                  >
                    <td className="px-5 py-4">
                      <span className="font-mono text-indigo-400 text-sm">{fmu.type_name}</span>
                    </td>
                    <td className="px-5 py-4">
                      <Badge color="gray">v{fmu.version}</Badge>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={(e) => { e.stopPropagation(); setSelectedFMU(fmu.type_name) }}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m5.231 13.481L15 17.25m-4.5-15H5.625c-.621 0-1.125.504-1.125 1.125v16.5c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9zm3.75 11.625a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                          </svg>
                          Resources
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            if (confirm(`Delete FMU "${fmu.type_name}"? This removes the FMU and all its data files.`)) {
                              void deleteFMU(fmu.type_name).then(() => load())
                            }
                          }}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-rose-400 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                          </svg>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modals */}
      {showUpload && (
        <UploadModal onClose={() => setShowUpload(false)} onSuccess={handleUploadSuccess} />
      )}
      {uploadResult && (
        <UploadResult result={uploadResult} onClose={() => setUploadResult(null)} />
      )}
      {selectedFMU && (
        <ManifestDrawer typeName={selectedFMU} onClose={() => setSelectedFMU(null)} />
      )}
    </div>
  )
}
