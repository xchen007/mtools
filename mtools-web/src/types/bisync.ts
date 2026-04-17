export interface BisyncTarget {
  id: number
  task: number
  target_dir: string
  status: 'stopped' | 'running' | 'error'
  pid: number | null
  created_at: string
  updated_at: string
  log_tail: string
  log_mtime: number | null
}

export interface BisyncTask {
  id: number
  name: string
  source_dir: string
  interval: number
  debounce_seconds: number
  exclude_patterns: string
  created_at: string
  updated_at: string
  targets: BisyncTarget[]
}

export type BisyncTaskCreate = Omit<BisyncTask, 'id' | 'created_at' | 'updated_at' | 'targets'>
export type BisyncTaskUpdate = Partial<BisyncTaskCreate>
export type BisyncTargetCreate = { target_dir: string }
