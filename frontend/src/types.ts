/** 与 Python 侧 `docmorph.ui.bridge` 交换的数据结构。 */

export type StatusKey =
  | 'success'
  | 'success_with_warnings'
  | 'skipped_exists'
  | 'unsupported'
  | 'backend_unavailable'
  | 'invalid_input'
  | 'failed'
  | 'cancelled'

export interface TargetOption {
  target: string
  available: boolean
  backends: string[]
  reason: string
}

export interface SourceEntry {
  source: string
  default_target: string
  targets: TargetOption[]
}

export interface CapabilityItem {
  id: string
  label: string
  kind: string
  available: boolean
  detail: string
  hint: string
}

export interface CapabilityPayload {
  capabilities: CapabilityItem[]
  available: string[]
  missing: string[]
  /** 完整检测尚未完成（启动阶段先展示轻量结果） */
  pending?: boolean
  safe_mode?: boolean
  warmup_error?: string
}

export interface TaskResult {
  id: string
  input: string
  file_name: string
  status: StatusKey
  status_label: string
  backend: string
  outputs: string[]
  warnings: string[]
  error: string
  duration_s: number
}

export interface BatchSummary {
  total: number
  succeeded: number
  skipped: number
  failed: number
  cancelled: number
  duration_s: number
}

export interface AppState {
  version: string
  platform: string
  running: boolean
  cancel_requested: boolean
  progress: number
  progress_text: string
  summary: BatchSummary | null
  tasks: TaskResult[]
  output_directory: string
  input_directory: string
  keep_structure: boolean
  conflict_policy: string
  max_workers: number
  xlsx_csv_mode: string
  extract_media: boolean
  pdf_backend_preference: string
  theme_colors: string[]
  log_tail: string[]
  log_file: string
  config_path: string
  config_warnings: string[]
  webview_available: boolean
  safe_mode: boolean
  capability_pending: boolean
  temp_retention_hours: number
}

export interface SelectionPayload {
  files: string[]
  directory: string
  count: number
  notes: string[]
}

export interface StartPayload {
  target: string
  output_directory: string
  keep_structure: boolean
  conflict_policy: string
  workers: number
}

export interface OperationResult {
  ok: boolean
  message: string
  outputs?: string[]
}

export interface PdfTaskPayload {
  ok: boolean
  message: string
  outputs: string[]
}

/** 最近使用的转换设置（只存在界面本地，不入库、不含文件内容） */
export interface RecentPreset {
  source: string
  target: string
  at: number
}
