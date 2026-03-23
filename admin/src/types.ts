export interface FMUPort {
  name: string
  type: string
  causality: 'input' | 'output'
}

export interface FMUManifest {
  fmu_type: string
  fmi_version: string
  fmi_type: string
  version: string
  generation_tool: string
  guid: string
  model_identifier: string
  inputs: FMUPort[]
  outputs: FMUPort[]
  parameters: unknown[]
  compatible_connections: Record<string, string[]>
}

export interface FMUListItem {
  type_name: string
  version: string
}

export interface FMUDetail extends FMUListItem {
  fmu_path: string
  manifest: FMUManifest
}

export interface FMUUploadResponse {
  type_name: string
  version: string
  fmu_path: string
  fmi_version: string
  fmi_type: string
  generation_tool: string
  inputs: string[]
  outputs: string[]
  patched: boolean
  warnings: string[]
}

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface Job {
  id: string
  project_id: string
  project_name: string
  status: JobStatus
  queued_at: string | null
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  result_path: string | null
}

export interface JobStatusDetail extends Job {
  position: number | null
  estimated_wait_minutes: number | null
}

export interface ResultsData {
  job_id: string
  variables: string[]
  data: Record<string, number[]>
}

export interface FMUTestRunRequest {
  inputs: Record<string, number>
  start_time: number
  end_time: number
  ncp: number
}

export interface FMUTestRunResult {
  time: number[]
  outputs: Record<string, number[]>
}

export interface DataFileValidation {
  format_valid: boolean
  has_header: boolean
  n_points: number
  n_vars: number
  n_columns: number
  error: string | null
}

export interface DataFileEntry {
  name: string
  size_bytes: number
  validation?: DataFileValidation
}

