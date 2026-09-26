<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="logo-row">
        <div class="logo-badge">筑</div>
        <div>
          <div class="app-name">注册账号</div>
          <div class="app-sub">筑安云 · 工地安全智安协同平台</div>
        </div>
      </div>

      <el-tabs v-model="channel" class="reg-tabs">
        <el-tab-pane label="邮箱注册" name="email">
          <el-form @keyup.enter="doRegister">
            <el-form-item>
              <el-input v-model="form.email" placeholder="邮箱地址" size="large">
                <template #prefix><el-icon><Message /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <div class="code-row">
                <el-input v-model="form.code" placeholder="验证码" size="large" maxlength="6">
                  <template #prefix><el-icon><Key /></el-icon></template>
                </el-input>
                <el-button size="large" :disabled="countdown > 0" @click="sendCode">
                  {{ countdown > 0 ? countdown + 's' : '获取验证码' }}
                </el-button>
              </div>
            </el-form-item>
            <el-form-item>
              <el-input v-model="form.username" placeholder="账号（3-30位字母/数字/下划线）" size="large">
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="form.name" placeholder="姓名（选填）" size="large">
                <template #prefix><el-icon><Postcard /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <el-input v-model="form.password" type="password" show-password placeholder="密码（至少6位）" size="large">
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="doRegister">
              注 册
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane name="sms">
          <template #label>
            <span>手机号注册</span>
            <el-tag size="small" type="info" effect="plain" style="margin-left:4px">即将开通</el-tag>
          </template>
          <el-empty description="短信通道开通后即可使用手机号注册" :image-size="80" />
        </el-tab-pane>
      </el-tabs>

      <div class="reg-foot">
        已有账号？<router-link to="/login">直接登录</router-link>
        <span class="role-note">注册后默认为安全员角色，可上报隐患、审核工单</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import http from '../api'
import { setAuth, ROLE_HOME } from '../store'

const router = useRouter()
const channel = ref('email')
const form = reactive({ email: '', code: '', username: '', name: '', password: '' })
const loading = ref(false)
const countdown = ref(0)
let timer = null

function startCountdown() {
  countdown.value = 60
  timer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) clearInterval(timer)
  }, 1000)
}
onUnmounted(() => clearInterval(timer))

async function sendCode() {
  if (!form.email.trim()) return ElMessage.warning('请先输入邮箱地址')
  await http.post('/api/auth/send-code', { channel: 'email', target: form.email.trim() })
  ElMessage.success('验证码已发送，请查收邮件（注意垃圾箱）')
  startCountdown()
}

async function doRegister() {
  if (!form.email.trim() || !form.code.trim() || !form.username.trim() || !form.password) {
    return ElMessage.warning('请填写完整信息')
  }
  loading.value = true
  try {
    const data = await http.post('/api/auth/register', {
      channel: 'email',
      target: form.email.trim(),
      code: form.code.trim(),
      username: form.username.trim(),
      password: form.password,
      name: form.name.trim(),
    })
    setAuth(data.token, data.user)
    router.push(ROLE_HOME[data.user.role] || '/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped src="../views/login-style.css"></style>
<style scoped>
.reg-tabs { margin-top: 8px; }
.code-row { display: flex; gap: 10px; width: 100%; }
.code-row .el-button { width: 130px; }
.reg-foot { margin-top: 14px; font-size: 13px; color: #5a6a8a; text-align: center; }
.reg-foot a { color: var(--zhuan-blue); text-decoration: none; font-weight: 600; }
.role-note { display: block; color: #98a3b8; font-size: 12px; margin-top: 6px; }
</style>
