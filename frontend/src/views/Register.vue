<template>
  <div class="login-wrap">
    <AuthScene />
    <div class="login-card register-card">
      <div class="mobile-brand">
        <BrandMark />
        <div>
          <div class="app-name">筑安云</div>
          <div class="app-sub">工地安全 · 智安协同平台</div>
        </div>
      </div>
      <div class="form-heading">
        <span class="form-eyebrow">CREATE ACCOUNT</span>
        <h1>加入项目工作台</h1>
        <p>创建账号并选择工作角色，进入对应的安全协同流程。</p>
      </div>

      <el-tabs v-model="channel" class="reg-tabs">
        <el-tab-pane label="邮箱注册" name="email">
          <el-form aria-label="注册表单" @keyup.enter="doRegister">
            <el-form-item>
              <label class="field-label" for="reg-email">邮箱地址</label>
              <el-input id="reg-email" v-model="form.email" autocomplete="email" placeholder="用于接收验证码" size="large">
                <template #prefix><el-icon><Message /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <label class="field-label" for="reg-code">邮箱验证码</label>
              <div class="code-row">
                <el-input id="reg-code" v-model="form.code" inputmode="numeric" autocomplete="one-time-code" placeholder="6 位验证码" size="large" maxlength="6">
                  <template #prefix><el-icon><Key /></el-icon></template>
                </el-input>
                <el-button size="large" :disabled="countdown > 0" @click="sendCode">
                  {{ countdown > 0 ? countdown + 's' : '获取验证码' }}
                </el-button>
              </div>
            </el-form-item>
            <el-form-item>
              <label class="field-label" for="reg-username">登录账号</label>
              <el-input id="reg-username" v-model="form.username" autocomplete="username" placeholder="3-30 位字母、数字或下划线" size="large">
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <label class="field-label" for="reg-role">工作角色</label>
              <el-select id="reg-role" v-model="form.role" placeholder="注册角色" size="large" style="width: 100%" @change="onRoleChange">
                <el-option v-for="r in roles" :key="r.value" :label="r.label" :value="r.value" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.role === 'responsible'">
              <label class="field-label">所属分包单位</label>
              <el-select v-model="form.subcontractor_id" placeholder="所属分包单位" size="large" style="width: 100%">
                <el-option v-for="s in subs" :key="s.id" :label="s.name" :value="s.id" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <label class="field-label" for="reg-name">姓名 <span class="optional">选填</span></label>
              <el-input id="reg-name" v-model="form.name" autocomplete="name" placeholder="请输入姓名" size="large">
                <template #prefix><el-icon><Postcard /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <label class="field-label" for="reg-password">密码</label>
              <el-input id="reg-password" v-model="form.password" type="password" autocomplete="new-password" show-password placeholder="至少 6 位" size="large">
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="doRegister">
              注 册
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="reg-foot">
        已有账号？<router-link to="/login">直接登录</router-link>
        <span class="role-note">选择角色后注册，自动进入对应角色的专属工作台</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import http from '../api'
import { setAuth, ROLE_HOME } from '../store'
import BrandMark from '../components/BrandMark.vue'
import AuthScene from '../components/AuthScene.vue'

const router = useRouter()
const channel = ref('email')
const form = reactive({ email: '', code: '', username: '', name: '', password: '', role: 'safety_officer', subcontractor_id: null })
const roles = [
  { label: '安全员（上报隐患 / 审核工单）', value: 'safety_officer' },
  { label: '安全总监（看板 / 周报 / 重大风险复核）', value: 'safety_supervisor' },
  { label: '项目经理（看板 / 周报）', value: 'project_manager' },
  { label: '分包责任人（接收整改任务）', value: 'responsible' },
]
const subs = ref([])
const loading = ref(false)
const countdown = ref(0)
let timer = null

onMounted(async () => {
  try {
    subs.value = await http.get('/api/meta/subcontractors')
  } catch {}
})

function onRoleChange() {
  if (form.role !== 'responsible') form.subcontractor_id = null
}

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
  ElMessage.success('验证码已发送，请查收邮件')
  startCountdown()
}

async function doRegister() {
  if (!form.email.trim() || !form.code.trim() || !form.username.trim() || !form.password) {
    return ElMessage.warning('请填写完整信息')
  }
  if (form.role === 'responsible' && !form.subcontractor_id) {
    return ElMessage.warning('请选择所属分包单位')
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
      role: form.role,
      subcontractor_id: form.role === 'responsible' ? form.subcontractor_id : undefined,
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
.el-form-item { display: block; }
.optional { color: #929db0; font-weight: 400; }
.code-row { display: flex; gap: 10px; width: 100%; }
.code-row .el-button { width: 130px; }
.reg-foot { margin-top: 14px; font-size: 13px; color: #5a6a8a; text-align: center; }
.reg-foot a { color: var(--zhuan-blue); text-decoration: none; font-weight: 600; }
.role-note { display: block; color: #98a3b8; font-size: 12px; margin-top: 6px; }
</style>
