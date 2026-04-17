<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSync2PodStore } from '@/stores/sync2pod'
import TaskStatusTag from '@/components/TaskStatusTag.vue'
import LogViewer from '@/components/LogViewer.vue'

const route = useRoute()
const router = useRouter()
const store = useSync2PodStore()
const taskId = Number(route.params.id)
const wsUrl = `${import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'}/ws/sync2pod/task/${taskId}/logs/`

onMounted(async () => {
  await store.fetchTasks()
})

const task = computed(() => store.tasks.find((t) => t.id === taskId))

async function handleStart() {
  await store.startTask(taskId)
  ElMessage.success('已启动')
}

async function handleStop() {
  await store.stopTask(taskId)
  ElMessage.success('已停止')
}

async function handleDelete() {
  await ElMessageBox.confirm('确认删除该任务？', '提示', { type: 'warning' })
  await store.deleteTask(taskId)
  ElMessage.success('删除成功')
  router.push('/sync2pod')
}
</script>

<template>
  <div class="main-container" v-if="task">
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px">
      <el-button @click="router.push('/sync2pod')">← 返回</el-button>
      <h2 style="margin: 0">{{ task.name }}</h2>
      <TaskStatusTag :status="task.status" />
    </div>

    <el-card style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>任务信息</span>
          <div style="display: flex; gap: 8px">
            <el-button
              v-if="task.status !== 'running'"
              type="success"
              size="small"
              @click="handleStart"
              >启动</el-button
            >
            <el-button v-else type="warning" size="small" @click="handleStop">停止</el-button>
            <el-button size="small" @click="router.push(`/sync2pod/${taskId}/edit`)">编辑</el-button>
            <el-button type="danger" size="small" @click="handleDelete">删除</el-button>
          </div>
        </div>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="任务名称">{{ task.name }}</el-descriptions-item>
        <el-descriptions-item label="Pod 类型">{{ task.pod_type }}</el-descriptions-item>
        <el-descriptions-item label="源目录">{{ task.source_dir }}</el-descriptions-item>
        <el-descriptions-item label="Pod 目录">{{ task.pod_dir }}</el-descriptions-item>
        <el-descriptions-item label="集群">{{ task.cluster }}</el-descriptions-item>
        <el-descriptions-item label="命名空间">{{ task.namespace }}</el-descriptions-item>
        <el-descriptions-item label="Pod 标签">{{ task.pod_label }}</el-descriptions-item>
        <el-descriptions-item label="Pod 名称">{{ task.pod }}</el-descriptions-item>
        <el-descriptions-item label="容器">{{ task.container }}</el-descriptions-item>
        <el-descriptions-item label="PID">{{ task.pid ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="同步间隔">{{ task.interval }} 秒</el-descriptions-item>
        <el-descriptions-item label="TESS">{{ task.is_tess ? '是' : '否' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card>
      <template #header>实时日志</template>
      <LogViewer :ws-url="wsUrl" />
    </el-card>
  </div>

  <el-empty v-else description="任务不存在" />
</template>
