import { createRouter, createWebHashHistory } from 'vue-router'
import { isLoggedIn, userStore } from './store'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue') },
  { path: '/register', component: () => import('./views/Register.vue') },
  {
    path: '/',
    component: () => import('./views/Layout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', component: () => import('./views/Dashboard.vue') },
      { path: 'report', component: () => import('./views/Report.vue') },
      { path: 'orders', component: () => import('./views/Orders.vue') },
      { path: 'weekly', component: () => import('./views/Weekly.vue') },
      { path: 'chat', component: () => import('./views/Chat.vue'), meta: { assistant: 'safety' } },
      { path: 'pm-chat', component: () => import('./views/Chat.vue'), meta: { assistant: 'pm' } },
      { path: 'projects', component: () => import('./views/Projects.vue') },
      { path: 'settings', component: () => import('./views/Settings.vue') },
    ],
  },
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach((to) => {
  if (to.path !== '/login' && to.path !== '/register' && !isLoggedIn.value) return '/login'
  if (to.path === '/login' && isLoggedIn.value) return '/dashboard'
  // 项目管理助手仅项目经理可见，其余角色访问时回到看板
  if (to.path === '/pm-chat' && userStore.user?.role !== 'project_manager') return '/dashboard'
  return true
})

export default router
