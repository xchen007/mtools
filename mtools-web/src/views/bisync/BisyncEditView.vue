<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useBisyncStore } from '@/stores/bisync'

const store = useBisyncStore()
const router = useRouter()
const route = useRoute()
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  source_dir: '',
  interval: 5,
  debounce_seconds: 2,
  exclude_patterns: '',
  target_dirs: [] as string[], // 目标目录数组
  target_ids: [] as (number|null)[],  // 目标目录id数组
})

const targetDirInput = ref<string>('')

const rules: FormRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  source_dir: [{ required: true, message: '请输入源目录', trigger: 'blur' }],
  target_dirs: [{ required: true, validator: (rule, value, callback) => {
    if (!value || !Array.isArray(value) || value.length === 0 || value.some((v: string) => !v)) {
      callback(new Error('请填写至少一个目标目录'))
    } else {
      callback()
    }
  }, trigger: 'blur' }],
}

onMounted(async () => {
  const id = route.params.id as string
  const task = await (store as any).getTask(id)
  form.name = task.name
  form.source_dir = task.source_dir
  form.interval = task.interval
  form.debounce_seconds = task.debounce_seconds
  form.exclude_patterns = task.exclude_patterns
  form.target_dirs = task.targets.map((t: any) => t.target_dir)
  form.target_ids = task.targets.map((t: any) => t.id)
})

function addTargetDir() {
  const val = targetDirInput.value.trim()
  if (val && !form.target_dirs.includes(val)) {
    form.target_dirs.push(val)
    form.target_ids.push(null)
    targetDirInput.value = ''
  }
}
function removeTargetDir(idx: number) {
  form.target_dirs.splice(idx, 1)
  form.target_ids.splice(idx, 1)
}

async function handleSubmit() {
  await formRef.value?.validate()
  try {
    const id = route.params.id as string
    await store.updateTask(Number(id), {
      name: form.name,
      source_dir: form.source_dir,
      interval: form.interval,
      debounce_seconds: form.debounce_seconds,
      exclude_patterns: form.exclude_patterns,
    })
    // 处理目标目录的增删
    const oldTargets = (await (store as any).getTask(id)).targets
    // 删除被移除的目标
    for (const t of oldTargets) {
      if (!form.target_dirs.includes(t.target_dir)) {
        await store.deleteTarget(t.id)
      }
    }
    // 新增目标
    for (let i = 0; i < form.target_dirs.length; ++i) {
      if (!form.target_ids[i]) {
        await store.addTarget(Number(id), { target_dir: form.target_dirs[i] })
      }
    }
    ElMessage.success('更新成功')
    router.push('/bisync')
  } catch {
    ElMessage.error('更新失败')
  }
}
</script>

<template>
  <div class="main-container" style="max-width: 600px">
    <h2>编辑 Bisync 任务</h2>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
      <el-form-item label="任务名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入任务名称" />
      </el-form-item>
      <el-form-item label="源目录" prop="source_dir">
        <el-input v-model="form.source_dir" placeholder="例如 /home/user/project" />
      </el-form-item>
      <el-form-item label="目标目录" prop="target_dirs">
        <el-card shadow="never" style="width:100%;background:#f8f9fb;border-radius:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <el-input
              v-model="targetDirInput.value"
              placeholder="输入目标目录后回车或点击添加"
              style="flex:1"
              @keyup.enter="addTargetDir"
              clearable
            />
            <el-button type="primary" @click="addTargetDir" :disabled="!targetDirInput.value.trim()">添加</el-button>
          </div>
          <div style="margin-top:10px;min-height:32px;">
            <el-tag
              v-for="(dir, idx) in form.target_dirs"
              :key="dir"
              closable
              @close="removeTargetDir(idx)"
              style="margin-right:8px;margin-bottom:6px;"
              type="info"
            >
              {{ dir }}
            </el-tag>
          </div>
        </el-card>
      </el-form-item>
      <el-form-item label="同步间隔(秒)" prop="interval">
        <el-input-number v-model="form.interval" :min="1" />
      </el-form-item>
      <el-form-item label="防抖时间(秒)" prop="debounce_seconds">
        <el-input-number v-model="form.debounce_seconds" :min="0" />
      </el-form-item>
      <el-form-item label="排除规则" prop="exclude_patterns">
        <el-input
          v-model="form.exclude_patterns"
          type="textarea"
          :rows="4"
          placeholder="每行一条规则，例如 *.pyc"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSubmit">保存</el-button>
        <el-button @click="router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

