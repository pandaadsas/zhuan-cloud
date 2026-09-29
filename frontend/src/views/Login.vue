<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="logo-row">
        <BrandMark />
        <div>
          <div class="app-name">筑安云</div>
          <div class="app-sub">工地安全 · 智安协同平台</div>
        </div>
      </div>
      <div class="slogan">把案头交给AI，把安全留给现场</div>
      <el-form aria-label="登录表单" @keyup.enter="doLogin">
        <el-form-item>
          <label class="field-label" for="login-username">账号</label>
          <el-input id="login-username" v-model="form.username" autocomplete="username" placeholder="请输入账号或邮箱" size="large">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <label class="field-label" for="login-password">密码</label>
          <el-input id="login-password" v-model="form.password" type="password" autocomplete="current-password" show-password placeholder="请输入密码" size="large">
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
import BrandMark from '../components/BrandMark.vue'

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
.slogan { color: #5a6a8a; font-size: 13px; margin: 14px 0 24px; padding: 11px 13px; border-left: 3px solid var(--zhuan-orange); border-radius: 0 8px 8px 0; background: #f7f9fc; }
.el-form-item { display: block; }
.reg-foot { margin-top: 14px; font-size: 13px; color: #5a6a8a; text-align: center; }
.reg-foot a { color: var(--zhuan-blue); text-decoration: none; font-weight: 600; }
</style>
