export interface Sync2PodTask {
  id: number
  name: string
  pod_type: 'k8s' | 'docker'
  source_dir: string
  cluster: string
  namespace: string
  pod_label: string
  pod: string
  container: string
  pod_dir: string
  is_tess: boolean
  interval: number
  enable_alert: boolean
  status: 'stopped' | 'running' | 'error'
  pid: number | null
  last_sync_at: string | null
  created_at: string
  updated_at: string
  log_tail: string
}

export interface Sync2PodConfig {
  is_tess: boolean
  show_list_log: boolean
  custom_kubectl_cmd: string
  custom_docker_cmd: string
  alert_email: string
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_password: string
  smtp_use_tls: boolean
}

export interface KubeContext {
  context: string
  cluster: string
  namespace: string
  is_tess: boolean
  error?: string
}

export type Sync2PodTaskCreate = Omit<Sync2PodTask, 'id' | 'status' | 'pid' | 'last_sync_at' | 'created_at' | 'updated_at' | 'log_tail'>
export type Sync2PodTaskUpdate = Partial<Sync2PodTaskCreate>
