<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSync2PodStore } from '@/stores/sync2pod'
import TaskStatusTag from '@/components/TaskStatusTag.vue'

const store = useSync2PodStore()
const router = useRouter()

let timer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await store.fetchTasks()
  await store.fetchConfig()
  timer = setInterval(() => store.fetchTasks(), 3000)
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

const expandedRows = ref<number[]>([])
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
      <el-table-column label="目录" min-width="200">
        <template #default="{ row }">
          <span style="font-size: 12px">{{ row.source_dir }} → {{ row.pod_dir }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button
            v-if="row.status !== 'running'"
            size="small"
            type="success"
            @click="handleStart(row.id)"
            >启动</el-button
          >
          <el-button v-else size="small" type="warning" @click="handleStop(row.id)">停止</el-button>
          <el-button size="small" @click="router.push(`/sync2pod/${row.id}/edit`)">编辑</el-button>
          <el-button size="small" @click="router.push(`/sync2pod/${row.id}`)">详情</el-button>
          <el-button size="small" type="danger" @click="handleDeleteTask(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
