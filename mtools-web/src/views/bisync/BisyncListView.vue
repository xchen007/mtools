<script setup lang="ts">
import { onMounted, onUnmounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useBisyncStore } from '@/stores/bisync'

const store = useBisyncStore()
const router = useRouter()

let timer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await store.fetchTasks()
  timer = setInterval(() => store.fetchTasks(), 3000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const addTargetInputs: Record<number, string> = reactive({})

async function handleAddTarget(taskId: number) {
  const dir = addTargetInputs[taskId]?.trim()
  if (!dir) return
  await store.addTarget(taskId, { target_dir: dir })
  addTargetInputs[taskId] = ''
  await store.fetchTasks() // 刷新任务列表
  ElMessage.success('添加目标目录成功')
}

async function handleDeleteTask(id: number) {
  await ElMessageBox.confirm('确认删除该任务？', '提示', { type: 'warning' })
  await store.deleteTask(id)
  ElMessage.success('删除成功')
}

async function handleStartAll(id: number) {
  await store.startAll(id)
  ElMessage.success('已启动所有目标')
}

async function handleStopAll(id: number) {
  await store.stopAll(id)
  ElMessage.success('已停止所有目标')
}

function handleStartTarget(targetId: number) {
  store.startTarget(targetId)
}
function handleStopTarget(targetId: number) {
  store.stopTarget(targetId)
}
function handleDeleteTarget(targetId: number) {
  store.deleteTarget(targetId)
  ElMessage.success('删除目标目录成功')
}
</script>

<template>
  <div class="main-container bisync-list-page">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h2 style="margin: 0">Bisync 任务</h2>
      <el-button type="primary" @click="router.push('/bisync/create')">新建任务</el-button>
    </div>

    <el-empty v-if="!store.loading && store.tasks.length === 0" description="暂无任务" />

    <div v-else>
      <el-card v-for="task in store.tasks" :key="task.id" style="margin-bottom: 24px;">
        <div class="flex-row" style="justify-content: space-between; align-items: center;">
          <div>
            <div style="font-size: 18px; font-weight: bold; color: #1976d2; cursor: pointer;" @click="router.push(`/bisync/${task.id}`)">{{ task.name }}</div>
            <div style="font-size: 13px; color: #888; margin-top: 2px;">源目录: <span style="color:#1976d2">{{ task.source_dir }}</span></div>
            <div style="font-size: 12px; color: #aaa; margin-top: 2px;">创建于 {{ task.created_at ? task.created_at.slice(0, 16).replace('T', ' ') : '' }}</div>
          </div>
          <div class="flex-row">
            <el-input v-model="addTargetInputs[task.id]" placeholder="添加目标目录..." size="small" style="width: 220px" @keyup.enter="handleAddTarget(task.id)" />
            <el-button type="primary" size="small" @click="handleAddTarget(task.id)">+ 添加</el-button>
            <el-button size="small" type="success" @click="handleStartAll(task.id)">全部启动</el-button>
            <el-button size="small" type="warning" @click="handleStopAll(task.id)">全部停止</el-button>
            <el-button size="small" @click="router.push(`/bisync/${task.id}/edit`)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDeleteTask(task.id)">删除</el-button>
          </div>
        </div>
        <div style="margin-top: 12px;">
          <div class="overflow-x-auto">
            <el-table :data="task.targets" style="width: 100%; background: #f8f9fb; border-radius: 8px;" size="small" :header-cell-style="{background:'#f4f6fa',color:'#888',fontWeight:'bold'}">
              <el-table-column prop="target_dir" label="目标目录" min-width="200">
                <template #default="{ row }">
                  <span style="color: #1976d2; font-size: 15px;">{{ row.target_dir }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'running' ? 'success' : row.status === 'error' ? 'danger' : 'info'" size="small">
                    {{ row.status === 'running' ? '运行中' : row.status === 'error' ? '错误' : '已停止' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="pid" label="PID" width="100">
                <template #default="{ row }">
                  <span style="color:#888">{{ row.pid ?? '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="log_mtime" label="上次同步" width="120">
                <template #default="{ row }">
                  <span style="font-size:12px;color:#888">{{ row.log_mtime ? (Math.round((Date.now()/1000-row.log_mtime)/3600) + '小时前') : '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="失败次数" width="90">
                <template #default="{ row }">
                  <span style="color:#d23c3c;font-weight:bold;">{{ row.failCount || 0 }}</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="220">
                <template #default="{ row }">
                  <el-button v-if="row.status !== 'running'" size="small" type="success" @click="() => handleStartTarget(row.id)">启动</el-button>
                  <el-button v-else size="small" type="warning" @click="() => handleStopTarget(row.id)">停止</el-button>
                  <el-button size="small" @click="router.push(`/bisync/${task.id}`)">日志</el-button>
                  <el-button size="small" type="danger" @click="() => handleDeleteTarget(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.bisync-list-page {
  flex: 1 1 0;
  min-width: 0;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  padding: 0 24px;
  margin: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  min-height: 100vh;
}
@media (max-width: 1200px) {
  .bisync-list-page {
    padding: 0 8px;
  }
}
.overflow-x-auto {
  overflow-x: auto;
}
</style>
