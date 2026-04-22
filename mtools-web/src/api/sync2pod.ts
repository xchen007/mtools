import client from './client'
import type { KubeContext, Sync2PodConfig, Sync2PodTask, Sync2PodTaskCreate, Sync2PodTaskUpdate } from '@/types/sync2pod'

const BASE = '/api/sync2pod'

export const sync2podApi = {
  listTasks: () => client.get<Sync2PodTask[]>(`${BASE}/tasks/`),
  getTask: (id: number) => client.get<Sync2PodTask>(`${BASE}/tasks/${id}/`),
  createTask: (data: Sync2PodTaskCreate) => client.post<Sync2PodTask>(`${BASE}/tasks/`, data),
  updateTask: (id: number, data: Sync2PodTaskUpdate) => client.patch<Sync2PodTask>(`${BASE}/tasks/${id}/`, data),
  deleteTask: (id: number) => client.delete(`${BASE}/tasks/${id}/`),
  startTask: (id: number) => client.post(`${BASE}/tasks/${id}/start/`),
  stopTask: (id: number) => client.post(`${BASE}/tasks/${id}/stop/`),
  restartTask: (id: number) => client.post(`${BASE}/tasks/${id}/restart/`),
  getLogs: (id: number) => client.get(`${BASE}/tasks/${id}/logs/`),
  getKubeContext: (tess: boolean) => client.get<KubeContext>(`${BASE}/kube-context/`, { params: { tess: tess ? '1' : '0' } }),
  getConfig: () => client.get<Sync2PodConfig>(`${BASE}/config/`),
  updateConfig: (data: Partial<Sync2PodConfig>) => client.patch<Sync2PodConfig>(`${BASE}/config/`, data),
}
