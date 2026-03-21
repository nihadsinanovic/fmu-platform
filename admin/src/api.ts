import type { FMUListItem, FMUDetail, FMUUploadResponse, Job, JobStatusDetail, ResultsData } from './types'

const BASE = ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
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

export async function uploadResource(typeName: string, file: File): Promise<{ message: string }> {
  const form = new FormData()
  form.append('file', file)
  return request(`/api/fmu-library/${encodeURIComponent(typeName)}/resources`, {
    method: 'POST',
    body: form,
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
