import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sync2podApi } from '@/api/sync2pod'
import type { Sync2PodConfig, Sync2PodTask, Sync2PodTaskCreate, Sync2PodTaskUpdate } from '@/types/sync2pod'

export const useSync2PodStore = defineStore('sync2pod', () => {
  const tasks = ref<Sync2PodTask[]>([])
  const config = ref<Sync2PodConfig | null>(null)
  const loading = ref(false)

  async function fetchTasks() {
    loading.value = true
    try {
      const res = await sync2podApi.listTasks()
      tasks.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function fetchConfig() {
    const res = await sync2podApi.getConfig()
    config.value = res.data
    return res.data
  }

  async function createTask(data: Sync2PodTaskCreate) {
    const res = await sync2podApi.createTask(data)
    tasks.value.push(res.data)
    return res.data
  }

  async function updateTask(id: number, data: Sync2PodTaskUpdate) {
    const res = await sync2podApi.updateTask(id, data)
    const idx = tasks.value.findIndex((t) => t.id === id)
    if (idx !== -1) tasks.value[idx] = res.data
    return res.data
  }

  async function deleteTask(id: number) {
    await sync2podApi.deleteTask(id)
    tasks.value = tasks.value.filter((t) => t.id !== id)
  }

  async function startTask(id: number) {
    await sync2podApi.startTask(id)
    await fetchTasks()
  }

  async function stopTask(id: number) {
    await sync2podApi.stopTask(id)
    await fetchTasks()
  }

  async function restartTask(id: number) {
    await sync2podApi.restartTask(id)
    await fetchTasks()
  }

  async function updateConfig(data: Partial<Sync2PodConfig>) {
    const res = await sync2podApi.updateConfig(data)
    config.value = res.data
    return res.data
  }

  return {
    tasks,
    config,
    loading,
    fetchTasks,
    fetchConfig,
    createTask,
    updateTask,
    deleteTask,
    startTask,
    stopTask,
    restartTask,
    updateConfig,
  }
})
