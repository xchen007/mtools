<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSync2PodStore } from '@/stores/sync2pod'
import TaskStatusTag from '@/components/TaskStatusTag.vue'

const store = useSync2PodStore()
const router = useRouter()

let timer: ReturnType<typeof setInterval> | null = null

// Expanded rows state with localStorage persistence
const STORAGE_KEY = 'sync2pod_expanded_rows'
const expandedRows = ref<number[]>([])

onMounted(async () => {
  await store.fetchTasks()
  await store.fetchConfig()
  timer = setInterval(() => store.fetchTasks(), 3000)

  // Load expanded rows from localStorage
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      expandedRows.value = JSON.parse(stored)
    }
  } catch (e) {
    console.error('Failed to load expanded rows state:', e)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

async function handleDeleteTask(id: number) {
  await ElMessageBox.confirm('确认删除该任务？', '提示', { type: 'warning' })
  await store.deleteTask(id)
  ElMessage.success('删除成功')
}

async function handleStart(id: number) {
  await store.startTask(id)
  ElMessage.success('已启动')
}

async function handleStop(id: number) {
  await store.stopTask(id)
  ElMessage.success('已停止')
}

async function handleRestart(id: number) {
  await store.restartTask(id)
  ElMessage.success('重启成功')
}

// Save expanded state to localStorage when it changes
function handleExpandChange(row: any, expandedRowsList: any[]) {
  const taskId = row.id
  const isExpanded = expandedRowsList.some((r: any) => r.id === taskId)

  if (isExpanded) {
    // Add to expanded rows
    if (!expandedRows.value.includes(taskId)) {
      expandedRows.value.push(taskId)
    }
  } else {
    // Remove from expanded rows
    expandedRows.value = expandedRows.value.filter(id => id !== taskId)
  }

  // Save to localStorage
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(expandedRows.value))
  } catch (e) {
    console.error('Failed to save expanded rows state:', e)
  }
}

function formatRelativeTime(isoString: string): string {
  const now = new Date()
  const then = new Date(isoString)
  const diffMs = now.getTime() - then.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 10) return '刚刚'
  if (diffSec < 60) return `${diffSec}秒前`
  if (diffMin < 60) return `${diffMin}分钟前`
  if (diffHour < 24) return `${diffHour}小时前`
  if (diffDay < 7) return `${diffDay}天前`

  // 超过7天显示具体日期
  return then.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<template>
  <div class="main-container">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h2 style="margin: 0">Sync2Pod 任务</h2>
      <el-button type="primary" @click="router.push('/sync2pod/create')">新建任务</el-button>
    </div>

    <el-empty v-if="!store.loading && store.tasks.length === 0" description="暂无任务" />

    <el-table
      v-else
      :data="store.tasks"
      v-loading="store.loading"
      :expand-row-keys="expandedRows"
      row-key="id"
      @expand-change="handleExpandChange"
      class="overflow-x-auto"
      style="width: 100%"
    >
      <el-table-column v-if="store.config?.show_list_log" type="expand">
        <template #default="{ row }">
          <pre style="margin: 8px 48px; font-size: 12px; background: #1e1e1e; color: #d4d4d4; padding: 8px; border-radius: 4px; white-space: pre-wrap; word-break: break-all">{{ row.log_tail || '（暂无日志）' }}</pre>
        </template>
      </el-table-column>

      <el-table-column prop="name" label="任务名称" />
      <el-table-column label="Pod" min-width="160">
        <template #default="{ row }">
          <span>{{ row.pod || row.pod_label }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="namespace" label="命名空间" width="120" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <TaskStatusTag :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column prop="pid" label="PID" width="80" />
      <el-table-column label="最后同步" width="160">
        <template #default="{ row }">
          <span v-if="row.last_sync_at" style="font-size: 12px">
            {{ formatRelativeTime(row.last_sync_at) }}
          </span>
          <span v-else style="font-size: 12px; color: #999">未同步</span>
        </template>
      </el-table-column>
      <el-table-column label="目录" min-width="200">
        <template #default="{ row }">
          <span style="font-size: 12px">{{ row.source_dir }} → {{ row.pod_dir }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="320">
        <template #default="{ row }">
          <el-button
            v-if="row.status !== 'running'"
            size="small"
            type="success"
            @click="handleStart(row.id)"
            >启动</el-button
          >
          <el-button v-else size="small" type="warning" @click="handleStop(row.id)">停止</el-button>
          <el-button
            v-if="row.status === 'running'"
            size="small"
            type="primary"
            @click="handleRestart(row.id)"
            >重启</el-button
          >
          <el-button size="small" @click="router.push(`/sync2pod/${row.id}/edit`)">编辑</el-button>
          <el-button size="small" @click="router.push(`/sync2pod/${row.id}`)">详情</el-button>
          <el-button size="small" type="danger" @click="handleDeleteTask(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
