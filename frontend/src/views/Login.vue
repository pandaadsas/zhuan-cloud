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
          <el-input v-model="form.username" placeholder="账号 / 邮箱" size="large">
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
      <div class="reg-foot">
        还没有账号？<router-link to="/register">立即注册</router-link>
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

<style scoped src="./login-style.css"></style>
<style scoped>
.slogan { color: #5a6a8a; font-size: 13px; margin: 12px 0 22px; padding-left: 2px; }
.reg-foot { margin-top: 14px; font-size: 13px; color: #5a6a8a; text-align: center; }
.reg-foot a { color: var(--zhuan-blue); text-decoration: none; font-weight: 600; }
</style>
