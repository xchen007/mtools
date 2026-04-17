<script setup lang="ts">
import { onMounted, ref, watch, nextTick } from 'vue'
import { useLogStream } from '@/composables/useLogStream'
import TaskStatusTag from './TaskStatusTag.vue'

const props = defineProps<{ wsUrl: string }>()

const { logs, status, connect, disconnect } = useLogStream(props.wsUrl)
const logContainer = ref<HTMLPreElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

watch(logs, scrollToBottom)

onMounted(() => {
  connect()
})
</script>

<template>
  <div class="log-viewer">
    <div class="log-header">
      <TaskStatusTag :status="status" />
    </div>
    <pre ref="logContainer" class="log-content">{{ logs || '（暂无日志）' }}</pre>
  </div>
</template>

<style scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.log-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.log-content {
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'Courier New', Courier, monospace;
  font-size: 12px;
  line-height: 1.5;
  padding: 12px;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
