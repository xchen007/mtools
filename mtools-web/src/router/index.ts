import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/bisync' },
    { path: '/bisync', component: () => import('@/views/bisync/BisyncListView.vue') },
    { path: '/bisync/create', component: () => import('@/views/bisync/BisyncCreateView.vue') },
    { path: '/bisync/:id', component: () => import('@/views/bisync/BisyncDetailView.vue') },
    { path: '/bisync/:id/edit', name: 'BisyncEdit', component: () => import('@/views/bisync/BisyncEditView.vue') },
    { path: '/sync2pod', component: () => import('@/views/sync2pod/Sync2PodListView.vue') },
    { path: '/sync2pod/create', component: () => import('@/views/sync2pod/Sync2PodCreateView.vue') },
    { path: '/sync2pod/settings', component: () => import('@/views/sync2pod/Sync2PodSettingsView.vue') },
    { path: '/sync2pod/:id/edit', component: () => import('@/views/sync2pod/Sync2PodEditView.vue') },
    { path: '/sync2pod/:id', component: () => import('@/views/sync2pod/Sync2PodDetailView.vue') },
  ],
})

export default router
