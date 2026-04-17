<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useBisyncStore } from '@/stores/bisync'
import type { BisyncTask } from '@/types/bisync'
import TaskStatusTag from '@/components/TaskStatusTag.vue'
import LogViewer from '@/components/LogViewer.vue'

const route = useRoute()
const router = useRouter()
const store = useBisyncStore()
const taskId = Number(route.params.id)

const task = ref<BisyncTask | null>(null)
const editMode = ref(false)
const formRef = ref<FormInstance>()
const newTargetDir = ref('')

const editForm = reactive({
  name: '',
  source_dir: '',
  interval: 5,
  debounce_seconds: 2,
  exclude_patterns: '',
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  source_dir: [{ required: true, message: '请输入源目录', trigger: 'blur' }],
}

const wsBase = `${import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'}/ws/bisync/target`

onMounted(async () => {
  await store.fetchTasks()
  const found = store.tasks.find((t) => t.id === taskId)
  if (found) {
    task.value = found
    Object.assign(editForm, {
      name: found.name,
      source_dir: found.source_dir,
      interval: found.interval,
      debounce_seconds: found.debounce_seconds,
      exclude_patterns: found.exclude_patterns,
    })
  }
})

const currentTask = computed(() => store.tasks.find((t) => t.id === taskId) ?? task.value)

async function handleSave() {
  await formRef.value?.validate()
  try {
    await store.updateTask(taskId, { ...editForm })
    ElMessage.success('保存成功')
    editMode.value = false
  } catch {
    ElMessage.error('保存失败')
  }
}

async function handleAddTarget() {
  if (!newTargetDir.value.trim()) return
  try {
    await store.addTarget(taskId, { target_dir: newTargetDir.value.trim() })
    ElMessage.success('添加成功')
    newTargetDir.value = ''
  } catch {
    ElMessage.error('添加失败')
  }
}

async function handleDeleteTarget(id: number) {
  await ElMessageBox.confirm('确认删除该目标？', '提示', { type: 'warning' })
  await store.deleteTarget(id)
  ElMessage.success('删除成功')
}

async function handleStartTarget(id: number) {
  await store.startTarget(id)
}

async function handleStopTarget(id: number) {
  await store.stopTarget(id)
}

async function handleResetTarget(id: number) {
  await store.resetTarget(id)
  ElMessage.success('已重置')
}
</script>

<template>
  <div class="main-container" v-if="currentTask">
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px">
      <el-button @click="router.push('/bisync')">← 返回</el-button>
      <h2 style="margin: 0">{{ currentTask.name }}</h2>
    </div>

    <!-- Task Info Card -->
    <el-card style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between">
          <span>任务信息</span>
          <el-button size="small" @click="editMode = !editMode">{{ editMode ? '取消' : '编辑' }}</el-button>
        </div>
      </template>

      <el-form v-if="editMode" ref="formRef" :model="editForm" :rules="rules" label-width="120px">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="源目录" prop="source_dir">
          <el-input v-model="editForm.source_dir" />
        </el-form-item>
        <el-form-item label="同步间隔(秒)">
          <el-input-number v-model="editForm.interval" :min="1" />
        </el-form-item>
        <el-form-item label="防抖时间(秒)">
          <el-input-number v-model="editForm.debounce_seconds" :min="0" />
        </el-form-item>
        <el-form-item label="排除规则">
          <el-input v-model="editForm.exclude_patterns" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSave">保存</el-button>
        </el-form-item>
      </el-form>

      <el-descriptions v-else :column="2" border>
        <el-descriptions-item label="任务名称">{{ currentTask.name }}</el-descriptions-item>
        <el-descriptions-item label="源目录">{{ currentTask.source_dir }}</el-descriptions-item>
        <el-descriptions-item label="同步间隔">{{ currentTask.interval }} 秒</el-descriptions-item>
        <el-descriptions-item label="防抖时间">{{ currentTask.debounce_seconds }} 秒</el-descriptions-item>
        <el-descriptions-item label="排除规则" :span="2">{{ currentTask.exclude_patterns || '无' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- Targets -->
    <el-card>
      <template #header>同步目标</template>

      <!-- Add target form -->
      <div style="display: flex; gap: 8px; margin-bottom: 16px">
        <el-input v-model="newTargetDir" placeholder="目标目录路径" style="max-width: 400px" />
        <el-button type="primary" @click="handleAddTarget">添加目标</el-button>
      </div>

      <div v-for="target in currentTask.targets" :key="target.id" style="margin-bottom: 20px; border: 1px solid #e6e6e6; border-radius: 4px; padding: 12px">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
          <div style="display: flex; align-items: center; gap: 8px">
            <TaskStatusTag :status="target.status" />
            <span>{{ target.target_dir }}</span>
            <span v-if="target.pid" style="color: #999; font-size: 12px">PID: {{ target.pid }}</span>
          </div>
          <div style="display: flex; gap: 6px">
            <el-button
              v-if="target.status !== 'running'"
              size="small"
              type="success"
              @click="handleStartTarget(target.id)"
              >启动</el-button
            >
            <el-button v-else size="small" type="warning" @click="handleStopTarget(target.id)"
              >停止</el-button
            >
            <el-button size="small" @click="handleResetTarget(target.id)">重置</el-button>
            <el-button size="small" type="danger" @click="handleDeleteTarget(target.id)">删除</el-button>
          </div>
        </div>
        <LogViewer :ws-url="`${wsBase}/${target.id}/logs/`" />
      </div>

      <el-empty v-if="currentTask.targets.length === 0" description="暂无同步目标" />
    </el-card>
  </div>

  <el-empty v-else description="任务不存在" />
</template>
