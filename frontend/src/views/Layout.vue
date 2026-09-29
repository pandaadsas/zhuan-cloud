<template>
  <el-container class="layout">
    <aside class="aside desktop-aside"><NavPanel /></aside>
    <el-drawer v-model="mobileNavOpen" direction="ltr" size="min(84vw, 300px)" :with-header="false" class="mobile-nav">
      <NavPanel @navigate="mobileNavOpen = false" />
    </el-drawer>

    <el-container class="workspace">
      <el-header class="header">
        <div class="header-leading">
          <el-button class="menu-trigger" text circle aria-label="打开导航菜单" @click="mobileNavOpen = true">
            <el-icon :size="22"><Menu /></el-icon>
          </el-button>
          <div>
            <div class="header-title">{{ currentPage.title }}</div>
            <div class="header-context">{{ currentPage.context }}</div>
          </div>
        </div>
        <el-dropdown trigger="click">
          <button class="user-menu" aria-label="打开用户菜单">
            <span class="avatar">{{ userInitial }}</span>
            <span class="user-copy">
              <strong>{{ user.name || user.username || '用户' }}</strong>
              <small>{{ user.role_label }}</small>
            </span>
            <el-icon><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="$router.push('/settings')"><el-icon><Setting /></el-icon>系统设置</el-dropdown-item>
              <el-dropdown-item divided @click="logout"><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { DataBoard, Camera, Tickets, Document, ChatDotRound, Setting } from '@element-plus/icons-vue'
import { userStore, useUserStore } from '../store'
import http from '../api'
import BrandMark from '../components/BrandMark.vue'

const router = useRouter()
const route = useRoute()
const user = computed(() => userStore.user || {})
const meta = ref({ project: {}, db_mode: '', ai_engine: '' })
const mobileNavOpen = ref(false)
const pages = {
  '/dashboard': { title: '安全看板', context: '项目风险态势与治理进度' },
  '/report': { title: '隐患上报', context: 'AI 辅助识别、分级与派单' },
  '/orders': { title: '整改工单', context: '跟进处置过程与闭环状态' },
  '/weekly': { title: '安全周报', context: '汇总本周治理成效与风险趋势' },
  '/chat': { title: 'AI 安全助手', context: '查询进度、统计与规范条款' },
  '/settings': { title: '系统设置', context: '管理 AI 引擎与模型配置' },
}
const currentPage = computed(() => pages[route.path] || { title: '筑安云', context: '工地安全智安协同平台' })
const userInitial = computed(() => (user.value.name || user.value.username || '筑').slice(0, 1))
const canReport = computed(() => ['safety_officer', 'safety_supervisor'].includes(user.value.role))
const canWeekly = computed(() => ['safety_officer', 'safety_supervisor', 'project_manager'].includes(user.value.role))

const NavPanel = defineComponent({
  emits: ['navigate'],
  setup(_, { emit }) {
    const items = computed(() => [
      { path: '/dashboard', label: '安全看板', icon: DataBoard, show: true },
      { path: '/report', label: '隐患上报', icon: Camera, show: canReport.value },
      { path: '/orders', label: '整改工单', icon: Tickets, show: true },
      { path: '/weekly', label: '安全周报', icon: Document, show: canWeekly.value },
      { path: '/chat', label: 'AI 安全助手', icon: ChatDotRound, show: true },
      { path: '/settings', label: '系统设置', icon: Setting, show: true },
    ].filter((item) => item.show))
    return () => h('div', { class: 'nav-panel' }, [
      h(RouterLink, { to: '/dashboard', class: 'brand', onClick: () => emit('navigate') }, {
        default: () => [h(BrandMark, { compact: true }), h('div', [h('div', { class: 'brand-name' }, '筑安云'), h('div', { class: 'brand-sub' }, meta.value.project?.name || '智安协同平台')])],
      }),
      h('nav', { class: 'menu', 'aria-label': '主导航' }, items.value.map((item) => h(RouterLink, { to: item.path, class: 'menu-item', onClick: () => emit('navigate') }, {
        default: () => [h('span', { class: 'menu-icon' }, [h(item.icon)]), h('span', item.label)],
      }))),
      h('div', { class: 'aside-foot' }, [
        h('div', { class: 'system-status' }, [h('span', { class: 'status-dot' }), h('span', `AI 服务 · ${meta.value.ai_engine || '检测中'}`)]),
        h('div', { class: 'db-line' }, `数据服务 · ${meta.value.db_mode === 'mysql' ? 'MySQL' : meta.value.db_mode ? 'SQLite' : '检测中'}`),
      ]),
    ])
  },
})

onMounted(async () => {
  try { meta.value = await http.get('/api/meta/info') } catch {}
})
function logout() { useUserStore().logout(); router.push('/login') }
</script>

<style scoped>
.layout { min-height: 100vh; background: var(--zhuan-bg); }
.aside { position: fixed; inset: 0 auto 0 0; z-index: 20; width: 236px; color: #fff; background: linear-gradient(180deg, #0b1c3b 0%, #102750 58%, #0c1e40 100%); }
.workspace { min-width: 0; margin-left: 236px; }
:deep(.nav-panel) { display: flex; flex-direction: column; height: 100%; }
:deep(.brand) { display: flex; align-items: center; gap: 12px; margin: 18px 16px 24px; color: inherit; text-decoration: none; }
:deep(.brand-name) { font-size: 18px; line-height: 1.25; font-weight: 760; letter-spacing: .04em; }
:deep(.brand-sub) { max-width: 145px; margin-top: 3px; overflow: hidden; color: #91a5ca; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
:deep(.menu) { flex: 1; padding: 0 12px; }
:deep(.menu-item) { display: flex; align-items: center; gap: 12px; height: 46px; margin-bottom: 5px; padding: 0 13px; border-radius: 10px; color: #aebddd; font-size: 14px; text-decoration: none; transition: color .18s ease, background .18s ease, transform .18s ease; }
:deep(.menu-item:hover) { color: #fff; background: rgba(255,255,255,.07); transform: translateX(2px); }
:deep(.menu-item.router-link-active) { color: #fff; background: linear-gradient(90deg, rgba(49,105,227,.85), rgba(49,105,227,.38)); box-shadow: inset 3px 0 #f5a817, 0 8px 20px rgba(0,0,0,.12); }
:deep(.menu-icon) { display: grid; place-items: center; width: 20px; font-size: 18px; }
:deep(.aside-foot) { padding: 16px 18px 18px; border-top: 1px solid rgba(255,255,255,.08); color: #8fa3c8; font-size: 11px; line-height: 1.7; }
:deep(.system-status) { display: flex; align-items: center; gap: 7px; color: #b8c5dc; }
:deep(.status-dot) { width: 7px; height: 7px; border-radius: 50%; background: #4ccc8c; box-shadow: 0 0 0 4px rgba(76,204,140,.12); }
:deep(.db-line) { margin-top: 4px; }
.header { position: sticky; top: 0; z-index: 15; display: flex; align-items: center; justify-content: space-between; height: 72px; padding: 0 24px; border-bottom: 1px solid rgba(218,226,237,.9); background: rgba(255,255,255,.9); backdrop-filter: blur(14px); }
.header-leading { display: flex; align-items: center; gap: 8px; min-width: 0; }
.header-title { color: var(--zhuan-text); font-size: 17px; font-weight: 750; }
.header-context { margin-top: 2px; color: var(--zhuan-muted); font-size: 11px; }
.menu-trigger { display: none; }
.user-menu { display: flex; align-items: center; gap: 9px; padding: 5px 7px 5px 5px; border: 0; border-radius: 11px; color: var(--zhuan-text); background: transparent; cursor: pointer; transition: background .18s ease; }
.user-menu:hover { background: #f1f4f9; }
.avatar { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; color: #fff; background: linear-gradient(145deg, var(--zhuan-blue), #4d7be2); font-size: 14px; font-weight: 750; }
.user-copy { display: grid; gap: 1px; min-width: 70px; text-align: left; }
.user-copy strong { font-size: 13px; font-weight: 650; }
.user-copy small { color: var(--zhuan-muted); font-size: 10px; }
.main { min-width: 0; padding: 22px 24px 30px; overflow: visible; }
:global(.mobile-nav .el-drawer__body) { padding: 0; background: var(--zhuan-navy); }
@media (max-width: 900px) {
  .desktop-aside { display: none; }
  .workspace { margin-left: 0; }
  .menu-trigger { display: inline-flex; margin-left: -6px; }
}
@media (max-width: 600px) {
  .header { height: 62px; padding: 0 12px; }
  .header-context, .user-copy { display: none; }
  .main { padding: 14px 12px 24px; }
}
</style>
