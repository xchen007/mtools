import { defineStore } from 'pinia'
import { ref } from 'vue'
import { bisyncApi } from '@/api/bisync'
import type { BisyncTask, BisyncTaskCreate, BisyncTaskUpdate, BisyncTargetCreate } from '@/types/bisync'

export const useBisyncStore = defineStore('bisync', () => {
  const tasks = ref<BisyncTask[]>([])
  const loading = ref(false)

  // 记录自启动和失败次数
  function ensureTargetMeta(task) {
    if (!task.targets) return
    for (const tgt of task.targets) {
      if (typeof tgt.autoRestart !== 'boolean') tgt.autoRestart = false
      if (typeof tgt.failCount !== 'number') tgt.failCount = 0
    }
  }

  async function fetchTasks() {
    loading.value = true
    try {
      const res = await bisyncApi.listTasks()
      tasks.value = res.data
      for (const task of tasks.value) ensureTargetMeta(task)
    } finally {
      loading.value = false
    }
  }

  async function createTask(data: BisyncTaskCreate) {
    const res = await bisyncApi.createTask(data)
    tasks.value.push(res.data)
    return res.data
  }

  async function updateTask(id: number, data: BisyncTaskUpdate) {
    const res = await bisyncApi.updateTask(id, data)
    const idx = tasks.value.findIndex((t) => t.id === id)
    if (idx !== -1) tasks.value[idx] = res.data
    return res.data
  }

  async function deleteTask(id: number) {
    await bisyncApi.deleteTask(id)
    tasks.value = tasks.value.filter((t) => t.id !== id)
  }

  async function startAll(id: number) {
    await bisyncApi.startAll(id)
    await fetchTasks()
  }

  async function stopAll(id: number) {
    await bisyncApi.stopAll(id)
    await fetchTasks()
  }

  async function addTarget(taskId: number, data: BisyncTargetCreate) {
    const res = await bisyncApi.addTarget(taskId, data)
    const task = tasks.value.find((t) => t.id === taskId)
    if (task) task.targets.push(res.data)
    return res.data
  }

  async function deleteTarget(id: number) {
    await bisyncApi.deleteTarget(id)
    for (const task of tasks.value) {
      task.targets = task.targets.filter((tgt) => tgt.id !== id)
    }
  }

  async function startTarget(id: number) {
    await bisyncApi.startTarget(id)
    await fetchTasks()
  }

  async function stopTarget(id: number) {
    await bisyncApi.stopTarget(id)
    await fetchTasks()
    // 检查自启动
    for (const task of tasks.value) {
      const tgt = task.targets.find(t => t.id === id)
      if (tgt && tgt.autoRestart) {
        try {
          await bisyncApi.startTarget(id)
          await fetchTasks()
        } catch {
          tgt.failCount = (tgt.failCount || 0) + 1
        }
      }
    }
  }

  function toggleAutoRestart(targetId: number, val: boolean) {
    for (const task of tasks.value) {
      const tgt = task.targets.find(t => t.id === targetId)
      if (tgt) tgt.autoRestart = val
    }
  }

  function clearFailCount(targetId: number) {
    for (const task of tasks.value) {
      const tgt = task.targets.find(t => t.id === targetId)
      if (tgt) tgt.failCount = 0
    }
  }

  async function resetTarget(id: number) {
    await bisyncApi.resetTarget(id)
    await fetchTasks()
  }

  async function getTask(id: number|string) {
    let task = tasks.value.find((t) => t.id === Number(id))
    if (!task) {
      const res = await bisyncApi.getTask(id)
      task = res.data
    }
    return task
  }

  return {
    tasks,
    loading,
    fetchTasks,
    createTask,
    updateTask,
    deleteTask,
    startAll,
    stopAll,
    addTarget,
    deleteTarget,
    startTarget,
    stopTarget,
    resetTarget,
    getTask,
    toggleAutoRestart,
    clearFailCount,
  }
})
