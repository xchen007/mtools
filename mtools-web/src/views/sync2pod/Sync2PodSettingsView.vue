<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useSync2PodStore } from '@/stores/sync2pod'

const store = useSync2PodStore()

const form = reactive({
  is_tess: false,  // 已废弃，但保留以兼容旧数据
  show_list_log: false,
  custom_kubectl_cmd: '',
  custom_docker_cmd: '',
  alert_email: '',
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  smtp_use_tls: false,
})

onMounted(async () => {
  try {
    const config = await store.fetchConfig()
    Object.assign(form, config)
  } catch {
    ElMessage.error('加载配置失败')
  }
})

async function handleSave() {
  try {
    await store.updateConfig({ ...form })
    ElMessage.success('保存成功')
  } catch {
    ElMessage.error('保存失败')
  }
}
</script>

<template>
  <div class="main-container settings-content">
    <h3 class="section-title">Sync2Pod 配置</h3>

    <!-- 列表显示日志 -->
    <div class="option-card">
      <el-checkbox v-model="form.show_list_log">
        <span class="option-label">列表页显示日志</span>
      </el-checkbox>
      <p class="option-desc">启用后，列表操作栏显示日志按钮，可展开内联日志面板</p>
    </div>

    <el-divider />

    <!-- 自定义命令 -->
    <h4 class="subsection-title">自定义命令</h4>

    <el-form :model="form" label-position="top" style="max-width: 800px; margin-bottom: 24px">
      <el-form-item label="自定义 kubectl 命令">
        <el-input
          v-model="form.custom_kubectl_cmd"
          placeholder="例如: tess kubectl（留空使用默认 kubectl）"
        />
        <div class="field-hint">
          自定义 kubectl 命令前缀，例如 "tess kubectl" 或 "/usr/local/bin/kubectl"。<br>
          优先级：自定义命令 > is_tess 设置 > 默认 kubectl
        </div>
      </el-form-item>

      <el-form-item label="自定义 docker 命令">
        <el-input
          v-model="form.custom_docker_cmd"
          placeholder="例如: podman（留空使用默认 docker）"
          disabled
        />
        <div class="field-hint">
          自定义 docker 命令（Docker 容器同步功能暂未实现）
        </div>
      </el-form-item>
    </el-form>

    <el-divider />

    <!-- 邮件告警 -->
    <h4 class="subsection-title">邮件告警（任务意外停止时通知）</h4>

    <el-form :model="form" label-position="top">
      <el-form-item label="告警收件邮箱">
        <el-input v-model="form.alert_email" placeholder="alert@example.com" />
        <div class="field-hint">任务意外停止时的收件邮箱；为空则不发送</div>
      </el-form-item>

      <div class="form-row">
        <el-form-item label="SMTP 主机" class="flex-grow">
          <el-input v-model="form.smtp_host" placeholder="e.g. smtp.gmail.com / smtp.exmail.qq.com" />
        </el-form-item>
        <el-form-item label="SMTP 端口" class="port-field">
          <el-input-number
            v-model="form.smtp_port"
            :min="1"
            :max="65535"
            controls-position="right"
            style="width: 100%"
          />
          <div class="field-hint">通常：587（STARTTLS）、465（SSL）、25（无加密）</div>
        </el-form-item>
      </div>

      <el-form-item label="SMTP 用户名">
        <el-input v-model="form.smtp_user" placeholder="user@example.com（同时作为发件人地址）" />
      </el-form-item>

      <el-form-item label="SMTP 密码">
        <el-input
          v-model="form.smtp_password"
          type="password"
          show-password
          placeholder="留空保持不变"
        />
      </el-form-item>

      <el-form-item>
        <el-checkbox v-model="form.smtp_use_tls">使用 TLS</el-checkbox>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
.settings-content {
  padding: 0 8px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 16px;
  color: var(--el-text-color-primary);
}

.option-card {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 12px;
  background: var(--el-fill-color-blank);
  transition: background 0.2s;
}

.option-card.is-active {
  background: #fffbe6;
  border-color: #ffe58f;
}

.option-label {
  font-weight: 500;
}

.option-desc {
  margin: 6px 0 0 22px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.subsection-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 16px;
  color: var(--el-text-color-primary);
}

.form-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.form-row .flex-grow {
  flex: 1;
}

.form-row .port-field {
  width: 340px;
  flex-shrink: 0;
}

.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.4;
}
</style>
