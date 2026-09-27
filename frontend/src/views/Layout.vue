<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand" @click="$router.push('/dashboard')">
        <div class="brand-badge">筑</div>
        <div>
          <div class="brand-name">筑安云</div>
          <div class="brand-sub">{{ meta.project.name || '智安协同平台' }}</div>
        </div>
      </div>
      <el-menu :default-active="$route.path" router background-color="#14285e" text-color="#aebbdd" active-text-color="#ffffff" class="menu">
        <el-menu-item index="/dashboard"><el-icon><DataBoard /></el-icon>安全看板</el-menu-item>
        <el-menu-item v-if="canReport" index="/report"><el-icon><Camera /></el-icon>隐患上报</el-menu-item>
        <el-menu-item index="/orders"><el-icon><Tickets /></el-icon>整改工单</el-menu-item>
        <el-menu-item v-if="canWeekly" index="/weekly"><el-icon><Document /></el-icon>安全周报</el-menu-item>
        <el-menu-item index="/chat"><el-icon><ChatDotRound /></el-icon>AI安全助手</el-menu-item>
        <el-menu-item index="/settings"><el-icon><Setting /></el-icon>系统设置</el-menu-item>
      </el-menu>
      <div class="aside-foot">
        <el-tag v-if="meta.ai_engine" :type="'success'" size="small" effect="dark">
          AI引擎：{{ meta.ai_engine }}
        </el-tag>
        <div class="db-line">数据库：{{ meta.db_mode === 'mysql' ? 'MySQL' : 'SQLite' }}</div>
      </div>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-title">{{ titleMap[$route.path] || '筑安云' }}</div>
        <div class="header-right">
          <el-tag effect="plain" type="info" size="small">{{ user.role_label }}</el-tag>
          <span class="uname">{{ user.name }}</span>
          <el-button link type="danger" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { userStore, useUserStore } from '../store'
import http from '../api'

const router = useRouter()
const user = computed(() => userStore.user || {})
const meta = ref({ project: {}, db_mode: '', ai_engine: '' })

const titleMap = {
  '/dashboard': '安全看板',
  '/report': '隐患上报',
  '/orders': '整改工单',
  '/weekly': '安全周报',
  '/chat': 'AI安全助手',
  '/settings': '系统设置',
}

const canReport = computed(() => ['safety_officer', 'safety_supervisor'].includes(user.value.role))
const canWeekly = computed(() => ['safety_officer', 'safety_supervisor', 'project_manager'].includes(user.value.role))

onMounted(async () => {
  try {
    meta.value = await http.get('/api/meta/info')
  } catch {}
})

function logout() {
  useUserStore().logout()
  router.push('/login')
}
</script>

<style scoped>
.layout { height: 100vh; }
.aside { background: #14285e; display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 10px; padding: 18px 16px 14px; cursor: pointer; }
.brand-badge {
  width: 40px; height: 40px; border-radius: 10px; background: var(--zhuan-blue);
  color: #fff; font-weight: 800; font-size: 20px; display: flex; align-items: center; justify-content: center;
}
.brand-name { color: #fff; font-weight: 700; font-size: 17px; }
.brand-sub { color: #8fa3d0; font-size: 11px; max-width: 130px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.menu { border-right: none; flex: 1; }
.menu .el-menu-item.is-active { background: var(--zhuan-blue) !important; }
.aside-foot { padding: 12px 16px; border-top: 1px solid rgba(255,255,255,.08); }
.db-line { color: #8fa3d0; font-size: 11px; margin-top: 8px; }
.header {
  background: #fff; display: flex; align-items: center; justify-content: space-between;
  box-shadow: 0 1px 4px rgba(30,60,120,.06);
}
.header-title { font-size: 16px; font-weight: 700; color: #1d2b4f; }
.header-right { display: flex; align-items: center; gap: 10px; }
.uname { font-size: 14px; color: #33415e; }
.main { padding: 18px; overflow-y: auto; }
</style>
