import client from './client'
import type { BisyncTarget, BisyncTargetCreate, BisyncTask, BisyncTaskCreate, BisyncTaskUpdate } from '@/types/bisync'

const BASE = '/api/bisync'

export const bisyncApi = {
  // Tasks
  listTasks: () => client.get<BisyncTask[]>(`${BASE}/tasks/`),
  getTask: (id: number) => client.get<BisyncTask>(`${BASE}/tasks/${id}/`),
  createTask: (data: BisyncTaskCreate) => client.post<BisyncTask>(`${BASE}/tasks/`, data),
  updateTask: (id: number, data: BisyncTaskUpdate) => client.patch<BisyncTask>(`${BASE}/tasks/${id}/`, data),
  deleteTask: (id: number) => client.delete(`${BASE}/tasks/${id}/`),
  startAll: (id: number) => client.post(`${BASE}/tasks/${id}/start_all/`),
  stopAll: (id: number) => client.post(`${BASE}/tasks/${id}/stop_all/`),

  // Targets
  listTargets: (taskId: number) => client.get<BisyncTarget[]>(`${BASE}/tasks/${taskId}/targets/`),
  addTarget: (taskId: number, data: BisyncTargetCreate) =>
    client.post<BisyncTarget>(`${BASE}/tasks/${taskId}/targets/`, data),
  getTarget: (id: number) => client.get<BisyncTarget>(`${BASE}/targets/${id}/`),
  deleteTarget: (id: number) => client.delete(`${BASE}/targets/${id}/`),
  startTarget: (id: number) => client.post(`${BASE}/targets/${id}/start/`),
  stopTarget: (id: number) => client.post(`${BASE}/targets/${id}/stop/`),
  resetTarget: (id: number) => client.post(`${BASE}/targets/${id}/reset/`),
  getTargetLogs: (id: number) => client.get(`${BASE}/targets/${id}/logs/`),

  openPath: (path: string) => client.get(`${BASE}/tasks/open/`, { params: { path } }),
}
