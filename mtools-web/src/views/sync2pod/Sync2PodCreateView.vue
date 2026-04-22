<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useSync2PodStore } from '@/stores/sync2pod'
import { sync2podApi } from '@/api/sync2pod'

const store = useSync2PodStore()
const router = useRouter()
const formRef = ref<FormInstance>()
const loadingContext = ref(false)

const form = reactive({
  name: '',
  pod_type: 'k8s' as 'k8s' | 'docker',
  source_dir: '',
  cluster: '',
  namespace: '',
  pod_label: '',
  pod: '',
  container: '',
  pod_dir: '',
  is_tess: false,  // 已废弃，使用全局 custom_kubectl_cmd
  enable_alert: false,
  interval: 5,
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  source_dir: [{ required: true, message: '请输入源目录', trigger: 'blur' }],
  pod_dir: [{ required: true, message: '请输入 Pod 目录', trigger: 'blur' }],
}

async function loadKubeContext(silent = false) {
  loadingContext.value = true
  try {
    // Use global config to determine if using custom kubectl (e.g., tess kubectl)
    const useTess = store.config?.custom_kubectl_cmd?.includes('tess') ?? false
    const res = await sync2podApi.getKubeContext(useTess)
    if (res.data.error) {
      ElMessage.warning(`读取上下文失败：${res.data.error}`)
      return
    }
    form.namespace = res.data.namespace
    form.cluster = res.data.cluster
    if (!silent) ElMessage.success('已读取当前上下文')
  } catch {
    ElMessage.warning('读取上下文失败，请手动填写集群和命名空间')
  } finally {
    loadingContext.value = false
  }
}

// Auto-load on mount
onMounted(async () => {
  await store.fetchConfig()
  await loadKubeContext(true)
})

async function handleSubmit() {
  await formRef.value?.validate()
  if (form.pod_type === 'k8s' && !form.pod && !form.pod_label) {
    ElMessage.error('k8s 类型需填写 Pod 名称或 Pod 标签')
    return
  }
  try {
    await store.createTask({ ...form })
    ElMessage.success('创建成功')
    router.push('/sync2pod')
  } catch {
    ElMessage.error('创建失败')
  }
}

async function handleSubmitAndStart() {
  await formRef.value?.validate()
  if (form.pod_type === 'k8s' && !form.pod && !form.pod_label) {
    ElMessage.error('k8s 类型需填写 Pod 名称或 Pod 标签')
    return
  }
  try {
    const task = await store.createTask({ ...form })
    await store.startTask(task.id)
    ElMessage.success('创建并启动成功')
    router.push('/sync2pod')
  } catch {
    ElMessage.error('操作失败')
  }
}
</script>

<template>
  <div class="main-container" style="max-width: 680px">
    <h2>新建 Sync2Pod 任务</h2>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="130px">
      <el-form-item label="任务名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入任务名称" />
      </el-form-item>
      <el-form-item label="Pod 类型" prop="pod_type">
        <el-select v-model="form.pod_type" style="width: 200px">
          <el-option label="Kubernetes" value="k8s" />
          <el-option label="Docker" value="docker" />
        </el-select>
      </el-form-item>
      <el-form-item label="源目录" prop="source_dir">
        <el-input v-model="form.source_dir" placeholder="/local/path" />
      </el-form-item>
      <el-form-item label="Pod 目录" prop="pod_dir">
        <el-input v-model="form.pod_dir" placeholder="/pod/path" />
      </el-form-item>
      <el-form-item label="同步间隔(秒)">
        <el-input-number v-model="form.interval" :min="1" />
      </el-form-item>

      <template v-if="form.pod_type === 'k8s'">
        <el-form-item label="Kubernetes 上下文">
          <el-button
            size="small"
            :loading="loadingContext"
            @click="loadKubeContext"
            >读取当前上下文</el-button
          >
          <span style="margin-left: 12px; font-size: 12px; color: #909399">
            kubectl 命令可在全局设置中配置
          </span>
        </el-form-item>
        <el-form-item label="集群">
          <el-input v-model="form.cluster" placeholder="cluster name" />
        </el-form-item>
        <el-form-item label="命名空间">
          <el-input v-model="form.namespace" placeholder="namespace" />
        </el-form-item>
        <el-form-item label="Pod 标签">
          <el-input v-model="form.pod_label" placeholder="app=myapp" />
        </el-form-item>
        <el-form-item label="Pod 名称">
          <el-input v-model="form.pod" placeholder="pod name（标签为空时使用）" />
        </el-form-item>
        <el-form-item label="容器名称">
          <el-input v-model="form.container" placeholder="container (可选)" />
        </el-form-item>
      </template>

      <el-form-item label="开启告警">
        <el-switch v-model="form.enable_alert" />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="handleSubmit">创建</el-button>
        <el-button type="success" @click="handleSubmitAndStart">创建并启动</el-button>
        <el-button @click="router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>
