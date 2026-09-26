<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="logo-row">
        <div class="logo-badge">筑</div>
        <div>
          <div class="app-name">筑安云</div>
          <div class="app-sub">工地安全 · 智安协同平台</div>
        </div>
      </div>
      <div class="slogan">把案头交给AI，把安全留给现场</div>
      <el-form @keyup.enter="doLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="账号" size="large">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" show-password placeholder="密码" size="large">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="doLogin">
          登 录
        </el-button>
      </el-form>
      <el-divider>演示账号（密码均为 zhuan@123）</el-divider>
      <div class="demo-accounts">
        <div v-for="a in accounts" :key="a.u" class="demo-item" @click="fill(a.u)">
          <b>{{ a.label }}</b><span>{{ a.u }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '../api'
import { setAuth, ROLE_HOME } from '../store'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

const accounts = [
  { label: '安全员', u: 'zhangmin' },
  { label: '安全总监', u: 'liqiang' },
  { label: '项目经理', u: 'wangjianguo' },
  { label: '分包责任人', u: 'zeren01' },
]

function fill(u) {
  form.username = u
  form.password = 'zhuan@123'
}

async function doLogin() {
  if (!form.username || !form.password) return
  loading.value = true
  try {
    const data = await http.post('/api/auth/login', form)
    setAuth(data.token, data.user)
    router.push(ROLE_HOME[data.user.role] || '/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #16419f 0%, #1d5bd8 55%, #3f8bfd 100%);
}
.login-card {
  width: 400px; background: #fff; border-radius: 16px; padding: 34px 36px 24px;
  box-shadow: 0 18px 50px rgba(10, 30, 80, 0.35);
}
.logo-row { display: flex; align-items: center; gap: 12px; }
.logo-badge {
  width: 52px; height: 52px; border-radius: 12px; background: var(--zhuan-blue);
  color: #fff; font-size: 26px; font-weight: 700; display: flex; align-items: center; justify-content: center;
}
.app-name { font-size: 24px; font-weight: 800; color: #1d2b4f; }
.app-sub { color: #7a869c; font-size: 13px; }
.slogan { color: #5a6a8a; font-size: 13px; margin: 12px 0 22px; padding-left: 2px; }
.login-btn { width: 100%; margin-top: 4px; letter-spacing: 6px; }
.demo-accounts { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.demo-item {
  border: 1px solid #e4e9f2; border-radius: 8px; padding: 8px 10px; cursor: pointer;
  display: flex; justify-content: space-between; font-size: 12px; color: #5a6a8a;
}
.demo-item:hover { border-color: var(--zhuan-blue); color: var(--zhuan-blue); }
</style>
