<script setup lang="ts">
defineProps<{ status: string }>()

function tagType(status: string) {
  if (status === 'running') return 'success'
  if (status === 'error') return 'danger'
  return 'info'
}

function label(status: string) {
  if (status === 'running') return '运行中'
  if (status === 'error') return '错误'
  return '已停止'
}
</script>

<template>
  <el-tag :type="tagType(status)" size="small">{{ label(status) }}</el-tag>
</template>
