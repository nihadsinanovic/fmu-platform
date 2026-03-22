import type { FMUListItem, FMUDetail, FMUUploadResponse, FMUTestRunRequest, FMUTestRunResult, Job, JobStatusDetail, ResultsData } from './types'

const BASE = ''
const STORAGE_KEY = 'fmu_auth'

function getToken(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return parsed.token ?? null
    }
  } catch { /* ignore */ }
  return null
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = { ...authHeaders(), ...init?.headers }
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (res.status === 401) {
    localStorage.removeItem(STORAGE_KEY)
    window.location.href = '/admin/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ── FMU Library ───────────────────────────────────────────────────────────────

export async function listFMUs(): Promise<FMUListItem[]> {
  return request('/api/fmu-library')
}

export async function getFMUManifest(typeName: string): Promise<FMUDetail['manifest']> {
  return request(`/api/fmu-library/${typeName}/manifest`)
}

export async function deleteFMU(typeName: string): Promise<{ message: string }> {
  return request(`/api/fmu-library/${encodeURIComponent(typeName)}`, {
    method: 'DELETE',
  })
}

export async function uploadFMU(
  file: File,
  typeName: string,
  version: string,
): Promise<FMUUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  return request(`/api/fmu-library/upload?type_name=${encodeURIComponent(typeName)}&version=${encodeURIComponent(version)}`, {
    method: 'POST',
    body: form,
  })
}

export async function runFMUTest(typeName: string, body: FMUTestRunRequest): Promise<FMUTestRunResult> {
  return request(`/api/fmu-library/${encodeURIComponent(typeName)}/test-run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function uploadResource(typeName: string, file: File): Promise<{ message: string }> {
  const form = new FormData()
  form.append('file', file)
  return request(`/api/fmu-library/${encodeURIComponent(typeName)}/resources`, {
    method: 'POST',
    body: form,
  })
}

export async function listResources(typeName: string): Promise<{ type_name: string; resources: { name: string; size_bytes: number }[] }> {
  return request(`/api/fmu-library/${encodeURIComponent(typeName)}/resources`)
}

export async function deleteResource(typeName: string, filename: string): Promise<{ message: string }> {
  return request(`/api/fmu-library/${encodeURIComponent(typeName)}/resources/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  })
}

// ── Admin Jobs ────────────────────────────────────────────────────────────────

export async function listAllJobs(): Promise<Job[]> {
  return request('/api/admin/jobs')
}

export async function getJobStatus(jobId: string): Promise<JobStatusDetail> {
  return request(`/api/jobs/${jobId}/status`)
}

// ── Results ───────────────────────────────────────────────────────────────────

export async function getResultData(jobId: string): Promise<ResultsData> {
  return request(`/api/admin/results/${jobId}`)
}
