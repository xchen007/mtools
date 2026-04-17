<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => route.path)

function handleMenuSelect(key: string) {
  router.push(key)
}
</script>

<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" style="border-right: 1px solid #e6e6e6">
      <div style="padding: 16px; font-weight: bold; font-size: 16px; border-bottom: 1px solid #e6e6e6">
        MTools
      </div>
      <el-menu :default-active="activeMenu" @select="handleMenuSelect" style="border-right: none">
        <el-menu-item index="/bisync">
          <el-icon><Files /></el-icon>
          <span>Bisync</span>
        </el-menu-item>
        <el-menu-item index="/sync2pod">
          <el-icon><Connection /></el-icon>
          <span>Sync2Pod</span>
        </el-menu-item>
        <el-menu-item index="/sync2pod/settings">
          <el-icon><Setting /></el-icon>
          <span>Sync2Pod 设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main style="padding: 20px; overflow-y: auto">
      <router-view />
    </el-main>
  </el-container>
</template>
